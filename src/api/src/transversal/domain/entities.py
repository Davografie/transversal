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

# Who may hold faction membership. A roster entry is member → faction, so the
# member end is a person-like or owned thing; a faction cannot be a member of a
# faction through this edge (nested orgs are a `relation` between two factions).
MEMBERSHIP_HOLDER_TYPES: frozenset[EntityType] = frozenset({
    EntityType.CHARACTER,
    EntityType.GMC,
    EntityType.ASSET,
})

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
    """A pin on a location's background image that opens a **child location**.

    The label is **derived** — the dot renders the linked child's name, which is
    not stored here. A stored copy used to live on this model and went stale the
    moment the child was renamed (2026-09-23 cleanup).
    """
    location_id: str  # _key of the child location this zone links to
    background_image: Optional[str] = None
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
    # The objective this character is being *guided* to: a location id, written by
    # the effects system's "set destination" action and read by the viewer to light
    # the next hop ([[Location Viewer]]). Null = no directions. Only the id is
    # stored — the destination's name and the route are both derived, so a rename
    # or a graph change can never leave a stale label or a stale route behind.
    destination_location: Optional[str] = None
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
    # Trait chip positions, keyed by trait-setting id: {"<ts-id>": {"x": 30, "y": 55}}.
    # Image-space percentages, exactly like `nav_positions`, so a chip pans with
    # the scene. Per LOCATION, deliberately: an inherited trait's chip is placed
    # where this location wants it, and nothing is written onto the owner — the
    # same doom pool can sit differently in the hall and in the cellar ([[B92]],
    # [[Location Trait Chips]]). A trait with no entry is auto-stacked.
    trait_positions: dict = Field(default_factory=dict)
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
    # The **highest die face that counts as a hitch** on this entity's rolls.
    # ``1`` (the default) is the base rule — a 1 hitches. ``2`` is a rule that
    # widens the range ("both 1s and 2s count as hitches"), which is the commonest
    # non-cost mechanic in the written SFX: MHR *Growing Dread*, ToX *Dread*,
    # TorchLite *Sunlight Sensitivity*, Cortex Lite *Violent Escalation*, Xine One
    # *Finite Energies* ([[B231]]). Set by a ``modify_hitch_threshold`` effect and
    # reverted by a duration or a cancelled activation.
    #
    # A **botch** is unaffected: it stays "every die shows 1". Widening the range
    # makes 2s *buyable* (and so un-keepable in the total), not botching — see
    # ``dice_resolver._is_botch``.
    hitch_threshold: int = 1
    sfx_ids: list[str] = Field(default_factory=list)  # SFX owned directly by this entity
    scheduled_events: list["ScheduledEvent"] = Field(default_factory=list)  # pending timed reverts
    # Universe — per-entity-type LoRA configuration
    lora_config: Optional[dict] = None  # {"CHARACTER": ["lora1"], "LOCATION": []}
    # Universe — free-text style steering appended to every prompt generated here
    prompt_steering: str = ""
    # Location image prompts — also describe the ancestor chain ("located in …").
    # Useful for exteriors and landscapes, usually noise for interiors, so it is
    # per-location and off by default. Sub-locations ("zones") are always
    # included and are not gated by this.
    prompt_include_ancestors: bool = False
    # Universe — the universe's look: accent, surfaces, borders and type, as
    # semantic knob groups ("dark"/"light") plus "font"/"radius". Applied by the
    # frontend as `:root` custom-property overrides while that universe is in
    # play ([[UI-UX Design#Theming]]). The shape and two worked examples live in
    # `db/universe_palettes.py`; a knob outside that vocabulary does nothing.
    palette: Optional[dict] = None
    # Life path tracking — **per body** ([[B271]]).
    #
    # A term is served by a body, in that body's universe: it grants its traits,
    # makes its membership edge and musters. So both the checkpoint and the
    # memberships it produces are keyed by the projection living them, and a
    # character mid-term in one universe is *not* mid-term in another. Before
    # this, one checkpoint sat on the entity and followed the character into every
    # body — you could advance a Three Realms term while playing an Earth
    # projection, and the executor, which never checked a universe, would apply
    # its effects there.
    life_paths: list["Enrollment"] = Field(default_factory=list)  # memberships (body + faction + path)
    active_universes: list[str] = Field(default_factory=list)  # faction-only: where active
    suitable_life_path_ids: list[str] = Field(default_factory=list)  # faction-only: offered paths
    discovered_life_paths: list[str] = Field(default_factory=list)  # _keys of discovered paths
    #: projection id → the term that body is part-way through. Keyed rather than a
    #: single value because a character has one body per universe.
    pending_terms: dict[str, "PendingTerm"] = Field(default_factory=dict)
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
