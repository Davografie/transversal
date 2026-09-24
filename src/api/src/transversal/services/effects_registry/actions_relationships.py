"""Relationships — action definitions split out of ``effects_registry.py``."""

from transversal.services.effects_registry.action_types import (
    EffectActionMeta,
    EffectFieldDef,
)


ACTIONS: list[EffectActionMeta] = [
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
            # A picker, not free text: the types are a vocabulary the graph
            # already holds, and a typo here creates an edge nothing can find.
            EffectFieldDef(name="result", label="Relationship Type", field_type="select",
                          required=True, options_from="relationship_types"),
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

    # ── Contests ───────────────────────────────────────
    # The missing half of the contest vocabulary: the engine could *react* to a
    # contest (`contest_win`) but nothing could put two entities into one. Until
    # now the only way in was the UI's challenge button, which is why teach/take
    # could not be rebuilt as SFX — `take` is a contest, and an SFX could not
    # start it. See [[Character Growth#Trait Transfer — removed (2026-09-10)]].
    #
    # No duration and no inverse, deliberately: a contest is beat-scoped
    # *ephemeral* state ([[Contest Tracker]]) that ends by resolution or by giving
    # in — never by a timer expiring. An "un-start" would have to decide what to
    # do about a contest already fought, and every answer is wrong.
    EffectActionMeta(
        action_id="start_contest",
        label="Start Contest",
        description=(
            "Oppose another entity: this starts a fresh contest between them at the "
            "acting entity's location (their rolls become contests until it resolves)"
        ),
        category="either",
        effect_type="contest",
        effect_action="start",
        valid_timings=["IMMEDIATE"],
        fields=[
            EffectFieldDef(name="target", label="Opponent", field_type="text", required=True),
        ],
        target_kind="entity",
    ),
]
