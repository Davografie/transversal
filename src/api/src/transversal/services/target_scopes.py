"""The scope vocabulary, expressed as catalog paths.

``Effect.target_scope`` is a compact way of saying *which targets*: ``subtree:X``,
``faction:Y``, ``traitset:Z``. It used to be a **second vocabulary** for the same
question — a prefix registered beside a resolver, with the ``scope → kind``
compatibility living only in ``if kind ==`` branches. Nothing could read that
mapping (a caller had to extract it by reading this source), and the flat picker
and a targeting path were free to disagree about what "occupants at X" meant.

Here each scope is declared once, as the **path** it stands for: a list of
catalog steps ending on the element the scope selects. :func:`resolve_candidates`
runs it through the same resolver every other path uses, so there is one
vocabulary (the catalog) and one evaluator.

A builder is a function of the scope's value and the acting entity — the only two
things the flat form ever depended on — and everything it emits is catalog terms.
The acting entity is what makes the actor-relative selections expressible without
inventing anything: *not me* is ``filter id != <the actor's id>`` and *my
universe* is ``filter universe == <the universe the actor is in>``. Both are
ordinary filter steps, resolved by the ordinary resolver.

Adding a scope means declaring a path here — not registering a callback.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from transversal.domain import Entity
from transversal.services.target_resolver import (
    TargetContext,
    resolve,
    serialize_candidates,
)
from transversal.services.target_spec import (
    AggregateStep,
    ChooseStep,
    FilterStep,
    LiteralStep,
    NavigateStep,
    SelectStep,
    TargetSpec,
    TargetStep,
)


# ── Candidates + picker filters ──────────────────────────────

@dataclass(frozen=True)
class TargetCandidate:
    """A selectable target id plus enough display info for a picker."""
    id: str
    name: str
    universe: str = ""
    subtitle: str = ""  # kind-specific secondary label (e.g. trait → traitset name)


@dataclass(frozen=True)
class FilterField:
    """A target-candidate field the author may filter on, with editor metadata."""
    field: str
    label: str
    value_type: str = "boolean"  # "boolean" | "string" | "number"
    kinds: tuple[str, ...] = ("location",)  # target kinds this filter applies to
    options: tuple[str, ...] = ()  # allowed values for "string" filters (e.g. entity types)


# Candidate filters the SFX editor can build. Adding an entry here makes it
# available in the UI; each names a *catalog* field, so the narrowing is a filter
# step like any other (`{"starter_location": True}` → `filter starter_location`).
FILTER_FIELDS: tuple[FilterField, ...] = (
    FilterField("starter_location", "Starter location", "boolean", ("location",)),
    FilterField("type", "Entity type", "string", ("entity", "occupant"),
                options=("character", "gmc", "asset")),
)


# Trait actions that only make sense on a trait the entity already has. The
# effect-die comparison pair belongs here too: both act on the *rating* of a
# trait the entity holds, so picking from the whole registry would offer traits
# there is nothing to mutate.
MUTATE_EXISTING_TRAIT_ACTIONS = {"step_down", "step_up", "set", "remove"}


# ── Errors ───────────────────────────────────────────────────
#
# The old resolver answered an unsupported pair with `[]`, which is
# indistinguishable from "nothing matched" — a wrong pair read as empty data.

class ScopeError(ValueError):
    """A scope, or a scope/kind pair, the vocabulary does not define."""


class UnknownScope(ScopeError):
    def __init__(self, prefix: str):
        known = ", ".join(sorted(s.prefix or "(none)" for s in TARGET_SCOPES))
        super().__init__(f"unknown target scope {prefix!r}; known scopes: {known}")


class UnsupportedScopeKind(ScopeError):
    def __init__(self, prefix: str, kind: str, kinds: tuple[str, ...]):
        super().__init__(
            f"target kind {kind!r} cannot be selected in scope {prefix or '(none)'!r}; "
            f"it supports: {', '.join(kinds)}")


# ── The declaration ──────────────────────────────────────────

#: ``(value, subject)`` → the steps that select the scope's targets.
Builder = Callable[[str, Any], list[TargetStep]]


@dataclass(frozen=True)
class ScopeSelection:
    """One target kind a scope can produce, as the path that produces it.

    ``kind`` is the flat/editor vocabulary (``occupant``, ``rating_die`` …) and
    ``element`` the catalog type the path ends on — the two differ only for
    ``occupant``, which is an *entity at a place*: a scope question, not a type.
    """
    kind: str
    element: str
    build: Builder
    #: A narrower form for actions that mutate a trait the entity already holds
    #: (it selects from the entity's own instances rather than the registry).
    owned_build: Optional[Builder] = None


@dataclass(frozen=True)
class TargetScope:
    """A prefix of ``target_scope`` and what each kind it can select means."""
    prefix: str          # "" is the bare, unprefixed form
    label: str
    description: str
    selections: tuple[ScopeSelection, ...]

    @property
    def kinds(self) -> tuple[str, ...]:
        return tuple(s.kind for s in self.selections)


# ── Step helpers ─────────────────────────────────────────────

#: The acting entity, for a path that will be **stored**: a rule fires for
#: whoever activates it, so a stored path must not bake in the author's universe
#: or id. A builder given this sentinel defers the actor into the path itself
#: (`select self` binds it; a filter compares against the binding). A preview
#: knows the entity, resolves it eagerly, and can leave an unknown universe
#: unnarrowed — which is what keeps the whole registry reachable while authoring.
ACTOR_AT_RUNTIME = object()

_ACTOR = "_actor"
_UNIVERSE = "_universe"


def _select(collection: str, output: Optional[str] = None) -> SelectStep:
    return SelectStep(collection=collection, output=output)


def _nav(edge: str, output: Optional[str] = None, dedup: bool = False) -> NavigateStep:
    return NavigateStep(edge=edge, output=output, dedup=dedup)


def _literal(element: str, value: str) -> LiteralStep:
    return LiteralStep(element=element, value=value)


def _filter(field: str, value: Any, operator: str = "==") -> FilterStep:
    return FilterStep(field=field, value=value, operator=operator)


def _subject_id(subject: Any) -> str:
    return (getattr(subject, "id", "") or "") if subject is not None else ""


def _subject_universe(subject: Any) -> str:
    """The acting entity's universe ("" when there is nothing to read it from)."""
    return (getattr(subject, "current_universe", "") or "") if subject is not None else ""


