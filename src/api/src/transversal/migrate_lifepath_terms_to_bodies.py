"""Move existing life-path terms and memberships onto the body that lived them ([[B271]]).

Before: ``Entity.pending_term`` held one checkpoint for the whole character, and
``Enrollment`` had no body — so a term begun in one universe followed the
character into every other, and two bodies serving one path were one fact.

After: ``Entity.pending_terms`` is keyed by projection id, ``Enrollment`` carries
``projection_id``, and ``PendingTerm.projection_id`` records the body.

**This is what actually fixes the bug.** The app keeps a read shim for the
deprecated field (``services/lifepath_scope``), so nothing is lost or stranded
before this runs — but an unscoped term is handed to *every* body, which is the
original complaint. Assigning it to the body that lived it is the fix.

It reads raw documents because ``pending_term`` is no longer declared on the
model and Pydantic ignores undeclared fields; the value is on disk but invisible
through ``get_entity``.

Which body a term belonged to, best effort:

1. the projection of that entity whose ``universe`` matches the **path's**
   universe — the term was started in a faction of that path, and a body lives in
   one universe;
2. else ``entity.current_projection``, if that body is in the path's universe;
3. else the entity's current body;
4. else the unscoped key, which the read shim hands to whichever body asks.

Memberships use the same rule per enrollment, keyed by *that enrollment's* path
rather than one answer for the whole entity — a character's two memberships may
have been earned in two universes.

Idempotent: entities with nothing to move are skipped, and a body that already
has a term keeps it. Re-running reports zero without rewriting.

Usage:
    docker compose exec api python -m transversal.migrate_lifepath_terms_to_bodies
"""

from __future__ import annotations

import sys

from transversal.db.arango import ENTITIES
from transversal.db.repository import EntityRepository
from transversal.domain import Entity, PendingTerm
from transversal.services.lifepath_scope import UNSCOPED


def _by_universe(repo, entity: Entity, universe: str) -> str:
    """The entity's body in ``universe``, preferring the one it is playing."""
    projections = repo.get_projections_for_entity(entity.id)
    if entity.current_projection:
        for p in projections:
            if p.id == entity.current_projection and p.universe == universe:
                return p.id
    for p in projections:
        if p.universe == universe:
            return p.id
    return ""


def _body_for(repo, entity: Entity, path_id: str) -> str:
    """The body that served something in ``path_id``, best effort."""
    lp = repo.get_lifepath(path_id) if path_id else None
    universe = getattr(lp, "universe", "") if lp is not None else ""
    if universe:
        body = _by_universe(repo, entity, universe)
        if body:
            return body
    return entity.current_projection or UNSCOPED


def migrate() -> int:
    repo = EntityRepository()
    docs = list(repo.db.aql.execute(f"FOR e IN {ENTITIES} RETURN e"))

    moved_terms, scoped_enrollments, entities_touched, unresolved = 0, 0, 0, []

    for doc in docs:
        legacy_term = doc.get("pending_term")
        raw_enrollments = doc.get("life_paths") or []
        needs = bool(legacy_term) or any(
            not (e.get("projection_id") or "") for e in raw_enrollments
        )
        if not needs:
            continue

        entity = Entity.model_validate({**doc, "id": doc["_key"]})
        changed = False

        if legacy_term:
            path_id = legacy_term.get("path_id", "") or ""
            body = _body_for(repo, entity, path_id)
            if body == UNSCOPED:
                unresolved.append(f"{entity.id} (term {path_id!r})")
            elif body in entity.pending_terms:
                pass  # a body already has a term; do not overwrite it
            else:
                term = PendingTerm(**legacy_term)
                term.projection_id = body
                entity.pending_terms[body] = term
                moved_terms += 1
                changed = True

        for enrollment in entity.life_paths:
            if enrollment.projection_id:
                continue
            body = _body_for(repo, entity, enrollment.path_id)
            enrollment.projection_id = body
            scoped_enrollments += 1
            changed = True
            if body == UNSCOPED:
                unresolved.append(f"{entity.id} (membership {enrollment.path_id!r})")

        if changed:
            repo.update_entity(entity)
            entities_touched += 1

    print(f"  terms moved onto a body:      {moved_terms}")
    print(f"  memberships given a body:     {scoped_enrollments}")
    print(f"  entities rewritten:           {entities_touched}")
    if unresolved:
        print(f"  left unscoped (no body matched, still readable): {len(unresolved)}")
        for line in unresolved[:10]:
            print(f"    - {line}")
    print("\nDone: terms and memberships are per body")
    return 0


if __name__ == "__main__":
    sys.exit(migrate())
