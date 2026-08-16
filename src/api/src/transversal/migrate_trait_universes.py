"""One-off migration: normalize trait/traitset universe scoping.

Cleans transversal2's own registry data (not the old-app migration):

1. Clamp each traitset's ``universes`` to the real universe keys present in the
   ``entities`` collection (case-insensitive).
2. Clamp each trait's ``universes`` to its traitset's universes
   (case-insensitive). When the intersection is empty, inherit the traitset's
   universes. Traits without a traitset are simply clamped to the real keys.

Idempotent: re-running is safe.

Usage:
    docker compose exec api python -m transversal.migrate_trait_universes
"""

from __future__ import annotations

import sys

from transversal.db.repository import EntityRepository
from transversal.domain import EntityType


def _norm(value: str) -> str:
    return (value or "").strip().lower()


def _real_universe_keys(repo: EntityRepository) -> set[str]:
    return {
        _norm(e.current_universe)
        for e in repo.list_all_entities()
        if e.type == EntityType.UNIVERSE and e.current_universe
    }


def _clamp(universes: list[str], real: set[str]) -> list[str]:
    out: list[str] = []
    for u in universes:
        key = _norm(u)
        if key in real and key not in out:
            out.append(key)
    return sorted(out)


def migrate() -> int:
    repo = EntityRepository()
    real = _real_universe_keys(repo)
    print(f"Real universe keys: {sorted(real)}")

    tsets_cleaned = 0
    traits_cleaned = 0
    traits_inherited = 0
    no_traitset = 0

    # 1. Clean traitsets first (traits derive from them).
    for ts in repo.get_all_traitsets():
        cleaned = _clamp(ts.universes, real)
        if cleaned != ts.universes:
            ts.universes = cleaned
            repo.update_traitset(ts)
            tsets_cleaned += 1
            print(f"  SET  {ts.name:<24} → {cleaned}")

    # 2. Clean traits against their cleaned traitset.
    for trait in repo.get_all_traits():
        current = [_norm(u) for u in trait.universes]

        if not trait.traitset_id:
            cleaned = _clamp(trait.universes, real)
            inherited = False
            no_traitset += 1
        else:
            traitset = repo.get_traitset_by_id(trait.traitset_id)
            if traitset is None:
                cleaned = _clamp(trait.universes, real)
                inherited = False
                no_traitset += 1
            else:
                set_unis = set(_clamp(traitset.universes, real))
                intersection = [u for u in current if u in set_unis]
                if intersection:
                    cleaned = sorted(set(intersection))
                    inherited = False
                else:
                    cleaned = sorted(set_unis)
                    inherited = True

        if cleaned != current:
            trait.universes = cleaned
            repo.update_trait(trait)
            traits_cleaned += 1
            if inherited:
                traits_inherited += 1
                print(f"  TRAIT {trait.name:<24} → inherit {cleaned}")

    print("\n=== DONE ===")
    print(f"Traitsets cleaned: {tsets_cleaned}")
    print(f"Traits cleaned: {traits_cleaned} (inherited: {traits_inherited})")
    print(f"Traits without a traitset (clamped directly): {no_traitset}")
    return 0


if __name__ == "__main__":
    sys.exit(migrate())
