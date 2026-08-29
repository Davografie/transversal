"""Transversal domain models — v2.

Multi-collection data model inspired by the v1 ArangoDB schema.

Collections:
  entities      — metadata (name, type, razmerit, universe state)
  projections   — per-universe body grouping
  traits        — registry of all possible traits per universe
  traitsets     — registry of trait groupings
  traitsettings — edge: entity → trait, carries rating/type/statement
  sfxs          — SFX registry
  relationships — edge: entity → entity
  life_paths    — life path definitions (Traveller-style term loops)
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from transversal.services.target_spec import TargetSpec


# ── Dice ──────────────────────────────────────────────

class DieType(str, Enum):
    D4 = "d4"
    D6 = "d6"
    D8 = "d8"
    D10 = "d10"
    D12 = "d12"

    @property
    def max_value(self) -> int:
        return int(self.value[1:])

    def step_up(self) -> "DieType":
        order = list(DieType)
        idx = order.index(self)
        return order[idx + 1] if idx < len(order) - 1 else self

    def step_down(self) -> "DieType":
        order = list(DieType)
        idx = order.index(self)
        return order[idx - 1] if idx > 0 else self


class RatingType(str, Enum):
    STATIC = "static"
    RESOURCE = "resource"
    CHALLENGE = "challenge"
    EMPTY = "empty"


class Polarity(str, Enum):
    """Whether a trait is a benefit/asset (positive) or a complication (negative).

    Applies to every trait, not just challenge pools.  Trait settings bake a
    concrete polarity at creation from the trait/traitset defaults; the enum is
    the single source of truth for that sign.
    """
    NEGATIVE = "negative"
    POSITIVE = "positive"


class OutcomeTier(str, Enum):
    FAIL = "fail"
    MARGINAL = "marginal"
    SUCCESS = "success"
    EXCEPTIONAL = "exceptional"
    PERFECT = "perfect"

    @property
    def effect_die(self) -> Optional[DieType]:
        return {
            OutcomeTier.FAIL: None,
            OutcomeTier.MARGINAL: DieType.D4,
            OutcomeTier.SUCCESS: DieType.D6,
            OutcomeTier.EXCEPTIONAL: DieType.D8,
            OutcomeTier.PERFECT: DieType.D10,
        }[self]


class EntityType(str, Enum):
    CHARACTER = "character"
    LOCATION = "location"
    FACTION = "faction"
    ASSET = "asset"
    GMC = "gmc"
    UNIVERSE = "universe"
    SUBTRAIT = "subtrait"
    RELATION = "relation"


class TransversalType(str, Enum):
    NATIVE = "native"
    CONSCIOUSNESS = "consciousness"
    INAPPOSITE = "inapposite"


# ── Die Roll Models ───────────────────────────────────

class DieSpec(BaseModel):
    """A die awaiting a roll — the shape shared by pools and roll requests.

    ``source_kind`` is extensible (trait / difficulty / manual / entity /
    projection / location / …); ``source_id`` is the specific identifier;
    ``label`` is the display name; ``ts_id`` is the trait-setting id.
    """
    die: DieType
    source_kind: str = "manual"
    source_id: str = ""
    label: str = ""
    ts_id: Optional[str] = None
    resource: bool = False  # resource-pool die: rolled separately, highest applies to total


class DieRoll(DieSpec):
    """A rolled die — a DieSpec plus its result and outcome tier.

    ``tier`` is the OutcomeTiers-table mapping of ``result`` (1–12) to an
    outcome tier; ``tier.effect_die`` gives the tier's virtual effect die.
    """
    result: int
    tier: Optional[OutcomeTier] = None


def _coerce_die_list(value) -> list[DieSpec]:
    """Accept both legacy `(die, source)` tuples and DieSpec-like dicts."""
    out: list[DieSpec] = []
    for item in value:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            die, source = item
            src = str(source or "")
            out.append(DieSpec(die=die, source_kind="manual", source_id=src, label=src))
        else:
            out.append(item)
    return out


class Opposition(BaseModel):
    type: str  # "challenge", "gmc", "static_difficulty"
    dice: list[DieSpec] = Field(default_factory=list)
    challenge_die: Optional[DieType] = None
    static_difficulty: Optional[int] = None

    @field_validator("dice", mode="before")
    @classmethod
    def _coerce_dice(cls, v):
        return _coerce_die_list(v)


class RollKind(str, Enum):
    """What kind of roll a dice pool represents.

    - ``test``: one side rolls against a difficulty/opposition.
    - ``contest``: two sides roll head-to-head; a winner is declared.
    - ``roll_table``: reserved for random-table outcomes (resolved via
      ``resolve_table``, not the dice resolver, today).
    """
    TEST = "test"
    CONTEST = "contest"
    ROLL_TABLE = "roll_table"


class DicePoolRequest(BaseModel):
    entity_id: str
    universe: str
    dice: list[DieSpec]
    opposition: Optional[Opposition] = None
    razmerit_spent: int = 0
    kind: RollKind = RollKind.TEST
    pipeline: Optional[str] = None  # "simplified" | "pool" | None (auto by size)
    hitches_apply: bool = True  # False for GM difficulty rolls (1s are just dice)

    @field_validator("dice", mode="before")
    @classmethod
    def _coerce_dice(cls, v):
        return _coerce_die_list(v)


class ChallengeResult(BaseModel):
    targeted_die: DieType
    effect_die: Optional[DieType]
    outcome: str
    new_challenge_rating: Optional[str] = None


class SimplifiedResult(BaseModel):
    pipeline: str = "simplified"
    kind: RollKind = RollKind.TEST
    rolls: list[DieRoll]
    highest: int
    tier: OutcomeTier
    effect_die: Optional[DieType]
    hitches: list[DieRoll]
    botch: bool
    opposition_roll: Optional[DieRoll] = None
    opposition_total: Optional[int] = None
    challenge_result: Optional[ChallengeResult] = None
    hitches_count: int = 0


class PoolResult(BaseModel):
    pipeline: str = "pool"
    kind: RollKind = RollKind.TEST
    rolls: list[DieRoll]
    kept: list[DieRoll]
    total: int
    resource_rolls: list[DieRoll] = Field(default_factory=list)
    resource_kept: Optional[DieRoll] = None
    effect_die: Optional[DieType]
    effect_die_value: Optional[int]
    unused: list[DieRoll]
    hitches: list[DieRoll]
    botch: bool
    opposition_rolls: list[DieRoll] = Field(default_factory=list)
    opposition_total: Optional[int] = None
    challenge_result: Optional[ChallengeResult] = None
    hitches_count: int = 0


RollResult = SimplifiedResult | PoolResult


class ContestWinner(str, Enum):
    """Winner of a two-sided contest.

    ``PLAYER`` is the challenger/initiator (the side that set the
    difficulty); ``OPPONENT`` is the defendant. Ties favor the initiator,
    so a tied contest resolves to ``PLAYER``.
    """
    PLAYER = "player"
    OPPONENT = "opponent"


class ContestResult(BaseModel):
    """Result of a head-to-head contest between two sides.

    Both sides roll their pools independently (they may use different
    pipelines) and the resolver compares totals/tiers to declare a winner.
    Effect dies are available for both sides — the winner's effect die
    determines the magnitude of their success; the loser's may still
    matter for certain SFX or narrative mechanics.

    """
    pipeline: str  # "simplified" or "pool" — which pipeline the contest used
    kind: RollKind = RollKind.CONTEST
    winner: ContestWinner
    player_result: SimplifiedResult | PoolResult
    opponent_result: SimplifiedResult | PoolResult
    pushed: bool = False
    push_cost: int = 1


class CommittedResult(BaseModel):
    """One side's committed contest result (after rolling + picking).

    ``total`` is the pool total, or the highest die for a simplified side.
    ``tier`` is the outcome tier for simplified sides.  A committed result
    is frozen — further trait changes don't touch it.
    """
    total: int
    effect_die: Optional[DieType] = None
    tier: Optional[OutcomeTier] = None
    pipeline: str = "pool"  # "pool" | "simplified"


class ContestOutcome(BaseModel):
    """The outcome of a manual contest after both sides commit (or give in).

    ``gave_in`` records which side conceded (``ContestWinner.PLAYER`` means
    the challenger gave in); the other side is the winner.
    """
    winner: ContestWinner
    challenger: Optional[CommittedResult] = None
    defendant: Optional[CommittedResult] = None
    gave_in: Optional[ContestWinner] = None
    pushed: bool = False
    high_stakes: bool = False
    effect_die: Optional[DieType] = None  # effective complication die to apply to the loser
    taken_out: bool = False


class ContestCompare(BaseModel):
    """Provisional contest comparison after both sides commit.

    Produced instead of a final outcome when the attacker beats the current
    difficulty: the now-losing side must give in or push (continue) once.
    """
    status: str = "compare"
    pending: str                       # entity_id that must give in or push
    initiative: str                    # entity_id holding the current difficulty
    challenger_id: str
    defendant_id: str
    challenger: Optional[CommittedResult] = None
    defendant: Optional[CommittedResult] = None
    margin: int = 0                    # attacker total - difficulty total (positive)


# ── Registry: Traits ──────────────────────────────────

class SubTraitRef(BaseModel):
    """Reference to a sub-trait in the registry."""
    trait_id: str
    name: str
    die_type: DieType

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

class TransferFlags(BaseModel):
    """Declares whether traits in a set or a specific trait can be transferred."""
    teachable: bool = False
    giftable: bool = False
    takable: bool = False


class Trait(BaseModel):
    """Registry entry — defines a trait that can exist in a universe.

    Stored in the `traits` collection.
    """
    id: str
    name: str
    universes: list[str] = Field(default_factory=list)
    traitset_id: str
    default_die_type: DieType = DieType.D6
    default_rating_type: RatingType = RatingType.STATIC
    required_trait_ids: list[str] = Field(default_factory=list)
    possible_subtrait_ids: list[str] = Field(default_factory=list)
    possible_sfx_ids: list[str] = Field(default_factory=list)
    default_sfx_ids: list[str] = Field(default_factory=list)
    location_restricted: bool = False
    default_ego: bool = False  # grant default: true = entity (ego/persists), false = projection (morph/gated)
    polarity: Optional["Polarity"] = None  # default polarity override (None = inherit traitset)
    explanation: str = ""
    random_weight: int = 0
    display_names: list[TraitDisplayName] = Field(default_factory=list)
    transfer_flags: Optional[TransferFlags] = None


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
    location_restricted: bool = False
    polarity: Optional["Polarity"] = None  # default polarity override (None = global positive)
    default_rating_type: RatingType = RatingType.STATIC
    default_die_type: DieType = DieType.D4
    transfer_flags: Optional[TransferFlags] = None


# ── Dice helpers ──────────────────────────────────────

def dice_list_to_rating(dice: list[DieType]) -> str:
    """Convert a dice array to a human-readable rating string.

    [D4, D4, D4, D4] → "4d4"
    [D4, D4, D6, D6] → "2d4 + 2d6"
    [D8]             → "d8"
    []               → "empty"
    """
    if not dice:
        return "empty"
    counts: dict[DieType, int] = {}
    for d in dice:
        counts[d] = counts.get(d, 0) + 1
    parts: list[str] = []
    for die in sorted(counts.keys(), key=lambda d: d.max_value):
        n = counts[die]
        parts.append(die.value if n == 1 else f"{n}{die.value}")
    return " + ".join(parts)

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



# ── Per-Entity: Trait Settings ─────────────────────────

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
    """
    id: str
    entity_id: str
    trait_id: str
    from_type: str = "entity"  # "entity" | "projection" | "relationship" — anchor collection for _from
    projection_id: Optional[str] = None  # projection anchor id when from_type == "projection"
    traitset_id: str
    rating_type: RatingType = RatingType.STATIC
    dice: list[DieType] = Field(default_factory=list)
    spent_dice: list[DieType] = Field(default_factory=list)  # spent-but-recoverable (resource pools)
    polarity: Polarity = Polarity.POSITIVE  # baked sign (benefit/asset vs complication)
    statement: str = ""        # distinction statement or flavor
    notes: str = ""            # longer freeform notes
    sub_trait_settings: list["TraitSetting"] = Field(default_factory=list)
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
    stolen: bool = False  # trait was taken — may have narrative consequences
    scheduled_events: list["ScheduledEvent"] = Field(default_factory=list)  # pending timed reverts

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


