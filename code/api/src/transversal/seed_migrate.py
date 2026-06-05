"""Seed migration: import location tree from old application data.

Reads the paste JSON, converts old entity IDs to Transversal location entities,
creates super edges, and copies images from the uploads directory.

Usage:
    PYTHONPATH=src python -m transversal.seed_migrate
"""

import json
import os
import re
import shutil
import sys
from pathlib import Path

# Parse the paste file
PASTE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".deepseek", "pastes")
PASTE_FILE = None
for f in sorted(os.listdir(PASTE_PATH), reverse=True):
    if f.startswith("paste-") and f.endswith(".md"):
        PASTE_FILE = os.path.join(PASTE_PATH, f)
        break

if not PASTE_FILE:
    print("No paste file found in", PASTE_PATH)
    sys.exit(1)

UPLOADS_DIR = "/home/dave/dev/transversal/media/uploads"
MEDIA_DIR = "/home/dave/dev/transversal2/media"

# Read and extract JSON from paste
with open(PASTE_FILE) as fh:
    content = fh.read()

# Find the JSON array
start = content.index("[")
json_str = content[start:]
data = json.loads(json_str)

print(f"Parsed {len(data)} locations from paste")

# Build id → entry map
id_map = {}
for entry in data:
    old_id = entry["_id"]
    numeric_id = old_id.split("/")[-1]
    id_map[old_id] = {
        "numeric_id": numeric_id,
        "new_id": f"loc-{numeric_id}",
        "name": entry["name"],
        "description": entry.get("description", ""),
        "parent_id": entry.get("parent"),
    }

# ── Seed into database ─────────────────────────────

from transversal.db.repository import EntityRepository
from transversal.domain import Entity, EntityType

repo = EntityRepository()

created = 0
for old_id, info in id_map.items():
    new_id = info["new_id"]
    if repo.get_entity(new_id):
        continue

    entity = Entity(
        id=new_id,
        type=EntityType.LOCATION,
        name=info["name"],
        current_universe="three_realms",
        current_location=new_id,
        razmerit=0,
    )
    repo.create_entity(entity)
    created += 1

print(f"Created {created} new location entities")

# ── Create super edges ─────────────────────────────

edge_count = 0
for old_id, info in id_map.items():
    parent_old_id = info["parent_id"]
    if not parent_old_id:
        continue

    parent_info = id_map.get(parent_old_id)
    if not parent_info:
        continue

    child_id = info["new_id"]
    parent_id = parent_info["new_id"]
    edge_key = f"edge:{child_id}:{parent_id}:super"

    if not repo._relationships.has(edge_key):
        repo._relationships.insert({
            "_key": edge_key,
            "_from": f"entities/{child_id}",
            "_to": f"entities/{parent_id}",
            "type": "super",
        })
        edge_count += 1

print(f"Created {edge_count} super edges")

# ── Copy images ────────────────────────────────────

image_count = 0
for old_id, info in id_map.items():
    numeric_id = info["numeric_id"]
    src = os.path.join(UPLOADS_DIR, numeric_id, "original.png")
    if not os.path.isfile(src):
        continue

    dst_name = f"{info['new_id']}.png"
    dst = os.path.join(MEDIA_DIR, dst_name)

    if os.path.isfile(dst):
        # Update entity background_image if not set
        entity = repo.get_entity(info["new_id"])
        if entity and not entity.background_image:
            entity.background_image = f"/media/{dst_name}"
            repo.update_entity(entity)
            image_count += 1
        continue

    shutil.copy2(src, dst)

    # Update entity background_image
    entity = repo.get_entity(info["new_id"])
    if entity:
        entity.background_image = f"/media/{dst_name}"
        repo.update_entity(entity)
        image_count += 1

print(f"Copied/set images for {image_count} locations")
print("Migration complete.")
