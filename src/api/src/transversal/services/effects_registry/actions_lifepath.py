"""Rank and life-path flow — action definitions split out of ``effects_registry.py``."""

from transversal.services.effects_registry.action_types import (
    EffectActionMeta,
    EffectFieldDef,
)


ACTIONS: list[EffectActionMeta] = [
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
            EffectFieldDef(name="target", label="Life Path", field_type="text", required=True, hidden_when_ref="life_path"),
        ],
        target_kind="life_path",
    ),
    EffectActionMeta(
        action_id="enter_life_path",
        label="Enter Life Path",
        description=(
            "Begin a term in a life path for the entity — the door the life-path "
            "wizard's own chooser opens. Writes the cursor, so a rule can drop a "
            "character straight into the path's first table; pair it with Show "
            "Life Path to put that table in front of the player, ready to roll"
        ),
        category="either",
        effect_type="life_path",
        effect_action="enter",
        valid_timings=["IMMEDIATE"],
        fields=[
            EffectFieldDef(name="target", label="Life Path", field_type="text",
                          required=True, hidden_when_ref="life_path"),
        ],
        target_kind="life_path",
    ),
    EffectActionMeta(
        action_id="open_roll_table",
        label="Open Roll Table (Menu)",
        description="Open a roll table as an interactive menu: pick an entry, pay its cost effects, then gain its effects",
        category="either",
        effect_type="roll_table",
        effect_action="menu",
        valid_timings=["IMMEDIATE"],
        fields=[
            EffectFieldDef(name="target", label="Roll Table", field_type="text", required=True, hidden_when_ref="table"),
        ],
        target_kind="roll_table",
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
            EffectFieldDef(name="target", label="Next Table", field_type="text", required=False, hidden_when_ref="table"),
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
            EffectFieldDef(name="target", label="Life Path", field_type="text", required=True, hidden_when_ref="life_path"),
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

]
