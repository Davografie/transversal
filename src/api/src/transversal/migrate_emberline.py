"""Author the Emberline universe's life-path / roll-table content.

Emberline was authored as a *skeleton* through the MCP tools (1 universe,
2 factions, 12 locations, 3 flow-only life paths, 7 traits). This migration
fills in the life-path content layer:

1. **Enrich the three life-path Entry tables** — each entry gains an ``enroll``
   flow effect, the universe ``Distinction`` (d8) and one path-appropriate
   skill (d6), plus a short description. The existing ``next_step`` → Muster
   flow is preserved.
2. **Add a B58 roll-table-as-menu table** — ``rt-emberline-support-cast`` is a
   shared (``life_path=None``) Emberline menu table whose entries each cost
   1 razmerit and grant the Distinction + one skill, so the open→pick→pay→gain
   loop can be exercised end-to-end.
3. **Wire the two factions** to their life paths via ``suitable_life_path_ids``.

Idempotent: safe to re-run; every write is an explicit upsert of full values.

Usage:
    docker compose exec api python -m transversal.migrate_emberline
"""

from __future__ import annotations

import sys

from transversal.db.repository import EntityRepository
from transversal.domain import (
    DieType,
    Effect,
    EffectTiming,
    LifePath,
    RollTable,
    RollTableEntry,
    RollTableScheme,
)

# ── Emberline trait ids (ts-emberline) ────────────────────────────────────
DISTINCTION = "trait-emberline-distinction"      # d8
RIVER_PILOTING = "trait-emberline-river-piloting"
CHART_LORE = "trait-emberline-chart-lore"
EMBER_TENDING = "trait-emberline-ember-tending"
TIDE_SENSE = "trait-emberline-tide-sense"
EMBER_GRACE = "trait-emberline-ember-grace"
SALT_GRIT = "trait-emberline-salt-grit"

# ── Faction ids ───────────────────────────────────────────────────────────
MERIDIAN = "faction-meridian-cartographe-505d8fe9"
CINDER_CHOIR = "faction-cinder-choir-c6eb5790"


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


def _flow(action, target="", context=None) -> Effect:
    return _eff("life_path", action, target, context=context)


def _enroll() -> Effect:
    return _flow("enroll")


def _next_step(target: str) -> Effect:
    return _flow("next_step", target)


def _gain(trait_id: str, die: str) -> Effect:
    """Gain a trait at ``die`` if absent, else step it up once."""
    return _eff("modify_trait", "gain_or_step_up", trait_id, result=die)


def _spend_razmerit(amount: int) -> Effect:
    return _eff("transfer_razmerit", "spend", "self", result=str(amount))


def _entry(label: str, description: str, min_v: int, max_v: int,
           cost_effects=None, effects=None) -> RollTableEntry:
    return RollTableEntry(
        label=label,
        description=description,
        min_value=min_v,
        max_value=max_v,
        cost_effects=cost_effects or [],
        effects=effects or [],
    )


# ── Life-path Entry enrichment ────────────────────────────────────────────
# Each path's Entry table: label → (skill trait, description). Every entry
# grants the Distinction (d8) + its skill (d6), enrolls the entity, and steps
# onward to the path's Muster table.
_PATH_ENTRIES = {
    "rt-riverborn-entry": {
        "muster": "rt-riverborn-muster",
        "entries": [
            ("River-brat", SALT_GRIT, "Raised barefoot on the banks, tough as river stone."),
            ("Ferry-child", RIVER_PILOTING, "Grew up poling the family ferry against the current."),
            ("Lamp-bearer", EMBER_TENDING, "Carried the bank-lanterns that keep the dark at bay."),
            ("Tide-singer", TIDE_SENSE, "Sang the tide's moods and learned to feel them shift."),
            ("Dock-rat", SALT_GRIT, "Worked the docks, learned every knot and every debt."),
            ("Drowned-kin", EMBER_GRACE, "Came back from the river changed — half-ember, light on your feet."),
        ],
    },
    "rt-cartographers-apprentice-entry": {
        "muster": "rt-cartographers-apprentice-muster",
        "entries": [
            ("Map-runner", CHART_LORE, "Carried fresh charts between the guild's survey camps."),
            ("Tide-reader", TIDE_SENSE, "Read the river's currents for the guild's soundings."),
            ("Ledger-clerk", CHART_LORE, "Kept the guild's chart-ledgers and learned the river by rote."),
            ("Needle-bearer", TIDE_SENSE, "Bore the surveyor's needle, felt true north in the water."),
            ("Surveyor", CHART_LORE, "Walked the banks and marked them true."),
            ("Anchor-sworn", SALT_GRIT, "Swore to hold the line where the chart ends."),
        ],
    },
    "rt-ember-touched-entry": {
        "muster": "rt-ember-touched-muster",
        "entries": [
            ("Cinder-kissed", EMBER_TENDING, "The river's fire left its mark and its warmth in you."),
            ("Glow-mad", EMBER_GRACE, "The glow took something; it left grace in its place."),
            ("Bell-woken", TIDE_SENSE, "Woke to the Drowned Bell — now you hear what others can't."),
            ("Ash-seer", EMBER_TENDING, "You read the ash, and the ash answers."),
            ("Hollow-burned", SALT_GRIT, "Burned hollow and didn't break."),
            ("Flood-survivor", EMBER_GRACE, "Outswam the flood and came back burning."),
        ],
    },
}


