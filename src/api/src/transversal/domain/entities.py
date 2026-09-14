"""Entities — split out of src/api/src/transversal/domain/__init__.py."""

from pydantic import BaseModel
from pydantic import Field
from typing import Optional
from transversal.domain.effects import (
    ConsequenceOption,
    ScheduledEvent,
)
from transversal.domain.enums import (
    AttunementOp,
    AttunementScope,
    EffectTiming,
    EntityType,
    TransversalType,
)
from transversal.domain.lifepath import (
    Enrollment,
    PendingTerm,
)


STRUCTURAL_RELATIONSHIP_TYPES: frozenset[str] = frozenset({
    "super",        # child location → parent location
    "membership",   # entity → faction
    "agency",       # player → entity (carries the ``main`` flag)
    "transversal",  # location travel / portal
    "commands",     # GMC → GMC command chain (conspyramid)
    "support",      # support character → main
})

PERSONAL_RELATIONSHIP_TYPE: str = "relation"

def is_structural_relationship_type(rel_type: str) -> bool:
    """Whether ``rel_type`` is structural system wiring (vs a personal relation)."""
    return rel_type in STRUCTURAL_RELATIONSHIP_TYPES

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
    support_eligible: bool = False  # GMC may be taken over as a support character (B86)
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
    # Universe — free-text style steering appended to every prompt generated here
    prompt_steering: str = ""
    # Life path tracking
    life_paths: list["Enrollment"] = Field(default_factory=list)  # memberships (faction + path)
    active_universes: list[str] = Field(default_factory=list)  # faction-only: where active
    suitable_life_path_ids: list[str] = Field(default_factory=list)  # faction-only: offered paths
    discovered_life_paths: list[str] = Field(default_factory=list)  # _keys of discovered paths
    pending_term: Optional["PendingTerm"] = None  # in-progress term state (checkpoint)
    # Post-roll consequence menu — location/lair moves authored directly on the entity.
    consequence_options: list["ConsequenceOption"] = Field(default_factory=list)

class Attunement(BaseModel):
    """A projection grant: a body made live, or cut off.

    Stored on the entity document (``Entity.attunements``). The entity's *active
    projection set* is **derived** from these on read (see
    [[Active Projections Design Log]]); expiry is driven by the effects system:
    when the ``until`` timing fires, the effects system removes the grant.

    Two target forms (which generalise to a resolved targeting path):
    ``universe`` names every one of the carrier's bodies from that universe
    (needed for ``domain`` grants, which cannot name one occupant's body), and
    ``projection_id`` names one specific body (the ``suppress`` form).
    """
    universe: Optional[str] = None
    projection_id: Optional[str] = None
    op: AttunementOp = AttunementOp.ADD
    scope: AttunementScope = AttunementScope.SELF
    until: Optional[EffectTiming] = None
    source_sfx_id: Optional[str] = None
