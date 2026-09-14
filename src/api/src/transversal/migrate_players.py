"""Phase 6 migration: old ``Players`` → new ``players`` + ``agency``/``support`` edges.

- Players are name-matched (case-insensitive) against the existing new-app
  ``players`` collection; matches reuse the existing key. New players get a
  deterministic ``player-{md5(name)[:6]}`` key (idempotent, matches the
  ``player-{hex6}`` convention).
- ``agency`` relations (``Players/* → Entities/*``) become ``relationships``
  edges of type ``agency``, keyed ``edge:{player}:{entity}:agency``.
- ``main`` is derived from the old archetypes: an agency-owned ``character``
  inheriting ``default character`` (Entities/3) but **not** ``support
  character`` (Entities/206403975) is a main.
- ``support`` edges (SC → main) are derived by following a support character's
  ``relation`` edges (both directions) to *other players'* mains; a support
  character may support multiple mains (one edge each).
- The old ``count`` / ``last_used`` recency fields are dropped — recency now
  lives in spotlight state (stamped at runtime), not migration.
- ``--include-archetypes`` resolves agency targets that migrated as Phase 2b
  archetype GMCs (e.g. the old ``Dvanda`` template).

Dry-run by default. Pass ``--apply`` to write.

Usage:
    docker compose exec api python -m transversal.migrate_players [--apply]
    docker compose exec api python -m transversal.migrate_players --apply --include-archetypes
"""

from __future__ import annotations

import hashlib
import sys
from collections import Counter, defaultdict

from transversal.db.arango import ENTITIES, PLAYERS, RELATIONSHIPS, get_db
from transversal.migrate_common import (
    build_archetype_depths,
    build_entity_key_map,
    load_json,
)

DEFAULT_CHARACTER = "Entities/3"          # "default character" = player-character archetype
SUPPORT_CHARACTER = "Entities/206403975"  # "support character" archetype (inherits default)


def _player_key(name: str) -> str:
    return f"player-{hashlib.md5(name.lower().strip().encode()).hexdigest()[:6]}"


def migrate(apply: bool = False, include_archetypes: bool = False) -> int:
    entities = load_json("entities.json")
    relations = load_json("relations.json")
    old_players = load_json("players.json")

    entity_key_map = build_entity_key_map(
        entities, relations, include_archetypes=include_archetypes
    )
    archetype_depths = build_archetype_depths(relations)
    entity_type = {e["_key"]: e.get("type") for e in entities}

    agency = [r for r in relations if r.get("type") == "agency"]
    relation_edges = [r for r in relations if r.get("type") == "relation"]

    # relation adjacency (undirected: both directions), entity ref → related refs
    related: dict[str, set[str]] = defaultdict(set)
    for r in relation_edges:
        related[r["_from"]].add(r["_to"])
        related[r["_to"]].add(r["_from"])

    owner = {r["_to"]: r["_from"] for r in agency}  # entity ref → player ref

    def _anc(ref: str) -> dict[str, int]:
        return archetype_depths.get(ref, {})

    def is_support(ref: str) -> bool:
        return SUPPORT_CHARACTER in _anc(ref)

    def is_main(ref: str) -> bool:
        anc = _anc(ref)
        return DEFAULT_CHARACTER in anc and SUPPORT_CHARACTER not in anc

    # agency-owned mains: character type + default (not support)
    main_entities = {
        e for e in owner
        if entity_type.get(e.split("/")[1]) == "character" and is_main(e)
    }
    # agency-owned support characters
    support_entities = {e for e in owner if is_support(e)}

    db = get_db()
    player_col = db.collection(PLAYERS)
    rel_col = db.collection(RELATIONSHIPS)

    existing_by_name = {
        (p.get("name") or "").lower().strip(): p["_key"] for p in player_col.all()
    }

    report: Counter = Counter()

    # old Players/{key} → new player key
    old_to_new_player: dict[str, str] = {}
    for p in old_players:
        name = p.get("name") or ""
        key = p["_key"]
        matched = existing_by_name.get(name.lower().strip())
        if matched is not None:
            old_to_new_player[key] = matched
            report["player_matched"] += 1
            continue
        new_key = _player_key(name)
        old_to_new_player[key] = new_key
        report["player_created"] += 1
        if apply and player_col.get(new_key) is None:
            player_col.insert({"_key": new_key, "name": name, "role": "player"})

    # agency edges
    for r in agency:
        player_key = r["_from"].split("/")[1]
        entity_ref = r["_to"]
        new_player = old_to_new_player.get(player_key)
        new_entity = entity_key_map.get(entity_ref)
        if new_player is None:
            report["skip_agency_player_missing"] += 1
            continue
        if new_entity is None:
            report["skip_agency_entity_dangling"] += 1
            continue

        report["agency_created"] += 1
        edge_key = f"edge:{new_player}:{new_entity}:agency"
        doc = {
            "_key": edge_key,
            "_from": f"{PLAYERS}/{new_player}",
            "_to": f"{ENTITIES}/{new_entity}",
            "type": "agency",
            "main": entity_ref in main_entities,
        }
        if apply and rel_col.get(edge_key) is None:
            rel_col.insert(doc)

    # support edges: SC → main (another player's main), via relation adjacency
    for sc in support_entities:
        sc_player = owner[sc]
        new_sc = entity_key_map.get(sc)
        if new_sc is None:
            report["skip_support_sc_dangling"] += 1
            continue
        for target in related.get(sc, set()):
            if target not in main_entities or owner.get(target) == sc_player:
                continue
            new_main = entity_key_map.get(target)
            if new_main is None:
                continue
            report["support_created"] += 1
            edge_key = f"edge:{new_sc}:{new_main}:support"
            doc = {
                "_key": edge_key,
                "_from": f"{ENTITIES}/{new_sc}",
                "_to": f"{ENTITIES}/{new_main}",
                "type": "support",
            }
            if apply and rel_col.get(edge_key) is None:
                rel_col.insert(doc)

    print("=== PLAYERS + AGENCY + SUPPORT MIGRATION (Phase 6) ===")
    print(f"apply={apply}")
    print(f"source players: {len(old_players)}; source agency: {len(agency)}")
    print(f"mains: {len(main_entities)}; support chars: {len(support_entities)}")
    for k in sorted(report):
        print(f"  {k}: {report[k]}")
    return 0


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    include_archetypes = "--include-archetypes" in sys.argv
    sys.exit(migrate(apply=apply, include_archetypes=include_archetypes))
