"""Mark the shared Survive/Continue roll tables as fundamental.

``rt-survive`` and ``rt-continue`` are shared across every life path and
should be universe-agnostic (``universe=""``), so they show under the
Fundamental group and are available from every universe. They were briefly
written with ``universe="three_realms"``; this migration clears that.

Idempotent: safe to re-run.

Usage:
    docker compose exec api python -m transversal.migrate_shared_roll_tables
"""

from __future__ import annotations

import sys

from transversal.db.repository import EntityRepository

FUNDAMENTAL_IDS = ("rt-survive", "rt-continue")


def migrate() -> int:
    repo = EntityRepository()
    changed = 0

    for table in repo.list_roll_tables():
        if table.id not in FUNDAMENTAL_IDS:
            continue
        if table.life_path is not None or not table.universe:
            continue
        table.universe = ""
        repo.update_roll_table(table)
        changed += 1
        print(f"  {table.id} ({table.name}) → fundamental (universe='')")

    print(f"\nMarked {changed} shared roll table(s) fundamental")
    return 0


if __name__ == "__main__":
    sys.exit(migrate())
