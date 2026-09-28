"""Relationships — action definitions split out of ``effects_registry.py``."""

from transversal.services.effects_registry.action_types import (
    EffectActionMeta,
    EffectFieldDef,
    RefDef,
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
    # ── Knowledge (fog of war) ─────────────────────────
    # "Who is here?" as an effect: the subject's `known_to` gains the resolved
    # targets. It **unions** and never replaces — the whole point of [[B121]],
    # where a GM assuming a hidden occupant must not wipe what that occupant
    # already knew. A path fans out, so "every occupant of my location" arrives
    # one id at a time and the dedupe is the membership check.
    #
    # No inverse: forgetting is not the undo of learning. A rule that should
    # unlearn something has to say what it forgets.
    EffectActionMeta(
        action_id="learn_entities",
        label="Learn",
        description=(
            "Someone learns about the resolved entity: its id joins their known_to "
            "list, deduped, without disturbing what they already know"
        ),
        category="benefit",
        effect_type="entity",
        effect_action="learn",
        valid_timings=["IMMEDIATE"],
        fields=[
            EffectFieldDef(name="target", label="Which Entity", field_type="text",
                           required=False),
        ],
        # Two halves, and they answer different questions, so both are declared:
        # **who learns** is the `learner` reference (a targeting path — "everyone
        # with him"), and **which entity they learn about** is the target. Same
        # shape Reveal Trait uses ([[B226]]). An empty learner means the entity the
        # effect lands on, which is the only reading this had before the reference.
        refs=[RefDef("learner", "Learner", "entity")],
        target_kind="entity",
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
