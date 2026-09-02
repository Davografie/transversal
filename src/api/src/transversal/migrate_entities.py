"""Phase 1 migration: old Entities → new entities (and the old→new key map).

Reads old-app JSON dumps from /app/data and migrates the `Entities` collection
into the new `entities` collection. Produces a persistent old→new key map so
later phases (relationships, traitsettings, traitsetsettings) can remap their
``Entities/{numeric}`` references.

Conventions (see [[Data Migration Plan]]):
- ``npc`` / ``gm`` → ``gmc``; other types unchanged.
- old universe locations (direct children of Multiverse ``Entities/2``) → new
  ``universe`` entities; all other locations → ``location``.
- ID: ``{type}-{old_numeric_key}`` for non-universes (matches the existing
  ``loc-{numeric}`` convention); ``universe-{slug}`` for universes.
- archetype templates (``is_archetype``) are dropped (D1).

Dry-run by default. Pass ``--apply`` to write.

Usage:
    docker compose exec api python -m transversal.migrate_entities [--apply]
"""

from __future__ import annotations

import json
import re
import sys

from transversal.db.repository import EntityRepository
from transversal.domain import Entity, EntityType, RatingType, TraitSetting

DATA_DIR = "/app/data"
MULTIVERSE = "2"  # Entities/2 = Multiverse root

# The registry trait that carries an entity's freeform description as `notes`.
DESCRIPTION_TRAIT = "trait-description"
DESCRIPTION_TRAITSET = "ts-secrets-1b55"

# Type → new-key prefix. Locations use the short `loc-` prefix (established by
# the already-migrated 153 locations); everything else uses its type name.
TYPE_PREFIX = {
    "character": "character",
    "location": "loc",
    "faction": "faction",
    "asset": "asset",
    "npc": "gmc",
    "gm": "gmc",
}

# Universe name → slug. Matches the existing universe entity keys where present;
# new universes get a fresh slug. (Dry-run prints these for review.)
UNIVERSE_SLUGS = {
    "Earth": "earth",
    "Three Realms": "three_realms",
    "Intergalactic Planetary": "intergalactic-planetary",
    "the Dreamlands": "the-dreamlands",
    "Chromotopia": "chromotopia",
    "Living World": "living-world",
    "Valhalla": "valhalla",
    "Albinora": "albinora",
    "Ælor Cıtar": "aelor-citar",
    "Superhero World": "superhero-world",
    "The Floating Vagabond": "the-floating-vagabond",
    "One Piece": "one-piece",
    "Magic: the Gathering": "magic-the-gathering",
    "Discworld": "discworld",
    "Varenya": "varenya",
}