# ── Per-Entity: Trait Set Settings ───────────────────

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


# ── Projections ───────────────────────────────────────

class Projection(BaseModel):
    """Per-universe body grouping.

    Stored in the `projections` collection.

    ``id`` is immutable and uniquely identifies a body. The first body in a
    universe keys as ``"{entity_id}:{origin_universe}"``; additional bodies in
    the same universe append a numeric suffix (``:2``, ``:3``, …). Inapposite
    travel mutates ``universe`` and ``current_location`` in place — never the key.
    """
    id: str
    entity_id: str
    origin_universe: str = ""       # native/home universe (immutable)
    universe: str                   # current universe (mutable)
    name: str = ""                  # display name; falls back to entity name
    background_image: Optional[str] = None  # falls back to entity background_image
    current_location: Optional[str] = None   # where this body currently is
    transversal_type: TransversalType = TransversalType.NATIVE
    sfx_ids: list[str] = Field(default_factory=list)  # SFX owned by this body
    last_used_at: Optional[str] = None  # ISO timestamp of when this body was last active


# ── Entities ──────────────────────────────────────────

class Zone(BaseModel):
    name: str
    background_image: Optional[str] = None
    location_id: Optional[str] = None  # _key of the child location this zone links to
    x: float = 50.0   # percentage position on background image (0–100)
    y: float = 50.0   # percentage position on background image (0–100)


