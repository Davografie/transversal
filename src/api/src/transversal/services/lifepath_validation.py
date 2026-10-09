"""Structural validation for a wrapped life path ([[B266]]).

The wrapper moved the flow out of the entries and into the path, which makes a
whole class of authoring mistake newly possible: an edge that names a step the
path does not have, an entry step that names nothing, a row bound twice. The
executor ends a term rather than looping when it meets one, so the failure is
survivable — but silent, which is why this exists.

What it checks, and what it deliberately does not:

* every ``steps[].id`` is unique, and ``entry_step`` names one of them;
* every ``steps[].table_id`` resolves to a real roll table;
* every ``bindings[].next`` names a step in **this** path (a step id, not a table
  id — the whole point of the inversion);
* every binding key names a row that exists in the table it sits on;
* no row is bound twice on one step;
* a ``draft`` exit names a path that exists.

It does **not** check effect targets, which is [[B156]]'s carrier-agnostic job,
and it does not re-derive the target half — one implementation of the resolution
rules or the two drift. Returns a list of human-readable problems; empty is valid.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from transversal.services.roll_table import row_key

if TYPE_CHECKING:
    from transversal.domain import LifePath


def validate_life_path(lp: "LifePath", repo) -> list[str]:
    """Every structural problem with this path, phrased for an author."""
    problems: list[str] = []

    if not lp.steps:
        # Not an error: a pre-wrapper path is legal and the executor shims it.
        # It IS worth saying, because such a path's flow still lives in its tables.
        return problems

    step_ids = [s.id for s in lp.steps]
    seen: set[str] = set()
    for sid in step_ids:
        if sid in seen:
            problems.append(f"duplicate step id {sid!r}")
        seen.add(sid)

    if not lp.entry_step:
        problems.append("path declares steps but no entry_step")
    elif lp.entry_step not in seen:
        problems.append(f"entry_step {lp.entry_step!r} is not one of its steps")

    for step in lp.steps:
        table = repo.get_roll_table(step.table_id)
        if table is None:
            problems.append(f"step {step.id!r}: table {step.table_id!r} does not exist")
            continue

        if step.next and step.next not in seen:
            problems.append(
                f"step {step.id!r}: next {step.next!r} is not a step in this path"
            )

        keys = {row_key(e, i) for i, e in enumerate(table.entries)}
        bound: set[str] = set()
        for binding in step.bindings:
            if binding.key not in keys:
                problems.append(
                    f"step {step.id!r}: binding names row {binding.key!r}, "
                    f"which {table.id!r} does not have"
                )
            if binding.key in bound:
                problems.append(
                    f"step {step.id!r}: row {binding.key!r} is bound twice"
                )
            bound.add(binding.key)

            if binding.next and binding.next not in seen:
                problems.append(
                    f"step {step.id!r} row {binding.key!r}: next {binding.next!r} "
                    f"is not a step in this path"
                )
            if binding.next and binding.exit_kind:
                problems.append(
                    f"step {step.id!r} row {binding.key!r}: both next "
                    f"{binding.next!r} and exit {binding.exit_kind!r} — one or the other"
                )
            if binding.exit_kind == "draft":
                if not binding.exit_path:
                    problems.append(
                        f"step {step.id!r} row {binding.key!r}: draft with no destination"
                    )
                elif repo.get_lifepath(binding.exit_path) is None:
                    problems.append(
                        f"step {step.id!r} row {binding.key!r}: draft to unknown "
                        f"path {binding.exit_path!r}"
                    )
            elif binding.exit_path:
                problems.append(
                    f"step {step.id!r} row {binding.key!r}: exit_path set but exit "
                    f"kind is {binding.exit_kind!r}"
                )

    return problems
