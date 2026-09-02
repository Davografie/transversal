"""Shared helpers for the old-app → new-app migration.

Centralizes the deterministic old→new entity key map so every migration phase
(entities, relationships, traitsettings, traitsetsettings) remaps the same
``Entities/{numeric}`` references the same way.
"""

from __future__ import annotations

import json
import re

DATA_DIR = "/app/data"
MULTIVERSE = "2"  # Entities/2 = Multiverse root

# Type → new-key prefix. Locations use the short `loc-` prefix (established by
# the already-migrated locations); everything else uses its type name.
TYPE_PREFIX = {
    "character": "character",
    "location": "loc",
    "faction": "faction",
    "asset": "asset",
    "npc": "gmc",
    "gm": "gmc",
}

# Universe name → slug. Matches existing universe entity keys where present.
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


def build_parent_map(relations: list[dict]) -> dict[str, str]:
    """child numeric key → parent numeric key, from ``super`` edges."""
    return {
        r["_from"].split("/")[1]: r["_to"].split("/")[1]
        for r in relations
        if r["type"] == "super"
    }


def build_universe_map(entities: list[dict], relations: list[dict]) -> dict[str, str]:
    """Map old universe numeric key → slug, from the children of Multiverse."""
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
    """Walk the super chain from an entity up to the first universe key."""
    cur = entity_key
    seen = set()
    while cur and cur not in seen:
        if cur in universe_keys:
            return cur
        seen.add(cur)
        cur = parent_map.get(cur, "")
    return None


def build_entity_key_map(
    entities: list[dict], relations: list[dict]
) -> dict[str, str]:
    """Return the full old→new entity key map (``Entities/{numeric}`` → new id).

    Applies the same rules as the entity migration: archetypes and system
    entities are excluded (they have no new id); universes key as
    ``universe-{slug}``; everything else as ``{prefix}-{numeric}``.
    """
    parent_map = build_parent_map(relations)
    universe_map = build_universe_map(entities, relations)
    universe_keys = set(universe_map.keys())

    old_to_new: dict[str, str] = {}
    for e in entities:
        key = e["_key"]
        old_type = e.get("type")
        is_arch = e.get("is_archetype") is True

        # System entities with no new-model equivalent
        if key == MULTIVERSE or (key == "1" and old_type == "gm"):
            continue

        is_universe = old_type == "location" and key in universe_keys

        # Archetype templates are dropped (D1), but a universe flagged
        # is_archetype (The Floating Vagabond) still migrates as a universe.
        if is_arch and not is_universe:
            continue

        if old_type == "npc" or old_type == "gm":
            new_id = f"gmc-{key}"
        elif is_universe:
            new_id = f"universe-{universe_map[key]}"
        elif old_type in ("character", "faction", "asset", "location"):
            new_id = f"{TYPE_PREFIX[old_type]}-{key}"
        else:
            continue

        old_to_new[f"Entities/{key}"] = new_id

    return old_to_new


# ── Rating encoding (old integer rating → DieType) ─────────────

# Old ``rating`` values encode a die size by integer: 1=d4, 2=d6, 3=d8, 4=d10,
# 5=d12. Negative = complication/negative polarity (same die size).
RATING_TO_DIE: dict[int, str] = {
    1: "d4", 2: "d6", 3: "d8", 4: "d10", 5: "d12",
    -1: "d4", -2: "d6", -3: "d8", -4: "d10", -5: "d12",
}

# Old rating_type → new RatingType (identity mapping; already uses same vocab).
RATING_TYPE_MAP = {"static": "static", "resource": "resource",
                   "challenge": "challenge", "empty": "empty"}


def resolve_universes_from_default(
    en: list[str], dis: list[str], universe_lookup: dict[str, str]
) -> set[str]:
    """Resolve universe slugs from a default's locations_enabled/disabled.

    ``en``/``dis`` are lists of ``Entities/{numeric}`` refs. ``"2"`` is the
    Multiverse root = the "all universes" sentinel. ``universe_lookup`` maps
    old universe numeric key → slug (the 15 children of Multiverse).

    Semantics (reconciled across the two buggy prior scripts):
    - ``2`` in ``en`` → enabled everywhere, minus any specific ``dis``.
    - otherwise a non-empty ``en`` → explicit whitelist.
    - otherwise empty ``en``: ``2`` in ``dis`` → nowhere; else all minus ``dis``.
    """
    ALL = "2"
    en_ids = [e.split("/")[1] for e in (en or []) if e]
    dis_ids = [e.split("/")[1] for e in (dis or []) if e]

    all_names = set(universe_lookup.values())
    en_specific = {universe_lookup[i] for i in en_ids if i in universe_lookup}
    dis_specific = {universe_lookup[i] for i in dis_ids if i in universe_lookup}

    if ALL in en_ids:
        if ALL in dis_ids:
            return set()
        return all_names - dis_specific

    if en_specific:
        return en_specific - dis_specific

    if ALL in dis_ids:
        return set()

    return all_names - dis_specific


def build_universe_lookup(entities: list[dict], relations: list[dict]) -> dict[str, str]:
    """Map old universe numeric key → slug (children of Multiverse)."""
    return build_universe_map(entities, relations)