class TargetingBan(BaseModel):
    """A directional ban: the owning entity may not target ``target_id``.

    Expiry is driven by a scheduled event (``entity/remove_targeting_ban``), not
    by a countdown stored here.
    """
    target_id: str


class Entity(BaseModel):
    """Core entity metadata.

    Stored in the `entities` collection.
    """
    id: str
    type: EntityType
    name: str
    razmerit: int = 0
    current_universe: str
    current_location: Optional[str] = None
    current_projection: Optional[str] = None  # active projection id (occupant types)
    hidden: bool = False
    unpublished: bool = False  # GM draft: real in-world but not yet revealed to players
    known_to: list[str] = Field(default_factory=list)
    # Location
    background_image: Optional[str] = None
    starter_location: bool = False  # location is a valid random-spawn destination
    zones: list[Zone] = Field(default_factory=list)
    # Map positioning (percentage, per-location)
    map_x: Optional[float] = None
    map_y: Optional[float] = None
    # Visual overlay preset
    overlay: Optional[str] = None  # null, "mist", "fire", "rain", "snow", "sparkles", "fog"
    # Navigation dot positions
    nav_positions: dict = Field(default_factory=dict)  # e.g. {"parent": {"x": 90, "y": 15}}
    # Faction (conspyramid)
    node_ids: list[str] = Field(default_factory=list)
    # Asset
    owned_by: Optional[str] = None
    attunements: list["Attunement"] = Field(default_factory=list)  # active attunements (effect-managed)
    targeting_bans: list["TargetingBan"] = Field(default_factory=list)  # directional contest-target bans
    taken_out: bool = False  # scene-scoped: high-stakes contest removed this entity from the scene
    # Dice-pool selection-limit modifiers (deltas over the base limits: 2 total dice, 1 effect die).
    # Adjusted by ``modify_dice_limit`` effects; duration reverts undo the delta.
    total_dice_bonus: int = 0
    effect_dice_bonus: int = 0
    sfx_ids: list[str] = Field(default_factory=list)  # SFX owned directly by this entity
    scheduled_events: list["ScheduledEvent"] = Field(default_factory=list)  # pending timed reverts
    # Universe — per-entity-type LoRA configuration
    lora_config: Optional[dict] = None  # {"CHARACTER": ["lora1"], "LOCATION": []}
    # Life path tracking
    life_paths: list["Enrollment"] = Field(default_factory=list)  # memberships (faction + path)
    active_universes: list[str] = Field(default_factory=list)  # faction-only: where active
    suitable_life_path_ids: list[str] = Field(default_factory=list)  # faction-only: offered paths
    discovered_life_paths: list[str] = Field(default_factory=list)  # _keys of discovered paths
    pending_term: Optional["PendingTerm"] = None  # in-progress term state (checkpoint)
    # Post-roll consequence menu — location/lair moves authored directly on the entity.
    consequence_options: list["ConsequenceOption"] = Field(default_factory=list)