def _deferred(subject: Any) -> bool:
    """True when the actor is not known at build time (a path that will be stored)."""
    return subject is ACTOR_AT_RUNTIME


def _bind_actor() -> list[TargetStep]:
    """Bind the acting entity's id, so a selection can leave it out or read from it."""
    return [_select("self", output=_ACTOR)]


def _not_actor(subject: Any) -> list[TargetStep]:
    """Leave the acting entity out.

    There is no special notion of "self" in the catalog and none is needed: the
    excluded id is a filter value — read from the entity when it is known, and
    from a binding when the path has to work for whoever activates it.
    """
    if _deferred(subject):
        return [_filter("id", f"{{{_ACTOR}}}", "!=")]
    actor = _subject_id(subject)
    return [_filter("id", actor, "!=")] if actor else []


def _only_actor(subject: Any) -> list[TargetStep]:
    """Keep only the acting entity's own rows (used for its projections)."""
    if _deferred(subject):
        return [_filter("entity_id", f"{{{_ACTOR}}}")]
    actor = _subject_id(subject)
    return [_filter("entity_id", actor)] if actor else []


def _universe_narrowing(field: str, value: str, subject: Any,
                        operator: str = "==") -> tuple[list[TargetStep], list[TargetStep]]:
    """``(leading, narrowing)`` steps that restrict a selection to one universe.

    A concrete value is a plain filter. ``""``/``"current"`` means the acting
    entity's own universe: read from the entity when it is known (an authoring
    preview), and otherwise *carried* as a binding — which is why that form needs
    leading steps, the binding having to exist before the filter that reads it.
    With no universe to narrow by at all (a preview with no entity) nothing is
    restricted, which keeps the whole registry reachable while authoring.
    """
    if value and value != "current":
        return [], [_filter(field, value, operator)]
    if _deferred(subject):
        return ([_select("self", output=_ACTOR), _nav("universe", output=_UNIVERSE)],
                [_filter(field, f"{{{_UNIVERSE}}}", operator)])
    universe = _subject_universe(subject)
    return [], ([_filter(field, universe, operator)] if universe else [])


def _narrowed(collection: str, field: str, value: str, subject: Any,
              operator: str = "==") -> list[TargetStep]:
    """Seed a collection and narrow it to a universe (the common shape)."""
    lead, narrow = _universe_narrowing(field, value, subject, operator)
    return [*lead, _select(collection), *narrow]


