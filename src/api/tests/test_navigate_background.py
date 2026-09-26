"""The ``navigate`` payload's background is the *resolved* one (`P7.16`-class).

The viewer reads ``GET /locations/{id}/navigate`` twice over: the hole preview
probes ``location.background_image`` for the destination's aspect, and the arrival
paints the GraphQL ``image(role: "background")`` answer. Those are two different
code paths, so they can disagree — and when they did, the hole silently degraded.

The stored ``background_image`` on the entity document is **denormalized** and goes
stale whenever the media pipeline renames a file: on 2026-09-26, 9 of the 127
locations carrying one pointed at an ``_anim_<hash>`` path that no longer existed.
The fix is that this payload serves what the renderer resolves
(``resolve_role_image``), so the two cannot disagree.

The stale value is not a stub file path on purpose — nothing reads the filesystem
here; the property under test is *which* of the two answers the payload returns.

Live-ArangoDB, namespaced fixtures, skipped when ArangoDB is unavailable.
"""

import asyncio

import pytest

from transversal.api.rest import locations as locations_rest
from transversal.db.repository import EntityRepository
from transversal.domain import Entity, EntityType, ImageType, MediaImage

try:
    _repo = EntityRepository()
    HAVE_DB = True
except Exception:
    _repo = None
    HAVE_DB = False

pytestmark = pytest.mark.skipif(not HAVE_DB, reason="ArangoDB not available")

LOC = "loc-test-navbg"
BG_IMAGE = "test-navbg-bg"
U = "test-navbg-u"

# What the entity document remembers. Deliberately a path that names a file the
# media pipeline has since renamed — the live shape of the bug.
STALE = f"/media/animated/{LOC}/{U}/Beast_Pools_three_realms_anim_1275cdfa.webp"


def _cleanup(repo):
    if repo.get_image(BG_IMAGE):
        repo.delete_image(BG_IMAGE)
    try:
        repo.delete_entity(LOC)
    except Exception:
        pass


@pytest.fixture
def data(monkeypatch):
    repo = _repo
    _cleanup(repo)
    entity = Entity(id=LOC, type=EntityType.LOCATION, name="Nav Bg Hall",
                    current_universe=U)
    entity.background_image = STALE
    repo.create_entity(entity)
    monkeypatch.setattr(locations_rest, "_repo", lambda: repo)
    yield repo
    _cleanup(repo)


def _navigate():
    return asyncio.run(locations_rest.navigate(LOC))


def test_the_payload_serves_the_resolved_background_not_the_stored_one(data):
    """The hole preview and the arrival must be given the same URL.

    The entity field is stale; the resolver derives the real path from the image
    record. The payload has to carry the resolver's answer — that is the one the
    arrival renders — or the preview probes a 404, gets a null aspect, and drops
    the hole illustration to a plain cover thumbnail.
    """
    data.create_image(MediaImage(
        id=BG_IMAGE, owner_kind="entity", owner_id=LOC, variant_id=None,
        universe=U, image_type=ImageType.UPLOADED, roles=["background"],
        filename="beast_pools_still", extension="webp",
    ))

    payload = _navigate()
    served = payload["location"]["background_image"]

    # The invariant, stated without hardcoding a tier: what the payload serves is
    # what the GraphQL `image(role:)` resolver — hence the arrival — serves.
    assert served == data.resolve_role_image(LOC, "background")
    assert served != STALE, "the stale stored field must not win"


def test_a_location_with_no_image_record_keeps_its_stored_background(data):
    """The legacy flat `/media/{id}.webp` case: nothing to resolve, so nothing moves."""
    assert _navigate()["location"]["background_image"] == STALE


def test_the_resolved_url_is_not_the_animated_path_that_vanished(data):
    """A still-only record resolves to its still tier, not to a missing loop.

    The live failure was a record whose animated path was emitted while the file
    on disk was a different name. A record with no animated render must resolve to
    the still ladder, which is what the human meant by "there's also a still
    variant".
    """
    data.create_image(MediaImage(
        id=BG_IMAGE, owner_kind="entity", owner_id=LOC, variant_id=None,
        universe=U, image_type=ImageType.UPLOADED, roles=["background"],
        filename="beast_pools_still", extension="webp",
    ))
    served = _navigate()["location"]["background_image"]
    assert "/animated/" not in served
    assert served.endswith("_XLarge.webp")
