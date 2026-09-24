"""Roll-table resolution — map a roll / tier / index to a table entry."""

from __future__ import annotations

import logging
from typing import Optional

from transversal.domain import (
    OutcomeTier,
    RollTable,
    RollTableEntry,
    RollTableScheme,
)

log = logging.getLogger("transversal.roll_table")


def resolve_table(
    table: RollTable,
    *,
    roll: Optional[int] = None,
    tier: Optional[OutcomeTier] = None,
    index: Optional[int] = None,
) -> Optional[RollTableEntry]:
    """Select an entry from a roll table.

    - ``index`` (1-based) is a manual / click selection and wins when provided.
    - ``roll`` drives RANGE, WEIGHT, and INDEX schemes.
    - ``tier`` drives the TIER scheme.

    Returns None when no entry matches.
    """
    if index is not None:
        i = index - 1
        return table.entries[i] if 0 <= i < len(table.entries) else None

    if table.scheme == RollTableScheme.TIER:
        if tier is None:
            return None
        for entry in table.entries:
            if entry.tier == tier:
                return entry
        return None

    if roll is None:
        return None

    if table.scheme == RollTableScheme.RANGE:
        for entry in table.entries:
            if (
                entry.min_value is not None
                and entry.max_value is not None
                and entry.min_value <= roll <= entry.max_value
            ):
                return entry
        return None

    if table.scheme == RollTableScheme.INDEX:
        i = roll - 1
        return table.entries[i] if 0 <= i < len(table.entries) else None

    if table.scheme == RollTableScheme.WEIGHT:
        total = sum(e.weight or 0 for e in table.entries)
        if total <= 0:
            return None
        r = ((roll - 1) % total) + 1  # normalize into 1..total
        cumulative = 0
        for entry in table.entries:
            cumulative += entry.weight or 0
            if r <= cumulative:
                return entry
        return None

    return None

# ── Content migration (B164) ─────────────────────────────────────────

def backfill_rolltable_anchor_paths(repo) -> int:
    """Move roll-table tie anchors off the legacy context pair onto the owner path.

    A trait gained or stepped on a *relationship* (a tenure on a faction) used to
    say which edge through ``context.relationship`` (+ an optional
    ``relationship_type``). That pair has no declarer left — no action offers it —
    so stored rules keeping it were uneditable, and the applier's handling is a
    legacy branch kept alive by exactly this content. The owner path is the same
    fact in the vocabulary everything else uses::

        select self → relationships → filter contact_id == <faction>
                                    → filter type == <membership|authored type>

    The ``type`` filter is **always** written, defaulting to ``membership``,
    because that is what the legacy branch looked up (``relationship_type or
    "membership"``) — without it the path would also match an edge of another kind
    to the same faction, which the rule never did.

    Idempotent: an effect that already carries an ``owner_spec`` is left alone, and
    so is one whose anchor is a runtime token (``{term_faction}`` — a *shared*
    table cannot name a faction, which is why the token exists; it stays on the
    context pair until a runtime binding can carry it). Returns the number of
    effects migrated.
    """
    from transversal.services.target_spec import TargetSpec

    changed = 0
    for table in repo.list_roll_tables():
        touched = False
        for entry in table.entries or []:
            for effect in [*(entry.cost_effects or []), *(entry.effects or [])]:
                if effect.owner_spec is not None:
                    continue
                context = dict(effect.context or {})
                faction = context.get("relationship")
                if not faction:
                    continue
                if str(faction).startswith("{") and str(faction).endswith("}"):
                    log.warning(
                        "[backfill_rolltable_anchor_paths] %s/%s: anchor %s is a runtime "
                        "token — left on the context pair", table.id, entry.label, faction)
                    continue
                rel_type = (context.get("relationship_type") or "membership").strip() or "membership"
                effect.owner_spec = TargetSpec.model_validate({"steps": [
                    {"kind": "select", "collection": "self"},
                    {"kind": "navigate", "edge": "relationships"},
                    {"kind": "filter", "field": "contact_id", "operator": "==", "value": faction},
                    {"kind": "filter", "field": "type", "operator": "==", "value": rel_type},
                ]})
                context.pop("relationship", None)
                context.pop("relationship_type", None)
                # `Effect.context` is a dict and never null: an emptied one is `{}`.
                effect.context = context
                changed += 1
                touched = True
        if touched:
            repo.update_roll_table(table)
    return changed
