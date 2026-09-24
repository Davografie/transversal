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
]