# ── Life Paths ─────────────────────────────────────────

class DiscoveryBlock(BaseModel):
    """Conditions for discovering a hidden life path.  Any one condition met → discovered."""
    at_location: list[str] = Field(default_factory=list)
    knows_entity: list[str] = Field(default_factory=list)
    possesses_trait: list[str] = Field(default_factory=list)
    has_trait_rating: dict[str, DieType] = Field(default_factory=dict)
    has_relationship: list[str] = Field(default_factory=list)


class LifePath(BaseModel):
    """A life path definition — an entry point into a graph of linked roll tables.

    Stored in the `life_paths` collection. Term structure lives in RollTable
    documents linked by ``next_step`` effects; discovery gating is optional.
    """
    id: str
    name: str
    universe: str
    description: str = ""
    entry_table_id: str = ""  # _key of the first RollTable in the flow
    discovery: Optional[DiscoveryBlock] = None  # null → always visible


class Enrollment(BaseModel):
    """A character's membership in a faction's life path."""
    faction_id: str
    path_id: str
    mustered: bool = False
    mishap_muster: bool = False


class PendingTerm(BaseModel):
    """In-progress life path term checkpoint.

    Holds where the entity is in the linked roll-table flow so a term can be
    resumed mid-way (reload / another device).
    """
    faction_id: str = ""
    path_id: str = ""
    current_table_id: str = ""
    continuation: list[str] = Field(default_factory=list)  # return-address stack (legacy single-exit)
    return_map: dict[str, str] = Field(default_factory=dict)  # named-exit map for shared tables (no nesting)


