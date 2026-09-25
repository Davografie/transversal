"""One-off: move image metadata to the generalised `images` collection.

`B200` does two things to the same documents, so they are one pass:

1. **Renames the collection** `entity_images` → `images`. Arango has no rename,
   so this creates the target and copies every document **preserving `_key`** —
   image ids are referenced by the app and must not change.
2. **Generalises the owner.** A row used to carry ``entity_id`` /
   ``projection_id``, which could only ever mean an entity. It now carries
   ``owner_kind`` (``"entity"`` or ``"trait"``), ``owner_id``, and ``variant_id``
   (a projection for an entity, a traitsetting for a trait; empty = the
   owner-level *definition* image). Every pre-existing row is entity-owned, so
   the stamp is mechanical::

       owner_kind = "entity"
       owner_id   = entity_id
       variant_id = projection_id or None

The legacy fields are kept on the copied rows, and `entity_images` is left in
place, both as the rollback — see the design log's two-step.

**Idempotent, and meant to be re-run.** The live database is shared: the
containers at `:3000` keep running the older code until the rename merges, so an
image created during that window lands in `entity_images`. Re-running after the
merge picks those up. A key already present in `images` is never overwritten —
only topped up if it is somehow missing its owner fields.

Dry-run by default. Usage::

    docker compose exec api python -m transversal.migrate_images_owner
    docker compose exec api python -m transversal.migrate_images_owner --apply
"""

from __future__ import annotations

import sys

from transversal.db.arango import get_db

#: Hardcoded rather than imported from `db/arango.py`: this script spans the
#: rename, so it must not move when the constant does.
SOURCE = "entity_images"
TARGET = "images"

#: Arango rejects these on insert; `_key` is deliberately kept.
_STRIPPED = ("_id", "_rev")


def migrate(apply: bool = False) -> int:
    db = get_db()

    if not db.has_collection(SOURCE):
        print(f"nothing to do: {SOURCE} does not exist (already renamed?)")
        return 0

    source = db.collection(SOURCE)
    target = db.collection(TARGET) if db.has_collection(TARGET) else None
    if target is None:
        if not apply:
            print(f"DRY-RUN would create the {TARGET} collection")
        else:
            target = db.create_collection(TARGET, edge=False)

    total = 0
    copied = 0
    present = 0
    topped_up = 0
    with_variant = 0

    for doc in source.all():
        total += 1
        key = doc.get("_key")
        entity_id = doc.get("entity_id") or ""
        projection_id = doc.get("projection_id") or None
        if projection_id:
            with_variant += 1

        payload = {k: v for k, v in doc.items() if k not in _STRIPPED}
        payload["owner_kind"] = "entity"
        payload["owner_id"] = entity_id
        payload["variant_id"] = projection_id

        existing = target.get(key) if (target is not None and key) else None
        if existing is not None:
            present += 1
            # Defensive: a row written directly into `images` before this ever
            # ran, or copied by an earlier pass, but somehow without an owner.
            if not existing.get("owner_id"):
                print(f"TOP-UP {key} ({entity_id or 'no owner'})")
                if apply:
                    target.update(payload)
                topped_up += 1
            continue

        if not apply:
            if copied < 5:
                print(f"DRY-RUN would copy {key} ({entity_id or 'NO OWNER'}) "
                      f"variant={projection_id or '-'}")
            copied += 1
            continue

        target.insert(payload)
        copied += 1

    print()
    print("=== IMAGE OWNER MIGRATION ===")
    print(f"apply={apply}  {SOURCE} -> {TARGET}")
    print(f"  source documents:   {total}")
    print(f"  entity-owned:       {total - with_variant} with variant "
          f"{with_variant} projection-owned")
    print(f"  copied:             {copied}")
    print(f"  already present:    {present}")
    print(f"  topped up:          {topped_up}")
    if not apply:
        print("  (dry run — nothing written; re-run with --apply)")
    return 0


if __name__ == "__main__":
    sys.exit(migrate(apply="--apply" in sys.argv))
