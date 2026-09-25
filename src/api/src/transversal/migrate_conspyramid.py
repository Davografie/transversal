"""Migration script: seed transversal edges and a faction conspyramid.

Reads the live ArangoDB location hierarchy and:

1. Creates lateral (leaf-to-leaf) ``transversal`` edges between locations that
   do not share a parent — preferring cross-universe pairs — so the relational
   canvas has visible travel links.
2. Seeds the *Crimson Hollow Sect*, a demonic-cultivator faction with a
   six-level conspyramid: GMC entities placed at existing leaf locations,
   ``membership`` edges, and ``rank`` / ``role`` traitsettings on those edges.
3. Wires the two existing GMCs (Su Hui, Gu Yuan) into *Verdant Steps Sect* as
   a contrasting transparent faction.

Usage:
    docker compose exec api python -m transversal.migrate_conspyramid
"""

from __future__ import annotations

import random

from transversal.db.arango import ENTITIES, RELATIONSHIPS, get_db
from transversal.db.repository import EntityRepository
from transversal.domain import (
    DieType,
    Entity,
    EntityType,
    RatingType,
    TraitSetting,
)

RELATIONS_TRAITSET = "ts-relations-b114"


def _relation_trait_id(repo: EntityRepository, name: str) -> str:
    """Resolve a trait by *name* inside the 'relations' trait set.

    Resolved rather than hard-coded: an earlier ``trait-role-cd1b`` constant does
    not exist in the registry at all, so the rank/role settings it wrote pointed
    at nothing and the faction canvas could not read them.
    """
    for trait in repo.get_traits_by_traitset(RELATIONS_TRAITSET):
        if trait.name == name:
            return trait.id
    raise RuntimeError(f"trait '{name}' not found in {RELATIONS_TRAITSET}")


def _ensure_rank_role(
    repo: EntityRepository, edge_key: str, rank_die: DieType, role_text: str
) -> None:
    """Attach rank + role traitsettings to a membership edge."""
    rank_trait = _relation_trait_id(repo, "rank")
    rank_id = f"{edge_key}:{rank_trait}"
    if repo.get_traitsetting(rank_id) is None:
        repo.create_traitsetting(TraitSetting(
            id=rank_id,
            entity_id=edge_key,
            trait_id=rank_trait,
            from_type="relationship",
            rating_type=RatingType.STATIC,
            dice=[rank_die],
        ))

    role_trait = _relation_trait_id(repo, "role")
    role_id = f"{edge_key}:{role_trait}"
    if repo.get_traitsetting(role_id) is None:
        repo.create_traitsetting(TraitSetting(
            id=role_id,
            entity_id=edge_key,
            trait_id=role_trait,
            from_type="relationship",
            rating_type=RatingType.STATIC,
            dice=[DieType.D4],
            statement=role_text,
        ))


def _ensure_gmc(repo: EntityRepository, gmc_id: str, name: str, location_id: str) -> None:
    """Create the GMC if it is not there yet."""
    if repo.get_entity(gmc_id) is None:
        repo.create_entity(Entity(
            id=gmc_id,
            type=EntityType.GMC,
            name=name,
            current_universe="three_realms",
            current_location=location_id,
        ))


def _ensure_faction(repo: EntityRepository, faction_id: str, name: str) -> None:
    if repo.get_entity(faction_id) is None:
        repo.create_entity(Entity(
            id=faction_id,
            type=EntityType.FACTION,
            name=name,
            current_universe="three_realms",
        ))


def _ensure_membership(repo: EntityRepository, gmc_id: str, faction_id: str) -> str:
    """Create (or return) the membership edge key for gmc → faction."""
    existing = repo.get_relationship(gmc_id, faction_id, "membership")
    if existing:
        return existing["_key"]
    edge = repo.create_relationship(gmc_id, faction_id, "membership")
    return edge["_key"]


def _ensure_relation(
    repo: EntityRepository, from_id: str, to_id: str, description: str
) -> None:
    if repo.get_relationship(from_id, to_id, "relation") is None:
        repo.create_relationship(from_id, to_id, "relation", description=description)


