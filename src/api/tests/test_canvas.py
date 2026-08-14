"""Integration tests for the relational canvas repository methods.

These hit the live ArangoDB (available in the dev container) and verify the
canvas queries against the data seeded by ``transversal.migrate_conspyramid``.
Run them inside the API container:

    docker compose exec api python -m pytest tests/test_canvas.py -v
"""

import pytest

from transversal.db.arango import get_db
from transversal.db.repository import EntityRepository

FACTION_ID = "fac-crimson-hollow"
FOCUS_LOCATION = "loc-40642106"  # Valley of Ascension
PATRIARCH_GMC = "gmc-hollow-patriarch"


@pytest.fixture(scope="module")
def repo():
    try:
        db = get_db()
    except Exception as exc:  # pragma: no cover - DB may be down in CI
        pytest.skip(f"ArangoDB unavailable: {exc}")
    return EntityRepository(db=db)


def test_neighborhood_shape(repo):
    nb = repo.canvas_neighborhood(FOCUS_LOCATION)
    assert nb["location"] is not None
    assert isinstance(nb["children"], list)
    assert isinstance(nb["transversal"], list)
    assert isinstance(nb["occupants"], list)
    # Canvas additions
    assert isinstance(nb["faction_memberships"], dict)
    assert isinstance(nb["occupant_relations"], list)


def test_faction_members_have_rank_role(repo):
    fc = repo.canvas_faction(FACTION_ID)
    assert fc["faction"] is not None
    assert fc["faction"]["name"] == "Crimson Hollow Sect"
    assert len(fc["members"]) == 6
    for m in fc["members"]:
        assert m["rank"] in ("d4", "d6", "d8", "d10", "d12")
        assert m["role"]
        assert m["location_id"]
    # Command chain relations carry a description (edge label).
    assert any(r["description"] == "commands" for r in fc["relations"])


def test_faction_ancestors_are_disjoint_scaffolding(repo):
    fc = repo.canvas_faction(FACTION_ID)
    member_locs = {l["id"] for l in fc["locations"]}
    ancestor_locs = {l["id"] for l in fc["ancestors"]}
    assert not (member_locs & ancestor_locs)
    # The pruned tree keeps the Valley of Ascension as scaffolding.
    assert any("Valley of Ascension" == l["name"] for l in fc["ancestors"])


def test_gmc_web_resolves_other_locations(repo):
    gw = repo.canvas_gmc_web(PATRIARCH_GMC)
    assert gw["gmc"]["name"] == "The Hollow Patriarch"
    assert gw["location"]["name"] == "The Sundered Peak"
    assert len(gw["relations"]) == 2
    for r in gw["relations"]:
        assert r["other_name"]
        assert r["other_location_id"]
        assert r["other_location_name"]


def test_unknown_ids_return_none(repo):
    assert repo.canvas_faction("nonexistent")["faction"] is None
    assert repo.canvas_gmc_web("nonexistent")["gmc"] is None
    assert repo.canvas_neighborhood("nonexistent")["location"] is None
