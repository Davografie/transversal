"""Converge authored faction rosters onto the `membership` edge.

A roster entry is **member → faction**. The authored Three Realms rosters predate
that type: they are `relation` ties carrying a `role` (or `rank`) trait. The
faction canvas reads both shapes, so nothing is broken — but `membership` is the
structural marker the rest of the platform keys on (`list_faction_members`, effect
targeting via `faction:<id>`, the roster read), so the two shapes are converged
here.

Two rules make this safe:

- **The edge is renamed in place**, never replaced. Relationship trait settings
  anchor to the edge ``_key``, so deleting and recreating would orphan every
  member's role and rank.
- **Only ``member → faction`` ties are promoted.** The reverse direction
  (``faction → member``, e.g. Azure Dawn's "outer sect disciple") is the
  organisation's own view of someone, which is a posture, not a roster slot.

Idempotent: re-running after an apply reports ``to_promote: 0``. Dry-run by
default; pass ``--apply`` to write.

Usage:
    docker compose exec api python -m transversal.migrate_faction_membership [--apply]
"""

from __future__ import annotations

import sys
from collections import Counter

from transversal.db.arango import ENTITIES
from transversal.db.arango import RELATIONSHIPS
from transversal.db.repository import EntityRepository

# A tie is a roster entry when it names a place in the org, or rates one. Matched
# by name: the registry carries more than one trait called `role`.
ROSTER_TRAIT_NAMES = ("role", "rank")

# Who may hold membership (mirrors MEMBERSHIP_HOLDER_TYPES in the domain).
MEMBER_TYPES = ("character", "gmc", "asset")


def find_candidates(repo: EntityRepository) -> list[dict]:
    """Authored roster ties that are still typed ``relation``."""
    query = f"""
        FOR r IN {RELATIONSHIPS}
        FILTER r.type == 'relation'
        LET faction = DOCUMENT(r._to)
        FILTER faction != null AND faction.type == 'faction'
        LET member = DOCUMENT(r._from)
        FILTER member != null AND member.type IN @member_types
        LET is_roster = LENGTH(
            FOR t IN traitsettings
            FILTER t.from_type == 'relationship' AND t.entity_id == r._key
            LET tr = DOCUMENT(CONCAT('traits/', t.trait_id))
            FILTER tr != null AND tr.name IN @names
            LIMIT 1
            RETURN 1
        ) > 0
        FILTER is_roster
        RETURN {{
            edge: r._key,
            member: member.name,
            member_type: member.type,
            faction: faction.name,
            role: FIRST(FOR t IN traitsettings
                        FILTER t.from_type == 'relationship' AND t.entity_id == r._key
                        RETURN t.statement),
        }}
    """
    return list(repo.db.aql.execute(query, bind_vars={
        "names": list(ROSTER_TRAIT_NAMES),
        "member_types": list(MEMBER_TYPES),
    }))


def promote(repo: EntityRepository, candidates: list[dict]) -> int:
    """Rename each tie's type in place, keeping its key and its traits."""
    for c in candidates:
        repo.db.aql.execute(
            f"FOR r IN {RELATIONSHIPS} FILTER r._key == @key "
            f"UPDATE r WITH {{ type: 'membership' }} IN {RELATIONSHIPS}",
            bind_vars={"key": c["edge"]},
        )
    return len(candidates)


def migrate(apply: bool = False) -> int:
    repo = EntityRepository()
    candidates = find_candidates(repo)

    print(f"roster ties still typed `relation`: {len(candidates)}")
    by_faction = Counter(c["faction"] for c in candidates)
    for faction, n in by_faction.most_common():
        print(f"  {n:3d}  {faction}")
    for c in candidates[:15]:
        role = f" — {c['role']}" if c.get("role") else ""
        print(f"    - {c['member']} ({c['member_type']}){role}")
    if len(candidates) > 15:
        print(f"    … and {len(candidates) - 15} more")

    if apply and candidates:
        print(f"  promoted: {promote(repo, candidates)}")
    elif not apply:
        print("dry run — pass --apply to write")

    return 0


if __name__ == "__main__":
    sys.exit(migrate(apply="--apply" in sys.argv))