def _lead_actor(subject: Any) -> list[TargetStep]:
    """The bind step a deferred path needs before it can exclude or read the actor."""
    return _bind_actor() if _deferred(subject) else []


# ── The default (unprefixed, and ``universe:``) selections ───

def _default_location(value: str, subject: Any) -> list[TargetStep]:
    return _narrowed("locations", "universe", value, subject)


def _default_occupant(value: str, subject: Any) -> list[TargetStep]:
    """Entities at a place (the value, else the actor's own location), less the actor."""
    steps = _lead_actor(subject)
    steps += ([_literal("location", value), _nav("occupants")] if value
              else [_select("occupants")])
    return [*steps, *_not_actor(subject)]


def _default_entity(value: str, subject: Any) -> list[TargetStep]:
    return _narrowed("entities", "current_universe", value, subject)


def _default_trait(value: str, subject: Any) -> list[TargetStep]:
    return _narrowed("traits", "universes", value, subject, "contains")


def _default_traitset(value: str, subject: Any) -> list[TargetStep]:
    return _narrowed("traitsets", "universes", value, subject, "contains")


def _default_life_path(value: str, subject: Any) -> list[TargetStep]:
    return _narrowed("life_paths", "universe", value, subject)


def _default_roll_table(value: str, subject: Any) -> list[TargetStep]:
    return _narrowed("roll_tables", "universe", value, subject)


def _default_universe(value: str, subject: Any) -> list[TargetStep]:
    """Every universe — the value is not a narrowing here."""
    return [_select("universes")]


def _default_projection(value: str, subject: Any) -> list[TargetStep]:
    """The actor's own bodies, optionally narrowed to one universe."""
    steps = [_select("self"), _nav("projections")]
    if value:
        steps.append(_filter("universe", value))
    return steps


def _default_scheduled_event(value: str, subject: Any) -> list[TargetStep]:
    return [_select("self"), _nav("scheduled_events")]


def _default_rating_die(value: str, subject: Any) -> list[TargetStep]:
    """The die *sizes* — a static vocabulary, not a narrowing of anything."""
    return [_select("die_types")]


# ── Place-scoped selections ──────────────────────────────────

def _location_occupant(value: str, subject: Any) -> list[TargetStep]:
    return [*_lead_actor(subject), _literal("location", value), _nav("occupants"),
            *_not_actor(subject)]


def _location_entity(value: str, subject: Any) -> list[TargetStep]:
    return [_literal("location", value), _nav("occupants")]


def _place_subtree(value: str, subject: Any) -> list[TargetStep]:
    """The place and everything under it (a zone is a target too)."""
    return [_literal("location", value), _nav("subtree")]


def _subtree_occupant(value: str, subject: Any) -> list[TargetStep]:
    return [*_lead_actor(subject), _literal("location", value), _nav("subtree"),
            _nav("occupants"), *_not_actor(subject)]


def _subtree_entity(value: str, subject: Any) -> list[TargetStep]:
    return [_literal("location", value), _nav("subtree"), _nav("occupants")]


def _place_projection(value: str, subject: Any) -> list[TargetStep]:
    """The actor's own bodies whose place is inside the named place.

    Owner-first, then the place: a travel effect reuses *my* body, so the
    narrowing to mine comes before the walk into the subtree.
    """
    return [*_lead_actor(subject), _literal("location", value), _nav("subtree"),
            _nav("projections"), *_only_actor(subject)]


# ── Roster-scoped selections ─────────────────────────────────

def _faction_entity(value: str, subject: Any) -> list[TargetStep]:
    return [*_lead_actor(subject), _literal("entity", value), _nav("members"),
            *_not_actor(subject)]


def _faction_roll_table(value: str, subject: Any) -> list[TargetStep]:
    return [_literal("entity", value), _nav("life_paths"), _nav("roll_tables")]


def _actor_faction_entity(value: str, subject: Any) -> list[TargetStep]:
    """The orgs the acting entity is itself on the roster of.

    ``value`` narrows to one by id. (The flat form also accepted a substring of
    the name; a path filters on a field, and the picker has its own search, so the
    fuzzy form is gone rather than half-expressed.)
    """
    steps = [_select("self"), _nav("factions")]
    if value:
        steps.append(_filter("id", value))
    return steps


