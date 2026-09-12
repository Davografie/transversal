"""Traits — split out of src/api/src/transversal/domain/__init__.py."""

from pydantic import BaseModel
from pydantic import Field
from pydantic import model_validator
from typing import Optional
from transversal.domain.effects import (
    ScheduledEvent,
)
from transversal.domain.enums import (
    DieType,
    EntityType,
    Polarity,
    RatingType,
)


class TraitDisplayName(BaseModel):
    """Dynamic display name for a trait, keyed by universe and rating.

    When an entity's dice rating matches one of the ``ratings`` entries in
    the matching ``universe``, this display name is used instead of the
    trait's base name.

    ``ratings`` is a list of dice-combination alternatives.  Each entry is
    itself a list of DieType values.  For example::

        [
          TraitDisplayName(name="dao sliver", universe="three_realms",
                           ratings=[[DieType.D4]]),
          TraitDisplayName(name="law of the dao", universe="three_realms",
                           ratings=[[DieType.D12], [DieType.D10, DieType.D10]]),
        ]

    The first entry whose ``ratings`` list contains the entity's exact dice
    set (in any order) wins.  If no display name matches, the trait's base
    ``name`` is used.
    """
    name: str
    universe: str
    ratings: list[list[DieType]] = Field(default_factory=list)

class Trait(BaseModel):
    """Registry entry — defines a trait that can exist in a universe.

    Stored in the `traits` collection.
    """
    id: str
    name: str
    universes: list[str] = Field(default_factory=list)
    traitset_id: str
    tags: list[str] = Field(default_factory=list)  # free-form labels a condition/target can match on (e.g. "violent")
    default_die_type: DieType = DieType.D6
    default_rating_type: RatingType = RatingType.STATIC
    required_trait_ids: list[str] = Field(default_factory=list)
    possible_subtrait_ids: list[str] = Field(default_factory=list)
    possible_subtraitset_ids: list[str] = Field(default_factory=list)
    possible_sfx_ids: list[str] = Field(default_factory=list)
    default_sfx_ids: list[str] = Field(default_factory=list)
    default_ego: bool = False  # grant default: true = entity (ego/persists), false = projection (morph/gated)
    polarity: Optional["Polarity"] = None  # default polarity override (None = inherit traitset)
    explanation: str = ""
    random_weight: int = 0
    display_names: list[TraitDisplayName] = Field(default_factory=list)

class TraitSet(BaseModel):
    """Registry entry — groups traits.

    Stored in the `traitsets` collection.
    """
    id: str
    name: str
    universes: list[str] = Field(default_factory=list)
    description: str = ""
    entity_types: list[EntityType] = Field(default_factory=list)
    order: int = 0
    limit: int = 1
    allow_duplicates: bool = False
    polarity: Optional["Polarity"] = None  # default polarity override (None = global positive)
    default_rating_type: RatingType = RatingType.STATIC
    default_die_type: DieType = DieType.D4

def resolve_trait_display_name(
    trait: "Trait", dice: list[DieType], universe: str
) -> str:
    """Resolve the dynamic display name for a trait given an entity's dice
    and current universe.

    Returns the first matching ``TraitDisplayName.name`` whose ``universe``
    matches (or is ``"*"``) and whose ``ratings`` contains the entity's
    exact dice combination (order-independent).  If no match is found,
    returns ``trait.name``.

    When ``dice`` is empty, returns ``trait.name`` immediately.
    """
    if not trait.display_names or not dice:
        return trait.name
    sorted_dice = sorted(die.value for die in dice)
    for dn in trait.display_names:
        if dn.universe != universe and dn.universe != "*":
            continue
        for rating in dn.ratings:
            if sorted(r.value for r in rating) == sorted_dice:
                return dn.name
    return trait.name

