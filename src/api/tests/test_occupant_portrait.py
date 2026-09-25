"""The occupant's portrait follows the body standing there ([[B137]] S1).

An entity has one **active** body (`entity.current_projection`) and any number of
others. When the consciousness travels to another universe it leaves a body
behind, and that left-behind body is what the map draws at its location — the
occupant query has always listed bodies by `projection.current_location`. What it
got wrong was the *face*: the portrait resolved through the entity's active body,
so each of the four left-behind bodies on the live map wore the face of the body
the consciousness went to. Three of the four own their own navdot art, so this was
visible rather than theoretical.

The rule pinned here, and it is one rule with two sides:

* listing the entities at a **place** resolves through the body standing there;
* everything else — a sheet, a roster, a plan row — still resolves through the
  entity's **active** body, which is the behaviour every existing caller had.

Live-ArangoDB tests. They build an isolated fixture and tear it down, and skip
when ArangoDB is unavailable.
"""

import pytest

from transversal.db.repository import EntityRepository
from transversal.domain import (
    Entity,
    MediaImage,
    EntityType,
    ImageType,
    Projection,
    TransversalType,
)

try:
    _repo = EntityRepository()
    HAVE_DB = True
except Exception:
    _repo = None
    HAVE_DB = False

pytestmark = pytest.mark.skipif(not HAVE_DB, reason="ArangoDB not available")

U = "test-portrait-u"
EARTH = "earth"
THREE_REALMS = "three_realms"

ENTITY = "test-portrait-entity"
HERE = "test-portrait-loc-here"      # the body that stayed
THERE = "test-portrait-loc-there"    # where the consciousness went

BODY_STAYED = f"{ENTITY}:{EARTH}"
BODY_ACTIVE = f"{ENTITY}:{THREE_REALMS}"

STAYED_FACE = "StayedFace"
ACTIVE_FACE = "ActiveFace"

_ALL_IDS = (ENTITY, HERE, THERE)


def _cleanup(repo):
    repo.delete_entity(ENTITY, rmtree=True)
    repo.delete_entity(HERE, rmtree=True)
    repo.delete_entity(THERE, rmtree=True)
    for img in repo.get_entity_images(ENTITY):
        repo.delete_entity_image(img.id)


def _seed(repo):
    """One character, two bodies: `:earth` left at HERE, `:three_realms` active at THERE.

    Each body owns its own navdot art, so the two are distinguishable by URL.
    """
    _cleanup(repo)
    repo.create_entity(Entity(id=HERE, type=EntityType.LOCATION, name="Here",
                              current_universe=U))
    repo.create_entity(Entity(id=THERE, type=EntityType.LOCATION, name="There",
                              current_universe=U))
    repo.create_entity(Entity(
        id=ENTITY, type=EntityType.CHARACTER, name="Traveller", current_universe=THREE_REALMS,
        current_location=THERE, current_projection=BODY_ACTIVE,
    ))
    for body_id, universe, location in (
        (BODY_STAYED, EARTH, HERE),
        (BODY_ACTIVE, THREE_REALMS, THERE),
    ):
        repo.create_projection(Projection(
            id=body_id, entity_id=ENTITY, universe=universe, origin_universe=universe,
            current_location=location, transversal_type=TransversalType.CONSCIOUSNESS,
        ))
    for body_id, universe, filename, transparent in (
        (BODY_STAYED, EARTH, STAYED_FACE, True),
        (BODY_ACTIVE, THREE_REALMS, ACTIVE_FACE, False),
    ):
        repo.create_entity_image(MediaImage(
            id=f"img-{filename}", entity_id=ENTITY, projection_id=body_id,
            universe=universe, image_type=ImageType.IMAGEN, roles=["navdot"],
            filename=filename, transparent=transparent,
        ))


def _occupant(repo, location_id: str) -> dict:
    occ = [o for o in repo.navigate_from(location_id)["occupants"] if o["id"] == ENTITY]
    assert len(occ) == 1, f"expected exactly one occupant row at {location_id}"
    return occ[0]


# ── The occupant at a place ──────────────────────────

def test_the_left_behind_body_wears_its_own_face():
    repo = _repo
    _seed(repo)
    try:
        occ = _occupant(repo, HERE)
        assert occ["body_id"] == BODY_STAYED
        assert STAYED_FACE in occ["image"]
        assert ACTIVE_FACE not in occ["image"]
    finally:
        _cleanup(repo)


def test_the_active_body_still_wears_its_own_face():
    """The fix must not invert the ordinary case — where the body *is* the active one."""
    repo = _repo
    _seed(repo)
    try:
        occ = _occupant(repo, THERE)
        assert occ["body_id"] == BODY_ACTIVE
        assert ACTIVE_FACE in occ["image"]
    finally:
        _cleanup(repo)


def test_the_occupant_payload_names_the_body():
    """S3 builds on this field, and S1 needs it to reach the REST layer at all."""
    repo = _repo
    _seed(repo)
    try:
        assert _occupant(repo, HERE)["body_id"] == BODY_STAYED
        assert _occupant(repo, THERE)["body_id"] == BODY_ACTIVE
    finally:
        _cleanup(repo)


# ── The reads behind it ──────────────────────────────

def test_navdot_images_default_to_the_active_body():
    """No override — every pre-existing caller keeps the old resolution."""
    repo = _repo
    _seed(repo)
    try:
        urls = repo.get_navdot_images([ENTITY])
        assert ACTIVE_FACE in urls[ENTITY]
    finally:
        _cleanup(repo)


def test_navdot_images_honour_an_explicit_body():
    repo = _repo
    _seed(repo)
    try:
        urls = repo.get_navdot_images([ENTITY], bodies={ENTITY: BODY_STAYED})
        assert STAYED_FACE in urls[ENTITY]
    finally:
        _cleanup(repo)


def test_transparency_follows_the_same_body():
    """The transparent flag has to come from the same image as the URL."""
    repo = _repo
    _seed(repo)
    try:
        assert repo.get_navdot_transparency([ENTITY], bodies={ENTITY: BODY_STAYED})[ENTITY] is True
        assert repo.get_navdot_transparency([ENTITY], bodies={ENTITY: BODY_ACTIVE})[ENTITY] is False
    finally:
        _cleanup(repo)


def test_a_body_without_its_own_art_falls_back_to_the_entity():
    """An entity-level navdot is still the fallback when a body has none of its own."""
    repo = _repo
    _seed(repo)
    try:
        repo.create_entity_image(MediaImage(
            id="img-entitylevel", entity_id=ENTITY, universe=EARTH,
            image_type=ImageType.IMAGEN, roles=["navdot"], filename="EntityLevel",
        ))
        # Clear the stayed body's own art so only the entity-level image remains.
        for img in repo.get_entity_images(ENTITY):
            if img.projection_id == BODY_STAYED:
                repo.delete_entity_image(img.id)
        urls = repo.get_navdot_images([ENTITY], bodies={ENTITY: BODY_STAYED})
        assert "EntityLevel" in urls[ENTITY]
    finally:
        _cleanup(repo)