def _actor_faction_trait(value: str, subject: Any) -> list[TargetStep]:
    """The traits those orgs actually hold — what a mutate action must pick from."""
    return [*_actor_faction_entity(value, subject), _nav("traitsettings"),
            _nav("trait", dedup=True)]


# ── Set- and path-scoped selections ──────────────────────────

def _traitset_trait(value: str, subject: Any) -> list[TargetStep]:
    return [_literal("traitset", value), _nav("traits")]


def _traitset_owned_trait(value: str, subject: Any) -> list[TargetStep]:
    """Only the traits this entity already holds *in that set*."""
    return [_select("self"), _nav("traitsettings"), _filter("traitset_id", value),
            _nav("trait", dedup=True)]


def _life_path_roll_table(value: str, subject: Any) -> list[TargetStep]:
    return [_literal("life_path", value), _nav("roll_tables")]



# ── The table ────────────────────────────────────────────────

TARGET_SCOPES: tuple[TargetScope, ...] = (
    TargetScope(
        prefix="", label="Current context",
        description="The acting entity's own context: its universe, its location, "
                    "its own bodies. A bare scope value is a universe.",
        selections=(
            ScopeSelection("rating_die", "rating_die", _default_rating_die),
            ScopeSelection("location", "location", _default_location),
            ScopeSelection("occupant", "entity", _default_occupant),
            ScopeSelection("entity", "entity", _default_entity),
            ScopeSelection("trait", "trait", _default_trait),
            ScopeSelection("traitset", "traitset", _default_traitset),
            ScopeSelection("life_path", "life_path", _default_life_path),
            ScopeSelection("roll_table", "roll_table", _default_roll_table),
            ScopeSelection("universe", "universe", _default_universe),
            ScopeSelection("projection", "projection", _default_projection),
            ScopeSelection("scheduled_event", "scheduled_event", _default_scheduled_event),
        ),
    ),
    TargetScope(
        prefix="location", label="At a place",
        description="The place named by the scope: its occupants, the place "
                    "itself and its zones, or the actor's own bodies there.",
        selections=(
            ScopeSelection("occupant", "entity", _location_occupant),
            ScopeSelection("entity", "entity", _location_entity),
            ScopeSelection("location", "location", _place_subtree),
            ScopeSelection("projection", "projection", _place_projection),
        ),
    ),
    TargetScope(
        prefix="subtree", label="In a place's subtree",
        description="Everything inside the named place, zones included.",
        selections=(
            ScopeSelection("occupant", "entity", _subtree_occupant),
            ScopeSelection("entity", "entity", _subtree_entity),
            ScopeSelection("location", "location", _place_subtree),
            ScopeSelection("projection", "projection", _place_projection),
        ),
    ),
    TargetScope(
        prefix="faction", label="On a faction's roster",
        description="The named faction's members, or the roll tables of the life "
                    "paths it may start people on.",
        selections=(
            ScopeSelection("entity", "entity", _faction_entity),
            ScopeSelection("roll_table", "roll_table", _faction_roll_table),
        ),
    ),
    TargetScope(
        prefix="actor_faction", label="The actor's faction",
        description="The orgs the acting entity is itself on the roster of.",
        selections=(
            ScopeSelection("entity", "entity", _actor_faction_entity),
            ScopeSelection("trait", "trait", _actor_faction_trait),
        ),
    ),
    TargetScope(
        prefix="traitset", label="In a trait set",
        description="The traits the named set defines.",
        selections=(
            ScopeSelection("trait", "trait", _traitset_trait,
                           owned_build=_traitset_owned_trait),
        ),
    ),
    TargetScope(
        prefix="life_path", label="Of a life path",
        description="The roll tables that follow the named life path.",
        selections=(
            ScopeSelection("roll_table", "roll_table", _life_path_roll_table),
        ),
    ),
)

#: `universe:X` is the bare form made explicit — the same selections, so the two
#: spellings can never drift.
SCOPES_BY_PREFIX: dict[str, TargetScope] = {s.prefix: s for s in TARGET_SCOPES}
SCOPES_BY_PREFIX["universe"] = SCOPES_BY_PREFIX[""]


def parse_scope(scope: Optional[str]) -> tuple[Optional[str], str]:
    """Split a scope string into ``(prefix, value)``.

    Bare scopes have no prefix (``None``) — they are the default scope's value.
    """
    if not scope:
        return None, ""
    if ":" in scope:
        prefix, _, value = scope.partition(":")
        return prefix, value
    return None, scope