def _enrich_entry_tables(repo: EntityRepository) -> int:
    changed = 0
    for table_id, spec in _PATH_ENTRIES.items():
        table = repo.get_roll_table(table_id)
        if table is None:
            print(f"  SKIP {table_id}: not found")
            continue

        entries: list[RollTableEntry] = []
        for idx, (label, skill, description) in enumerate(spec["entries"], start=1):
            effects = [
                _enroll(),
                _gain(DISTINCTION, "d8"),
                _gain(skill, "d6"),
                _next_step(spec["muster"]),
            ]
            entries.append(_entry(label, description, idx, idx, effects=effects))

        table.entries = entries
        repo.update_roll_table(table)
        changed += 1
        print(f"  enriched {table_id} ({len(entries)} entries: enroll + Distinction d8 + skill d6)")

    return changed


# ── B58 roll-table-as-menu: support-cast archetype table ──────────────────
_SUPPORT_CAST = "rt-emberline-support-cast"

_SUPPORT_CAST_ENTRIES = [
    ("Ferryhand", RIVER_PILOTING, "A steady hand on the poles and the fares."),
    ("Chartist's Helper", CHART_LORE, "A junior map-mender for the Meridian Cartographers."),
    ("Ember-bearer", EMBER_TENDING, "Tends the lamps and coals that light the banks."),
    ("Tidecaller", TIDE_SENSE, "Reads the river's moods before they break."),
    ("Ash-dancer", EMBER_GRACE, "Moves through firefall like the smoke itself."),
    ("Saltblood", SALT_GRIT, "Raised rough where the salt meets the ember."),
]


def _seed_support_cast(repo: EntityRepository) -> int:
    entries: list[RollTableEntry] = []
    for idx, (label, skill, description) in enumerate(_SUPPORT_CAST_ENTRIES, start=1):
        entries.append(_entry(
            label,
            description,
            idx,
            idx,
            cost_effects=[_spend_razmerit(1)],
            effects=[_gain(DISTINCTION, "d8"), _gain(skill, "d6")],
        ))

    table = RollTable(
        id=_SUPPORT_CAST,
        name="Emberline Support Cast",
        universe="emberline",
        life_path=None,  # shared / general — not tied to a single life path
        scheme=RollTableScheme.RANGE,
        die=DieType.D6,
        entries=entries,
    )

    existed = repo.get_roll_table(_SUPPORT_CAST) is not None
    if existed:
        repo.update_roll_table(table)
    else:
        repo.create_roll_table(table)
    print(f"  {'updated' if existed else 'created'} {_SUPPORT_CAST} "
          f"({len(entries)} archetypes, 1 razmerit each, pay-then-gain)")
    return 1


# ── Faction wiring ────────────────────────────────────────────────────────
def _wire_factions(repo: EntityRepository) -> int:
    wiring = {
        MERIDIAN: ["lp-cartographers-apprentice"],
        CINDER_CHOIR: ["lp-ember-touched"],
    }
    changed = 0
    for faction_id, paths in wiring.items():
        faction = repo.get_entity(faction_id)
        if faction is None:
            print(f"  SKIP {faction_id}: not found")
            continue
        faction.suitable_life_path_ids = paths
        repo.update_entity(faction)
        changed += 1
        print(f"  wired {faction.name} → {paths}")
    return changed


def migrate() -> int:
    repo = EntityRepository()

    print("Enriching Emberline life-path Entry tables…")
    enriched = _enrich_entry_tables(repo)

    print("Seeding B58 support-cast menu table…")
    menu = _seed_support_cast(repo)

    print("Wiring factions to life paths…")
    wired = _wire_factions(repo)

    print(f"\nDone: {enriched} entry table(s) enriched, {menu} menu table(s) seeded, "
          f"{wired} faction(s) wired")
    return 0


if __name__ == "__main__":
    sys.exit(migrate())
