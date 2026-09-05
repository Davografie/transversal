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


def resolve_direct_location(
    key: str,
    entity_type: dict[str, str],
    entity_loc: dict[str, str],
    parent_map: dict[str, str],
) -> str | None:
    """Return the old key of an entity's *direct* location (first hop).

    Mirrors the old app's ``retrieve_location``: non-location entities use their
    ``location`` field (recursing if it points at a non-location), while
    locations use their ``super`` parent.
    """
    seen: set[str] = set()
    cur = key
    while cur and cur not in seen:
        seen.add(cur)
        t = entity_type.get(cur)
        if t == "location":
            return parent_map.get(cur)
        loc = entity_loc.get(cur)
        if not loc:
            return None
        nxt = loc.split("/")[1]
        if entity_type.get(nxt) == "location":
            return nxt
        cur = nxt
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


def build_archetype_depths(relations: list[dict]) -> dict[str, dict[str, int]]:
    """Map each entity ref → {archetype ancestor ref: shortest depth}.

    Follows ALL ``archetype`` edges OUTBOUND (entity → template), transitively —
    an entity can inherit from several archetypes (e.g. a faction template plus
    a role template), so this is a multi-parent closure. Depth is the shortest
    path length (1 = direct archetype), used for the old app's priority tie-break
    (shallower archetype wins).
    """
    child_parents: dict[str, list[str]] = {}
    for r in relations:
        if r.get("type") == "archetype":
            child_parents.setdefault(r["_from"], []).append(r["_to"])

    result: dict[str, dict[str, int]] = {}
    for start in child_parents:
        depths: dict[str, int] = {}
        frontier = [(p, 1) for p in child_parents[start]]
        while frontier:
            ref, d = frontier.pop(0)
            if ref in depths and depths[ref] <= d:
                continue
            depths[ref] = d
            frontier.extend((p, d + 1) for p in child_parents.get(ref, []))
        result[start] = depths
    return result


# ── Trait/traitset registry key maps ─────────────────────
#
# Single source of truth for the old→new trait/traitset key formula, shared by
# migrate_registry (Phase 1) and migrate_traitsettings (Phase 4) so the two
# can never drift. Keys are deterministic ``trait-{old_numeric}`` /
# ``ts-{old_numeric}`` except for the few new-app-only traitsets that already
# carry hand-authored content and are preserved by name.

PRESERVED_TRAITSETS = {
    "relations": "ts-relations-b114",
    "secrets": "ts-secrets-1b55",
    "location": "ts-location-afd2",
}

SKIP_TRAITSETS = {"custom", "tutorial"}


def traitset_key(old_key: str) -> str:
    return f"ts-{old_key}"


def trait_key(old_key: str) -> str:
    return f"trait-{old_key}"


def build_registry_key_maps(
    traitsets: list[dict], traits: list[dict]
) -> tuple[dict[str, str], dict[str, str], dict[str, str | None]]:
    """Return ``(tset_map, trait_map, trait_tset_map)``.

    - ``tset_map``: old traitset numeric key → new traitset key (skips
      ``custom``/``tutorial``; maps the three preserved-by-name sets).
    - ``trait_map``: ``"Traits/{old}"`` → new trait key.
    - ``trait_tset_map``: old trait numeric key → new traitset key (the
      ``traitset_id`` a migrated setting should denormalize), or ``None`` when
      the trait's traitset was skipped.
    """
    tset_map: dict[str, str] = {}
    for ts in traitsets:
        name = ts.get("name") or ""
        key = ts["_key"]
        if not name or name in SKIP_TRAITSETS:
            continue
        tset_map[key] = PRESERVED_TRAITSETS.get(name, traitset_key(key))

    trait_map: dict[str, str] = {
        f"Traits/{t['_key']}": trait_key(t["_key"]) for t in traits
    }

    trait_tset_map: dict[str, str | None] = {}
    for t in traits:
        ref = t.get("traitset") or ""
        ts_key = ref.split("/")[1] if "/" in ref else ""
        trait_tset_map[t["_key"]] = tset_map.get(ts_key)

    return tset_map, trait_map, trait_tset_map
