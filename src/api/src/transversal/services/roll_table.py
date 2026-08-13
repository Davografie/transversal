"""Roll-table resolution — map a roll / tier / index to a table entry."""

from __future__ import annotations

from typing import Optional

from transversal.domain import (
    OutcomeTier,
    RollTable,
    RollTableEntry,
    RollTableScheme,
)


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
