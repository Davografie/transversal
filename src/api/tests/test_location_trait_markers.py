"""A location trait's ``navdot`` marker on the viewer payload (`B200`).

The location viewer draws a location's traits as chips, and a chip's marker is the
trait's ``navdot``-role image ([[Media Pipeline]] §Traits as image owners). The
chip is fed by the **REST** read, not by the sheet's GraphQL query, so the
resolution has to be proved on that payload.

What is being pinned is the **read-through**: the registry **trait** owns the image
while the **trait setting** is the variant, exactly as ``TraitSetting.image(role)``
resolves for the sheet. Slice 2's per-instance override reaches the map through
that same rung, so a variant image beating the definition one is asserted here
rather than assumed.

Asserted with real ``MediaImage`` rows, because the ladder is the thing under test
and a stub would only prove the stub — the same reason
``test_media_image_owner.py`` runs live. Live-ArangoDB, namespaced fixtures, and
skipped when ArangoDB is unavailable.
"""

import asyncio

import pytest

from transversal.api.rest import locations as locations_rest
from transversal.db.repository import EntityRepository
from transversal.domain import (
    DieType,
    Entity,
    EntityType,
    ImageType,
    MediaImage,
    RatingType,
    Trait,
    TraitSet,
    TraitSetting,
)

try:
    _repo = EntityRepository()
    HAVE_DB = True
except Exception:
    _repo = None
    HAVE_DB = False

pytestmark = pytest.mark.skipif(not HAVE_DB, reason="ArangoDB not available")

LOC = "loc-test-markers"
TRAIT = "trait-test-markers"
TRAIT2 = "trait-test-markers-second"
TSET = "test-markers-ts"
SETTING = f"{LOC}:{TRAIT}"
SETTING2 = f"{LOC}:{TRAIT2}"

MARKER = "test-markers-marker"
SHEET_ONLY = "test-markers-sheet"
OVERRIDE = "test-markers-override"

U = "test-markers-u"


def _image(image_id, roles, *, transparent=False, variant_id=None, filename=None):
    return MediaImage(
        id=image_id, owner_kind="trait", owner_id=TRAIT, variant_id=variant_id,
        universe=U, image_type=ImageType.UPLOADED, roles=roles,
        transparent=transparent, filename=filename or image_id, extension="png",
    )


def _cleanup(repo):
    for image_id in (MARKER, SHEET_ONLY, OVERRIDE):
        # `delete_image` is not missing-tolerant the way the trait deletes are.
        if repo.get_image(image_id):
            repo.delete_image(image_id)
    repo.delete_traitsetting(SETTING)
    repo.delete_traitsetting(SETTING2)
    repo.delete_trait(TRAIT)
    repo.delete_trait(TRAIT2)
    repo.delete_traitset(TSET)
    repo.delete_entity(LOC)


@pytest.fixture
def data(monkeypatch):
    repo = _repo
    _cleanup(repo)
    repo.create_entity(Entity(id=LOC, type=EntityType.LOCATION, name="Marker Hall",
                              current_universe=U))
    repo.create_traitset(TraitSet(id=TSET, name="Conditions", universes=[U]))
    repo.create_trait(Trait(id=TRAIT, name="spirit herb", traitset_id=TSET,
                            universes=[U], default_die_type=DieType.D6))
    repo.create_traitsetting(TraitSetting(
        id=SETTING, entity_id=LOC, trait_id=TRAIT,
        dice=[DieType.D6], rating_type=RatingType.STATIC,
    ))
    # `location_traits` builds its own repository; hand it this one so the fixture
    # and the read cannot end up on different connections.
    monkeypatch.setattr(locations_rest, "_repo", lambda: repo)
    yield repo
    _cleanup(repo)


def _traits():
    return asyncio.run(locations_rest.location_traits(LOC))["traits"]


def test_the_marker_is_the_traits_navdot_image(data):
    data.create_image(_image(MARKER, ["navdot"], transparent=True,
                             filename="herb_cut"))
    (entry,) = _traits()
    assert entry["navdot_image"] == f"/media/imagen/{TRAIT}/{U}/herb_cut_Large.png"
    assert entry["navdot_transparent"] is True


def test_a_sheet_only_image_is_not_a_marker(data):
    """The role filter is the whole reason a trait can hold a row picture and a
    map marker as two different files."""
    data.create_image(_image(SHEET_ONLY, ["sheet", "background"]))
    (entry,) = _traits()
    assert "navdot_image" not in entry
    assert "navdot_transparent" not in entry


def test_the_settings_own_image_wins_over_the_traits(data):
    """Slice 2's per-instance override is the variant rung; the map takes it with
    no change to this read, which is the point of resolving the same way."""
    data.create_image(_image(MARKER, ["navdot"], filename="definition"))
    data.create_image(_image(OVERRIDE, ["navdot"], variant_id=SETTING,
                             filename="override"))
    (entry,) = _traits()
    assert entry["navdot_image"].endswith("/override_Large.png")


def test_the_page_resolves_every_marker_in_one_query(data, monkeypatch):
    """A location can hold dozens of traits. B202 measured the per-owner read at
    ~2.7ms, so the payload batches; counting the calls is what pins that."""
    data.create_trait(Trait(id=TRAIT2, name="blessing", traitset_id=TSET,
                            universes=[U], default_die_type=DieType.D8))
    data.create_traitsetting(TraitSetting(
        id=SETTING2, entity_id=LOC, trait_id=TRAIT2,
        dice=[DieType.D8], rating_type=RatingType.STATIC,
    ))
    data.create_image(_image(MARKER, ["navdot"]))

    calls = []
    original = data.get_images_for_owners

    def counted(owner_ids):
        calls.append(sorted(owner_ids))
        return original(owner_ids)

    monkeypatch.setattr(data, "get_images_for_owners", counted)

    entries = _traits()
    assert len(entries) == 2, "the fixture should hold two traits"
    assert len(calls) == 1, "the page must resolve owners in one query"
    assert calls[0] == sorted([TRAIT, TRAIT2]), "and cover every owner on it"
