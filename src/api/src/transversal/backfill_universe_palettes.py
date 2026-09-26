"""One-off backfill: give the existing universes their example palettes.

`seed_universes` only runs on creation, so a universe that already exists never
picks up a palette added later. This pass writes `db/universe_palettes.py`'s
two worked examples (Earth, Three Realms) onto those universe entities, so
per-universe styling is visible on an existing database ([[UI-UX Design#Theming]]).

**Only fills a blank.** A universe that already carries a palette is reported
and left exactly as it is — the entity field is the source of truth once it has
a value, and a GM's authored look must not be clobbered by an example. So this
is safe to re-run, and it stops being needed the moment the examples are on the
entities.

Dry-run by default. Pass ``--apply`` to write.

Usage:
    docker compose exec api python -m transversal.backfill_universe_palettes
    docker compose exec api python -m transversal.backfill_universe_palettes --apply
"""

from __future__ import annotations

import sys

from transversal.db.arango import ENTITIES, get_db
from transversal.db.universe_palettes import PALETTES, palette_for


def migrate(apply: bool = False) -> int:
    db = get_db()
    entities = db.collection(ENTITIES)

    filled, already, unknown = 0, 0, []

    for doc in entities.all():
        if str(doc.get("type", "")).lower() != "universe":
            continue
        key = doc.get("current_universe") or ""
        palette = palette_for(key)

        if doc.get("palette"):
            print(f"SKIP    {doc['_key']:<34} {key:<16} already has a palette")
            already += 1
            continue

        if palette is None:
            unknown.append(key)
            print(f"SKIP    {doc['_key']:<34} {key:<16} no example palette")
            continue

        print(f"{'APPLY ' if apply else 'DRY-RUN'} {doc['_key']:<34} {key:<16} -> {len(palette)} groups")
        if apply:
            live = entities.get(doc["_key"])
            if live is None or live.get("palette"):
                continue
            entities.update({**live, "palette": palette})
        filled += 1

    print()
    print("=== UNIVERSE PALETTE BACKFILL ===")
    print(f"apply={apply}")
    print(f"  filled from examples: {filled}")
    print(f"  left alone (authored): {already}")
    if unknown:
        print(f"  universes with no example ({len(unknown)}):")
        for key in unknown:
            print(f"    - {key}")
    print(f"  example keys available: {', '.join(sorted(PALETTES))}")
    return 0


if __name__ == "__main__":
    sys.exit(migrate(apply="--apply" in sys.argv))