# ── SFX ───────────────────────────────────────────────

# Timing for deferred effects.

class EffectTiming(str, Enum):
    """When an effect fires relative to its trigger.

    Time boundaries (``end_of_beat``…) are persisted timers advanced on the
    matching global/state-change event. Roll events (``on_roll``/``on_set``/
    ``on_result``) are ephemeral, per-roll deferrals — they arm the effect and
    fire it at the next matching roll event (see ``services/roll_deferral``).
    """
    IMMEDIATE = "immediate"
    END_OF_BEAT = "end_of_beat"
    END_OF_SCENE = "end_of_scene"
    END_OF_SESSION = "end_of_session"
    AFTER_BEATS = "after_beats"
    ON_CONDITION = "on_condition"
    ON_ROLL = "on_roll"
    ON_SET = "on_set"
    ON_RESULT = "on_result"
    # Outcome-gated timings — fire at the next contest/roll resolution, gated by
    # the outcome. Also expressible via an effect condition, but kept as timing
    # names to mirror the SFX trigger vocabulary.
    ON_CONTEST_WIN = "on_contest_win"
    ON_CONTEST_LOSS = "on_contest_loss"
    ON_SUCCESS = "on_success"
    ON_FAILURE = "on_failure"


class AttunementScope(str, Enum):
    """Who an attunement affects."""
    SELF = "self"        # only the entity carrying the attunement
    DOMAIN = "domain"    # occupants in the entity's location subtree


class Attunement(BaseModel):
    """An active temporary addition of a universe to an entity's effective universes.

    Stored on the entity document (``Entity.attunements``).  Expiry is driven by
    the effects system: when the ``until`` timing fires, the effects system
    removes the attunement.
    """
    universe: str
    scope: AttunementScope = AttunementScope.SELF
    until: Optional[EffectTiming] = None
    source_sfx_id: Optional[str] = None


class TargetRef(BaseModel):
    """One named reference an effect resolves against game state.

    ``value`` is the concrete id after resolution — or, before resolution, a
    literal id / ``self`` / ``{choose_*}`` / ``{random:*}`` token. ``spec`` is
    the structured targeting pipeline that resolves ``value`` at fire time
    (None = literal). ``scope`` narrows runtime choice for ``{choose_*}`` /
    ``{random:*}``. The ref's element type is declared by the action's
    ``EffectActionMeta.refs`` entry, not stored per effect.
    """
    value: str = ""
    spec: Optional[TargetSpec] = None
    scope: Optional[str] = None


class EffectOutput(BaseModel):
    """A named value an effect exposes to later effects in the same activation.

    ``name`` is the variable name (referenced as ``{name}`` by later effects);
    ``field`` names which resolved field to bind (``target`` | ``entity`` |
    ``refs.<name>``); ``element`` is the catalog element type of the bound value
    (e.g. ``traitsetting``) so the targeting wizard can offer it as a typed
    ``select variable``. Empty ``element`` = untyped (string substitution only).
    """
    name: str
    field: str = "target"
    element: str = ""


class Effect(BaseModel):
    """A single operational effect — shared by SFX and life-path consequences.

    Sign (cost vs benefit) is derived from (type, action); it is not stored.
    """
    timing: EffectTiming = EffectTiming.IMMEDIATE
    type: str
    action: str
    target: str = ""
    entity: str = ""  # explicit subject entity; "" or "self" = the applyEffects entity
    result: Optional[str] = None
    target_scope: Optional[str] = None  # narrowing hint for runtime target choice
    entity_scope: Optional[str] = None  # narrowing hint for runtime entity choice
    target_filter: dict = Field(default_factory=dict)  # candidate field predicates, e.g. {"starter_location": True}
    die_filter: dict = Field(default_factory=dict)  # roll-die predicates for roll-deferred effects, e.g. {"role": None}
    conditions: list["Condition"] = Field(default_factory=list)  # per-effect gate (reuses the SFX condition model)
    negative: bool = False  # polarity of trait-grant effects: true = negative trait (opponent uses it)
    context: dict = Field(default_factory=dict)  # e.g. relationship description
    duration: Optional["EffectDuration"] = None  # when set, schedules the inverse effect on expiry
    # Structured targeting pipeline (the new model). None means the effect still
    # uses the legacy ``target`` string and is lazily migrated on read.
    target_spec: Optional[TargetSpec] = None
    # Structured subject resolution (who the effect applies to). None means the
    # effect still uses the legacy ``entity`` string.
    entity_spec: Optional[TargetSpec] = None
    # Named references — the multi-target model. Each key is a declared ref name
    # (see ``EffectActionMeta.refs``); ``target``/``entity`` remain as the
    # legacy single-reference fallback until the Step-3 migration removes them.
    refs: dict[str, TargetRef] = Field(default_factory=dict)
    # Values exposed to later effects in the same activation (see EffectOutput).
    outputs: list[EffectOutput] = Field(default_factory=list)


