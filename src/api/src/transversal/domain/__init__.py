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

from pydantic import BaseModel, Field


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


class ChallengePolarity(str, Enum):
    """For CHALLENGE-type traits: whether the pool represents danger or progress.

    NEGATIVE — doom pool: GM spends dice to strengthen opposition.
        Failures and hitches add dice or step existing dice up.

    POSITIVE — progress clock: players roll against the pool to reduce it.
        Successes remove or step down dice.  When empty, the project completes.
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

class DieRoll(BaseModel):
    die: DieType
    result: int
    source: str


class Opposition(BaseModel):
    type: str  # "challenge", "gmc", "static_difficulty"
    dice: list[tuple[DieType, str]] = Field(default_factory=list)
    challenge_die: Optional[DieType] = None
    static_difficulty: Optional[int] = None


class DicePoolRequest(BaseModel):
    entity_id: str
    universe: str
    dice: list[tuple[DieType, str]]
    opposition: Optional[Opposition] = None
    razmerit_spent: int = 0


class ChallengeResult(BaseModel):
    targeted_die: DieType
    effect_die: Optional[DieType]
    outcome: str
    new_challenge_rating: Optional[str] = None


class SimplifiedResult(BaseModel):
    pipeline: str = "simplified"
    rolls: list[DieRoll]
    highest: int
    tier: OutcomeTier
    effect_die: Optional[DieType]
    hitches: list[DieRoll]
    botch: bool
    opposition_roll: Optional[DieRoll] = None
    challenge_result: Optional[ChallengeResult] = None
    razmerit_earned: int = 0


class PoolResult(BaseModel):
    pipeline: str = "pool"
    rolls: list[DieRoll]
    kept: list[DieRoll]
    total: int
    effect_die: Optional[DieType]
    effect_die_value: Optional[int]
    unused: list[DieRoll]
    hitches: list[DieRoll]
    botch: bool
    opposition_rolls: list[DieRoll] = Field(default_factory=list)
    opposition_total: Optional[int] = None
    challenge_result: Optional[ChallengeResult] = None
    razmerit_earned: int = 0


RollResult = SimplifiedResult | PoolResult


class ContestWinner(str, Enum):
    PLAYER = "player"
    OPPONENT = "opponent"
    TIE_DEFENDER = "tie_defender"


class ContestResult(BaseModel):
    """Result of a head-to-head contest between two sides.

    Both sides roll their pools independently (they may use different
    pipelines) and the resolver compares totals/tiers to declare a winner.
    Effect dies are available for both sides — the winner's effect die
    determines the magnitude of their success; the loser's may still
    matter for certain SFX or narrative mechanics.
    """
    pipeline: str  # "simplified" or "pool" — which pipeline the contest used
    winner: ContestWinner
    player_result: SimplifiedResult | PoolResult
    opponent_result: SimplifiedResult | PoolResult
    pushed: bool = False
    push_cost: int = 1


# ── Per-Location Dice Pool Tracking ───────────────────

class PoolAssembly(BaseModel):
    """A dice pool being assembled for a contest at a specific location.

    Tracks which dice an entity has added to their pool for the current
    beat at a given location.  Pools are location-scoped so a player can
    build pools in different scenes independently.
    """
    entity_id: str
    location_id: str
    universe: str
    dice: list[tuple[DieType, str]] = Field(default_factory=list)
    opposition_entity_id: Optional[str] = None
    pushed_this_beat: bool = False
    razmerit_spent: int = 0


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

    The ``dice`` array is the single source of truth for what dice this
    trait contributes.  For a static d8 trait it is ``[D8]``.  For a
    resource pool of 4d4 it is ``[D4, D4, D4, D4]``.  Spending removes a
    die from the array; recovery appends one.

    ``rating_type`` determines behaviour (STATIC / RESOURCE / CHALLENGE /
    EMPTY) and is never inferred from the dice.
    """
    id: str
    entity_id: str
    trait_id: str
    from_type: str = "entity"  # "entity" | "relationship" — which collection _from points to
    traitset_id: str
    rating_type: RatingType = RatingType.STATIC
    dice: list[DieType] = Field(default_factory=list)
    polarity: Optional[ChallengePolarity] = None  # meaningful only for CHALLENGE traits
    statement: str = ""        # distinction statement or flavor
    negative: bool = False     # true = negative trait (opponent uses it)
    ego: bool = False          # true = persists across all universes/projections
    sub_trait_settings: list["TraitSetting"] = Field(default_factory=list)
    sfx_ids: list[str] = Field(default_factory=list)
    locations_enabled: list[str] = Field(default_factory=list)
    locations_disabled: list[str] = Field(default_factory=list)
    known_to: list[str] = Field(default_factory=list)
    # Provenance — how this trait was acquired
    source_type: Optional[str] = None
        # "taught" | "gifted" | "taken" | "life_path_term" | "event" | null
    source_entity_id: Optional[str] = None  # who taught/gifted it, or who it was taken from
    source_trait_setting_id: Optional[str] = None  # original TraitSetting this derived from (teach)
    source_life_path_id: Optional[str] = None  # which life path generated this (life_path_term)
    source_term_number: Optional[int] = None  # which term in that path (life_path_term)
    stolen: bool = False  # trait was taken — may have narrative consequences


