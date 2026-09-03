"""Author the B65 universe-scoped support-cast roll tables.

B65: the support-cast opener should be universe-aware — resolve the archetype
table from the main's ``current_universe`` (``rt-<universe>-support-cast``),
falling back to a generic ``rt-support-cast``. [[Effects]] landed the resolver
(``resolve_support_cast_table_id`` + the ``supportCastTableId`` query); this
migration authors the remaining *content* tables:

- ``rt-three_realms-support-cast`` — spirit beast / cultivator / martial artist
  archetypes (per [[Troupe Play]]).
- ``rt-support-cast`` — generic Earth fallback (used when a universe has no
  per-universe table).

(``rt-emberline-support-cast`` was authored by ``migrate_emberline.py``.)

Each entry costs 1 razmerit (a ``spend_razmerit`` cost effect) and grants a
distinction (d8) + one skill, so the open→pick→pay→gain loop applies.

Idempotent: safe to re-run; every write is an explicit upsert of full values.

Usage:
    docker compose exec api python -m transversal.migrate_support_cast
"""

from __future__ import annotations

import sys

from transversal.db.repository import EntityRepository
from transversal.domain import (
    DieType,
    Effect,
    EffectTiming,
    RollTable,
    RollTableEntry,
    RollTableScheme,
)


def _eff(type_, action, target="", result=None, context=None, negative=False) -> Effect:
    return Effect(
        timing=EffectTiming.IMMEDIATE,
        type=type_,
        action=action,
        target=target,
        result=result,
        negative=negative,
        context=context or {},
    )


def _gain(trait_id: str, die: str) -> Effect:
    """Gain a trait at ``die`` if absent, else step it up once."""
    return _eff("modify_trait", "gain_or_step_up", trait_id, result=die)


def _spend_razmerit(amount: int) -> Effect:
    return _eff("transfer_razmerit", "spend", "self", result=str(amount))


def _entry(label: str, description: str, distinction: str, distinction_die: str,
           skill: str, skill_die: str) -> RollTableEntry:
    return RollTableEntry(
        label=label,
        description=description,
        cost_effects=[_spend_razmerit(1)],
        effects=[_gain(distinction, distinction_die), _gain(skill, skill_die)],
    )


# ── Three Realms support cast (spirit beast / cultivator / martial artist) ─
_THREE_REALMS = (
    # (label, description, distinction, skill)
    ("Spirit Beast", "A spirit beast given form — fierce, loyal, and only half-tame.",
     "trait-species-4335", "d8", "trait-spirit-manifestation-2d0e", "d4"),
    ("Sword Cultivator", "Walks the sword path — the blade and the dao are one.",
     "trait-class-bd45", "d8", "trait-martial-934c", "d4"),
    ("Body Cultivator", "Tempered the vessel until flesh itself became a weapon.",
     "trait-background-744c", "d8", "trait-body-tempering-f4dc", "d4"),
    ("Dao Cultivator", "Seeks the truth at the heart of the dao, one insight at a time.",
     "trait-essence-e5ce", "d8", "trait-dao-conception-069f", "d4"),
    ("Beast Tamer", "Speaks the old tongue that spirit beasts remember.",
     "trait-origin-e4fb", "d8", "trait-beast-taming-2d3f", "d4"),
    ("Talisman Maker", "Writes the world's rules onto slips of jade and ink.",
     "trait-creativity-ae51", "d8", "trait-talisman-cb33", "d4"),
)


# ── Generic support cast (Earth fallback) ─────────────────────────────────
_GENERIC = (
    ("Muscle", "The one you point at a problem when talking is over.",
     "trait-class-bd45", "d8", "trait-brawl-774e", "d6"),
    ("Face", "Talks fast, smiles easy, and knows everyone worth knowing.",
     "trait-personality-348d", "d8", "trait-charm-0c77", "d6"),
    ("Hacker", "Sees the world as a system waiting to be asked the right question.",
     "trait-background-744c", "d8", "trait-hack-8a0f", "d8"),
    ("Driver", "Feels the machine through the seat of the pants.",
     "trait-origin-e4fb", "d8", "trait-drive-0a3b", "d4"),
    ("Medic", "Keeps everyone breathing long enough to finish the job.",
     "trait-essence-e5ce", "d8", "trait-heal-c241", "d4"),
    ("Ghost", "Was never there — and left no trace.",
     "trait-creativity-ae51", "d8", "trait-evade-2ec1", "d8"),
)


def _seed_table(repo: EntityRepository, table_id: str, name: str, universe: str,
                archetypes: tuple) -> int:
    entries = [
        _entry(label, description, distinction, d_die, skill, s_die)
        for (label, description, distinction, d_die, skill, s_die) in archetypes
    ]

    table = RollTable(
        id=table_id,
        name=name,
        universe=universe,
        life_path=None,  # shared / general — not tied to a single life path
        scheme=RollTableScheme.RANGE,
        die=DieType.D6,
        entries=entries,
    )

    existed = repo.get_roll_table(table_id) is not None
    if existed:
        repo.update_roll_table(table)
    else:
        repo.create_roll_table(table)
    print(f"  {'updated' if existed else 'created'} {table_id} "
          f"({len(entries)} archetypes, 1 razmerit each)")
    return 1


def migrate() -> int:
    repo = EntityRepository()

    n = 0
    n += _seed_table(repo, "rt-three_realms-support-cast",
                     "Three Realms Support Cast", "three_realms", _THREE_REALMS)
    n += _seed_table(repo, "rt-support-cast",
                     "Support Cast", "earth", _GENERIC)

    print(f"\nDone: {n} support-cast table(s) authored")
    return 0


if __name__ == "__main__":
    sys.exit(migrate())
