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
from transversal.services.media_utils import ROLE_RENDER

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
    """Only the URL formatter, marked so a test can see which image won.

    It mirrors the real builder's tier choice through the **shared** map, so this
    test still pins the invariant it exists for: the setting's read and the
    registry trait's read cannot disagree about what a role means.
    """

    def role_image_url(self, img, role):
        _, tier = ROLE_RENDER.get(role, ("", "Large"))
        return f"{img.id}:{tier}" if img else None


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


def _setting(setting_id=SETTING, picked_image_id=None):
    return TraitSetting(
        id=setting_id, entity_id="character-probe", trait_id=TRAIT,
         rating_type=RatingType.STATIC, dice=[DieType.D6],
        statement="", sfx_ids=[], polarity="POSITIVE",
        picked_image_id=picked_image_id,
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


# ── The pick ([[B288]]) ──────────────────────────────
# The instance names one of its trait's own pictures instead of the editor copying
# the file onto the setting's rung. A pointer, so a matte or a loop made on that
# picture belongs to the picture and every instance using it gets the variant.

async def test_a_picked_picture_wins_the_owner_level():
    """The pick carries **no** roles, and that is the only observable case.

    Roles are unique per rung — `set_image_roles` strips a role from its siblings —
    so at the owner level exactly one picture holds `sheet`, and a pick that only
    answered the roles its picture carries could only ever name the picture the
    ladder already returns. That is why the pick answers every role.
    """
    info = _info([_image("def"), _image("pick", roles=())])
    assert await _setting(picked_image_id="pick").image(info, "sheet") == "pick:Small"


async def test_a_pick_is_the_instances_picture_for_every_role():
    """Every role this instance asks for is served by the picked picture — the same
    thing the sole-image rule gave a copy on an empty rung, with no files. Which
    *render* and tier a role serves is still the role map's decision."""
    info = _info([_image("def", roles=("background", "sheet", "navdot")),
                  _image("pick", roles=())])
    setting = _setting(picked_image_id="pick")
    assert await setting.image(info, "sheet") == "pick:Small"
    assert await setting.image(info, "background") == "pick:XLarge"
    assert await setting.image(info, "navdot") == "pick:Large"


async def test_a_pick_wins_over_the_instances_own_picture():
    """The pick is the instance's *chosen* picture, so it comes first.

    An instance that still holds one of `B215`'s copies would otherwise ignore
    every pick — the copy carries the roles, so it would win the rung below — and a
    pick that appears to do nothing is the bug this ticket is about. The pick is
    visible in the editor and one click to clear, so clearing it restores the
    instance's own picture and then the definition.
    """
    info = _info([_image("def"), _image("pick", roles=()), _image("mine", variant_id=SETTING)])
    setting = _setting(picked_image_id="pick")
    assert await setting.image(info, "sheet") == "pick:Small"

    cleared = _setting()
    assert await cleared.image(info, "sheet") == "mine:Small", "no pick → the instance's own"


async def test_a_pick_that_names_nothing_is_ignored():
    """A picture since deleted must not blank the surface."""
    info = _info([_image("def")])
    assert await _setting(picked_image_id="gone").image(info, "sheet") == "def:Small"


async def test_a_pick_cannot_reach_another_settings_rung():
    """The pointer is restricted to owner-level pictures, so it can never drag in a
    sibling instance's override."""
    info = _info([_image("def"), _image("theirs", variant_id=OTHER)])
    assert await _setting(picked_image_id="theirs").image(info, "sheet") == "def:Small"


def test_the_converter_carries_the_pick():
    """`_gql_trait_setting` feeds every read path, and a field dropped there reads
    as its default everywhere — how `enabled` once reported True for disabled
    settings. `""` is the no-pick value the client sees (the domain value, unchanged;
    `test_trait_setting_converters` requires that)."""
    from transversal.api.graphql.type_defs.traits import _gql_trait_setting
    from transversal.domain.traits import TraitSetting as DomainSetting

    def domain(picked):
        return DomainSetting(
            id=SETTING, entity_id="character-probe", trait_id=TRAIT,
            picked_image_id=picked,
        )

    assert _gql_trait_setting(domain("pick")).picked_image_id == "pick"
    assert _gql_trait_setting(domain("")).picked_image_id == ""
