"""Effects action registry — metadata for every effect action the system supports.

This is the single source of truth for:
  - Available effect actions (label, description, category)
  - Per-action field requirements (what inputs does the UI need?)
  - Valid timings (which EffectTiming values make sense for this action?)
  - Implicit defaults (what fields can the UI auto-fill and hide?)

The frontend fetches this via GraphQL to render phased effect-edit forms.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ── Registry Entry Types ──────────────────────────────

@dataclass
class EffectFieldDef:
    """A single input field needed by an effect action."""
    name: str              # e.g. "result", "target", "amount"
    label: str             # e.g. "Die Rating", "Target Trait"
    field_type: str        # "die_select" | "text" | "number" | "select"
    required: bool = True
    default: str | None = None
    options: list[str] | None = None   # for select / die_select


@dataclass
class EffectActionMeta:
    """Metadata for one effect action the editor can create."""
    action_id: str              # unique key, e.g. "play_as_rating"
    label: str                  # "Play as Rating"
    description: str            # tooltip / help text
    category: str               # "cost" | "benefit" | "either" (UI hint)
    effect_type: str            # maps to Effect.type
    effect_action: str          # maps to Effect.action
    valid_timings: list[str] = field(default_factory=lambda: [
        "IMMEDIATE", "END_OF_BEAT", "END_OF_SCENE", "END_OF_SESSION",
    ])
    fields: list[EffectFieldDef] = field(default_factory=list)
    context_fields: list[EffectFieldDef] = field(default_factory=list)
    implicit_target: str | None = None   # if always the same, hide field
    implicit_result: str | None = None   # if always the same, hide field
    implicit_timing: str | None = None   # if only one valid timing, hide field
    requires_choice: bool = False        # target must be resolved at runtime
    target_kind: str | None = None       # trait | entity | life_path | ...
    supports_duration: bool = False      # UI shows a duration/timers builder
    supports_polarity: bool = False      # UI shows a negative (complication) toggle
    inverse: tuple[str, str] | None = None  # (type, action) to undo this effect
    inverse_captures_prior: bool = False    # revert needs the pre-apply value


# Reusable context-field definition: trait-modifying effects may target a
# character↔faction relationship edge instead of the entity (see
# effects_applier._trait_owner).
_RELATIONSHIP_CONTEXT_FIELD = EffectFieldDef(
    name="relationship",
    label="Faction (relationship)",
    field_type="text",
    required=False,
)


# ── The Registry ──────────────────────────────────────

EFFECT_ACTION_REGISTRY: list[EffectActionMeta] = [
    # ── Dice Pool (modify_roll) ───────────────────────
    EffectActionMeta(
        action_id="play_as_rating",
        label="Play as Rating",
        description="Use a trait at a specific die size instead of its normal rating for this roll",
        category="cost",
        effect_type="modify_roll",
        effect_action="play_as_rating",
        valid_timings=["IMMEDIATE"],
        fields=[
            EffectFieldDef(name="result", label="Die Rating", field_type="die_select",
                          required=True, options=["d4", "d6", "d8", "d10", "d12"]),
        ],
        implicit_target="{source_trait}",
    ),
    EffectActionMeta(
        action_id="step_up_die",
        label="Step Up Die",
        description="Increase a die in the pool by one step (d6→d8)",
        category="benefit",
        effect_type="modify_roll",
        effect_action="step_up_die",
        valid_timings=["IMMEDIATE"],
        fields=[
            EffectFieldDef(name="target", label="Target", field_type="text",
                          required=True, default="highest_trait_die"),
        ],
    ),
    EffectActionMeta(
        action_id="step_down_die",
        label="Step Down Die",
        description="Decrease a die in the pool by one step (d8→d6)",
        category="cost",
        effect_type="modify_roll",
        effect_action="step_down_die",
        valid_timings=["IMMEDIATE"],
        fields=[
            EffectFieldDef(name="target", label="Target", field_type="text",
                          required=True, default="highest_trait_die"),
        ],
    ),
    EffectActionMeta(
        action_id="double_die",
        label="Double Die",
        description="Add a second copy of a die to the pool",
        category="benefit",
        effect_type="modify_roll",
        effect_action="double_die",
        valid_timings=["IMMEDIATE"],
        fields=[
            EffectFieldDef(name="target", label="Target Die", field_type="text",
                          required=True),
        ],
    ),
    EffectActionMeta(
        action_id="reroll_die",
        label="Reroll Die",
        description="Reroll a single die and keep the new result",
        category="benefit",
        effect_type="modify_roll",
        effect_action="reroll_die",
        valid_timings=["IMMEDIATE"],
        fields=[
            EffectFieldDef(name="target", label="Target", field_type="text",
                          required=True, default="the_hitch_die"),
        ],
    ),
    EffectActionMeta(
        action_id="add_die",
        label="Add Die",
        description="Add a new die to the pool at the specified size",
        category="benefit",
        effect_type="modify_roll",
        effect_action="add_die",
        valid_timings=["IMMEDIATE"],
        fields=[
            EffectFieldDef(name="result", label="Die Size", field_type="die_select",
                          required=True, options=["d4", "d6", "d8", "d10", "d12"]),
            EffectFieldDef(name="target", label="Source", field_type="text",
                          required=False, default="sfx"),
        ],
    ),
    EffectActionMeta(
        action_id="remove_die",
        label="Remove Die",
        description="Remove a die from the pool",
        category="cost",
        effect_type="modify_roll",
        effect_action="remove_die",
        valid_timings=["IMMEDIATE"],
        fields=[
            EffectFieldDef(name="target", label="Target Die", field_type="text",
                          required=True),
        ],
    ),
    EffectActionMeta(
        action_id="split_die",
        label="Split Die",
        description="Split a die into two smaller dice, gaining an extra effect die option",
        category="benefit",
        effect_type="modify_roll",
        effect_action="split_die",
        valid_timings=["IMMEDIATE"],
        fields=[
            EffectFieldDef(name="target", label="Source Trait", field_type="text",
                          required=True, default="{source_trait}"),
        ],
    ),

    # ── Outcome (modify_outcome) ───────────────────────
    EffectActionMeta(
        action_id="step_up_effect",
        label="Step Up Effect",
        description="Increase the effect die by one step",
        category="benefit",
        effect_type="modify_outcome",
        effect_action="step_up_effect",
        valid_timings=["IMMEDIATE"],
    ),
    EffectActionMeta(
        action_id="step_up_outcome",
        label="Step Up Outcome",
        description="Bump the outcome tier by one level",
        category="benefit",
        effect_type="modify_outcome",
        effect_action="step_up_outcome",
        valid_timings=["IMMEDIATE"],
    ),
    EffectActionMeta(
        action_id="negate_complication",
        label="Negate Complication",
        description="Cancel one triggering complication",
        category="benefit",
        effect_type="modify_outcome",
        effect_action="negate_complication",
        valid_timings=["IMMEDIATE"],
    ),
    EffectActionMeta(
        action_id="convert_complication",
        label="Convert Complication",
        description="Turn a complication into a bonus die (adds d6 to a future roll)",
        category="benefit",
        effect_type="modify_outcome",
        effect_action="convert_complication",
        valid_timings=["IMMEDIATE"],
        fields=[
            EffectFieldDef(name="target", label="What to Convert", field_type="text",
                          required=True, default="botch_to_hitch"),
        ],
    ),
    EffectActionMeta(
        action_id="reroll_highest",
        label="Reroll Highest",
        description="Reroll the highest die and keep the new result",
        category="either",
        effect_type="modify_outcome",
        effect_action="reroll_highest",
        valid_timings=["IMMEDIATE"],
    ),

    # ── Trait Modification ─────────────────────────────
    EffectActionMeta(
        action_id="step_up_trait",
        label="Step Up Trait",
        description="Increase a trait die by one step permanently (or for duration)",
        category="benefit",
        effect_type="modify_trait",
        effect_action="step_up",
        valid_timings=["IMMEDIATE", "END_OF_BEAT", "END_OF_SCENE", "END_OF_SESSION", "AFTER_BEATS"],
        fields=[
            EffectFieldDef(name="target", label="Target Trait", field_type="text",
                          required=True, default="primary"),
        ],
        context_fields=[_RELATIONSHIP_CONTEXT_FIELD],
        supports_duration=True,
        inverse=("modify_trait", "step_down"),
        target_kind="trait",
    ),
    EffectActionMeta(
        action_id="step_down_trait",
        label="Step Down Trait",
        description="Decrease a trait die by one step",
        category="cost",
        effect_type="modify_trait",
        effect_action="step_down",
        valid_timings=["IMMEDIATE", "END_OF_BEAT", "END_OF_SCENE", "END_OF_SESSION", "AFTER_BEATS"],
        fields=[
            EffectFieldDef(name="target", label="Target Trait", field_type="text",
                          required=True, default="primary"),
            EffectFieldDef(name="result", label="Deferral", field_type="text",
                          required=False, default="after_resolution"),
        ],
        context_fields=[_RELATIONSHIP_CONTEXT_FIELD],
        supports_duration=True,
        inverse=("modify_trait", "step_up"),
        target_kind="trait",
    ),
    EffectActionMeta(
        action_id="set_trait",
        label="Set Trait Rating",
        description="Set a trait to a specific die value",
        category="either",
        effect_type="modify_trait",
        effect_action="set",
        valid_timings=["IMMEDIATE", "END_OF_BEAT", "END_OF_SCENE", "END_OF_SESSION"],
        fields=[
            EffectFieldDef(name="target", label="Target Trait", field_type="text",
                          required=True),
            EffectFieldDef(name="result", label="Die Rating", field_type="die_select",
                          required=True, options=["d4", "d6", "d8", "d10", "d12"]),
        ],
        context_fields=[_RELATIONSHIP_CONTEXT_FIELD],
        supports_duration=True,
        inverse=("modify_trait", "set"),
        inverse_captures_prior=True,
        target_kind="trait",
    ),

    # ── Razmerit ───────────────────────────────────────
    EffectActionMeta(
        action_id="earn_razmerit",
        label="Earn Razmerit",
        description="Gain razmerit from the system pool",
        category="benefit",
        effect_type="transfer_razmerit",
        effect_action="earn",
        fields=[
            EffectFieldDef(name="result", label="Amount", field_type="number",
                          required=True, default="1"),
        ],
        implicit_target="self",
    ),
    EffectActionMeta(
        action_id="spend_razmerit",
        label="Spend Razmerit",
        description="Pay razmerit as an activation or ongoing cost",
        category="cost",
        effect_type="transfer_razmerit",
        effect_action="spend",
        fields=[
            EffectFieldDef(name="result", label="Amount", field_type="number",
                          required=True, default="1"),
        ],
        implicit_target="self",
    ),
    EffectActionMeta(
        action_id="transfer_razmerit",
        label="Transfer Razmerit",
        description="Move razmerit from one entity to another",
        category="either",
        effect_type="transfer_razmerit",
        effect_action="transfer",
        fields=[
            EffectFieldDef(name="result", label="Amount", field_type="number",
                          required=True, default="1"),
            EffectFieldDef(name="target", label="Target Entity", field_type="text",
                          required=True),
        ],
    ),

    # ── Entity Creation ────────────────────────────────
    EffectActionMeta(
        action_id="create_asset",
        label="Create Asset",
        description="Create a temporary asset entity (lasts for the scene)",
        category="benefit",
        effect_type="create_entity",
        effect_action="create_asset",
        valid_timings=["IMMEDIATE"],
        fields=[
            EffectFieldDef(name="target", label="Asset Name", field_type="text",
                          required=True, default="anchor_point"),
        ],
        supports_duration=True,
        inverse=("entity", "delete_entity"),
    ),

    # ── Attunement ─────────────────────────────────────
    EffectActionMeta(
        action_id="attune",
        label="Attune",
        description="Add a universe to an entity's effective universes until a timing expires. Context scope 'self' (entity) or 'domain' (location subtree).",
        category="benefit",
        effect_type="attune",
        effect_action="enable",
        valid_timings=["IMMEDIATE"],
        fields=[
            EffectFieldDef(name="result", label="Target Universe", field_type="select",
                          required=True, options=["three_realms", "earth"]),
            EffectFieldDef(name="target", label="Target Entity", field_type="text",
                          required=False, default="wielder"),
        ],
        supports_duration=True,
        inverse=("attune", "disable"),
    ),

    # ── Travel / Transversal ───────────────────────────
    EffectActionMeta(
        action_id="travel",
        label="Travel",
        description="Move an entity across a universal boundary (inapposite relocates the body; consciousness transfers the mind)",
        category="benefit",
        effect_type="travel",
        effect_action="move",
        valid_timings=["IMMEDIATE"],
        fields=[
            EffectFieldDef(name="target", label="Target Entity", field_type="text",
                          required=False, default="self"),
            EffectFieldDef(name="result", label="Target Location", field_type="text",
                          required=True),
        ],
        context_fields=[
            EffectFieldDef(name="transversal_type", label="Transversal Type",
                          field_type="select", required=False, default="inapposite",
                          options=["inapposite", "consciousness"]),
        ],
    ),

    # ── Trait gain / complications ─────────────────────
    EffectActionMeta(
        action_id="gain_trait",
        label="Gain Trait",
        description="Add a new trait at a die rating (no-op if already present)",
        category="benefit",
        effect_type="modify_trait",
        effect_action="gain",
        valid_timings=["IMMEDIATE", "END_OF_BEAT", "END_OF_SCENE", "END_OF_SESSION"],
        fields=[
            EffectFieldDef(name="target", label="Trait", field_type="text", required=True),
            EffectFieldDef(name="result", label="Die Rating", field_type="die_select",
                          required=True, options=["d4", "d6", "d8", "d10", "d12"]),
        ],
        context_fields=[_RELATIONSHIP_CONTEXT_FIELD],
        supports_duration=True,
        inverse=("modify_trait", "remove"),
        target_kind="trait",
    ),
    EffectActionMeta(
        action_id="gain_or_step_up_trait",
        label="Gain or Step Up Trait",
        description="Create the trait at the rating if absent, otherwise step it up",
        category="benefit",
        effect_type="modify_trait",
        effect_action="gain_or_step_up",
        valid_timings=["IMMEDIATE", "END_OF_BEAT", "END_OF_SCENE", "END_OF_SESSION"],
        fields=[
            EffectFieldDef(name="target", label="Trait", field_type="text", required=True),
            EffectFieldDef(name="result", label="Create At", field_type="die_select",
                          required=True, options=["d4", "d6", "d8", "d10", "d12"]),
        ],
        context_fields=[_RELATIONSHIP_CONTEXT_FIELD],
        supports_duration=True,
        target_kind="trait",
    ),
    EffectActionMeta(
        action_id="gain_complication",
        label="Gain Complication",
        description="Add a negative complication trait at a die rating",
        category="cost",
        effect_type="modify_trait",
        effect_action="gain_complication",
        valid_timings=["IMMEDIATE", "END_OF_BEAT", "END_OF_SCENE", "END_OF_SESSION"],
        fields=[
            EffectFieldDef(name="target", label="Complication Trait", field_type="text", required=True),
            EffectFieldDef(name="result", label="Die Rating", field_type="die_select",
                          required=True, options=["d4", "d6", "d8", "d10", "d12"]),
        ],
        context_fields=[_RELATIONSHIP_CONTEXT_FIELD],
        supports_duration=True,
        inverse=("modify_trait", "remove"),
        target_kind="trait",
    ),
    EffectActionMeta(
        action_id="gain_or_step_up_complication",
        label="Gain or Step Up Complication",
        description="Create the complication at the rating if absent, otherwise step it up",
        category="cost",
        effect_type="modify_trait",
        effect_action="gain_or_step_up_complication",
        valid_timings=["IMMEDIATE", "END_OF_BEAT", "END_OF_SCENE", "END_OF_SESSION"],
        fields=[
            EffectFieldDef(name="target", label="Complication Trait", field_type="text", required=True),
            EffectFieldDef(name="result", label="Create At", field_type="die_select",
                          required=True, options=["d4", "d6", "d8", "d10", "d12"]),
        ],
        context_fields=[_RELATIONSHIP_CONTEXT_FIELD],
        supports_duration=True,
        target_kind="trait",
    ),
    EffectActionMeta(
        action_id="cortex_gain_trait",
        label="Cortex Gain Trait",
        description="Create the trait at the effect die if absent; if present, jump to the effect die when higher, else step up one step",
        category="either",
        effect_type="modify_trait",
        effect_action="cortex_gain",
        valid_timings=["IMMEDIATE", "END_OF_BEAT", "END_OF_SCENE", "END_OF_SESSION"],
        fields=[
            EffectFieldDef(name="target", label="Trait", field_type="text", required=True),
            EffectFieldDef(name="result", label="Die Rating", field_type="die_select",
                          required=True, options=["d4", "d6", "d8", "d10", "d12"]),
        ],
        context_fields=[_RELATIONSHIP_CONTEXT_FIELD],
        target_kind="trait",
        supports_polarity=True,
    ),

    # ── Rank and life-path flow ────────────────────────
    EffectActionMeta(
        action_id="discover_life_path",
        label="Discover Life Path",
        description="Add a life path to the entity's discovered paths",
        category="benefit",
        effect_type="life_path",
        effect_action="discover",
        valid_timings=["IMMEDIATE"],
        fields=[
            EffectFieldDef(name="target", label="Life Path", field_type="text", required=True),
        ],
        target_kind="life_path",
    ),
    EffectActionMeta(
        action_id="next_step",
        label="Next Step",
        description="Advance the term to a roll table (target = table id, empty to continue)",
        category="either",
        effect_type="life_path",
        effect_action="next_step",
        valid_timings=["IMMEDIATE"],
        fields=[
            EffectFieldDef(name="target", label="Next Table", field_type="text", required=False),
        ],
        context_fields=[
            EffectFieldDef(name="return_to", label="Return To", field_type="text", required=False),
        ],
        target_kind="roll_table",
    ),
    EffectActionMeta(
        action_id="draft_life_path",
        label="Draft Into Life Path",
        description="Draft the entity into another life path",
        category="either",
        effect_type="life_path",
        effect_action="draft",
        valid_timings=["IMMEDIATE"],
        fields=[
            EffectFieldDef(name="target", label="Life Path", field_type="text", required=True),
        ],
        target_kind="life_path",
    ),
    EffectActionMeta(
        action_id="force_muster",
        label="Force Muster Out",
        description="Force the entity out of the current life path (dishonorable)",
        category="cost",
        effect_type="life_path",
        effect_action="force_muster",
        valid_timings=["IMMEDIATE"],
        fields=[],
    ),
    EffectActionMeta(
        action_id="muster",
        label="Muster Out",
        description="End the current life path term on respectful terms",
        category="either",
        effect_type="life_path",
        effect_action="muster",
        valid_timings=["IMMEDIATE"],
        fields=[],
    ),
    EffectActionMeta(
        action_id="enroll_life_path",
        label="Enroll In Life Path",
        description="Record the entity's membership in the current faction path",
        category="either",
        effect_type="life_path",
        effect_action="enroll",
        valid_timings=["IMMEDIATE"],
        fields=[],
    ),

    # ── Relationships ──────────────────────────────────
    EffectActionMeta(
        action_id="create_relationship",
        label="Create Relationship",
        description="Create a directional relationship edge to another entity",
        category="either",
        effect_type="relationship",
        effect_action="create",
        valid_timings=["IMMEDIATE", "END_OF_BEAT", "END_OF_SCENE", "END_OF_SESSION"],
        fields=[
            EffectFieldDef(name="target", label="Target Entity", field_type="text", required=True),
            EffectFieldDef(name="result", label="Relationship Type", field_type="text", required=True),
        ],
        context_fields=[
            EffectFieldDef(name="description", label="Description", field_type="text", required=False),
        ],
        target_kind="entity",
    ),
    EffectActionMeta(
        action_id="entity_targeting_ban",
        label="Targeting Ban",
        description="Prevent the entity from targeting another entity (e.g. re-challenging after giving in)",
        category="cost",
        effect_type="entity",
        effect_action="targeting_ban",
        valid_timings=["IMMEDIATE"],
        fields=[
            EffectFieldDef(name="target", label="Target Entity", field_type="text", required=False),
        ],
        target_kind="entity",
        supports_duration=True,
        inverse=("entity", "remove_targeting_ban"),
    ),
]

# ── Lookup helpers ────────────────────────────────────

def get_action_meta(action_id: str) -> EffectActionMeta | None:
    """Look up a single action by its id."""
    for meta in EFFECT_ACTION_REGISTRY:
        if meta.action_id == action_id:
            return meta
    return None


def get_actions_by_category(category: str) -> list[EffectActionMeta]:
    """Return all actions matching a category ('cost', 'benefit', 'either')."""
    return [m for m in EFFECT_ACTION_REGISTRY if m.category == category]


def get_inverse(effect_type: str, effect_action: str) -> tuple[tuple[str, str] | None, bool]:
    """Return ``(inverse, captures_prior)`` for an effect (type, action)."""
    for meta in EFFECT_ACTION_REGISTRY:
        if meta.effect_type == effect_type and meta.effect_action == effect_action:
            return (meta.inverse, meta.inverse_captures_prior)
    return (None, False)
