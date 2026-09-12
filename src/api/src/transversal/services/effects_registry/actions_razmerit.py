"""Razmerit — action definitions split out of ``effects_registry.py``."""

from transversal.services.effects_registry.action_types import (
    EffectActionMeta,
    EffectFieldDef,
    _ENTITY_FIELD,
)


ACTIONS: list[EffectActionMeta] = [
    # ── Razmerit ───────────────────────────────────────
    EffectActionMeta(
        action_id="earn_razmerit",
        label="Earn Razmerit",
        description="Gain razmerit from the system pool",
        category="benefit",
        effect_type="transfer_razmerit",
        effect_action="earn",
        fields=[
            EffectFieldDef(name="result", label="Amount", field_type="number",
                          required=True, default="1"),
            _ENTITY_FIELD,
        ],
        implicit_target="self",
        # A gain undoes by paying it back — the cost of a rule that is taken back.
        inverse=("transfer_razmerit", "spend"),
    ),
    EffectActionMeta(
        action_id="spend_razmerit",
        label="Spend Razmerit",
        description="Pay razmerit as an activation or ongoing cost",
        category="cost",
        effect_type="transfer_razmerit",
        effect_action="spend",
        fields=[
            EffectFieldDef(name="result", label="Amount", field_type="number",
                          required=True, default="1"),
            _ENTITY_FIELD,
        ],
        implicit_target="self",
        # A cost undoes by refunding it.
        inverse=("transfer_razmerit", "earn"),
    ),
    EffectActionMeta(
        action_id="transfer_razmerit",
        label="Transfer Razmerit",
        description="Move razmerit from one entity to another",
        category="either",
        effect_type="transfer_razmerit",
        effect_action="transfer",
        fields=[
            EffectFieldDef(name="result", label="Amount", field_type="number",
                          required=True, default="1"),
            EffectFieldDef(name="target", label="Target Entity", field_type="text",
                          required=True),
        ],
        target_kind="entity",
    ),

]
