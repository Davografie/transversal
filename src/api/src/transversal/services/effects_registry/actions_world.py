"""Entity Creation + Attunement + Travel / Transversal + Set Location — action definitions split out of ``effects_registry.py``."""

from transversal.services.effects_registry.action_types import (
    EffectActionMeta,
    EffectFieldDef,
    RefDef,
    _ENTITY_FIELD,
)


ACTIONS: list[EffectActionMeta] = [
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
            # The fallback form: a universe named directly. Superseded by the
            # ``projection`` reference below — the intended way to source a
            # capability is from a resolved life, whose universe it takes.
            EffectFieldDef(name="result", label="Target Universe", field_type="select",
                          required=False, options_from="universes",
                          hidden_when_ref="projection",
                          # Fallback only — the editor lists the universes in the DB.
                          options=["three_realms", "earth"]),
            EffectFieldDef(name="target", label="Who It Applies To", field_type="text",
                          required=False, default="self"),
        ],
        refs=[
            # Declared *before* ``projection``: a reference is in scope for the
            # references that follow it, so the world is decided first and the
            # projection path can filter on it (``universe == {universe}``).
            RefDef(name="universe", label="Universe (which world)", element="universe"),
            # A path that starts at each entity the target resolved to and walks
            # to that entity's projection counterpart — optionally constrained to
            # the universe above.
            RefDef(name="projection", label="Attunes To (projection)", element="projection"),
        ],
        supports_duration=True,
        inverse=("attune", "disable"),
        target_kind="entity",
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

]
