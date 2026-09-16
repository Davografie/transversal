"""Dice Pool (modify_roll) + Outcome (modify_outcome) — action definitions split out of ``effects_registry.py``."""

from transversal.services.effects_registry.action_types import (
    EffectActionMeta,
    EffectFieldDef,
    RefDef,
)

#: How many steps along the die ladder a step-up/step-down moves (d8 + 2 → d12).
_STEPS_FIELD = EffectFieldDef(
    name="count", label="Steps", field_type="number", required=False, default="1",
    description="How many steps along the die ladder, clamped at d4/d12 (2 steps: d8 → d12).",
)

#: How many extra dice a double/split adds. `double 2` on a d8 gives 3d8; `split 2`
#: gives 3d6 — one extra die for each, the difference being the size of the results.
_EXTRA_DICE_FIELD = EffectFieldDef(
    name="count", label="Extra dice", field_type="number", required=False, default="1",
    description="How many extra dice (2: a d8 becomes 3 dice).",
)


ACTIONS: list[EffectActionMeta] = [
    # ── Change a Die ──────────────────────────────────
    # One family, one question: *which die, and what happens to it*. The path
    # answers the first half — a die in the assembled pool, or a die of a trait
    # instance's rating — and where it lands answers the second: a pool is rebuilt
    # every roll, so the change is transient; a rating is a fact about the
    # character, so the change persists and a duration is offered (see
    # `duration_elements` below). A die is not a *picker* kind, so these actions
    # declare no `target_kind`; the path is how a die is named.
    EffectActionMeta(
        action_id="set_die",
        label="Set Die",
        description=(
            "Set a die to a specific size. On a die in the pool this lasts the roll; "
            "on a die of a trait's rating it changes the trait"
        ),
        category="either",
        effect_type="modify_roll",
        effect_action="set_die",
        valid_timings=["IMMEDIATE", "END_OF_BEAT", "END_OF_SCENE", "END_OF_SESSION"],
        fields=[
            EffectFieldDef(name="target", label="Target", field_type="text",
                          required=True, default="highest_trait_die"),
            EffectFieldDef(name="result", label="Die Rating", field_type="die_select",
                          required=True, options=["d4", "d6", "d8", "d10", "d12"]),
        ],
        path_element=("die", "rating_die"),
        supports_duration=True,
        duration_elements=("rating_die",),
        inverse=("modify_roll", "restore_die"),
        inverse_captures_prior=True,
    ),
    EffectActionMeta(
        action_id="step_up_die",
        label="Step Up Die",
        description=(
            "Increase a die by N steps (d8 + 2 → d12, clamped at d12). On a die in "
            "the pool this lasts the roll; on a die of a trait's rating it changes "
            "the trait"
        ),
        category="benefit",
        effect_type="modify_roll",
        effect_action="step_up_die",
        valid_timings=["IMMEDIATE", "END_OF_BEAT", "END_OF_SCENE", "END_OF_SESSION"],
        fields=[
            EffectFieldDef(name="target", label="Target", field_type="text",
                          required=True, default="highest_trait_die"),
        ],
        # A `count` in `fields` would be dropped on save — only target/entity/result
        # persist from there; everything else is a context field, which is also
        # where the applier reads it from.
        context_fields=[_STEPS_FIELD],
        path_element=("die", "rating_die"),
        supports_duration=True,
        duration_elements=("rating_die",),
        inverse=("modify_roll", "restore_die"),
        inverse_captures_prior=True,
    ),
    EffectActionMeta(
        action_id="step_down_die",
        label="Step Down Die",
        description=(
            "Decrease a die by N steps (d8 − 2 → d4); a d4 stepped down is removed. "
            "On a die in the pool this lasts the roll; on a die of a trait's rating "
            "it changes the trait"
        ),
        category="cost",
        effect_type="modify_roll",
        effect_action="step_down_die",
        valid_timings=["IMMEDIATE", "END_OF_BEAT", "END_OF_SCENE", "END_OF_SESSION"],
        fields=[
            EffectFieldDef(name="target", label="Target", field_type="text",
                          required=True, default="highest_trait_die"),
        ],
        # A `count` in `fields` would be dropped on save — only target/entity/result
        # persist from there; everything else is a context field, which is also
        # where the applier reads it from.
        context_fields=[_STEPS_FIELD],
        path_element=("die", "rating_die"),
        supports_duration=True,
        duration_elements=("rating_die",),
        inverse=("modify_roll", "restore_die"),
        inverse_captures_prior=True,
    ),
    EffectActionMeta(
        action_id="double_die",
        label="Double Die",
        description=(
            "Add N copies of a die at the same size (d8 + 2 → 3d8). On a die in the "
            "pool this lasts the roll; on a die of a trait's rating it changes the "
            "trait"
        ),
        category="benefit",
        effect_type="modify_roll",
        effect_action="double_die",
        valid_timings=["IMMEDIATE", "END_OF_BEAT", "END_OF_SCENE", "END_OF_SESSION"],
        fields=[
            EffectFieldDef(name="target", label="Target", field_type="text", required=True),
        ],
        context_fields=[_EXTRA_DICE_FIELD],
        path_element=("die", "rating_die"),
        supports_duration=True,
        duration_elements=("rating_die",),
        inverse=("modify_roll", "restore_die"),
        inverse_captures_prior=True,
    ),
    EffectActionMeta(
        action_id="split_die",
        label="Split Die",
        description=(
            "Split a die into N+1 dice one step smaller (d8 + 2 → 3d6), gaining "
            "extra dice to choose from. On a die in the pool this lasts the roll; on "
            "a die of a trait's rating it changes the trait"
        ),
        category="benefit",
        effect_type="modify_roll",
        effect_action="split_die",
        valid_timings=["IMMEDIATE", "END_OF_BEAT", "END_OF_SCENE", "END_OF_SESSION"],
        fields=[
            EffectFieldDef(name="target", label="Target", field_type="text", required=True),
        ],
        context_fields=[_EXTRA_DICE_FIELD],
        path_element=("die", "rating_die"),
        supports_duration=True,
        duration_elements=("rating_die",),
        inverse=("modify_roll", "restore_die"),
        inverse_captures_prior=True,
    ),
    EffectActionMeta(
        action_id="remove_die",
        label="Remove Die",
        description=(
            "Remove a die. On a die in the pool this lasts the roll; on a die of a "
            "trait's rating the trait loses that die — a rating with no dice left is "
            "still a trait"
        ),
        category="cost",
        effect_type="modify_roll",
        effect_action="remove_die",
        valid_timings=["IMMEDIATE", "END_OF_BEAT", "END_OF_SCENE", "END_OF_SESSION"],
        fields=[
            EffectFieldDef(name="target", label="Target", field_type="text", required=True),
        ],
        path_element=("die", "rating_die"),
        supports_duration=True,
        duration_elements=("rating_die",),
        inverse=("modify_roll", "restore_die"),
        inverse_captures_prior=True,
    ),
    EffectActionMeta(
        action_id="reroll_die",
        label="Reroll Die",
        description="Reroll a die in the pool and keep the new result",
        category="benefit",
        effect_type="modify_roll",
        effect_action="reroll_die",
        valid_timings=["IMMEDIATE"],
        fields=[
            EffectFieldDef(name="target", label="Target", field_type="text",
                          required=True, default="the_hitch_die"),
        ],
        # A rating die has no result to reroll, so this one stays pool-only — the
        # destination set is what says so, rather than a runtime refusal.
        path_element=("die",),
    ),

    # ── Dice Pool ─────────────────────────────────────
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
        # The undo takes exactly these dice back out (the handler records which
        # ones it appended; see ``_apply_remove_added_dice``).
        inverse=("modify_pool", "remove_added_dice"),
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
        # The undo takes exactly the dice this put in back out (the handler records
        # which ones and where; see ``_apply_remove_added_dice``).
        inverse=("modify_pool", "remove_added_dice"),
    ),
    EffectActionMeta(
        action_id="roll_pool",
        label="Roll Dice Pool",
        description="Roll a target dice pool immediately (e.g. auto-roll the difficulty pool)",
        category="either",
        effect_type="modify_pool",
        effect_action="roll",
        valid_timings=["IMMEDIATE"],
        refs=[
            RefDef("pool", "Pool", "pool"),
        ],
    ),
    EffectActionMeta(
        action_id="resolve_pool",
        label="Resolve Dice Pool",
        description="Auto-resolve a target dice pool: roll it, pick the two highest as the total, and set the difficulty",
        category="either",
        effect_type="modify_pool",
        effect_action="resolve",
        valid_timings=["IMMEDIATE"],
        refs=[
            RefDef("pool", "Pool", "pool"),
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

]
