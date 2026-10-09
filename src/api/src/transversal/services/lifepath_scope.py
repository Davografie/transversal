"""Which **body** a life-path term belongs to ([[B271]]).

A term is served by a projection, in that projection's universe — it grants that
body's traits, makes its membership edge and musters it. So the checkpoint and the
enrollments it produces are keyed by projection, and the first question every
reader has to answer is *which body is asking*.

Precedence, and why:

1. **An explicit projection id** from the caller. The sheet knows which body the
   player is looking at, and a caller that names one is never second-guessed.
2. ``entity.current_projection`` — the entity's own active body
   (``domain/entities.py``), which is what the app already treats as "who I am".
3. **The body whose universe matches** ``entity.current_universe``. Older data can
   have projections without a ``current_projection`` set (and locations, which
   have no projections at all), and the universe is the next-best identity: two
   bodies of one character in the same universe is the ambiguous case, and the
   first match is taken because nothing better exists.
4. ``""`` — **unscoped**, meaning content that predates per-body tracking. A term
   or enrollment stored under ``""`` is treated as belonging to whichever body is
   asking, so pre-migration data keeps working until the migration runs. That
   shim is deliberately one-directional: a *scoped* term is never handed to a
   different body.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from transversal.domain import Entity, Enrollment, PendingTerm

#: The key used for content that predates per-body scoping.
UNSCOPED = ""


def resolve_projection_id(entity: "Entity", repo=None,
                          projection_id: Optional[str] = None) -> str:
    """The body a term is being served by, for this entity."""
    if projection_id:
        return projection_id

    current = getattr(entity, "current_projection", "") or ""
    if current:
        return current

    universe = getattr(entity, "current_universe", "") or ""
    if universe and repo is not None:
        try:
            projections = repo.get_projections_for_entity(entity.id)
        except AttributeError:  # a repo that does not model bodies
            projections = []
        for p in projections:
            if getattr(p, "universe", "") == universe:
                return p.id

    return UNSCOPED


def pending_term_for(entity: "Entity", projection_id: str) -> Optional["PendingTerm"]:
    """The term that body is part-way through, if any.

    Falls back to an unscoped term only when the body has none of its own — the
    read half of the compatibility shim described in the module docstring.
    """
    terms = getattr(entity, "pending_terms", None) or {}
    term = terms.get(projection_id)
    if term is None and projection_id != UNSCOPED:
        term = terms.get(UNSCOPED)
    if term is None:
        # Pre-[[B271]] data: one checkpoint on the entity, no body. Handed to
        # whoever asks, so a term is not lost before the migration runs — it is
        # still *unscoped*, which is exactly what the migration fixes.
        term = getattr(entity, "pending_term", None)
    return term


def active_term(entity: "Entity", repo=None,
                projection_id: Optional[str] = None) -> Optional["PendingTerm"]:
    """The term the asking body is part-way through."""
    return pending_term_for(entity, resolve_projection_id(entity, repo, projection_id))


def enrollments_for(entity: "Entity", projection_id: str) -> list["Enrollment"]:
    """That body's memberships — its own, plus unscoped ones it may inherit.

    Scoped memberships are filtered strictly: a membership another body earned is
    not knowledge this one has, which is the point of the change.
    """
    mine: list["Enrollment"] = []
    legacy: list["Enrollment"] = []
    for enrollment in getattr(entity, "life_paths", None) or []:
        scope = getattr(enrollment, "projection_id", "") or ""
        if scope == projection_id:
            mine.append(enrollment)
        elif scope == UNSCOPED and projection_id != UNSCOPED:
            legacy.append(enrollment)
    return mine or legacy


def enrollment_for_path(entity: "Entity", path_id: str,
                        projection_id: str) -> Optional["Enrollment"]:
    """This body's membership for one path, if it has one."""
    for enrollment in enrollments_for(entity, projection_id):
        if (getattr(enrollment, "path_id", "") or "") == path_id:
            return enrollment
    return None
