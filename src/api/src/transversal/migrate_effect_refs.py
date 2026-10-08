"""Store the effect path fold: move an effect's positional paths into its refs.

[[B261]] gave an effect one vocabulary for the paths it names. A ``RefDef`` may
declare ``legacy_field`` — the positional field it supersedes — and the resolver
folds that field into the ref every time the effect resolves
(``services.effect_refs.effective_refs``). This pass does the fold **once**, into
the stored content, so the positional fields can eventually be deleted.

It writes exactly what the resolver computes: `materialise_refs` is the same fold,
not a second implementation, so there is nothing to drift.

**The exception, and why this is not a blanket sweep.** The fold flips which
branch the engine takes, and two resolvers disagree on purpose when a path finds
nobody: ``resolve_effect_entity`` fails **open** (the effect acts on the acting
entity) while ``resolve_refs`` fails **closed** (nothing is applied). A subject
path also stops being resolved once — it fans out with the other refs. So an
effect carrying an ``entity_spec`` is **held back by default** and reported;
``--include-subject-paths`` migrates them too, which is a deliberate behaviour
change an author should accept rather than a silent one. Measured on the live
corpus, that is the difference between 258 behaviour-identical effects and the
2 that decide differently.

Idempotent: a migrated effect has nothing left to fold, so a re-run is a no-op.

Usage:
    docker compose exec api python -m transversal.migrate_effect_refs
    docker compose exec api python -m transversal.migrate_effect_refs --apply
    docker compose exec api python -m transversal.migrate_effect_refs --apply --include-subject-paths

``--apply`` writes a JSON backup of every document it is about to change, beside
the working directory, before changing anything.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

from transversal.domain import Effect
from transversal.services.effect_refs import materialise_refs


def holds_back(effect: Effect) -> bool:
    """Is this effect in the class whose behaviour changes when it is folded?

    A subject path (`entity_spec`) is the one that disagrees: it is resolved
    **once** before dispatch today and fans out once it is a reference, and a
    subject that resolves to nobody is fail-open today and fail-closed as a ref.
    """
    return effect.entity_spec is not None


def fold_effects(effects: list[Effect], include_subject_paths: bool = False):
    """Fold every effect that can be folded, in place-safe fashion.

    Returns ``(folded, held_back, unusable)`` — the new list, how many were left
    alone because of the subject-path exception, and the effects that could not be
    read at all (a row stored in the wire shape, for instance).
    """
    folded: list[Effect] = []
    held = 0
    unusable = 0
    for effect in effects:
        if holds_back(effect) and not include_subject_paths:
            held += 1
            folded.append(effect)
            continue
        try:
            folded.append(materialise_refs(effect))
        except Exception:
            unusable += 1
            folded.append(effect)
    return folded, held, unusable


def _changed(before: list, after: list) -> bool:
    return any(a is not b for a, b in zip(before, after))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true",
                        help="write the changes (default: report only)")
    parser.add_argument("--include-subject-paths", action="store_true",
                        help="also fold effects carrying an entity_spec — a "
                             "deliberate behaviour change (see the module docstring)")
    parser.add_argument("--backup-dir", default=".",
                        help="where the pre-change backup is written; must be a "
                             "mounted path or the file dies with the container")
    args = parser.parse_args(argv)

    from transversal.main import _get_repo

    repo = _get_repo()
    # Everything the pass would change, gathered *before* anything is written, so
    # the backup can be written first and a failure mid-way cannot leave changes
    # with no record of what they were.
    planned: list[tuple[str, str, object, object]] = []   # kind, id, before, after
    totals = {"documents": 0, "effects": 0, "changed": 0, "held_back": 0, "unusable": 0}

    for sfx in repo.get_all_sfxs():
        totals["documents"] += 1
        totals["effects"] += len(sfx.effects)
        if not sfx.effects:
            continue
        folded, held, unusable = fold_effects(sfx.effects, args.include_subject_paths)
        totals["held_back"] += held
        totals["unusable"] += unusable
        if _changed(sfx.effects, folded):
            totals["changed"] += 1
            planned.append(("sfx", sfx.id, sfx, sfx.model_copy(update={"effects": folded})))

    for table in repo.list_roll_tables():
        if not table.entries:
            continue
        totals["documents"] += 1
        new_entries = []
        table_changed = False
        for entry in table.entries:
            new_effects, held_a, unusable_a = fold_effects(entry.effects, args.include_subject_paths)
            new_costs, held_b, unusable_b = fold_effects(entry.cost_effects, args.include_subject_paths)
            totals["effects"] += len(entry.effects) + len(entry.cost_effects)
            totals["held_back"] += held_a + held_b
            totals["unusable"] += unusable_a + unusable_b
            if _changed(entry.effects, new_effects) or _changed(entry.cost_effects, new_costs):
                table_changed = True
                new_entries.append(entry.model_copy(
                    update={"effects": new_effects, "cost_effects": new_costs}))
            else:
                new_entries.append(entry)
        if table_changed:
            totals["changed"] += 1
            planned.append(("roll_table", table.id, table,
                            table.model_copy(update={"entries": new_entries})))

    mode = "APPLIED" if args.apply else "DRY RUN (nothing written)"
    print(f"\n{mode}")
    print(f"  documents examined      {totals['documents']}")
    print(f"  effects examined        {totals['effects']}")
    print(f"  documents that change   {totals['changed']}")
    print(f"  held back (entity_spec) {totals['held_back']}")
    print(f"  unreadable effects      {totals['unusable']}")

    if not args.apply:
        print("\n  re-run with --apply to write. The backup is written *before* the")
        print("  first change, so nothing is written without a record of the old rows.")
        return 0

    if not planned:
        print("\n  nothing to do — every effect already reads from its references.")
        return 0

    # The backup comes first, and a backup that cannot be written stops the run:
    # a change with no record of what it replaced is not recoverable. Write it
    # somewhere durable — for `docker compose exec api` that is the mounted main
    # checkout; for a throwaway container, mount `--backup-dir` or it dies with it.
    backup = {
        "kind": "B261 effect-refs migration — the documents as they were before folding",
        "written_at": datetime.now(timezone.utc).isoformat(),
        "documents": [{"kind": k, "id": i, "before": b.model_dump()} for k, i, b, _ in planned],
    }
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.abspath(os.path.join(args.backup_dir, f"effect-refs-backup-{stamp}.json"))
    try:
        with open(path, "w") as fh:
            json.dump(backup, fh, indent=1)
    except OSError as exc:
        print(f"\n  ABORTED: could not write the backup to {path} ({exc}).")
        print("  Nothing was changed. Pass --backup-dir pointing at a mounted path.")
        return 1
    print(f"  backup written          {path}  ({len(planned)} documents)")

    for kind, doc_id, _before, after in planned:
        if kind == "sfx":
            repo.update_sfx(after)
        else:
            repo.update_roll_table(after)
    print(f"\n  {len(planned)} documents written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