def scope_for(prefix: Optional[str]) -> TargetScope:
    """The declared scope for a prefix, or raise :class:`UnknownScope`."""
    declared = SCOPES_BY_PREFIX.get(prefix or "")
    if declared is None:
        raise UnknownScope(prefix or "")
    return declared


def selection_for(kind: str, scope: TargetScope) -> ScopeSelection:
    """The scope's selection for a target kind, or raise :class:`UnsupportedScopeKind`."""
    for selection in scope.selections:
        if selection.kind == kind:
            return selection
    raise UnsupportedScopeKind(scope.prefix, kind, scope.kinds)


def selection_spec(kind: str, value: str, subject: Any, prefix: Optional[str] = None,
                   action: Optional[str] = None,
                   filter: Optional[dict] = None) -> TargetSpec:
    """The path a ``(kind, scope, filter)`` triple stands for.

    The one place a flat target choice becomes catalog steps: used to resolve
    candidates, and readable as-is, so what the picker offers and what a path
    resolves cannot be two different things.
    """
    declared = scope_for(prefix)
    selection = selection_for(kind, declared)
    build = selection.build
    if action in MUTATE_EXISTING_TRAIT_ACTIONS and selection.owned_build is not None:
        build = selection.owned_build
    steps = list(build(value, subject))
    # The picker's candidate filters are filter steps too — a narrowing of the
    # same path, not a second predicate language.
    for field_name, wanted in (filter or {}).items():
        steps.append(_filter(field_name, wanted))
    return TargetSpec(steps=steps)


def choice_spec(kind: str, scope: Optional[str], mode: str = "choose", count: int = 1,
                filter: Optional[dict] = None) -> TargetSpec:
    """The spec a legacy choice target stands for.

    ``{choose_kind}`` / ``{random:kind}`` plus a ``target_scope`` and a
    ``target_filter`` were a compact spelling of *pick from this path* — so that is
    exactly what they compile to: the declared scope path with a terminal
    ``choose``/``random`` step. The actor is deferred (``ACTOR_AT_RUNTIME``),
    because the effect is stored and fires for whoever activates it.

    This is how stored content moves off the flat form without changing what it
    selects: the compiled path *is* the one the picker's scope resolves to.
    """
    prefix, value = parse_scope(scope)
    spec = selection_spec(kind, value, ACTOR_AT_RUNTIME, prefix, None, filter)
    if mode == "random":
        spec.steps.append(AggregateStep(fn="random", count=max(1, count)))
    else:
        spec.steps.append(ChooseStep(count=max(1, count)))
    return spec


def _universe_of(value: Any) -> str:
    """A candidate's universe, read from whichever field carries it."""
    for field_name in ("current_universe", "universe", "universes"):
        raw = getattr(value, field_name, None)
        if isinstance(raw, list):
            raw = raw[0] if raw else ""
        if raw:
            return raw
    return ""


def resolve_candidates(kind: str, scope: Optional[str], entity: Entity, repo,
                       action: Optional[str] = None,
                       filter: Optional[dict] = None) -> list[TargetCandidate]:
    """Return the selectable candidates for a ``(kind, scope, filter)`` triple.

    ``kind`` is a target kind (``location``, ``occupant``, ``entity``, ``trait``,
    ``traitset``, ``life_path``, ``roll_table``, ``rating_die``, ``universe``,
    ``projection``, ``scheduled_event``); ``scope`` is the ``target_scope``
    narrowing string. ``action`` narrows trait picks to the entity's own
    instances for mutate-only actions. ``filter`` is a map of candidate fields to
    required values (e.g. ``{"starter_location": True}``).

    Raises :class:`ScopeError` for a pair the vocabulary does not define: an
    unsupported pair used to answer ``[]``, which is indistinguishable from
    "nothing matched".
    """
    prefix, value = parse_scope(scope)
    declared = scope_for(prefix)
    selection = selection_for(kind, declared)
    spec = selection_spec(kind, value, entity, prefix, action, filter)
    resolution = resolve(spec, TargetContext(subject=entity, repo=repo))

    displays = serialize_candidates(selection.element, resolution.values, repo)
    return [
        TargetCandidate(
            id=display.id,
            name=display.name or str(display.id),
            universe=_universe_of(value_obj),
            subtitle=display.subtitle,
        )
        for value_obj, display in zip(resolution.values, displays)
    ]
