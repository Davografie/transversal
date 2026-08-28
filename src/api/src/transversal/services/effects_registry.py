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
class RefDef:
    """A named reference an effect action declares (the multi-target model).

    Each ref is a targeting-wizard selection the editor renders as its own
    picker/spec builder. ``element`` is the catalog element type the ref must
    resolve to (drives the picker + fire-time type-check).
    """
    name: str          # key into Effect.refs, e.g. "trait", "pool", "subject"
    label: str         # editor label, e.g. "Trait", "Destination pool"
    element: str       # target_catalog element type, e.g. "traitsetting", "pool"


@dataclass
class EffectActionMeta:
    """Metadata for one effect action the editor can create."""
    action_id: str              # unique key, e.g. "play_as_rating"
    label: str                  # "Play as Rating"
    description: str            # tooltip / help text
    category: str               # "cost" | "benefit" | "either" (UI hint)
    effect_type: str            # maps to Effect.type
    effect_action: str          # maps to Effect.action
    group: str = ""             # functional group for the editor dropdown (optgroup)
    valid_timings: list[str] = field(default_factory=lambda: [
        "IMMEDIATE", "END_OF_BEAT", "END_OF_SCENE", "END_OF_SESSION",
        "ON_ROLL", "ON_SET", "ON_RESULT",
        "ON_CONTEST_WIN", "ON_CONTEST_LOSS", "ON_SUCCESS", "ON_FAILURE",
    ])
    fields: list[EffectFieldDef] = field(default_factory=list)
    context_fields: list[EffectFieldDef] = field(default_factory=list)
    implicit_target: str | None = None   # if always the same, hide field
    implicit_result: str | None = None   # if always the same, hide field
    implicit_timing: str | None = None   # if only one valid timing, hide field
    requires_choice: bool = False        # target must be resolved at runtime
    target_kind: str | None = None       # trait | entity | life_path | ...
    refs: list[RefDef] = field(default_factory=list)  # named references (multi-target model)
    supports_duration: bool = False      # UI shows a duration/timers builder
    supports_polarity: bool = False      # UI shows a negative (complication) toggle
    supports_return_exit: bool = False   # UI offers a "{return:<name>}" target mode (shared tables)
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

# Step magnitude for step_up / step_down / gain_or_step_up.  Free text so it
# can hold either a literal number or a ``{variable}`` token.
_STEPS_CONTEXT_FIELD = EffectFieldDef(
    name="steps",
    label="Steps",
    field_type="text",
    required=False,
    default="1",
)

# Explicit subject entity for trait/razmerit effects (blank = the entity the
# effect is applied to).  Accepts a literal id, an entity_id ``{variable}``, or
# ``{choose_entity}`` / ``{random:entity}``.
_ENTITY_FIELD = EffectFieldDef(
    name="entity",
    label="Entity",
    field_type="entity",
    required=False,
)

