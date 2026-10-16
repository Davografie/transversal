"""The migration's model must claim every file a reader can ask for ([[B88]]).

`variants_of` describes a picture's shape; `RepositoryImages.image_url` is the reader
it has to agree with. It disagreed: the matte was listed at **one** tier while
`ROLE_RENDER` sends `sheet` to `cutout/Small`, so 1,236 matte files — 309 pictures,
618 records across two campaigns — stayed on the owner-named legacy path, still
shared between campaigns, and the legacy tree could not be retired without 404ing
every sheet portrait.

Two properties made that invisible, and both are asserted here rather than the list
itself: the model was written out by hand, and a record carrying **any** blobs was
skipped outright — so adding the missing tier and re-running would have changed
nothing at all.
"""

from transversal.migrate_media_blobs import missing_variants, variants_of
from transversal.services.media_utils import PICTURE_TIERS, ROLE_RENDER


def _doc(**over):
    """One picture as it is stored: a still, webp, one owner, one universe."""
    doc = {
        "owner_id": "trait-1",
        "universe": "earth",
        "filename": "upload_ab12cd34",
        "extension": "webp",
        "renders": [],
        "blobs": {},
    }
    doc.update(over)
    return doc


def _wanted(render: str, tier: str) -> tuple[str, str]:
    """The ``(kind, suffix)`` `image_url` asks for — its branch, not a copy of it."""
    if render == "animated":
        return ("animated", "")
    if render == "cutout":
        return ("imagen", f"_Cutout_{tier}")
    return ("imagen", f"_{tier}")


def test_every_render_a_role_can_serve_is_modelled():
    """The invariant, not the list: walk the render policy and require the model to
    claim the file each role resolves to — its preferred render **and** the static
    tier it falls back to when the picture has no such render."""
    variants = {
        (kind, suffix)
        for kind, suffix, _ in variants_of(
            _doc(renders=["cutout", "animated"], animated_extension="webm")
        )
    }
    for role, (render, tier) in ROLE_RENDER.items():
        for served in (render, "static"):
            wanted = _wanted(served, tier)
            assert wanted in variants, (
                f"{role} can serve {served} at {tier}, so {wanted} must be claimed"
            )


def test_the_matte_keeps_the_whole_ladder():
    """Not one tier. The matte is the still's ladder under its own prefix, so every
    tier can be asked for — `sheet` takes `Small`, `navdot` `Large`, and XLarge is
    in the same ladder ([[B207]])."""
    suffixes = {suffix for _, suffix, _ in variants_of(_doc())}
    for tier in PICTURE_TIERS:
        assert f"_{tier}" in suffixes
        assert f"_Cutout_{tier}" in suffixes


def test_a_partially_migrated_record_is_topped_up_rather_than_skipped():
    """The property that made the gap unhealable: any blobs at all meant "done"."""
    doc = _doc(renders=["cutout"], blobs={"_Cutout_Large": "aa"})
    missing = {suffix for _, suffix, _ in missing_variants(doc)}

    assert "_Cutout_Small" in missing, "the tier `sheet` serves"
    assert "_Cutout_Large" not in missing, "already recorded: not re-moved, not re-retained"
    assert "_Large" in missing


def test_a_complete_record_has_nothing_to_do():
    doc = _doc(renders=["animated"], animated_extension="webm")
    doc["blobs"] = {suffix: "digest" for _, suffix, _ in variants_of(doc)}
    assert missing_variants(doc) == []