def _slugify(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[:'\"]", "", s)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"[^a-z0-9_-]", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s


def load_json(name: str) -> list[dict]:
    with open(f"{DATA_DIR}/{name}") as f:
        return json.load(f)


def build_universe_map(entities: list[dict], relations: list[dict]) -> dict[str, str]:
    """Map old universe numeric key → slug, from the 15 children of Multiverse."""
    # child → parent from super edges
    parent = {r["_from"]: r["_to"] for r in relations if r["type"] == "super"}
    unis = {}
    for e in entities:
        if e["_id"] in parent and parent[e["_id"]] == f"Entities/{MULTIVERSE}":
            slug = UNIVERSE_SLUGS.get(e["name"], _slugify(e["name"]))
            unis[e["_key"]] = slug
    return unis


def resolve_universe_key(
    entity_key: str, parent_map: dict[str, str], universe_keys: set[str]
) -> str | None:
    """Walk super chain from an entity up to the first universe key."""
    cur = entity_key
    seen = set()
    while cur and cur not in seen:
        if cur in universe_keys:
            return cur
        seen.add(cur)
        cur = parent_map.get(cur, "")
    return None


def migrate(apply: bool = False) -> int:
    entities = load_json("entities.json")
    relations = load_json("relations.json")

    parent_map = {
        r["_from"].split("/")[1]: r["_to"].split("/")[1]
        for r in relations
        if r["type"] == "super"
    }
    universe_map = build_universe_map(entities, relations)
    universe_keys = set(universe_map.keys())

    repo = EntityRepository()

    # Existing new-entity keys — for idempotency + reuse of already-migrated data.
    existing = {e.id for e in repo.list_all_entities()}

    old_to_new: dict[str, str] = {}
    report = {
        "total_old": len(entities),
        "dropped_archetype": 0,
        "skipped_system": 0,
        "skipped_existing": 0,
        "created_entity": 0,
        "created_universe": 0,
        "type_map": {},
        "dropped_fields": ["active", "favorite",
                           "imagened", "imagening", "archetype_id",
                           "subtitle", "entity_type", "is_archetype"],
        "mapped_fields": ["pp -> razmerit", "description -> traitsetting.notes (trait-description)"],
        "universe_slugs": universe_map,
    }

    for e in entities:
        key = e["_key"]
        name = e.get("name", "")
        old_type = e.get("type")
        is_arch = e.get("is_archetype") is True

        # System entities with no new-model equivalent
        if key == MULTIVERSE or (key == "1" and old_type == "gm"):
            report["skipped_system"] += 1
            continue

        # Universe classification takes precedence — a universe flagged
        # is_archetype (e.g. "The Floating Vagabond") still migrates as a universe.
        is_universe = old_type == "location" and key in universe_keys

        # D1 — drop archetype templates (but never a universe)
        if is_arch and not is_universe:
            report["dropped_archetype"] += 1
            continue

        # Type remap
        if old_type == "npc" or old_type == "gm":
            new_type = EntityType.GMC
        elif is_universe:
            new_type = EntityType.UNIVERSE
        elif old_type in ("character", "faction", "asset", "location"):
            new_type = EntityType(old_type)
        else:
            report["skipped_system"] += 1
            continue

        report["type_map"][old_type] = report["type_map"].get(old_type, 0) + 1

        # Resolve universe (which universe does this entity belong to?)
        uni_key = resolve_universe_key(key, parent_map, universe_keys)
        current_universe = universe_map.get(uni_key, "") if uni_key else ""

        # Resolve current_location: the entity's parent in the super chain
        parent_new = None
        parent_old = parent_map.get(key)
        if parent_old and parent_old != MULTIVERSE:
            if parent_old in universe_keys:
                parent_new = f"universe-{universe_map[parent_old]}"
            else:
                parent_new = f"loc-{parent_old}"

        # ID
        if new_type == EntityType.UNIVERSE:
            new_id = f"universe-{universe_map[key]}"
        else:
            prefix = TYPE_PREFIX[old_type]
            new_id = f"{prefix}-{key}"

        old_to_new[f"Entities/{key}"] = new_id

        if new_id in existing:
            report["skipped_existing"] += 1
        else:
            doc = Entity(
                id=new_id,
                type=new_type,
                name=name,
                razmerit=e.get("pp") or 0,
                current_universe=current_universe,
                current_location=parent_new,
            )
            if new_type == EntityType.UNIVERSE:
                report["created_universe"] += 1
            else:
                report["created_entity"] += 1
            if apply:
                repo.create_entity(doc)

        # Description → traitsetting.notes on the registry trait `trait-description`.
        # Runs for every migrated entity (new or pre-existing), so descriptions
        # land even on the 136 already-migrated locations.
        desc = (e.get("description") or "").strip()
        if desc:
            ts_id = f"{new_id}:{DESCRIPTION_TRAIT}"
            if repo.get_traitsetting(ts_id) is None:
                report["description_notes"] = report.get("description_notes", 0) + 1
                if apply:
                    repo.create_traitsetting(TraitSetting(
                        id=ts_id,
                        entity_id=new_id,
                        trait_id=DESCRIPTION_TRAIT,
                        from_type="entity",
                        traitset_id=DESCRIPTION_TRAITSET,
                        rating_type=RatingType.EMPTY,
                        dice=[],
                        notes=desc,
                    ))

    # Persist the key map (always, even dry-run, so later phases can inspect it)
    if apply:
        with open(f"{DATA_DIR}/old_to_new_keys.json", "w") as f:
            json.dump(old_to_new, f, indent=2)

    print("=== ENTITY MIGRATION (Phase 1) ===")
    print(f"apply={apply}")
    for k, v in report.items():
        if k == "universe_slugs":
            print(f"  universe_slugs:")
            for uk, us in sorted(v.items()):
                print(f"    {uk}: {us}")
        elif k == "dropped_fields":
            print(f"  dropped_fields: {', '.join(v)}")
        else:
            print(f"  {k}: {v}")
    print(f"  old_to_new keys mapped: {len(old_to_new)}")
    return 0


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    sys.exit(migrate(apply=apply))
