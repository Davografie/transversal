"""The create mutation must carry every field its input accepts.

`TraitSettingInput` had two fields accepted and then dropped on the way to the
domain object — `parentTraitsettingId` (which wrote a dangling
``_from = TRAITSETTINGS/None``, putting the child in no container at all) and
`enabled`. Both were invisible from outside: the mutation succeeded and returned a
setting, just not the one that was asked for.

So this test does not spot-check fields and does not use the repository — the
repository stores whatever model it is handed, which is exactly why the bugs hid
there. It runs the **mutation** with every input field set to a non-default and
requires each one to have arrived.

Live-ArangoDB. Skips when ArangoDB is unavailable.
"""

import asyncio

import pytest

from transversal.api.graphql.schema import schema
from transversal.db.repository import EntityRepository
from transversal.domain import Entity, EntityType, Polarity

try:
    _repo = EntityRepository()
    HAVE_DB = True
except Exception:
    _repo = None
    HAVE_DB = False

pytestmark = pytest.mark.skipif(not HAVE_DB, reason="ArangoDB not available")

ENTITY_ID = "test-create-input-entity"
CONTAINER_TRAIT = "trait-3160510"
CONTAINER_TS = "ts-2200695"
STATEMENT = "the envoy is turned away"

_MUTATION = """
mutation($e: ID!, $i: TraitSettingInput!) {
  addTraitSetting(entityId: $e, input: $i) {
    id parentTraitsettingId order capacity enabled notes tags polarity statement fromType
  }
}
"""


def _cleanup(repo):
    repo.delete_entity(ENTITY_ID, rmtree=True)


@pytest.fixture
def repo():
    r = _repo
    _cleanup(r)
    r.create_entity(Entity(id=ENTITY_ID, type=EntityType.FACTION,
                           name="Input Test", current_universe="earth"))
    yield r
    _cleanup(r)


def _add(repo, input_vars: dict):
    """Run the create mutation against the live repo, returning the response.

    The EntityManager is built from the fixture's repo rather than taken from
    `transversal.main`'s singleton: `test_graphql.py` swaps that singleton for an
    in-memory repository, so depending on it makes this test order-dependent.
    """
    from transversal.main import build_loaders
    from transversal.services.entity_manager import EntityManager

    em = EntityManager(repo)
    return asyncio.run(schema.execute(
        _MUTATION,
        variable_values={"e": ENTITY_ID, "i": input_vars},
        context_value={"entity_manager": em, "loaders": build_loaders(em)},
    ))


def _base_input() -> dict:
    return {"traitId": CONTAINER_TRAIT, "traitsetId": CONTAINER_TS,
            "ratingType": "EMPTY", "dice": []}


def test_create_carries_every_input_field(repo):
    """Nest a setting with every field non-default; nothing may be dropped."""
    container = _add(repo, _base_input())
    assert not container.errors, container.errors
    container_id = container.data["addTraitSetting"]["id"]

    result = _add(repo, {**_base_input(),
                   "fromType": "traitsetting",
                   "parentTraitsettingId": container_id,
                   "statement": STATEMENT,
                   "notes": "gm only",
                   "order": 3,
                   "tags": ["coming"],
                   "polarity": "NEGATIVE",
                   "enabled": False})
    assert not result.errors, result.errors
    node = result.data["addTraitSetting"]

    # The mutation response — what an MCP tool has to read back.
    assert node["parentTraitsettingId"] == container_id, "parent dropped on create"
    assert node["enabled"] is False, "enabled dropped on create"
    assert node["order"] == 3
    assert node["polarity"] == "NEGATIVE"
    assert node["notes"] == "gm only"
    assert node["tags"] == ["coming"]
    assert node["statement"] == STATEMENT
    assert node["fromType"] == "traitsetting"

    # And the row itself, including the anchor the dangling edge corrupted.
    got = repo.get_traitsetting(node["id"])
    assert got is not None
    assert got.enabled is False
    assert got.order == 3
    assert got.polarity == Polarity.NEGATIVE
    assert f"traitsettings/{container_id}" in str(
        list(repo.db.aql.execute(
            "FOR ts IN traitsettings FILTER ts._key == @k RETURN ts._from",
            bind_vars={"k": node["id"]}))[0]
    ), "the child is anchored to its parent"
    assert [t.id for t in repo.get_sub_traitsettings(container_id)] == [node["id"]]


def test_a_parent_without_the_nesting_anchor_is_refused(repo):
    """The silent-drop trap: a parent with fromType left default must not pass."""
    container = _add(repo, _base_input())
    container_id = container.data["addTraitSetting"]["id"]

    result = _add(repo, {**_base_input(), "parentTraitsettingId": container_id})
    assert result.errors, "a parent without fromType 'traitsetting' was accepted"
    assert "parentTraitsettingId requires fromType" in str(result.errors[0])
