"""Author ``rt-earth-regions`` — a population-weighted list of Earth's regions.

A **random location roller**. Roll a d100 and you get a region of Earth, chosen in
proportion to how many people live there. It is *usable* as a birthplace — a
character's region of origin is the first thing an Earth life path will want to
know — but that is a use, not what the table is. It names and describes places,
and carries no effects, so anything may impose its own meaning on the result.

Authored **shared / unaffiliated** (``life_path=None``) on the human's instruction,
for exactly that reason: a scene's location, a traveller's origin, a support
cast's home and a character's birth all want the same roll.

**The weights are Earth's, flattened.** Each entry's band is the region's real
share of world population (UN WPP 2024), put through one rule: every region
**floors at 3 faces**, India and China **cap at 12**, and the remaining 49 faces
are handed out by population. Straight population would make India and China 18
and 17 faces each and leave Oceania (0.4%) with *no face at all* — unreachable on
a d100 — so the floor is what keeps every one of the seventeen places rollable,
and the cap is what stops the party being a third Indian-or-Chinese. Only those
two entries move by 3 points or more; the middle is already realistic.

Region membership follows the human's three blocs — **West** (N. America, western
Europe, Japan/Korea, Oceania), **East** (eastern Europe, Russia, Asia, the
Pacific), **South** (Africa, Latin America, the Caribbean) — and the bands sum to
West 14 / East 54 / South 32, so the bloc is recoverable from the roll without a
second table.

Held back from ``die=DieType``: a d100 is not a Cortex trait die, which is why
this needs [[B264]]'s ``TableDie`` notation. ``d100``'s digits differ, so it stays
a true percentile rather than a digit read.

Idempotent: safe to re-run, but every write is a full upsert of the table's
values — re-running **overwrites** anything a GM has since authored onto it.

Usage:
    docker compose exec api python -m transversal.migrate_earth_regions
"""

from __future__ import annotations

import sys

from transversal.db.repository import EntityRepository
from transversal.domain import (
    RollTable,
    RollTableEntry,
    RollTableScheme,
    TableDie,
)

TABLE_ID = "rt-earth-regions"

#: The table was merged briefly as ``rt-earth-origin``; the id implied a birth
#: table, which this is not. Removed on sight so a database that ran the earlier
#: version does not keep a stale duplicate.
SUPERSEDED_IDS: tuple[str, ...] = ("rt-earth-origin",)

# (min, max, label, description) — bands are contiguous 1..100 by construction.
_REGIONS: tuple[tuple[int, int, str, str], ...] = (
    (1, 12, "India",
     "A subcontinent of languages, faiths and castes — the world's largest "
     "nation, where family is the first institution and the state the last."),
    (13, 24, "China",
     "An ancient civilisation run as a modern machine — a billion and a half "
     "lives ordered by family, work unit and the state's long horizon."),
    (25, 31, "Southeast Asia",
     "Archipelago and mainland — river deltas, megacities and ten thousand "
     "islands, trading since before there were nations."),
    (32, 37, "Pakistan & Bangladesh",
     "The Indus and the Ganges plains — dense, young, and shaped by partition, "
     "monsoon and migration. The rest of South Asia."),
    (38, 43, "East Africa",
     "Highlands and the Horn — the oldest human places, now the youngest nations "
     "on Earth."),
    (44, 49, "Western Europe",
     "The rich, ageing core — old institutions, open borders, and welfare states "
     "older than most of the people living in them."),
    (50, 55, "West Africa",
     "The Gulf of Guinea belt — the fastest-growing region on Earth, loud with "
     "markets, music and cities still being built."),
    (56, 61, "South America",
     "Between the Andes and the Amazon — a continent of cities, extractive "
     "wealth and hard-won democracies."),
    (62, 66, "The Middle East",
     "The crossroads of three continents — where the world's oldest cities sit "
     "on its most contested ground."),
    (67, 71, "The United States & Canada",
     "The settler West — continental, car-centred, and rich enough that poverty "
     "here looks like comfort almost anywhere else."),
    (72, 76, "Central & Southern Africa",
     "The Congo basin and the southern plateau — mineral wealth underfoot, and "
     "the long shadow of its extraction."),
    (77, 81, "Eastern Europe",
     "Between the Baltic and the Black Sea — a belt of nations that changed "
     "hands, names and ideologies within living memory."),
    (82, 86, "North Africa",
     "The Mediterranean's southern shore — Arab, Amazigh and African at once, "
     "with the desert at the door."),
    (87, 90, "Central America & the Caribbean",
     "The isthmus and the islands — small nations with large diasporas, "
     "hurricanes and revolution within living memory."),
    (91, 94, "Japan & Korea",
     "The developed East — dense, disciplined, technologically saturated, and "
     "demographically shrinking."),
    (95, 97, "Central Asia",
     "The steppe and the old Silk Road — landlocked, post-Soviet, and ruled by "
     "men who were ruling it before."),
    (98, 100, "Australia, New Zealand & the Pacific",
     "The settler South and the island Pacific — rich, remote, and built on land "
     "taken from older peoples."),
)


def _table() -> RollTable:
    entries = [
        RollTableEntry(label=label, description=description,
                       min_value=lo, max_value=hi)
        for (lo, hi, label, description) in _REGIONS
    ]
    return RollTable(
        id=TABLE_ID,
        name="Where on Earth",
        universe="earth",
        life_path=None,  # shared / unaffiliated — not tied to one life path
        scheme=RollTableScheme.RANGE,
        die=TableDie("d100"),
        entries=entries,
    )


def _check_bands(entries: list[RollTableEntry]) -> None:
    """The bands must tile 1..100 exactly — a gap is a roll with no answer."""
    seen: set[int] = set()
    for e in entries:
        seen.update(range(e.min_value, e.max_value + 1))
    missing = sorted(set(range(1, 101)) - seen)
    overlap = len(seen) != sum(e.max_value - e.min_value + 1 for e in entries)
    if missing or overlap:
        raise SystemExit(
            f"{TABLE_ID}: bands do not tile 1..100 "
            f"(missing={missing or 'none'}, overlapping={overlap})"
        )


def migrate() -> int:
    repo = EntityRepository()

    for old in SUPERSEDED_IDS:
        if repo.delete_roll_table(old):
            print(f"  removed superseded {old}")

    table = _table()
    _check_bands(table.entries)

    existed = repo.get_roll_table(TABLE_ID) is not None
    if existed:
        repo.update_roll_table(table)
    else:
        repo.create_roll_table(table)

    faces = sum(e.max_value - e.min_value + 1 for e in table.entries)
    print(f"  {'updated' if existed else 'created'} {TABLE_ID} "
          f"({len(table.entries)} regions, {faces} faces, die {table.die})")
    print(f"\nDone: 'Where on Earth' authored (shared, universe=earth)")
    return 0


if __name__ == "__main__":
    sys.exit(migrate())