class TraitSetting(BaseModel):
    """Entity-specific configuration of a trait.

    Stored as an edge in the `traitsettings` collection.
    _from → entity, _to → trait (registry).

    The ``dice`` array holds the currently-available dice this trait
    contributes.  For a static d8 trait it is ``[D8]``.  For a resource
    pool, ``dice`` is the unspent remainder and ``spent_dice`` holds the
    dice that have been spent and are recoverable; the pool's capacity is
    ``dice + spent_dice``.  Spending moves a die ``dice → spent_dice``;
    recovery moves it back, so recovery can never exceed what was spent.

    ``rating_type`` determines behaviour (STATIC / RESOURCE / CHALLENGE /
    EMPTY) and is never inferred from the dice.

    ``capacity`` is the challenge pool's target/cap: for a positive
    (progress) challenge it is the completion target (e.g. ``[D6, D6, D6]``)
    the ``dice`` ledger fills toward; for a negative (doom) challenge it is an
    optional growth ceiling (currently unused). Resources may optionally store
    their explicit original capacity here too.
    """
    id: str
    entity_id: str
    trait_id: str
    from_type: str = "entity"  # "entity" | "projection" | "relationship" | "traitsetting" — anchor collection for _from
    projection_id: Optional[str] = None  # projection anchor id when from_type == "projection"
    parent_traitsetting_id: Optional[str] = None  # parent TraitSetting id when from_type == "traitsetting" (sub-trait)
    traitset_id: str
    rating_type: RatingType = RatingType.STATIC
    dice: list[DieType] = Field(default_factory=list)
    spent_dice: list[DieType] = Field(default_factory=list)  # spent-but-recoverable (resource pools)
    capacity: Optional[list[DieType]] = None  # challenge target (positive) / ceiling (negative)
    polarity: Polarity = Polarity.POSITIVE  # baked sign (benefit/asset vs complication)
    statement: str = ""        # distinction statement or flavor
    notes: str = ""            # longer freeform notes
    tags: list[str] = Field(default_factory=list)  # instance-level labels, matched alongside the trait's own (B116)
    sfx_ids: list[str] = Field(default_factory=list)
    locations_enabled: list[str] = Field(default_factory=list)
    locations_disabled: list[str] = Field(default_factory=list)
    enabled: bool = True  # false = disabled; contributes no dice until re-enabled
    known_to: list[str] = Field(default_factory=list)
    # Provenance — how this trait was acquired
    source_type: Optional[str] = None
        # "taught" | "gifted" | "taken" | "life_path_term" | "event" | null
    source_entity_id: Optional[str] = None  # who taught/gifted it, or who it was taken from
    source_trait_setting_id: Optional[str] = None  # original TraitSetting this derived from (teach)
    source_life_path_id: Optional[str] = None  # which life path generated this (life_path_term)
    source_term_number: Optional[int] = None  # which term in that path (life_path_term)
    scheduled_events: list["ScheduledEvent"] = Field(default_factory=list)  # pending timed reverts

    @property
    def rating(self) -> Optional[DieType]:
        """The trait's current rating = its highest die (None when empty).

        This is the runtime backing for the catalog's ``traitsetting.rating``
        filter field, so a targeting path can predicate on ``rating >= d8``.
        """
        if not self.dice:
            return None
        return max(self.dice, key=lambda d: d.max_value)

    @model_validator(mode="before")
    @classmethod
    def _fold_legacy_negative(cls, data):
        """Fold the old ``negative``/challenge ``polarity`` split into one field.

        Legacy docs may store ``polarity=None`` and carry the sign in
        ``negative``.  Bake a concrete polarity at load so the model stays
        non-null without requiring a migration to run first.
        """
        if isinstance(data, dict):
            data = {**data}
            if data.get("negative"):
                data["polarity"] = "negative"
            if data.get("polarity") is None:
                data["polarity"] = "positive"
            data.pop("negative", None)
        return data

class TraitSetSetting(BaseModel):
    """Entity-specific configuration of a trait set.

    Stored as an edge in the `traitsetsettings` collection.
    _from → entity (or projection), _to → traitset (registry).

    This is the set-level sibling of `TraitSetting`. It carries SFX that apply
    to the trait set *as a unit* (not per-trait) for a specific entity/projection,
    plus an optional ``limit`` override (registry default when None).
    sort-order/order fields are Phase 4, not modeled yet.
    """
    id: str
    entity_id: str
    traitset_id: str
    from_type: str = "entity"  # "entity" | "projection" — anchor collection for _from
    projection_id: Optional[str] = None  # projection anchor id when from_type == "projection"
    sfx_ids: list[str] = Field(default_factory=list)
    limit: Optional[int] = None  # per-entity override of the trait set's registry limit (None = registry default)

def derive_placement(trigger: str) -> str:
    """The activation surface implied by a trigger (``auto``/``sheet``/``menu``).

    ``manual`` → sheet (owner card), ``on_*`` → auto (event-driven), and the
    legacy menu-context triggers (``test_success``/``contest_win``/…) → menu.
    """
    if trigger == "manual":
        return "sheet"
    if trigger.startswith("on_"):
        return "auto"
    return "menu"

def derive_arming_scope(trigger: str) -> str:
    """The listener scope implied by a trigger (``self``/``global``).

    ``on_session_start`` → ``global`` (a passive rule that listens to every
    entity's rolls); any other trigger → ``self`` (listen to the triggering
    entity). This is the default when an SFX declares no explicit scope.
    """
    return "global" if trigger == "on_session_start" else "self"