class Timer(BaseModel):
    """One countdown within an effect duration.

    ``event`` names the advancement signal that decrements it: ``"beat"``,
    ``"scene"``, ``"session"``, or any state-change event (e.g.
    ``"location_changed"``). ``remaining`` is the countdown; ``0`` (or event
    ``"immediate"``) fires on the next advancement pass.
    """
    event: str = "scene"
    remaining: int = 0


class TimerCombine(str, Enum):
    """How multiple timers combine to determine expiry."""
    FIRST_TO_FIRE = "first_to_fire"      # any timer reaches 0
    ALL_TRANSPIRED = "all_transpired"    # every timer reaches 0


class EffectDuration(BaseModel):
    """Timers + combine that turn a forward effect into a temporary one."""
    timers: list["Timer"] = Field(default_factory=list)
    combine: TimerCombine = TimerCombine.FIRST_TO_FIRE


class ScheduledEvent(BaseModel):
    """A persisted, centrally-scheduled revert fired when its timers expire.

    ``target_type`` + ``target_id`` identify the owner (entity or trait setting)
    the effect applies against; resolved at fire time so a deleted target is a
    no-op.
    """
    id: str
    target_type: str = "entity"           # "entity" | "trait_setting"
    target_id: str = ""                   # entity id or trait-setting id
    effect: "Effect"                     # the revert effect to apply
    timers: list["Timer"] = Field(default_factory=list)
    combine: TimerCombine = TimerCombine.FIRST_TO_FIRE
    source_sfx_id: Optional[str] = None


class ConsequenceOption(BaseModel):
    """A selectable entry in the post-roll consequence menu.

    Authored directly on entities (location moves), registered as base moves,
    or derived from ``on_consequence`` SFX. Choosing one applies its effects.
    """
    id: str
    label: str
    side: str = "player"  # "player" | "gm" | "either"
    effects: list[Effect] = Field(default_factory=list)
    source: str = "base"  # "base" | "entity" | "sfx"


class SFX(BaseModel):
    """SFX registry entry.

    Stored in the `sfxs` collection. ``trigger`` names the single activation
    axis — an auto-fire event, ``manual``, or a consequence menu; ``conditions``
    filter which instance of that activation applies (target/threshold/narrative).
    """
    id: str
    name: str
    description: str = ""
    trigger: str
    # Declarative owner type — what kind of thing carries this SFX (its
    # activation source). One of the ``SOURCE_KINDS`` keys in
    # ``target_catalog`` (``trait_setting``/``traitset_setting``/``entity``/
    # ``projection``); ``None`` = bucket/passive (no meaningful origin).
    source_kind: Optional[str] = None
    effects: list[Effect] = Field(default_factory=list)
    conditions: list["Condition"] = Field(default_factory=list)
    # How long the SFX stays in effect once triggered (the in-memory effective
    # tracker). Default = one roll. ``rolls``/``beat``/``scene``/``session`` or
    # a state-change event (``location_changed``/``trait_updated``) timer
    # extends it; ``None`` = indefinite (until cleared).
    duration: Optional["EffectDuration"] = Field(
        default_factory=lambda: EffectDuration(timers=[Timer(event="rolls", remaining=1)])
    )

    @model_validator(mode="before")
    @classmethod
    def _fold_legacy_menu_context(cls, data):
        """Migrate ``menu_context`` into ``trigger`` (single activation axis)."""
        if isinstance(data, dict) and data.get("menu_context"):
            data = {**data}
            data["trigger"] = data["menu_context"]
            data.pop("menu_context", None)
        return data

    @model_validator(mode="before")
    @classmethod
    def _fold_legacy_limit(cls, data):
        """Migrate the old ``limit`` string into a NARRATIVE condition."""
        if isinstance(data, dict) and data.get("limit"):
            limit = data["limit"]
            data = {**data}
            data.pop("limit", None)
            if not data.get("conditions"):
                data["conditions"] = [
                    Condition(type=ConditionType.NARRATIVE, narrative=limit)
                ]
        return data

    @property
    def limit(self) -> str:
        """Backward-compatible read of the narrative limit."""
        for c in self.conditions:
            if c.type == ConditionType.NARRATIVE and c.narrative:
                return c.narrative
        return ""