# ── Projections ───────────────────────────────────────

class Projection(BaseModel):
    """Per-universe body grouping.

    Stored in the `projections` collection.
    """
    id: str
    entity_id: str
    universe: str
    transversal_type: TransversalType = TransversalType.NATIVE


# ── Entities ──────────────────────────────────────────

class Zone(BaseModel):
    name: str
    background_image: Optional[str] = None
    location_id: Optional[str] = None  # _key of the child location this zone links to
    x: float = 50.0   # percentage position on background image (0–100)
    y: float = 50.0   # percentage position on background image (0–100)


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
    hidden: bool = False
    known_to: list[str] = Field(default_factory=list)
    # Location
    background_image: Optional[str] = None
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
    # Universe — per-entity-type LoRA configuration
    lora_config: Optional[dict] = None  # {"CHARACTER": ["lora1"], "LOCATION": []}
    # Life path tracking
    terms_served: int = 0                     # total terms across all paths
    current_life_path_id: Optional[str] = None  # _key of active path
    current_rank: int = 0                     # rank in current path
    life_history: list["LifeTerm"] = Field(default_factory=list)
    drifter_terms: int = 0                    # terms spent as a drifter
    discovered_life_paths: list[str] = Field(default_factory=list)  # _keys of discovered paths


# ── Life Paths ─────────────────────────────────────────

class DiscoveryBlock(BaseModel):
    """Conditions for discovering a hidden life path.  Any one condition met → discovered."""
    at_location: list[str] = Field(default_factory=list)
    knows_entity: list[str] = Field(default_factory=list)
    possesses_trait: list[str] = Field(default_factory=list)
    has_trait_rating: dict[str, DieType] = Field(default_factory=dict)
    has_relationship: list[str] = Field(default_factory=list)


class QualificationInfo(BaseModel):
    """Entry requirements for a life path."""
    trait_id: str
    difficulty: DieType = DieType.D6
    must_be_at_location: Optional[str] = None  # location entity ID required to take a term
    draft: Optional[str] = None  # path _key to draft into on failure


class CurriculumItem(BaseModel):
    """A trait gained or stepped up during the Learn phase."""
    trait_id: str
    create_at: DieType = DieType.D4  # rating if trait is new to the character
    step_up: bool = False  # if the character already has the trait, step up instead
    min_rank: int = 0  # rank required for this curriculum item


class SurvivalInfo(BaseModel):
    """Survival phase configuration for a life path."""
    trait_ids: list[str] = Field(default_factory=list)
    difficulty: DieType = DieType.D6
    term_penalty_after: Optional[int] = 4  # after N terms in this path, difficulty steps up
    mishaps: list[dict] = Field(default_factory=list)  # [{description, effect}]


