"""Roll-table-as-menu — pick an entry (pay its cost effects, then gain its effects).

B58: an SFX carries a ``roll_table/menu`` effect whose ``target`` is a roll-table
id. The frontend opens that table as an interactive menu; picking an entry pays
the entry's ``cost_effects`` (e.g. ``spend_razmerit``, ``step_down_trait``) and
then applies its ``effects``. This module is the pay-then-gain backend.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from transversal.domain import RollTableEntry
from transversal.services.roll_table import resolve_table

if TYPE_CHECKING:
    from transversal.domain import Entity
    from transversal.services.effects_applier import EffectsResult


def entry_razmerit_cost(entry: RollTableEntry) -> int:
    """Total razmerit an entry costs — the sum of its ``spend_razmerit`` cost effects."""
    return sum(
        int(e.result or "0")
        for e in (entry.cost_effects or [])
        if e.type == "transfer_razmerit" and e.action == "spend"
    )


def pick_roll_table_entry(
    repo,
    entity: "Entity",
    table_id: str,
    index: int,
):
    """Resolve ``index`` in ``table_id``; pay its cost effects, then gain its effects.

    Returns ``(EffectsResult, structured)`` — the committed result plus any
    structured ``choose`` choices the caller must drive through the targeting
    wizard (mirrors the ``applyEffects`` mutation shape). Raises ``ValueError``
    when the table/entry is missing or the entity can't afford the razmerit cost.
    """
    from transversal.services.effects_commit import commit_effects
    from transversal.services.effects_engine import resolve_effect_spec_choices

    table = repo.get_roll_table(table_id)
    if table is None:
        raise ValueError(f"roll table '{table_id}' not found")

    entry = resolve_table(table, index=index)
    if entry is None:
        raise ValueError(f"no entry at index {index} in '{table_id}'")

    raz_cost = entry_razmerit_cost(entry)
    if entity.razmerit < raz_cost:
        raise ValueError(
            f"insufficient razmerit: need {raz_cost}, have {entity.razmerit}"
        )

    # Pay first, then gain — cost_effects come before effects.
    structured = []
    to_commit = []
    for eff in list(entry.cost_effects or []) + list(entry.effects or []):
        if eff.target_spec is not None:
            applied, pending = resolve_effect_spec_choices(eff, "target", {}, entity, repo)
            to_commit.extend(applied)
            structured.extend(pending)
        else:
            to_commit.append(eff)

    result = commit_effects(entity, to_commit, repo)
    return result, structured, entry.label, raz_cost
