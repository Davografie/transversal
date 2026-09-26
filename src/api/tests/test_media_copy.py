"""Copying a picture onto another rung of the ladder ([[B215]]).

The trait-instance editor takes one of the trait's own pictures as its override;
`copy_media` is what puts it on that rung. Driven against a fake repository and a
temporary media tree, because the work is file-and-record surgery.
"""

import io

import pytest
from fastapi import HTTPException
from PIL import Image

from transversal.api.rest import media as media_mod
from transversal.db.repository_mixins.images import RepositoryImages
from transversal.domain import ImageType, MediaImage
from transversal.services.media_utils import save_image_variants

TRAIT = "trait-1"
SETTING = "character-1:earth:trait-1"


class _Repo(RepositoryImages):
    """Stands in for the storage primitives, and **inherits** `set_image_roles`
    from the real mixin — the sibling-stripping invariant is what this test is
    about, so it must not be a second implementation in the fake."""

    def __init__(self, images=()):
        self.images = list(images)

    def get_image(self, image_id):
        return next((i for i in self.images if i.id == image_id), None)

    def get_images_for_owner(self, owner_id, variant_id=None):
        return [
            i for i in self.images
            if i.owner_id == owner_id and (i.variant_id or None) == variant_id
        ]

    def create_image(self, image):
        self.images.append(image)
        return image

    def update_image(self, image_id, updates):
        image = self.get_image(image_id)
        for key, value in updates.items():
            setattr(image, key, value)
        return image


def _record(key="def_1", filename="def_1", **fields):
    base = dict(
        id=key, owner_kind="trait", owner_id=TRAIT, universe="earth",
        image_type=ImageType.UPLOADED, filename=filename, extension="webp",
        roles=["sheet"], renders=[], width=200, height=300,
    )
    base.update(fields)
    return MediaImage(**base)


def _write(tmp_path, base, *, matte=False):
    directory = tmp_path / TRAIT / "earth"
    directory.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    Image.new("RGB", (200, 300), (10, 90, 200)).save(buf, format="PNG")
    save_image_variants(buf.getvalue(), directory, base)
    if matte:
        buf = io.BytesIO()
        img = Image.new("RGBA", (200, 300), (0, 0, 0, 0))
        img.paste(Image.new("RGBA", (60, 90), (10, 90, 200, 255)), (70, 100))
        img.save(buf, format="PNG")
        save_image_variants(buf.getvalue(), directory, f"{base}_Cutout")


@pytest.fixture
def media(tmp_path, monkeypatch):
    monkeypatch.setattr(media_mod, "IMAGEN_DIR", tmp_path)
    return tmp_path


async def test_a_definition_picture_is_copied_onto_the_instance_rung(media, monkeypatch):
    _write(media, "def_1")
    repo = _Repo([_record()])
    monkeypatch.setattr(media_mod, "EntityRepository", lambda: repo)

    res = await media_mod.copy_media(
        "def_1", owner_kind="trait", owner_id=TRAIT, variant_id=SETTING
    )

    copied = repo.get_image(res["image_id"])
    assert copied is not None, "a new record was registered"
    assert (copied.owner_id, copied.variant_id) == (TRAIT, SETTING), "on the instance's rung"
    assert copied.id != "def_1", "the definition is untouched"
    # The sole-image rule, as upload has it: a fresh override takes effect at once.
    assert copied.roles == ["background", "sheet", "navdot"]
    ladder = list((media / TRAIT / "earth").glob(f"{copied.filename}_*.webp"))
    assert len(ladder) >= 5, ladder


async def test_the_copy_carries_the_citation_and_the_matte(media, monkeypatch):
    """The artwork is the artwork — provenance and the matte travel with it."""
    from transversal.domain import ImageCredit

    _write(media, "def_2", matte=True)
    repo = _Repo([_record(
        key="def_2", filename="def_2", renders=["cutout"], transparent=True,
        flags=["ai_generated"],
        credits=[ImageCredit(role="artist", name="Jane Doe", url="https://example.org/j")],
        license="CC BY-SA 4.0", credit_text="Art by Jane Doe",
    )])
    monkeypatch.setattr(media_mod, "EntityRepository", lambda: repo)

    res = await media_mod.copy_media(
        "def_2", owner_kind="trait", owner_id=TRAIT, variant_id=SETTING
    )

    copied = repo.get_image(res["image_id"])
    assert copied.flags == ["ai_generated"]
    assert [(c.role, c.name) for c in copied.credits] == [("artist", "Jane Doe")]
    assert (copied.license, copied.credit_text) == ("CC BY-SA 4.0", "Art by Jane Doe")
    assert copied.renders == ["cutout"], "a copy that lost the matte would render opaque"
    assert copied.transparent is True
    # The matte ladder came too, so `sheet` and `navdot` serve the cutout.
    assert (media / TRAIT / "earth" / f"{copied.filename}_Cutout_Small.webp").exists()


async def test_the_definition_keeps_its_own_files(media, monkeypatch):
    _write(media, "def_3")
    repo = _Repo([_record(key="def_3", filename="def_3")])
    monkeypatch.setattr(media_mod, "EntityRepository", lambda: repo)

    await media_mod.copy_media("def_3", owner_kind="trait", owner_id=TRAIT, variant_id=SETTING)

    assert (media / TRAIT / "earth" / "def_3_Original.webp").exists(), "not moved"
    assert repo.get_image("def_3").filename == "def_3"


async def test_a_missing_source_is_a_404(media, monkeypatch):
    monkeypatch.setattr(media_mod, "EntityRepository", lambda: _Repo())
    with pytest.raises(HTTPException) as exc:
        await media_mod.copy_media("nope", owner_id=TRAIT, variant_id=SETTING)
    assert exc.value.status_code == 404


async def test_copy_needs_an_owner(media, monkeypatch):
    monkeypatch.setattr(media_mod, "EntityRepository", lambda: _Repo([_record()]))
    with pytest.raises(HTTPException) as exc:
        await media_mod.copy_media("def_1", variant_id=SETTING)
    assert exc.value.status_code == 400


async def test_a_second_pick_takes_over_from_the_one_that_was_there(media, monkeypatch):
    """Picking a picture is meant to *replace* the override, not to add an
    untagged sibling that renders nowhere. Assigning a role strips it from the
    siblings, so the tags move onto the copy."""
    _write(media, "def_4")
    _write(media, "mine_1")
    existing = _record(key="mine_1", filename="mine_1", variant_id=SETTING,
                       roles=["sheet", "navdot"])
    repo = _Repo([_record(key="def_4", filename="def_4"), existing])
    monkeypatch.setattr(media_mod, "EntityRepository", lambda: repo)

    res = await media_mod.copy_media(
        "def_4", owner_kind="trait", owner_id=TRAIT, variant_id=SETTING
    )

    copied = repo.get_image(res["image_id"])
    assert sorted(copied.roles) == ["navdot", "sheet"], "it took over what was rendering"
    assert existing.roles == [], "and the previous picture gave the tags up"
