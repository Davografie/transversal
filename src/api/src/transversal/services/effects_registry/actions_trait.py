"""Trait Modification — action definitions split out of ``effects_registry.py``."""

from transversal.services.effects_registry.action_types import (
    TRAIT_OWNER_ELEMENTS,
    EffectActionMeta,
    EffectFieldDef,
    RefDef,
    _ENTITY_FIELD,
    _STEPS_CONTEXT_FIELD,
)

#: The recipient of a copy/move. ``_ENTITY_FIELD`` says only "Entity"; for these
#: two actions the entity is specifically *where the trait ends up*, which is the
#: question the author is actually answering.
_RECIPIENT_FIELD = EffectFieldDef(
    name="entity",
    label="Give To",
    field_type="entity",
    required=False,
    hidden_when_ref="recipient",
    description="The entity that ends up holding the trait.",
)


ACTIONS: list[EffectActionMeta] = [
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
        context_fields=[_STEPS_CONTEXT_FIELD],
        supports_duration=True,
        inverse=("modify_trait", "step_down"),
        target_kind="trait",
        # Retired from the picker, but live roll-table content still uses it, and
        # the applier reads the *declaration* to know what an owner path may anchor
        # to — so the anchor set belongs here even though the verb is gone.
        owner_elements=TRAIT_OWNER_ELEMENTS,
        # Superseded by the change-die family, on a rating die.
        retired=True,
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
        context_fields=[_STEPS_CONTEXT_FIELD],
        supports_duration=True,
        inverse=("modify_trait", "step_up"),
        target_kind="trait",
        owner_elements=TRAIT_OWNER_ELEMENTS,
        # Superseded by the change-die family, on a rating die.
        retired=True,
    ),
    EffectActionMeta(
        action_id="set_trait_statement",
        label="Set Trait Statement",
        description=(
            "Rewrite the statement on an existing trait instance — what the trait "
            "*is* (a challenge redefined) rather than what it is rated. The prior "
            "statement is recorded, so a duration can put it back."
        ),
        category="either",
        effect_type="modify_trait",
        effect_action="set_statement",
        valid_timings=["IMMEDIATE", "END_OF_BEAT", "END_OF_SCENE", "END_OF_SESSION",
                       "AFTER_BEATS", "ON_ROLL", "ON_SET", "ON_RESULT"],
        fields=[
            EffectFieldDef(name="target", label="Trait", field_type="text", required=True),
            EffectFieldDef(name="result", label="New Statement", field_type="text",
                           required=True),
        ],
        supports_duration=True,
        path_element=("trait",),
        owner_elements=TRAIT_OWNER_ELEMENTS,
    ),
    EffectActionMeta(
        action_id="reduce_by_effect_die",
        label="Reduce by Effect Die",
        description=(
            "Compare the effect die to a die: remove it if the effect die is "
            "larger, else step it down. Targets a die in either home — a rating "
            "die (which persists) or a die in the pool (which lasts the roll)"
        ),
        category="benefit",
        effect_type="modify_trait",
        effect_action="reduce_by_effect",
        valid_timings=["IMMEDIATE", "ON_ROLL", "ON_SET", "ON_RESULT", "ON_SUCCESS", "ON_FAILURE"],
        # A targeting spec is the only way to name the die — there is no die
        # picker. `entity` and `relationship` are gone with the trait form: the
        # spec resolves the instance, so *whose* die and which anchor are already
        # in the reference, not questions the author answers separately.
        fields=[
            EffectFieldDef(name="target", label="Target", field_type="text", required=True),
        ],
        context_fields=[
            EffectFieldDef(name="effect_die", label="Effect Die", field_type="die_select", required=False, default="{effect_die}", options=["d4", "d6", "d8", "d10", "d12"]),
        ],
        path_element=("die", "rating_die"),
    ),
    EffectActionMeta(
        action_id="increase_by_effect_die",
        label="Increase by Effect Die",
        description=(
            "Compare the effect die to a die: set it to the effect die if the "
            "effect die is larger, else step it up. Targets a die in either home "
            "— a rating die (which persists) or a die in the pool (which lasts "
            "the roll)"
        ),
        category="benefit",
        effect_type="modify_trait",
        effect_action="increase_by_effect",
        valid_timings=["IMMEDIATE", "ON_ROLL", "ON_SET", "ON_RESULT", "ON_SUCCESS", "ON_FAILURE"],
        fields=[
            EffectFieldDef(name="target", label="Target", field_type="text", required=True),
        ],
        context_fields=[
            EffectFieldDef(name="effect_die", label="Effect Die", field_type="die_select", required=False, default="{effect_die}", options=["d4", "d6", "d8", "d10", "d12"]),
        ],
        path_element=("die", "rating_die"),
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
            EffectFieldDef(name="result", label="Die Rating", field_type="die_select",
                          required=True, options=["d4", "d6", "d8", "d10", "d12"]),
        ],
        supports_duration=True,
        inverse=("modify_trait", "set"),
        inverse_captures_prior=True,
        path_element=("traitsetting",),
    ),
    EffectActionMeta(
        action_id="add_rating_die",
        label="Add Die to Rating",
        description="Add a die to a trait's rating (any rating type: static, resource, or challenge)",
        category="benefit",
        effect_type="modify_trait",
        effect_action="add_die",
        valid_timings=["IMMEDIATE", "END_OF_BEAT", "END_OF_SCENE", "END_OF_SESSION", "ON_ROLL", "ON_SET", "ON_RESULT"],
        fields=[
            EffectFieldDef(name="target", label="Target Trait", field_type="text", required=True),
            EffectFieldDef(name="result", label="Die Rating", field_type="die_select",
                          required=True, options=["d4", "d6", "d8", "d10", "d12"]),
        ],
        supports_duration=True,
        inverse=("modify_trait", "remove_die"),
        path_element=("traitsetting",),
    ),
    EffectActionMeta(
        action_id="remove_rating_die",
        label="Remove Die from Rating",
        description="Remove a die from a trait's rating (any rating type)",
        category="cost",
        effect_type="modify_trait",
        effect_action="remove_die",
        valid_timings=["IMMEDIATE", "END_OF_BEAT", "END_OF_SCENE", "END_OF_SESSION", "ON_ROLL", "ON_SET", "ON_RESULT"],
        fields=[
            EffectFieldDef(name="target", label="Target Trait", field_type="text", required=True),
            _ENTITY_FIELD,
            EffectFieldDef(name="result", label="Die Rating", field_type="die_select",
                          required=True, options=["d4", "d6", "d8", "d10", "d12"]),
        ],
        context_fields=[],
        supports_duration=True,
        inverse=("modify_trait", "add_die"),
        target_kind="trait",
        # Superseded by the change-die family, on a rating die.
        retired=True,
    ),
    # ── Rating type (B100) ─────────────────────────────
    # What a trait instance *does* with its dice, which nothing could change after
    # the fact: a challenge filling toward its capacity could never become the
    # static technique it turns into once trained. The author names the value, so
    # the effect is idempotent, and the inverse captures the prior so a duration
    # restores it — the same shape as Set Trait Rating and Set Polarity.
    EffectActionMeta(
        action_id="set_trait_rating_type",
        label="Change Rating Type",
        description=(
            "Change what the trait instance's rating is: a static die, a spendable "
            "resource, a challenge filling toward its capacity, or empty"
        ),
        category="either",
        effect_type="modify_trait",
        effect_action="set_rating_type",
        valid_timings=["IMMEDIATE", "END_OF_BEAT", "END_OF_SCENE", "END_OF_SESSION",
                       "ON_ROLL", "ON_SET", "ON_RESULT"],
        fields=[
            EffectFieldDef(name="target", label="Target Trait", field_type="text",
                          required=True),
            # The value is the **result**, like Set Trait Rating's die: that is the
            # field a revert's captured prior arrives in, so a duration can restore
            # the old type without a second mechanism (the mistake `set_polarity`
            # made — see its handler).
            EffectFieldDef(name="result", label="Rating Type", field_type="select",
                          required=True, default="static",
                          options=["static", "resource", "challenge", "empty"]),
        ],
        supports_duration=True,
        inverse=("modify_trait", "set_rating_type"),
        inverse_captures_prior=True,
        path_element=("traitsetting",),
    ),
    EffectActionMeta(
        action_id="delete_trait",
        label="Remove Trait",
        description=(
            "Remove a trait instance from its owner — the trait burns away, is lost or "
            "destroyed (the same removal a temporary grant does when it expires)"
        ),
        category="cost",
        effect_type="modify_trait",
        effect_action="remove",
        valid_timings=["IMMEDIATE", "END_OF_BEAT", "END_OF_SCENE", "END_OF_SESSION"],
        fields=[
            EffectFieldDef(name="target", label="Target Trait", field_type="text", required=True),
        ],
        path_element=("traitsetting",),
    ),
    EffectActionMeta(
        action_id="copy_trait",
        output_element="traitsetting",
        label="Copy Trait",
        description=(
            "Give another entity a copy of a trait instance — its dice, rating type, "
            "polarity, statement and notes. Teaching hands over what you have, not "
            "the trait's default"
        ),
        category="either",
        effect_type="modify_trait",
        effect_action="copy",
        valid_timings=["IMMEDIATE"],
        fields=[_RECIPIENT_FIELD],
        # How the recipient came by it. The vocabulary is the data model's own
        # (`source_type`), minus the two the engine writes for other reasons
        # (a life-path term, an event). "gifted" is the neutral default: a copy
        # is a hand-over; "taught" is a deliberate lesson, and the teach
        # reduction table attaches to it as a separate SFX.
        context_fields=[
            EffectFieldDef(name="provenance", label="How They Got It",
                          field_type="select", required=False, default="gifted",
                          options=["gifted", "taught"]),
        ],
        refs=[RefDef("trait", "Trait to Copy", "traitsetting")],
        refs_first=True,
    ),
    EffectActionMeta(
        action_id="move_trait",
        output_element="traitsetting",
        label="Move Trait",
        description=(
            "Take a trait instance from another entity and give it to this one — "
            "stealing an asset, transferring a bond. The instance keeps its dice, "
            "grants and spent dice"
        ),
        category="cost",
        effect_type="modify_trait",
        effect_action="move",
        valid_timings=["IMMEDIATE"],
        fields=[_RECIPIENT_FIELD],
        refs=[RefDef("trait", "Trait to Move", "traitsetting")],
        refs_first=True,
    ),
    EffectActionMeta(
        action_id="change_trait",
        output_element="traitsetting",
        label="Change Trait",
        description=(
            "Point a trait instance at a different registry trait — the instance keeps "
            "its owner, dice, rating type, polarity, statement and grants, but it *is* "
            "the other trait now. 'Your blade' becomes 'a blade of fire'"
        ),
        category="either",
        effect_type="modify_trait",
        effect_action="change",
        valid_timings=["IMMEDIATE"],
        fields=[
            EffectFieldDef(name="target", label="Target Trait", field_type="text",
                          required=True, default=""),
        ],
        # The *definition* is a path of its own: the wizard offers one ending on a
        # registry trait, the engine resolves it, and the card reads it as the
        # thing the instance becomes.
        refs=[RefDef("trait", "Change To", "trait")],
        supports_duration=True,
        # The undo is *this action* pointed back at the prior definition, which the
        # handler captures on apply (the way `set` captures the prior rating) — so a
        # timed change is a timed revert, and an untimed one is a cancellable hold.
        inverse=("modify_trait", "change"),
        inverse_captures_prior=True,
        path_element=("traitsetting",),
    ),
    EffectActionMeta(
        action_id="invert_polarity",
        label="Invert Polarity",
        description=(
            "Flip a trait instance between complication and asset. The instance keeps "
            "its id, traitset and grants; only its polarity moves — pair it with "
            "*Change Trait* when it should also become a different definition"
        ),
        category="either",
        effect_type="modify_trait",
        effect_action="invert_polarity",
        valid_timings=["IMMEDIATE", "END_OF_BEAT", "END_OF_SCENE", "END_OF_SESSION", "AFTER_BEATS"],
        fields=[
            EffectFieldDef(name="target", label="Target", field_type="text", required=True),
        ],
        supports_duration=True,
        # A polarity has two values, so the inverse of a flip is the same flip.
        inverse=("modify_trait", "invert_polarity"),
        path_element=("traitsetting",),
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
        ],
        supports_duration=True,
        inverse=("modify_trait", "enable"),
        path_element=("traitsetting",),
    ),
    EffectActionMeta(
        action_id="enable_trait",
        label="Enable Trait",
        description=(
            "Bring a disabled trait back into play, so it contributes its dice again "
            "(the counterpart of Disable Trait; needed by the portent agenda)"
        ),
        category="benefit",
        effect_type="modify_trait",
        effect_action="enable",
        valid_timings=["IMMEDIATE", "END_OF_BEAT", "END_OF_SCENE", "END_OF_SESSION", "AFTER_BEATS", "ON_ROLL", "ON_SET", "ON_RESULT"],
        fields=[
            EffectFieldDef(name="target", label="Target Trait", field_type="text",
                          required=True, default="primary"),
        ],
        supports_duration=True,
        # The handler already existed as `disable`'s duration-revert and had no
        # action name of its own, so it could not be authored directly.
        inverse=("modify_trait", "disable"),
        path_element=("traitsetting",),
    ),
    EffectActionMeta(
        action_id="set_polarity",
        label="Set Polarity",
        description=(
            "Set a trait instance's polarity outright, rather than flipping it — "
            "the same change as Invert Polarity when the other value is known"
        ),
        category="either",
        effect_type="modify_trait",
        effect_action="set_polarity",
        valid_timings=["IMMEDIATE", "END_OF_BEAT", "END_OF_SCENE", "END_OF_SESSION", "AFTER_BEATS"],
        fields=[
            EffectFieldDef(name="target", label="Target", field_type="text", required=True),
        ],
        context_fields=[
            EffectFieldDef(name="polarity", label="Polarity", field_type="select",
                          required=True, default="positive", options=["positive", "negative"]),
        ],
        supports_duration=True,
        inverse=("modify_trait", "set_polarity"),
        inverse_captures_prior=True,
        path_element=("traitsetting",),
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
        ],
        supports_duration=True,
        inverse=("modify_trait", "toggle"),
        path_element=("traitsetting",),
    ),

]
