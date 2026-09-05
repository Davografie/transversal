"""Phase 6 migration: old ``Players`` → new ``players`` + ``agency`` edges.

- Players are name-matched (case-insensitive) against the existing new-app
  ``players`` collection; matches reuse the existing key. New players get a
  deterministic ``player-{md5(name)[:6]}`` key (idempotent, matches the
  ``player-{hex6}`` convention).
- ``agency`` relations (``Players/* → Entities/*``) become ``relationships``
  edges of type ``agency``, keyed ``edge:{player}:{entity}:agency``.
- The old ``count`` / ``last_used`` recency fields are dropped — the new model
  has no equivalent (see report).

Dry-run by default. Pass ``--apply`` to write.

Usage:
    docker compose exec api python -m transversal.migrate_players [--apply]
"""

from __future__ import annotations

import hashlib
import sys
from collections import Counter

from transversal.db.arango import ENTITIES, PLAYERS, RELATIONSHIPS, get_db
from transversal.migrate_common import build_entity_key_map, load_json


def _player_key(name: str) -> str:
    return f"player-{hashlib.md5(name.lower().strip().encode()).hexdigest()[:6]}"


def migrate(apply: bool = False) -> int:
    entities = load_json("entities.json")
    relations = load_json("relations.json")
    old_players = load_json("players.json")

    entity_key_map = build_entity_key_map(entities, relations)
    agency = [r for r in relations if r.get("type") == "agency"]

    db = get_db()
    player_col = db.collection(PLAYERS)
    rel_col = db.collection(RELATIONSHIPS)

    # Existing players: lowercase-name → key.
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
            "main": False,  # troupe-play B54: no old-app main concept; mains designated post-migration
        }
        if apply and rel_col.get(edge_key) is None:
            rel_col.insert(doc)

    print("=== PLAYERS + AGENCY MIGRATION (Phase 6) ===")
    print(f"apply={apply}")
    print(f"source players: {len(old_players)}; source agency: {len(agency)}")
    for k in sorted(report):
        print(f"  {k}: {report[k]}")
    return 0


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    sys.exit(migrate(apply=apply))
