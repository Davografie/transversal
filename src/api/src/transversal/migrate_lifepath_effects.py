"""Repair life-path roll-table effects that were seeded with the wrong
``relationship`` context.

Rank and tenure (``trait-rel-*``) are the only traits that should attach to
the ``character ↔ faction`` membership edge. Learn-skill gains and personal
complications were accidentally seeded with ``context.relationship = faction``,
so they landed on the relationship edge instead of the character entity and
never showed on the character sheet.

This pass also promotes the seeded ``gain_complication`` mishap effects to the
idempotent ``gain_or_step_up_complication`` action (which mirrors
``gain_or_step_up`` and no longer collides when the complication already exists).

Idempotent: safe to re-run.

Usage:
    docker compose exec api python -m transversal.migrate_lifepath_effects
"""

from __future__ import annotations

import sys

from transversal.db.repository import EntityRepository


def _fix_effect(effect) -> bool:
    """Return True if the effect was changed."""
    changed = False

    if effect.type != "modify_trait":
        return False

    # Only relationship traits (rank/tenure) should carry a relationship scope.
    if not str(effect.target).startswith("trait-rel-"):
        ctx = effect.context or {}
        if ctx.get("relationship"):
            ctx.pop("relationship", None)
            effect.context = ctx
            changed = True

    if effect.action == "gain_complication":
        effect.action = "gain_or_step_up_complication"
        changed = True

    return changed


def migrate() -> int:
    repo = EntityRepository()
    changed_tables = 0
    changed_effects = 0

    for table in repo.list_roll_tables():
        table_changed = False
        for entry in table.entries:
            for effect in entry.effects:
                if _fix_effect(effect):
                    table_changed = True
                    changed_effects += 1

        if table_changed:
            repo.update_roll_table(table)
            changed_tables += 1
            print(f"  {table.id} ({table.name}) — repaired effects")

    print(f"\nRepaired {changed_effects} effect(s) across {changed_tables} roll table(s)")
    return 0


if __name__ == "__main__":
    sys.exit(migrate())