def seed_transversal_edges(repo: EntityRepository) -> int:
    """Create lateral leaf-to-leaf transversal edges. Returns edge count."""
    db = repo.db

    super_edges = list(db.aql.execute(f"""
        FOR r IN {RELATIONSHIPS}
        FILTER r.type == 'super'
        RETURN {{ child: PARSE_IDENTIFIER(r._from).key, parent: PARSE_IDENTIFIER(r._to).key }}
    """))
    parent_of = {e["child"]: e["parent"] for e in super_edges}

    leaves = list(db.aql.execute(f"""
        FOR e IN {ENTITIES}
        FILTER e.type == 'location'
        LET has_children = LENGTH(
            FOR r IN {RELATIONSHIPS}
            FILTER r._to == e._id AND r.type == 'super'
            RETURN 1
        ) > 0
        FILTER !has_children
        RETURN {{ key: e._key, name: e.name, universe: e.current_universe }}
    """))

    if len(leaves) < 2:
        return 0

    # Group leaves by (universe, immediate parent) so pairs never share a
    # parent and are therefore not in the same parent/child chain.
    groups: dict[tuple[str, str], list[dict]] = {}
    for leaf in leaves:
        key = (leaf["universe"], parent_of.get(leaf["key"], ""))
        groups.setdefault(key, []).append(leaf)

    rng = random.Random(20260814)

    earth = [l for l in leaves if l["universe"] == "earth"]
    three = [l for l in leaves if l["universe"] == "three_realms"]
    three_groups = [g for g in groups.values() if any(l["universe"] == "three_realms" for l in g)]

    pairs: list[tuple[dict, dict]] = []

    # Cross-universe: each earth leaf to a few three_realms leaves.
    for e in earth:
        for t in rng.sample(three, min(3, len(three))):
            pairs.append((e, t))

    # Same-universe: a few three_realms pairs across distinct parent groups.
    for _ in range(4):
        if len(three_groups) < 2:
            break
        a, b = rng.sample(three_groups, 2)
        pairs.append((rng.choice(a), rng.choice(b)))

    def add_edge(frm: str, to: str) -> None:
        k = f"edge:{frm}:{to}:transversal"
        if not repo._relationships.has(k):
            repo._relationships.insert({
                "_key": k,
                "_from": f"entities/{frm}",
                "_to": f"entities/{to}",
                "type": "transversal",
            })

    created = 0
    for a, b in pairs:
        if a["key"] == b["key"]:
            continue
        for frm, to in [(a["key"], b["key"]), (b["key"], a["key"])]:
            k = f"edge:{frm}:{to}:transversal"
            if not repo._relationships.has(k):
                add_edge(frm, to)
                created += 1
    return created


def seed_demonic_faction(repo: EntityRepository) -> None:
    """Seed the Crimson Hollow Sect conspyramid."""
    faction_id = "fac-crimson-hollow"
    _ensure_faction(repo, faction_id, "Crimson Hollow Sect")

    # (id, name, leaf location, rank die, role)
    members = [
        ("gmc-hollow-patriarch", "The Hollow Patriarch", "loc-174486794", DieType.D12, "hollow patriarch"),
        ("gmc-elder-wenqiang", "Elder Wenqiang", "loc-207781517", DieType.D10, "inner-circle elder"),
        ("gmc-master-shen", "Master Shen", "loc-207781646", DieType.D10, "regional master"),
        ("gmc-daoist-hua", "Daoist Hua", "loc-194228804", DieType.D8, "cell leader"),
        ("gmc-ruo", "Ruo", "loc-188475168", DieType.D6, "operative"),
        ("gmc-street-runner", "The Weeping Willow Runner", "loc-177382901", DieType.D4, "street runner"),
    ]

    for gmc_id, name, loc, rank_die, role in members:
        _ensure_gmc(repo, gmc_id, name, loc)
        edge_key = _ensure_membership(repo, gmc_id, faction_id)
        _ensure_rank_role(repo, edge_key, rank_die, role)

    # Command chain: superior → subordinate.
    chain = [
        ("gmc-hollow-patriarch", "gmc-elder-wenqiang", "commands"),
        ("gmc-hollow-patriarch", "gmc-master-shen", "commands"),
        ("gmc-elder-wenqiang", "gmc-daoist-hua", "commands"),
        ("gmc-master-shen", "gmc-ruo", "commands"),
        ("gmc-daoist-hua", "gmc-street-runner", "commands"),
    ]
    for frm, to, desc in chain:
        _ensure_relation(repo, frm, to, desc)


def seed_verdant_steps_members(repo: EntityRepository) -> None:
    """Wire existing GMCs into Verdant Steps as a contrasting open faction."""
    faction_id = "fac-verdant-steps"
    members = [
        ("gmc-su-hui-7291e7bb", DieType.D8, "sect senior"),
        ("gmc-gu-yuan-22844ad1", DieType.D6, "outer disciple"),
    ]
    for gmc_id, rank_die, role in members:
        if repo.get_entity(gmc_id) is None:
            continue
        edge_key = _ensure_membership(repo, gmc_id, faction_id)
        _ensure_rank_role(repo, edge_key, rank_die, role)


def main() -> None:
    db = get_db()
    repo = EntityRepository(db=db)

    transversal_edges = seed_transversal_edges(repo)
    seed_demonic_faction(repo)
    seed_verdant_steps_members(repo)

    print(f"Migration complete: {transversal_edges} transversal edges created.")


if __name__ == "__main__":
    main()
