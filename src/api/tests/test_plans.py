"""Integration tests for the plan staging + promote flow.

Hit the live ArangoDB (available in the dev container). Run inside the API container:

    docker compose exec api python -m pytest tests/test_plans.py -v
"""

import pytest

from transversal.db.arango import get_db
from transversal.db.repository import EntityRepository
from transversal.services.entity_manager import EntityManager
from transversal.services.plan_service import PlanService

PLAN = "test-plan-pytest"


@pytest.fixture(scope="module")
def svc():
    try:
        db = get_db()
    except Exception as exc:  # pragma: no cover - DB may be down in CI
        pytest.skip(f"ArangoDB unavailable: {exc}")
    repo = EntityRepository(db=db)
    return PlanService(repository=repo, entity_manager=EntityManager(repository=repo))


def _draft(svc, draft_ref, name, etype, **kw):
    doc = {
        "_key": f"{PLAN}:{draft_ref}",
        "plan_id": PLAN,
        "draft_ref": draft_ref,
        "name": name,
        "type": etype,
        "universe": "three_realms",
    }
    doc.update(kw)
    svc.repo.create_plan_entity(doc)


def _cleanup(svc, *ids):
    for eid in ids:
        if svc.repo.get_entity(eid):
            svc.em.delete(eid)
    svc.discard(PLAN)


def test_draft_promote_resolves_refs_and_edges(svc):
    svc.discard(PLAN)  # clean slate

    _draft(svc, "fac", "Zz Pytest Sect", "faction")
    _draft(svc, "apex", "Zz Pytest GMC", "gmc", location="entity:loc-174486794")
    svc.repo.create_plan_relationship({
        "_from": f"plan_entities/{PLAN}:apex",
        "_to": f"plan_entities/{PLAN}:fac",
        "plan_id": PLAN,
        "type": "membership",
    })

    created = svc.promote(PLAN)["created"]
    fac_id = created[f"{PLAN}:fac"]
    gmc_id = created[f"{PLAN}:apex"]

    try:
        # Fresh ids — never colliding with the draft keys.
        assert fac_id != f"{PLAN}:fac"
        assert gmc_id != f"{PLAN}:apex"

        # Membership edge resolved from draft refs to real ids.
        rel = svc.repo.get_relationship(gmc_id, fac_id, "membership")
        assert rel is not None and rel["type"] == "membership"

        # entity:ref location resolved to the real id (passthrough).
        gmc = svc.repo.get_entity(gmc_id)
        assert gmc.current_location == "loc-174486794"
        # Promoted content starts unpublished (GM-only) until revealed.
        assert gmc.unpublished is True
    finally:
        _cleanup(svc, gmc_id, fac_id)


def test_draft_ref_location_resolves_to_promoted_id(svc):
    svc.discard(PLAN)

    _draft(svc, "loc", "Zz Pytest Valley", "location")
    _draft(svc, "apex", "Zz Pytest GMC2", "gmc", location="draft:loc")

    created = svc.promote(PLAN)["created"]
    loc_id = created[f"{PLAN}:loc"]
    gmc_id = created[f"{PLAN}:apex"]

    try:
        # draft:ref location resolves to the promoted location's real id.
        gmc = svc.repo.get_entity(gmc_id)
        assert gmc.current_location == loc_id
    finally:
        _cleanup(svc, gmc_id, loc_id)
