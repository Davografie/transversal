"""Change Trait must move the instance's registry pointer — ``traitsettings._to``.

A trait instance stores its definition as an Arango edge: ``_from`` is the owner
(entity, relationship, projection or parent instance) and ``_to`` is the registry
trait. "Change Trait" edits ``trait_id``, and the repository derives ``_to`` from
that field on every write — so this test exists to prove the pointer really
follows, because the effect would otherwise look like it worked (the model reads
back changed) while the edge still pointed at the old definition.

Live-ArangoDB. Skips when ArangoDB is unavailable.
"""

import pytest

from transversal.db.arango import ENTITIES, TRAITS
from transversal.db.repository import EntityRepository
from transversal.domain import DieType, Entity, EntityType, Trait, TraitSet, TraitSetting

try:
    _repo = EntityRepository()
    HAVE_DB = True
except Exception:
    _repo = None
    HAVE_DB = False

pytestmark = pytest.mark.skipif(not HAVE_DB, reason="ArangoDB not available")

ENTITY_ID = "test-change-trait-entity"
TRAIT_A = "test-change-trait-blade"
TRAIT_B = "test-change-trait-fire-blade"
TSET_A = "test-change-trait-weapons"
TSET_B = "test-change-trait-elements"
TS_ID = f"{ENTITY_ID}:{TRAIT_A}"


def _cleanup(repo):
    repo.delete_traitsetting(TS_ID)
    repo.delete_entity(ENTITY_ID)
    repo.delete_trait(TRAIT_A)
    repo.delete_trait(TRAIT_B)
    repo.delete_traitset(TSET_A)
    repo.delete_traitset(TSET_B)


@pytest.fixture
def data():
    repo = _repo
    _cleanup(repo)
    repo.create_entity(Entity(id=ENTITY_ID, type=EntityType.CHARACTER, name="Changer",
                              current_universe="earth"))
    repo.create_traitset(TraitSet(id=TSET_A, name="Weapons", universes=["earth"]))
    repo.create_traitset(TraitSet(id=TSET_B, name="Elements", universes=["earth"]))
    repo.create_trait(Trait(id=TRAIT_A, name="blade", traitset_id=TSET_A,
                            universes=["earth"], default_die_type=DieType.D8))
    repo.create_trait(Trait(id=TRAIT_B, name="blade of fire", traitset_id=TSET_B,
                            universes=["earth"], default_die_type=DieType.D8))
    yield repo
    _cleanup(repo)


def test_the_registry_pointer_follows_a_changed_definition(data):
    repo = data
    repo.create_traitsetting(TraitSetting(
        id=TS_ID, entity_id=ENTITY_ID, trait_id=TRAIT_A,
        dice=[DieType.D8], statement="my blade",
    ))
    doc = repo._traitsettings.get(TS_ID)
    assert doc["_to"] == f"{TRAITS}/{TRAIT_A}"
    assert doc["_from"] == f"{ENTITIES}/{ENTITY_ID}"

    # Exactly what the handler does: point the instance at the other definition
    # and let the commit write it.
    ts = repo.get_traitsetting(TS_ID)
    ts.trait_id = TRAIT_B
    repo.update_traitsetting(ts)

    doc = repo._traitsettings.get(TS_ID)
    assert doc["_to"] == f"{TRAITS}/{TRAIT_B}", "the registry pointer did not move"
    assert doc["_from"] == f"{ENTITIES}/{ENTITY_ID}", "the owner moved with it"
    # The instance's own state is untouched by the re-pointing.
    read_back = repo.get_traitsetting(TS_ID)
    assert read_back.trait_id == TRAIT_B
    # The set is not copied onto the instance ([[B200]]) — it is read through the
    # trait, so pointing at TRAIT_B *is* being in TSET_B.
    assert repo.get_trait(read_back.trait_id).traitset_id == TSET_B
    assert read_back.dice == [DieType.D8]
    assert read_back.statement == "my blade"

    # ...and the same write moves it back, which is what a timed revert does.
    read_back.trait_id = TRAIT_A
    repo.update_traitsetting(read_back)
    assert repo._traitsettings.get(TS_ID)["_to"] == f"{TRAITS}/{TRAIT_A}"
