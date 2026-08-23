"""Target-candidate resolution for ``choose`` / ``random`` effect targets.

One place that turns ``(kind, scope)`` into a list of selectable candidates.
The backend ``random`` target mode and the frontend choose-picker both consume
:func:`resolve_candidates`, so they can never drift apart.

Scope grammar (``Effect.target_scope``)::

    prefix:value    e.g. ``faction:ru-maffia``, ``subtree:krasnoyarsk``
    bare value      legacy default — universe for universe-scoped kinds,
                    current location for occupants
    empty           current context

New scopes are added by calling :func:`register_scope` with a prefix and a
resolver.  No dispatch table lives inside the picker or the random picker.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from transversal.domain import DieType, Entity, EntityType


@dataclass(frozen=True)
class TargetCandidate:
    """A selectable target id plus enough display info for a picker."""
    id: str
    name: str
    universe: str = ""


# Resolver signature: (kind, value, entity, repo) -> list[TargetCandidate]
ScopeResolver = Callable[[str, str, Entity, object], list[TargetCandidate]]

_SCOPE_RESOLVERS: dict[str, ScopeResolver] = {}


def register_scope(prefix: str, resolver: ScopeResolver) -> None:
    """Register a scope prefix. Future scopes plug in here."""
    _SCOPE_RESOLVERS[prefix] = resolver


def parse_scope(scope: Optional[str]) -> tuple[Optional[str], str]:
    """Split a scope string into ``(prefix, value)``.

    Bare scopes have no prefix (``None``) — they keep the legacy default
    behaviour (universe / current location).
    """
    if not scope:
        return None, ""
    if ":" in scope:
        prefix, _, value = scope.partition(":")
        return prefix, value
    return None, scope


def _candidate(id: str, name: str, universe: str = "") -> TargetCandidate:
    return TargetCandidate(id=id, name=name, universe=universe)


def _die_candidates() -> list[TargetCandidate]:
    return [TargetCandidate(id=d.value, name=d.value) for d in DieType]


def _default_scope(kind: str, value: str, entity: Entity, repo) -> list[TargetCandidate]:
    """No explicit scope: narrow by the entity's current context."""
    if kind == "rating_die":
        return _die_candidates()
    if kind == "location":
        universe = value or entity.current_universe
        return [
            _candidate(e.id, e.name, e.current_universe)
            for e in repo.list_entities_by_type(EntityType.LOCATION, universe=universe)
        ]
    if kind == "starter_location":
        universe = value or entity.current_universe
        return [
            _candidate(e.id, e.name, e.current_universe)
            for e in repo.list_entities_by_type(EntityType.LOCATION, universe=universe)
            if e.starter_location
        ]
    if kind == "occupant":
        location_id = value or entity.current_location
        if not location_id:
            return []
        return [
            _candidate(e.id, e.name, e.current_universe)
            for e in repo.list_entities_by_location(location_id)
            if e.id != entity.id
        ]
    if kind == "entity":
        universe = value or entity.current_universe
        return [
            _candidate(e.id, e.name, e.current_universe)
            for e in repo.list_all_entities(universe=universe)
        ]
    if kind == "trait":
        universe = value or entity.current_universe
        return [_candidate(t.id, t.name, universe) for t in repo.get_traits_by_universe(universe)]
    if kind == "life_path":
        universe = value or entity.current_universe
        return [_candidate(lp.id, lp.name, lp.universe) for lp in repo.list_lifepaths_by_universe(universe)]
    if kind == "roll_table":
        return [_candidate(t.id, t.name, t.universe) for t in repo.list_roll_tables()]
    if kind == "universe":
        return [
            _candidate(e.id, e.name, e.current_universe)
            for e in repo.list_entities_by_type(EntityType.UNIVERSE)
        ]
    if kind == "projection":
        universe = value or None
        projs = repo.get_projections_for_entity(entity.id)
        if universe:
            projs = [p for p in projs if p.universe == universe]
        return [
            _candidate(p.id, p.name or entity.name, p.universe)
            for p in projs
        ]
    return []


def _location_scope(kind: str, value: str, entity: Entity, repo) -> list[TargetCandidate]:
    if kind == "occupant":
        return [
            _candidate(e.id, e.name, e.current_universe)
            for e in repo.list_entities_by_location(value)
            if e.id != entity.id
        ]
    if kind == "entity":
        return [
            _candidate(e.id, e.name, e.current_universe)
            for e in repo.list_entities_by_location(value)
        ]
    if kind == "location":
        # The location itself plus its sub-locations (zones).
        location_ids = [value] + list(repo.list_location_descendants(value))
        return [
            _candidate(e.id, e.name, e.current_universe)
            for e in repo.get_entities_by_ids(location_ids)
        ]
    if kind == "projection":
        location_ids = [value] + list(repo.list_location_descendants(value))
        return [
            _candidate(p.id, p.name or entity.name, p.universe)
            for p in repo.get_projections_for_entity(entity.id)
            if p.current_location in location_ids
        ]
    return []


def _subtree_scope(kind: str, value: str, entity: Entity, repo) -> list[TargetCandidate]:
    location_ids = [value] + list(repo.list_location_descendants(value))
    if kind == "location":
        return [
            _candidate(e.id, e.name, e.current_universe)
            for e in repo.get_entities_by_ids(location_ids)
        ]
    if kind in ("occupant", "entity"):
        occupants = repo.list_entities_by_locations(location_ids)
        return [
            _candidate(e.id, e.name, e.current_universe)
            for e in occupants
            if not (kind == "occupant" and e.id == entity.id)
        ]
    if kind == "projection":
        return [
            _candidate(p.id, p.name or entity.name, p.universe)
            for p in repo.get_projections_for_entity(entity.id)
            if p.current_location in location_ids
        ]
    return []


def _faction_scope(kind: str, value: str, entity: Entity, repo) -> list[TargetCandidate]:
    if kind == "entity":
        return [
            _candidate(e.id, e.name, e.current_universe)
            for e in repo.list_faction_members(value)
            if e.id != entity.id
        ]
    return []


def _traitset_scope(kind: str, value: str, entity: Entity, repo) -> list[TargetCandidate]:
    if kind == "trait":
        return [
            _candidate(t.id, t.name, t.universes[0] if t.universes else "")
            for t in repo.get_traits_by_traitset(value)
        ]
    return []


# ── Default registrations ────────────────────────────

register_scope("universe", _default_scope)
register_scope("location", _location_scope)
register_scope("subtree", _subtree_scope)
register_scope("faction", _faction_scope)
register_scope("traitset", _traitset_scope)


def resolve_candidates(kind: str, scope: Optional[str], entity: Entity, repo) -> list[TargetCandidate]:
    """Return the selectable candidates for a ``(kind, scope)`` pair."""
    prefix, value = parse_scope(scope)
    resolver = _SCOPE_RESOLVERS.get(prefix, _default_scope)
    return resolver(kind, value, entity, repo)