class EventItem(BaseModel):
    """A single event in a life path's event table."""
    description: str
    effect: dict = Field(default_factory=dict)
    min_rank: int = 0  # rank required for this event to be rollable


class RankInfo(BaseModel):
    """A rank in a life path's advancement ladder."""
    number: int
    name: str
    benefits: list[dict] = Field(default_factory=list)


class AdvancementInfo(BaseModel):
    """Advancement phase configuration for a life path."""
    trait_ids: list[str] = Field(default_factory=list)
    difficulty: DieType = DieType.D6
    ranks: list[RankInfo] = Field(default_factory=list)


class MusterOutInfo(BaseModel):
    """Benefits granted when mustering out of a life path."""
    per_term_benefits: list[dict] = Field(default_factory=list)  # razmerit, asset traits, contacts
    at_ranks: dict[str, list[dict]] = Field(default_factory=dict)  # rank_number → benefits


class LifePath(BaseModel):
    """A life path definition — a structured narrative container for character growth.

    Stored in the `life_paths` collection.
    """
    id: str
    name: str
    universe: str
    description: str = ""
    qualification: Optional[QualificationInfo] = None
    discovery: Optional[DiscoveryBlock] = None  # null → always visible
    curriculum: list[CurriculumItem] = Field(default_factory=list)
    survival: Optional[SurvivalInfo] = None
    events: list[EventItem] = Field(default_factory=list)
    advancement: Optional[AdvancementInfo] = None
    muster_out: Optional[MusterOutInfo] = None


class LifeTerm(BaseModel):
    """Record of a completed life path term in an entity's life_history."""
    path_id: str
    path_name: str
    universe: str
    terms_served: int
    final_rank: int
    mustered_out: bool = False
    mishap_muster: bool = False  # true if forced out by mishap → re-entry at rank 0


# ── SFX ───────────────────────────────────────────────

# Timing for deferred effects.

class EffectTiming(str, Enum):
    IMMEDIATE = "immediate"
    END_OF_BEAT = "end_of_beat"
    END_OF_SCENE = "end_of_scene"
    END_OF_SESSION = "end_of_session"
    AFTER_BEATS = "after_beats"
    ON_CONDITION = "on_condition"


class Effect(BaseModel):
    """A single operational effect — shared by SFX and life-path consequences.

    Sign (cost vs benefit) is derived from (type, action); it is not stored.
    """
    timing: EffectTiming = EffectTiming.IMMEDIATE
    type: str
    action: str
    target: str = ""
    result: Optional[str] = None
    target_scope: Optional[str] = None  # narrowing hint for runtime target choice
    context: dict = Field(default_factory=dict)  # e.g. relationship description


class SFX(BaseModel):
    """SFX registry entry.

    Stored in the `sfxs` collection.
    """
    id: str
    name: str
    description: str = ""
    limit: str = ""          # narrative condition / restriction (markdown)
    trigger: str
    effects: list[Effect] = Field(default_factory=list)


# ── Roll Tables ──────────────────────────────────────

class RollTableScheme(str, Enum):
    """How a roll table selects an entry."""
    RANGE = "range"    # entry declares min_value / max_value
    WEIGHT = "weight"  # entry declares weight; cumulative proportional pick
    TIER = "tier"      # entry keyed to an OutcomeTier
    INDEX = "index"    # ordered list; roll 1 → first entry


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
    effects: list[Effect] = Field(default_factory=list)


class RollTable(BaseModel):
    """A reusable roll table whose entries execute effects when selected."""
    id: str
    name: str
    universe: str = ""
    scheme: RollTableScheme = RollTableScheme.RANGE
    die: DieType = DieType.D6  # die size for range/index rolls
    entries: list[RollTableEntry] = Field(default_factory=list)


# ── Assembled Views (not stored, built by repo) ───────

class CharacterView(BaseModel):
    """Full character assembled from multiple collections."""
    entity: Entity
    projections: dict[str, Projection] = Field(default_factory=dict)
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
    """
    id: str  # uuid
    entity_id: str
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