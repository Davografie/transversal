"""One-off migration: clamp trait.universes to their trait set's universes.

Fixes traits whose ``universes`` list includes universes their trait set is
not enabled in (e.g. cultivation traits leaking into Earth after the v1→v2
migration).  Sets each trait's ``universes`` to the intersection with its
trait set's ``universes``.

Usage:
    docker compose exec api python -m transversal.migrate_trait_universes
"""

from __future__ import annotations

import sys

from transversal.db.repository import EntityRepository


def migrate() -> int:
    repo = EntityRepository()
    traits = repo.get_all_traits()

    corrected = 0
    skipped = 0
    for trait in traits:
        if not trait.traitset_id:
            skipped += 1
            continue
        traitset = repo.get_traitset_by_id(trait.traitset_id)
        if traitset is None or not traitset.universes:
            skipped += 1
            continue

        allowed = set(traitset.universes)
        clamped = [u for u in trait.universes if u in allowed]
        if clamped != trait.universes:
            before = list(trait.universes)
            trait.universes = clamped
            repo.update_trait(trait)
            corrected += 1
            print(f"  {trait.name:<28} {before} → {clamped}")

    print(f"\n=== DONE ===")
    print(f"Corrected: {corrected}, Skipped: {skipped}, Total: {len(traits)}")
    return 0


if __name__ == "__main__":
    sys.exit(migrate())
