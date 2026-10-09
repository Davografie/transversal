"""Migrate life paths to the wrapper model ([[B266]]).

Before: a life path was an entry table, and the *flow* lived in the entries'
``life_path`` effects (``next_step`` / ``muster`` / ``force_muster`` /
``enroll`` / ``draft``). ``RollTable.life_path`` said which path owned a table.

After: the path declares the tables it **wraps** (``steps``) and what each row
means to it (``LifePathBinding``). Roll tables carry no flow at all.

Measured on the live collection before writing this (2026-10-09): 9 paths,
31 tables, 163 entries, 103 ``next_step`` effects — 99 of them literal targets
that all exist, **0 token targets**, 4 empty (deliberate term-ends). The
return-address machinery was never used by content, so nothing has to be
translated into it; the four empty targets become ``next: ""`` and the rest
become plain step edges.

What it does, per life path:

1. Walks the tables reachable from ``entry_table_id`` by following ``next_step``
   (the same walk the canvas does) and gives each a **step id** in visit order.
2. For every row carrying any flow effect, writes a binding: ``next_step`` →
   ``next`` (a *step* id), ``muster``/``force_muster`` → ``exit_kind``,
   ``draft`` → ``exit_kind`` + ``exit_path``, ``enroll`` → ``enroll``.
3. Strips those ``life_path`` effects from the entries — the flow now lives in
   the path, and leaving both would give one edge two sources of truth.
4. Sets ``entry_step``.

Separately, every entry in every table gets a stable ``key`` if it has none, so a
binding has something durable to name; the key is derived once from the scheme and
then **stored**, so re-cutting a band cannot orphan the bindings written against
it.

Idempotent: keys are only written when absent, and a path that already declares
steps is left exactly as it is. Safe to re-run; it is also safe to run *before*
anyone edits — but it rewrites rows, so it does not touch a path twice.

``RollTable.life_path`` is deliberately **not** cleared here. Readers still use it
(the canvas, the GM grouping, ``target_resolver``); it is dropped in a later step
once they read the wrapper instead.

⚠ **This migration and its code must land together.** It strips the flow effects
that the *deployed* executor reads, so running it against a database while the
old code is still serving breaks every in-flight term — the entry resolves, no
flow effect fires, and the term sits on the same step. Run it as part of the same
release as ``services/lifepath_executor.py``'s wrapper support, never before it.
(Taken 2026-10-09 against the pre-wrapper api by mistake, and restored from the
backup this script's sibling took; hence the warning.)

A path with no ``entry_table_id`` but exactly one owned table is wrapped as a
single entry step — such a path was unusable before (``start_term`` refuses a path
with no entry), and the table would otherwise be left unwrapped and orphaned. The
paths this affects are named in the output.

Usage:
    docker compose exec api python -m transversal.migrate_lifepath_wrapper
"""

from __future__ import annotations

import sys

from transversal.db.repository import EntityRepository
from transversal.domain import (
    LifePathBinding,
    LifePathStep,
)
from transversal.services.effect_refs import target_value
from transversal.services.effects_registry.lookup import get_action_meta_for
from transversal.services.roll_table import row_key

FLOW_ACTIONS = ("next_step", "muster", "force_muster", "enroll", "draft")


def _target(eff) -> str:
    return target_value(eff, get_action_meta_for(eff.type, eff.action))


def _walk(repo, entry_table_id: str) -> list[str]:
    """Tables reachable from the entry, in visit order — the canvas's own walk."""
    order: list[str] = []
    seen: set[str] = set()
    queue = [entry_table_id]
    while queue:
        tid = queue.pop(0)
        if tid in seen or not tid:
            continue
        table = repo.get_roll_table(tid)
        if table is None:
            continue
        seen.add(tid)
        order.append(tid)
        for entry in table.entries:
            for eff in entry.effects:
                if eff.type == "life_path" and eff.action == "next_step":
                    target = _target(eff)
                    if target and not target.startswith("{") and target not in seen:
                        queue.append(target)
    return order


