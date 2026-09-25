"""The trait **setting**'s image read-through (`B200`, the sheet's half of slice 1).

A trait rendered on a sheet is a ``TraitSetting``, but images are stored against
the registry ``Trait`` — so the sheet needs a read-through, and the design log
names it: ``TraitSetting.image(role)``.

What that read adds over media's ``Trait.image(role)`` is **the ladder**: the
trait is the *owner* and the setting is the *variant*, exactly as a projection is
an entity's variant. Getting those two ids the wrong way round would silently
resolve the definition image where an override exists — slice 2's whole purpose —
while looking correct, so these assert the ladder's outcome with real
``MediaImage`` rows rather than checking that a stub was called.

The loader is keyed by the **owner**: a sheet holds several settings of one trait,
and a trait and its setting share an owner, so the batch collapses those as well
as the round trips. That is asserted too — a key of the setting id would still
produce the right picture here and be wrong in production.

No database: the resolution is media's, and `test_media_image_owner.py` walks it
against live Arango. This is the wiring and the convention on top.
"""

from types import SimpleNamespace

from transversal.api.graphql.type_defs.traits import TraitRef, TraitSetting
from transversal.domain import DieType, ImageType, MediaImage, RatingType

TRAIT = "trait-probe-image"
SETTING = "character-probe:trait-probe-image"
OTHER = "character-probe:trait-probe-image:2"


class _Images:
    """Stands in for the per-request DataLoader, recording the keys it is asked for."""

    def __init__(self, images):
        self.images = images
        self.keys = []

    async def load(self, key):
        self.keys.append(key)
        return self.images


class _Repo:
    """Only the URL formatter, marked so a test can see which image won."""

    def role_image_url(self, img, variant="Large"):
        return f"{img.id}:{variant}" if img else None


def _info(images):
    return SimpleNamespace(context={
        "entity_manager": SimpleNamespace(repo=_Repo()),
        "loaders": SimpleNamespace(images=_Images(images)),
    })


def _image(image_id, *, variant_id=None, roles=("sheet",), transparent=False):
    return MediaImage(
        id=image_id, owner_kind="trait", owner_id=TRAIT, variant_id=variant_id,
        universe="earth", image_type=ImageType.IMAGEN, roles=list(roles),
        transparent=transparent, filename=f"probe_{image_id}", extension="webp",
        created_at="2026-01-01T00:00:00+00:00",
    )


def _setting(setting_id=SETTING):
    return TraitSetting(
        id=setting_id, entity_id="character-probe", trait_id=TRAIT,
        traitset_id="ts-probe", rating_type=RatingType.STATIC, dice=[DieType.D6],
        statement="", sfx_ids=[], polarity="POSITIVE",
    )


async def test_the_setting_prefers_its_own_image_over_the_traits():
    """The point of reading through the setting: slice 2's override wins."""
    definition = _image("def")
    override = _image("override", variant_id=SETTING)
    info = _info([definition, override])

    assert await _setting().image(info, "sheet") == "override:Small"
    # Owner is the trait; the setting is only the variant.
    assert info.context["loaders"].images.keys == [TRAIT]


async def test_and_falls_back_to_the_traits_own_image():
    info = _info([_image("def")])
    assert await _setting().image(info, "sheet") == "def:Small"


async def test_another_settings_override_is_not_mine():
    """A sibling setting's picture must not answer for this one."""
    info = _info([_image("def"), _image("theirs", variant_id=OTHER)])
    assert await _setting().image(info, "sheet") == "def:Small"


async def test_each_role_reads_its_own_stored_variant():
    """The role→variant map is shared with the registry trait's read, so a role
    cannot mean one file here and another there.

    Updated 2026-09-25: `background` moved from `Large` to `XLarge` (2048) when the
    full-bleed tiers were added — a backdrop is drawn at viewport size, while
    `navdot` is a map dot and `sheet` a panel portrait and both stay small. The
    map is now one constant in `services/media_utils.py`, which is the invariant
    this test is really about."""
    info = _info([_image("def", roles=("background", "sheet", "navdot"))])
    setting = _setting()
    assert await setting.image(info, "sheet") == "def:Small"
    assert await setting.image(info, "background") == "def:XLarge"
    assert await setting.image(info, "navdot") == "def:Large"


async def test_a_role_the_picture_cannot_carry_is_absent():
    info = _info([_image("def")])
    assert await _setting().image(info, "portrait") is None
    assert info.context["loaders"].images.keys == [], "an unknown role must not read"


async def test_no_image_anywhere_is_absent():
    assert await _setting().image(_info([]), "sheet") is None


async def test_transparency_comes_from_the_same_resolution():
    """The flag and the URL must describe one image — so the setting's own cutout
    decides, not the definition's."""
    info = _info([_image("def"), _image("override", variant_id=SETTING, transparent=True)])
    assert await _setting().image_transparent(info, "sheet") is True

    opaque = _info([_image("def")])
    assert await _setting().image_transparent(opaque, "sheet") is False
    assert await _setting().image_transparent(_info([]), "sheet") is False


async def test_the_registry_trait_reads_through_the_same_loader():
    """`Trait.image` serves the registry editor, which asks about every trait in a
    set at once — the read that motivated batching."""
    trait = TraitRef(
        id=TRAIT, name="Probe", universes=["earth"], traitset_id="ts-probe",
        default_die_type=DieType.D6, default_rating_type=RatingType.STATIC,
        possible_sfx_ids=[], default_sfx_ids=[], possible_subtrait_ids=[],
        possible_subtraitset_ids=[], tags=[], display_names=[],
    )
    info = _info([_image("def")])
    assert await trait.image(info, "sheet") == "def:Small"
    assert info.context["loaders"].images.keys == [TRAIT]