# Inline trait-editor fields: authored per gained trait instance, so an SFX can
# stamp a specific distinction statement + notes (e.g. Crimson Scars).
_STATEMENT_CONTEXT_FIELD = EffectFieldDef(
    name="statement",
    label="Statement",
    field_type="text",
    required=False,
)
_NOTES_CONTEXT_FIELD = EffectFieldDef(
    name="notes",
    label="Notes",
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
        action_id="add_dice",
        label="Add Dice",
        description="Add dice to a target dice pool (the GM difficulty pool or an entity's pool)",
        category="benefit",
        effect_type="modify_pool",
        effect_action="add_dice",
        valid_timings=["IMMEDIATE"],
        fields=[
            EffectFieldDef(name="target", label="Pool", field_type="text", required=True),
        ],
        context_fields=[
            EffectFieldDef(name="dice", label="Dice", field_type="dice_array", required=True),
        ],
        target_kind="pool",
    ),
    EffectActionMeta(
        action_id="add_trait_rating_dice",
        label="Add Trait Rating Dice",
        description="Add a target trait instance's rating dice to a target dice pool",
        category="either",
        effect_type="modify_pool",
        effect_action="add_trait_rating",
        valid_timings=["IMMEDIATE"],
        refs=[
            RefDef("trait", "Trait", "traitsetting"),
            RefDef("pool", "Destination pool", "pool"),
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
    EffectActionMeta(
        action_id="increase_dice_limit",
        label="Increase Dice Limit",
        description="Increase how many dice can be kept as the total or effect die (e.g. +1 total die)",
        category="benefit",
        effect_type="modify_dice_limit",
        effect_action="increase",
        valid_timings=["IMMEDIATE", "END_OF_BEAT", "END_OF_SCENE", "END_OF_SESSION", "ON_ROLL", "ON_SET", "ON_RESULT"],
        fields=[
            EffectFieldDef(name="result", label="Amount", field_type="number",
                          required=True, default="1"),
        ],
        context_fields=[
            EffectFieldDef(name="limit", label="Limit", field_type="select",
                          required=True, default="total", options=["total", "effect"]),
        ],
        supports_duration=True,
        inverse=("modify_dice_limit", "decrease"),
    ),
    EffectActionMeta(
        action_id="decrease_dice_limit",
        label="Decrease Dice Limit",
        description="Decrease how many dice can be kept as the total or effect die (e.g. -1 total die)",
        category="cost",
        effect_type="modify_dice_limit",
        effect_action="decrease",
        valid_timings=["IMMEDIATE", "END_OF_BEAT", "END_OF_SCENE", "END_OF_SESSION", "ON_ROLL", "ON_SET", "ON_RESULT"],
        fields=[
            EffectFieldDef(name="result", label="Amount", field_type="number",
                          required=True, default="1"),
        ],
        context_fields=[
            EffectFieldDef(name="limit", label="Limit", field_type="select",
                          required=True, default="total", options=["total", "effect"]),
        ],
        supports_duration=True,
        inverse=("modify_dice_limit", "increase"),
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
        valid_timings=["IMMEDIATE", "END_OF_BEAT", "END_OF_SCENE", "END_OF_SESSION", "AFTER_BEATS", "ON_ROLL", "ON_SET", "ON_RESULT"],
        fields=[
            EffectFieldDef(name="target", label="Target Trait", field_type="text",
                          required=True, default="primary"),
            _ENTITY_FIELD,
        ],
        context_fields=[_RELATIONSHIP_CONTEXT_FIELD, _STEPS_CONTEXT_FIELD],
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
        valid_timings=["IMMEDIATE", "END_OF_BEAT", "END_OF_SCENE", "END_OF_SESSION", "AFTER_BEATS", "ON_ROLL", "ON_SET", "ON_RESULT"],
        fields=[
            EffectFieldDef(name="target", label="Target Trait", field_type="text",
                          required=True, default="primary"),
            _ENTITY_FIELD,
        ],
        context_fields=[_RELATIONSHIP_CONTEXT_FIELD, _STEPS_CONTEXT_FIELD],
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
        valid_timings=["IMMEDIATE", "END_OF_BEAT", "END_OF_SCENE", "END_OF_SESSION", "ON_ROLL", "ON_SET", "ON_RESULT"],
        fields=[
            EffectFieldDef(name="target", label="Target Trait", field_type="text",
                          required=True),
            _ENTITY_FIELD,
            EffectFieldDef(name="result", label="Die Rating", field_type="die_select",
                          required=True, options=["d4", "d6", "d8", "d10", "d12"]),
        ],
        context_fields=[_RELATIONSHIP_CONTEXT_FIELD],
        supports_duration=True,
        inverse=("modify_trait", "set"),
        inverse_captures_prior=True,
        target_kind="trait",
    ),
    EffectActionMeta(
        action_id="disable_trait",
        label="Disable Trait",
        description="Disable a trait so it contributes no dice (until re-enabled or the duration ends)",
        category="cost",
        effect_type="modify_trait",
        effect_action="disable",
        valid_timings=["IMMEDIATE", "END_OF_BEAT", "END_OF_SCENE", "END_OF_SESSION", "AFTER_BEATS", "ON_ROLL", "ON_SET", "ON_RESULT"],
        fields=[
            EffectFieldDef(name="target", label="Target Trait", field_type="text",
                          required=True, default="primary"),
            _ENTITY_FIELD,
        ],
        context_fields=[_RELATIONSHIP_CONTEXT_FIELD],
        supports_duration=True,
        inverse=("modify_trait", "enable"),
        target_kind="trait",
    ),
    EffectActionMeta(
        action_id="toggle_trait",
        label="Toggle Trait",
        description="Flip a trait between enabled and disabled",
        category="either",
        effect_type="modify_trait",
        effect_action="toggle",
        valid_timings=["IMMEDIATE", "END_OF_BEAT", "END_OF_SCENE", "END_OF_SESSION", "AFTER_BEATS", "ON_ROLL", "ON_SET", "ON_RESULT"],
        fields=[
            EffectFieldDef(name="target", label="Target Trait", field_type="text",
                          required=True, default="primary"),
            _ENTITY_FIELD,
        ],
        context_fields=[_RELATIONSHIP_CONTEXT_FIELD],
        supports_duration=True,
        inverse=("modify_trait", "toggle"),
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
            _ENTITY_FIELD,
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
            _ENTITY_FIELD,
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
        description="Create a temporary asset entity at a location (duration-scoped; deleted on revert)",
        category="benefit",
        effect_type="create_entity",
        effect_action="create_asset",
        valid_timings=["IMMEDIATE"],
        fields=[
            EffectFieldDef(name="target", label="Asset Name", field_type="text",
                          required=True, default="anchor_point"),
        ],
        context_fields=[
            EffectFieldDef(name="location", label="Location", field_type="text", required=False),
        ],
        supports_duration=True,
        inverse=("entity", "delete_entity"),
    ),
    EffectActionMeta(
        action_id="end_active_effect",
        label="End Active Effect",
        description="Cancel a running temporary effect (a pending timer) on the target",
        category="either",
        effect_type="entity",
        effect_action="cancel_scheduled_event",
        valid_timings=["IMMEDIATE"],
        fields=[
            _ENTITY_FIELD,
            EffectFieldDef(name="target", label="Active Effect", field_type="text", required=True),
        ],
        target_kind="scheduled_event",
        requires_choice=True,
    ),
    EffectActionMeta(
        action_id="create_projection",
        label="Temporary Projection (Disguise)",
        description="Create and activate a temporary alternate body in the current universe/location; reverts to the prior body on expiry",
        category="benefit",
        effect_type="projection",
        effect_action="create",
        valid_timings=["IMMEDIATE"],
        fields=[
            _ENTITY_FIELD,
            EffectFieldDef(name="target", label="Disguise Name", field_type="text", required=False, default="disguise"),
        ],
        supports_duration=True,
        inverse=("projection", "restore"),
        inverse_captures_prior=True,
    ),
    EffectActionMeta(
        action_id="set_traitset_limit",
        label="Set Trait-set Limit",
        description="Override how many traits this entity can hold in a trait set (set to a number)",
        category="either",
        effect_type="modify_traitset",
        effect_action="set_limit",
        valid_timings=["IMMEDIATE", "END_OF_BEAT", "END_OF_SCENE", "END_OF_SESSION", "ON_ROLL", "ON_SET", "ON_RESULT"],
        fields=[
            _ENTITY_FIELD,
            EffectFieldDef(name="target", label="Trait Set", field_type="text", required=True),
            EffectFieldDef(name="result", label="Limit", field_type="number", required=True, default="1"),
        ],
        supports_duration=True,
        inverse=("modify_traitset", "set_limit"),
        inverse_captures_prior=True,
        target_kind="traitset",
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
        target_kind="location",
        fields=[
            _ENTITY_FIELD,
            EffectFieldDef(name="target", label="Destination Location", field_type="text",
                          required=True, default=""),
        ],
        context_fields=[
            EffectFieldDef(name="transversal_type", label="Transversal Type",
                          field_type="select", required=False, default="inapposite",
                          options=["inapposite", "consciousness"]),
            EffectFieldDef(name="projection", label="Body", field_type="select",
                          required=False, default="{last_projection}",
                          options=["{last_projection}", "{new_projection}", "{random_projection}", "{choose_projection}"]),
        ],
    ),

    # ── Set Location ───────────────────────────────────
    EffectActionMeta(
        action_id="set_location",
        label="Set Location",
        description="Place the entity at a specific or random location (its active body relocates in sync)",
        category="either",
        effect_type="location",
        effect_action="set",
        valid_timings=["IMMEDIATE"],
        target_kind="location",
        fields=[
            _ENTITY_FIELD,
            EffectFieldDef(name="target", label="Destination Location", field_type="text",
                          required=True, default=""),
        ],
    ),

    # ── Trait gain / complications ─────────────────────
    EffectActionMeta(
        action_id="gain_trait",
        label="Gain Trait",
        description="Add a new trait at a die rating (no-op if already present)",
        category="either",
        effect_type="modify_trait",
        effect_action="gain",
        valid_timings=["IMMEDIATE", "END_OF_BEAT", "END_OF_SCENE", "END_OF_SESSION", "ON_ROLL", "ON_SET", "ON_RESULT"],
        fields=[
            EffectFieldDef(name="target", label="Trait", field_type="text", required=True),
            _ENTITY_FIELD,
            EffectFieldDef(name="result", label="Die Rating", field_type="die_select",
                          required=True, options=["d4", "d6", "d8", "d10", "d12"]),
        ],
        context_fields=[_RELATIONSHIP_CONTEXT_FIELD, _STATEMENT_CONTEXT_FIELD, _NOTES_CONTEXT_FIELD],
        supports_duration=True,
        supports_polarity=True,
        inverse=("modify_trait", "remove"),
        target_kind="trait",
    ),
    EffectActionMeta(
        action_id="gain_or_step_up_trait",
        label="Gain or Step Up Trait",
        description="Create the trait at the rating if absent, otherwise step it up",
        category="either",
        effect_type="modify_trait",
        effect_action="gain_or_step_up",
        valid_timings=["IMMEDIATE", "END_OF_BEAT", "END_OF_SCENE", "END_OF_SESSION", "ON_ROLL", "ON_SET", "ON_RESULT"],
        fields=[
            EffectFieldDef(name="target", label="Trait", field_type="text", required=True),
            _ENTITY_FIELD,
            EffectFieldDef(name="result", label="Create At", field_type="die_select",
                          required=True, options=["d4", "d6", "d8", "d10", "d12"]),
        ],
        context_fields=[_RELATIONSHIP_CONTEXT_FIELD, _STEPS_CONTEXT_FIELD, _STATEMENT_CONTEXT_FIELD, _NOTES_CONTEXT_FIELD],
        supports_duration=True,
        supports_polarity=True,
        target_kind="trait",
    ),
    EffectActionMeta(
        action_id="cortex_gain_trait",
        label="Cortex Gain Trait",
        description="Create the trait at the effect die if absent; if present, jump to the effect die when higher, else step up one step",
        category="either",
        effect_type="modify_trait",
        effect_action="cortex_gain",
        valid_timings=["IMMEDIATE", "END_OF_BEAT", "END_OF_SCENE", "END_OF_SESSION", "ON_ROLL", "ON_SET", "ON_RESULT"],
        fields=[
            EffectFieldDef(name="target", label="Trait", field_type="text", required=True),
            _ENTITY_FIELD,
            EffectFieldDef(name="result", label="Die Rating", field_type="die_select",
                          required=True, options=["d4", "d6", "d8", "d10", "d12"]),
        ],
        context_fields=[_RELATIONSHIP_CONTEXT_FIELD, _STATEMENT_CONTEXT_FIELD, _NOTES_CONTEXT_FIELD],
        target_kind="trait",
        supports_polarity=True,
    ),
    EffectActionMeta(
        action_id="reveal_trait",
        label="Reveal Trait (Learn)",
        description="Add the learner to a trait's known_to list so it stops showing as ??? on their sheet",
        category="benefit",
        effect_type="modify_trait",
        effect_action="reveal",
        valid_timings=["IMMEDIATE"],
        fields=[
            EffectFieldDef(name="target", label="Trait", field_type="text", required=True),
            _ENTITY_FIELD,
        ],
        context_fields=[
            EffectFieldDef(name="learner", label="Learner", field_type="entity",
                          required=False, default="self"),
        ],
        target_kind="trait",
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
            EffectFieldDef(name="return_to", label="Return To", field_type="return_map", required=False),
        ],
        target_kind="roll_table",
        supports_return_exit=True,
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
        valid_timings=["IMMEDIATE", "END_OF_BEAT", "END_OF_SCENE", "END_OF_SESSION", "ON_ROLL", "ON_SET", "ON_RESULT"],
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

# ── Functional grouping (editor optgroups) ─────────────
# Assigned after construction so each action's group lives beside the section
# it belongs to, without repeating the label in every constructor call.
_ACTION_GROUPS: dict[str, str] = {
    "play_as_rating": "Dice Pool", "step_up_die": "Dice Pool",
    "step_down_die": "Dice Pool", "double_die": "Dice Pool",
    "reroll_die": "Dice Pool", "add_dice": "Dice Pool",
    "add_trait_rating_dice": "Dice Pool",
    "remove_die": "Dice Pool", "split_die": "Dice Pool",
    "step_up_effect": "Outcome", "step_up_outcome": "Outcome",
    "increase_dice_limit": "Outcome", "decrease_dice_limit": "Outcome",
    "negate_complication": "Outcome", "convert_complication": "Outcome",
    "reroll_highest": "Outcome",
    "step_up_trait": "Trait", "step_down_trait": "Trait", "set_trait": "Trait",
    "disable_trait": "Trait", "toggle_trait": "Trait", "set_traitset_limit": "Trait",
    "gain_trait": "Trait", "gain_or_step_up_trait": "Trait",
    "cortex_gain_trait": "Trait", "reveal_trait": "Trait",
    "earn_razmerit": "Razmerit", "spend_razmerit": "Razmerit",
    "transfer_razmerit": "Razmerit",
    "create_asset": "Entity", "end_active_effect": "Entity", "create_projection": "Entity", "attune": "Attunement",
    "travel": "Travel", "set_location": "Travel",
    "discover_life_path": "Life Path", "next_step": "Life Path",
    "draft_life_path": "Life Path", "force_muster": "Life Path",
    "muster": "Life Path", "enroll_life_path": "Life Path",
    "create_relationship": "Relationship", "entity_targeting_ban": "Relationship",
}

for _m in EFFECT_ACTION_REGISTRY:
    _m.group = _ACTION_GROUPS.get(_m.action_id, "Other")


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
