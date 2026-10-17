"""Rule-registry actions — granting a rule to an owner.

Split out as its own editor section ("Rules") because it acts on the SFX
registry itself rather than on a trait, a pool or the world.
"""

from transversal.services.effects_registry.action_types import (
    EffectActionMeta,
    EffectFieldDef,
    RefDef,
)


ACTIONS: list[EffectActionMeta] = [
    EffectActionMeta(
        action_id="grant_sfx",
        label="Grant SFX",
        description=(
            "Grant a rule from the registry to a target owner: an entity, a place, "
            "a body, a trait definition (its default rules), or a trait / trait-set "
            "instance. The teacher case: a place's rule hands a technique to "
            "whoever it applies to."
        ),
        category="benefit",
        effect_type="sfx",
        effect_action="grant",
        valid_timings=[
            "IMMEDIATE", "END_OF_BEAT", "END_OF_SCENE", "END_OF_SESSION",
            "ON_ROLL", "ON_SET", "ON_RESULT",
        ],
        # The positional fallback, still accepted and still hidden once the
        # reference is authored. Declared here rather than reusing `_ENTITY_FIELD`
        # because the reference now accepts every owner surface, so the label has
        # to say "Owner" — and the guard that keeps field and reference in step
        # compares the two labels ([[B326]]).
        fields=[
            EffectFieldDef(name="entity", label="Owner", field_type="entity",
                           required=False, hidden_when_ref="recipient"),
        ],
        # Which rule to grant, as a targeting-wizard reference: `select sfxs →
        # filter trigger == menu` reads "any post-roll rule", and the wizard
        # offers the registry's own columns as filters.
        refs=[RefDef("sfx", "SFX", "sfx")],
        target_kind="sfx",
    ),
]