def _ensure_keys(repo, table) -> int:
    """Give every row a stored key, once. Returns how many were written."""
    written = 0
    for i, entry in enumerate(table.entries):
        if not entry.key:
            entry.key = row_key(entry, i)
            written += 1
    if written:
        repo.update_roll_table(table)
    return written


def _bindings_for(table, step_ids: dict[str, str]) -> tuple[list[LifePathBinding], int]:
    """The path's overlay for this table, from the flow effects currently on it."""
    bindings: list[LifePathBinding] = []
    stripped = 0

    for i, entry in enumerate(table.entries):
        flow = [e for e in entry.effects
                if e.type == "life_path" and e.action in FLOW_ACTIONS]
        if not flow:
            continue

        binding = LifePathBinding(key=row_key(entry, i))
        for eff in flow:
            if eff.action == "next_step":
                target = _target(eff)
                if target.startswith("{"):
                    # `{choose:table}` — a deferred player choice, not an edge.
                    # None live; left as an empty edge and reported.
                    print(f"    ! {table.id}: token target {target!r} on "
                          f"{entry.label!r} — not migrated (no live content uses it)")
                    target = ""
                binding.next = step_ids.get(target, "")
                if target and not binding.next:
                    print(f"    ! {table.id}: next_step -> {target!r} is outside the "
                          f"path; edge left empty on {entry.label!r}")
            elif eff.action == "enroll":
                binding.enroll = True
            elif eff.action in ("muster", "force_muster"):
                binding.exit_kind = eff.action
            elif eff.action == "draft":
                binding.exit_kind = "draft"
                binding.exit_path = _target(eff)

        bindings.append(binding)
        entry.effects = [e for e in entry.effects if e.type != "life_path"]
        stripped += 1

    return bindings, stripped


def migrate() -> int:
    repo = EntityRepository()
    tables = {t.id: t for t in repo.list_roll_tables(None)}
    paths = repo.list_all_lifepaths()

    keys_written = sum(_ensure_keys(repo, t) for t in tables.values())
    print(f"row keys: {keys_written} assigned across {len(tables)} tables")

    migrated = 0
    touched: set[str] = set()
    for lp in paths:
        if lp.steps:
            print(f"  - {lp.id}: already wraps {len(lp.steps)} step(s); left alone")
            continue

        entry = lp.entry_table_id
        if not entry:
            owned = [t.id for t in tables.values() if t.life_path == lp.id]
            if len(owned) == 1:
                entry = owned[0]
                print(f"  * {lp.id}: no entry table; wrapping its single owned "
                      f"table {entry!r} (it was unusable before)")
            else:
                print(f"  - {lp.id}: no entry table and {len(owned)} owned table(s); "
                      f"left unwrapped")
                continue

        order = _walk(repo, entry)
        if not order:
            print(f"  - {lp.id}: entry {entry!r} resolves to no table; left unwrapped")
            continue

        # Step ids are positional and stable *because* this runs once: an existing
        # path is never re-derived, so an author's later reorder cannot shift them.
        step_ids = {tid: f"s{n + 1}" for n, tid in enumerate(order)}

        steps = []
        for tid in order:
            table = tables[tid]
            bindings, stripped = _bindings_for(table, step_ids)
            repo.update_roll_table(table)
            touched.add(tid)
            steps.append(LifePathStep(
                id=step_ids[tid],
                table_id=tid,
                label=table.name,
                bindings=bindings,
            ))
            print(f"  + {lp.id} {step_ids[tid]} <- {tid} "
                  f"({len(bindings)} binding(s), {stripped} row(s) stripped of flow)")

        lp.entry_step = step_ids[entry]
        lp.steps = steps
        repo.update_lifepath(lp)
        migrated += 1

    print(f"\nDone: {migrated} path(s) migrated, {len(touched)} table(s) rewritten")
    return 0


if __name__ == "__main__":
    sys.exit(migrate())
