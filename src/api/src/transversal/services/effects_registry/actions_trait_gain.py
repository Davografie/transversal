"""Trait gain / complications — action definitions split out of ``effects_registry.py``."""

from transversal.services.effects_registry.action_types import (
    TRAIT_OWNER_ELEMENTS,
    EffectActionMeta,
    EffectFieldDef,
    RefDef,
    _ENTITY_FIELD,
    _IF_NOT_EXISTS_FIELD,
    _NOTES_CONTEXT_FIELD,
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
            EffectFieldDef(name="target", label="Trait", field_type="text", required=True, hidden_when_ref="trait"),
            _ENTITY_FIELD,
            EffectFieldDef(name="result", label="Die Rating", field_type="die_select",
                          required=True, options=["d4", "d6", "d8", "d10", "d12"]),
        ],
        context_fields=[
            _IF_NOT_EXISTS_FIELD, _STATEMENT_CONTEXT_FIELD, _NOTES_CONTEXT_FIELD,
        ],
        supports_duration=True,
        supports_polarity=True,
        inverse=("modify_trait", "remove"),
        path_element=("trait",),
        owner_elements=TRAIT_OWNER_ELEMENTS,
    ),
    # The gain verbs differ in **what happens when the trait is already there**
    # (leave it, step it up, jump to the effect die), not in where it is anchored:
    # all of them take the same owner path, so `gain` alone serves a tie and a
    # facet as well as a sheet trait — which is why the two specialised verbs below
    # are retired (kept for stored content, gone from the picker). The
    # owner is a *path* (`Effect.owner_spec`) rather than a pair of context fields:
    # which edge, or which parent, is a fact you pick out of the world, and a path
    # is the only thing that can express "this one".
    EffectActionMeta(
        action_id="gain_relationship_trait",
        output_element="traitsetting",
        label="Gain Relationship Trait",
        description=(
            "Add a new trait anchored to a relationship edge — a tie to someone "
            "(a rank on a membership, a bond on a relation), rather than a trait "
            "you hold yourself"
        ),
        category="either",
        effect_type="modify_trait",
        effect_action="gain_relationship",
        valid_timings=["IMMEDIATE", "END_OF_BEAT", "END_OF_SCENE", "END_OF_SESSION", "ON_ROLL", "ON_SET", "ON_RESULT"],
        fields=[
            EffectFieldDef(name="target", label="Trait", field_type="text", required=True),
            _ENTITY_FIELD,
            EffectFieldDef(name="result", label="Die Rating", field_type="die_select",
                          required=True, options=["d4", "d6", "d8", "d10", "d12"]),
        ],
        context_fields=[_IF_NOT_EXISTS_FIELD, _STATEMENT_CONTEXT_FIELD, _NOTES_CONTEXT_FIELD],
        supports_duration=True,
        supports_polarity=True,
        inverse=("modify_trait", "remove"),
        path_element=("trait",),
        field_order=("target", "entity", "owner", "result"),
        owner_elements=("relationship",),
        # Subsumed by `gain` (same applier, same owner path) once the gain verbs
        # declare every anchor: two verbs that differ only in which kind they
        # declare is the split this merge undoes.
        retired=True,
    ),
    EffectActionMeta(
        action_id="gain_subtrait",
        output_element="traitsetting",
        label="Gain Sub-trait",
        description=(
            "Add a new trait instance nested under another one — a facet of a trait "
            "(an elemental root under Spiritual Power, the next step of an agenda) "
            "rather than something the entity holds"
        ),
        category="either",
        effect_type="modify_trait",
        effect_action="gain_subtrait",
        valid_timings=["IMMEDIATE", "END_OF_BEAT", "END_OF_SCENE", "END_OF_SESSION", "ON_ROLL", "ON_SET", "ON_RESULT"],
        fields=[
            EffectFieldDef(name="target", label="Trait", field_type="text", required=True, hidden_when_ref="trait"),
            EffectFieldDef(name="result", label="Die Rating", field_type="die_select",
                          required=True, options=["d4", "d6", "d8", "d10", "d12"]),
        ],
        context_fields=[
            # Only meaningful on a nested instance, which is why they belong to this
            # verb: an agenda step is created *in position*, and often as a step that
            # is not in play yet.
            EffectFieldDef(name="order", label="Order", field_type="text", required=False,
                           description="Where this instance sits in its parent's ordered list."),
            EffectFieldDef(name="enabled", label="Enabled", field_type="select", required=False,
                           options=["true", "false"], default="true",
                           description="Whether it is in play immediately (an agenda's later steps start disabled)."),
            _IF_NOT_EXISTS_FIELD, _STATEMENT_CONTEXT_FIELD, _NOTES_CONTEXT_FIELD,
        ],
        supports_duration=True,
        supports_polarity=True,
        inverse=("modify_trait", "remove"),
        path_element=("trait",),
        field_order=("target", "owner", "result"),
        # The container it hangs under: `select self → traitsettings → filter …`.
        owner_elements=("traitsetting",),
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
            EffectFieldDef(name="target", label="Trait", field_type="text", required=True, hidden_when_ref="trait"),
            _ENTITY_FIELD,
            EffectFieldDef(name="result", label="Create At", field_type="die_select",
                          required=True, options=["d4", "d6", "d8", "d10", "d12"]),
        ],
        context_fields=[_STEPS_CONTEXT_FIELD, _STATEMENT_CONTEXT_FIELD, _NOTES_CONTEXT_FIELD],
        supports_duration=True,
        supports_polarity=True,
        path_element=("trait",),
        owner_elements=TRAIT_OWNER_ELEMENTS,
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
            EffectFieldDef(name="target", label="Trait", field_type="text", required=True, hidden_when_ref="trait"),
            _ENTITY_FIELD,
            EffectFieldDef(name="result", label="Die Rating", field_type="die_select",
                          required=True, options=["d4", "d6", "d8", "d10", "d12"]),
        ],
        context_fields=[_STATEMENT_CONTEXT_FIELD, _NOTES_CONTEXT_FIELD],
        supports_polarity=True,
        path_element=("trait",),
        owner_elements=TRAIT_OWNER_ELEMENTS,
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
            EffectFieldDef(name="target", label="Trait", field_type="text", required=True, hidden_when_ref="trait"),
        ],
        # Who learns it is a **path**, not a text box: the useful case is dynamic
        # (the trait's *owner*, for spying), and that is exactly what a targeting
        # path expresses. The named reference is resolved by `resolve_refs` before
        # dispatch, so a multi-value path reveals to each in turn. Empty means the
        # entity the effect lands on. It used to be a `context` field, and stored
        # content still carries that key — `_resolve_learners` reads it as a fallback.
        refs=[RefDef("learner", "Learner", "entity")],
        path_element=("traitsetting",),
    ),


    # ── Flow control ─────────────────────────────────────
    # A **choice node** ([[B5]]): the effect is asked rather than applied, and the
    # answer's own effects run. Its options are structured effects, so the editor's
    # sub-form for them is the remaining client work; the action exists here so the
    # picker offers it, the card names it, and validation can see it.
    EffectActionMeta(
        action_id="choose_branch",
        label="Choice (branch)",
        description=(
            "Offer the player a labelled choice and run the chosen option's effects. "
            "At a boundary (end of beat/scene/session) it is asked there, so the rule "
            "holds its place instead of re-deriving what was chosen."
        ),
        category="either",
        effect_type="branch",
        effect_action="choose",
        valid_timings=["IMMEDIATE", "END_OF_BEAT", "END_OF_SCENE", "END_OF_SESSION",
                       "AFTER_BEATS", "ON_ROLL", "ON_SET", "ON_RESULT"],
        fields=[],
        context_fields=[_NOTES_CONTEXT_FIELD],
        supports_duration=False,
        requires_choice=True,
    ),
]