class SfxOwner(BaseModel):
    """A named SFX owner bucket.

    Stored in the `sfx_owners` collection. Ownership lives on the owner side:
    these buckets collect SFX ids that are available by category rather than by
    a single entity/trait/projection. Seeded with `table` (everyone) and `gm`
    (GM-context only).
    """
    id: str
    sfx_ids: list[str] = Field(default_factory=list)


# ── Conditions ──────────────────────────────────────

class ConditionType(str, Enum):
    """Kinds of automatically-evaluable gate/limit conditions."""
    ALWAYS = "always"
    AT_LOCATION = "at_location"          # target = location entity id
    HAS_TRAIT = "has_trait"              # target = trait id
    HAS_EFFECTIVE_TRAIT = "has_effective_trait"  # target = trait id; possession AND enabled
    HAS_TRAIT_IN_TRAITSET = "has_trait_in_traitset"  # target = traitset id
    HAS_RELATIONSHIP = "has_relationship"  # target = related entity id
    TRAIT_RATING = "trait_rating"        # target = trait id; value = rating threshold (e.g. d8)
    HAS_RAZMERIT = "has_razmerit"        # value = integer; operator = numeric comparator
    ENTITY_TYPE = "entity_type"          # target = entity type (character/gmc/asset); subject = the entity
    NARRATIVE = "narrative"              # human-readable only, never auto-blocks
    UNPLACED = "unplaced"                # entity has no current location yet
    IN_UNIVERSE = "in_universe"          # target = universe key; entity is currently there
    PHASE = "phase"                      # target = dice-pool phase (e.g. "adding"); reads trigger context
    CONTEST_OUTCOME = "contest_outcome"  # target = "player" | "opponent"; reads context["contest_winner"]
    ROLL_TIER = "roll_tier"              # operator + value against OutcomeTier (e.g. >= success); reads roll_result.tier
    TEST_OUTCOME = "test_outcome"        # target = "success" | "fail" (binary); success = tier != fail


class Condition(BaseModel):
    """A configurable, automatically-evaluated gate or limit.

    Parallel to Effect: authored once, evaluated against an entity's state.
    """
    type: ConditionType = ConditionType.ALWAYS
    subject: str = ""                # "" = current entity; else literal id or {variable}
    target: str = ""                  # trait / location / entity id (or {variable})
    value: Optional[str] = None       # threshold, e.g. rank number
    operator: str = ">="              # numeric comparator for HAS_RAZMERIT ("<", "<=", "==", "!=", ">=", ">")
    narrative: str = ""               # human-readable fallback text


# ── Roll Tables ──────────────────────────────────────

class RollTableScheme(str, Enum):
    """How a roll table selects an entry."""
    RANGE = "range"    # entry declares min_value / max_value
    WEIGHT = "weight"  # entry declares weight; cumulative proportional pick
    TIER = "tier"      # entry keyed to an OutcomeTier
    INDEX = "index"    # ordered list; roll 1 → first entry


class RollSource(str, Enum):
    """Where a roll table's number comes from.

    FIXED_DIE — roll the table's own ``die`` (the original behaviour).
    TRAIT_DICE — the player picks ``trait_dice_count`` traits they have and
    rolls those instead; the derived number selects the entry.
    """
    FIXED_DIE = "fixed_die"
    TRAIT_DICE = "trait_dice"


class RollTableEntry(BaseModel):
    """A single entry in a roll table.

    Which selection fields are meaningful depends on the parent table's
    ``scheme``: range uses ``min_value``/``max_value``, weight uses ``weight``,
    tier uses ``tier``, and index uses the entry's position in the list.
    """
    label: str = ""
    description: str = ""
    min_value: Optional[int] = None
    max_value: Optional[int] = None
    weight: Optional[int] = None
    tier: Optional[OutcomeTier] = None
    conditions: list[Condition] = Field(default_factory=list)
    effects: list[Effect] = Field(default_factory=list)


