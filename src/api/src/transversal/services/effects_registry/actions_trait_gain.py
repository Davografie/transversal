"""Trait gain / complications — action definitions split out of ``effects_registry.py``."""

from transversal.services.effects_registry.action_types import (
    EffectActionMeta,
    EffectFieldDef,
    _ENTITY_FIELD,
    _NOTES_CONTEXT_FIELD,
    _RELATIONSHIP_CONTEXT_FIELD,
    _STATEMENT_CONTEXT_FIELD,
    _STEPS_CONTEXT_FIELD,
)


ACTIONS: list[EffectActionMeta] = [
    # ── Trait gain / complications ─────────────────────
    EffectActionMeta(
        action_id="gain_trait",
        output_element="traitsetting",
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
        path_element=("trait",),
    ),
    EffectActionMeta(
        action_id="gain_or_step_up_trait",
        output_element="traitsetting",
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
        path_element=("trait",),
    ),
    EffectActionMeta(
        action_id="cortex_gain_trait",
        output_element="traitsetting",
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
        supports_polarity=True,
        path_element=("trait",),
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
        ],
        context_fields=[
            EffectFieldDef(name="learner", label="Learner", field_type="entity",
                          required=False, default="self"),
        ],
        path_element=("traitsetting",),
    ),

]