class RollTableCheck(BaseModel):
    """Dice-pool check metadata for a TIER-scheme roll table.

    When present, resolving the table assembles a pool (predetermined traits or a
    free player choice) and rolls against ``difficulty``; the outcome tier selects
    a tier-keyed entry.
    """
    trait_ids: list[str] = Field(default_factory=list)
    difficulty: DieType = DieType.D6
    free_choice: bool = False


class RollTable(BaseModel):
    """A reusable roll table whose entries execute effects when selected."""
    id: str
    name: str
    universe: str = ""
    life_path: Optional[str] = None  # owning life path id; None = shared/general
    scheme: RollTableScheme = RollTableScheme.RANGE
    roll_source: RollSource = RollSource.FIXED_DIE
    trait_dice_count: int = 1  # number of trait dice to roll (N=1 for now)
    die: DieType = DieType.D6  # die size for range/index rolls (FIXED_DIE)
    check: Optional[RollTableCheck] = None  # legacy dice-pool check; unused
    entries: list[RollTableEntry] = Field(default_factory=list)
    # Canvas layout persistence (GM manual arrangement of life-path nodes).
    canvas_x: Optional[float] = None
    canvas_y: Optional[float] = None


# ── Assembled Views (not stored, built by repo) ───────

class CharacterView(BaseModel):
    """Full character assembled from multiple collections."""
    entity: Entity
    projections: list[Projection] = Field(default_factory=list)
    trait_settings: list[TraitSetting] = Field(default_factory=list)


# ── Entity Images ─────────────────────────────────────

class ImageType(str, Enum):
    UPLOADED = "uploaded"
    IMAGEN = "imagen"
    ANIMATED = "animated"


class EntityImage(BaseModel):
    """Metadata for a generated image stored per-entity, per-universe.

    Stored in the `entity_images` collection.
    Files live at media/imagen/{entity_id}/{universe}/{image_id}_{variant}.{ext}

    ``projection_id`` ties the image to a specific body (projection). When
    empty the image is entity-level — the soul's default, used as fallback
    for any body that has no body-specific image for a role. Role uniqueness
    is keyed on the owner (projection id when set, else entity id) plus role.
    """
    id: str  # uuid
    entity_id: str
    projection_id: Optional[str] = None  # owning body; empty = entity-level default
    universe: str
    image_type: ImageType
    roles: list[str] = Field(default_factory=list)  # ["background", "sheet", "navdot"]
    prompt: str = ""
    negative_prompt: str = ""
    loras: list[str] = Field(default_factory=list)
    width: int = 0
    height: int = 0
    seed: int = 0
    steps: int = 0
    filename: str = ""  # base filename without variant suffix or extension
    extension: str = "png"
    created_at: str = ""  # ISO 8601


# ── Messages ────────────────────────────────────────────

class MessageKind(str, Enum):
    LETTER = "letter"
    JOURNAL = "journal"
    REPORT = "report"
    GM_NOTE = "gm_note"


class Message(BaseModel):
    """Persistent message between entities.

    Stored in the `messages` collection.
    Relationship descriptions are resolved at query time from
    the ``associate`` edge in ``relationships``.

    Kinds:
      letter   — entity → entity, visible to recipient + GM
      journal  — entity → GM only (private musings)
      report   — entity → GMC, visible to GM
      gm_note  — GM → entity (NPC correspondence, GM nudges)
    """
    id: str
    sender_entity_id: str
    recipient_entity_id: str
    kind: MessageKind = MessageKind.LETTER
    title: str = ""
    body: str = ""
    images: list[str] = Field(default_factory=list)  # media paths
    after_ids: list[str] = Field(default_factory=list)
    threads: list[str] = Field(default_factory=list)
    created_at: str = ""  # ISO 8601, populated by repository on insert


# ── Historical Records ──────────────────────────────────

class HistoricalRecordType(str, Enum):
    """Kinds of append-only historical events."""
    ROLL_TABLE = "roll_table"
    CONTEST = "contest"
    TRANSVERSAL = "transversal"


class HistoricalRecord(BaseModel):
    """An append-only historical event for an entity.

    Stored in the `historical_records` collection. ``record_type``
    discriminates the shape of ``data``; future event kinds (contests,
    location traversals) reuse the same collection.
    """
    id: str = ""
    entity_id: str = ""
    record_type: HistoricalRecordType = HistoricalRecordType.ROLL_TABLE
    universe: str = ""
    session_id: str = ""
    data: dict = Field(default_factory=dict)  # type-specific payload
    created_at: str = ""  # ISO 8601, populated by repository on insert