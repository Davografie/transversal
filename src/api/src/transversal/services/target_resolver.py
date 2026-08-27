"""Runtime resolution of a ``TargetSpec`` against game state.

The type-checker ([[target_spec]]) proves a spec *can* reach a type; this
module turns a spec into the *actual values*. It walks the steps over a
collection, and for ``navigate`` it consults a registry of edge resolvers — one
function per ``(source_type, edge_name)`` that maps an element to its related
elements via the repository.

The context carries the acting entity, the repository, and the seed collections
(``rolled_dice``, ``occupants``, …). ``select self`` seeds from ``context.subject``
rather than a collection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from transversal.services.target_spec import (
    AggregateStep,
    FilterStep,
    LiteralStep,
    NavigateStep,
    SelectStep,
    TargetSpec,
    TraceError,
    ValueType,
)
from transversal.services import target_catalog as tc


# ── Context + result ─────────────────────────────────────────

@dataclass
class TargetContext:
    """Everything the resolver needs for one evaluation."""
    subject: Any = None                    # the acting entity (for `select self`)
    repo: Any = None                       # repository (edge lookups)
    collections: dict[str, list[Any]] = field(default_factory=dict)  # seed collections


@dataclass
class Resolution:
    values: list[Any] = field(default_factory=list)   # resolved elements (or a scalar)
    errors: list[TraceError] = field(default_factory=list)


EdgeResolver = Callable[[Any, TargetContext], list[Any]]
_EDGE_RESOLVERS: dict[tuple[str, str], EdgeResolver] = {}


def register_edge(source: str, name: str, resolver: EdgeResolver) -> None:
    """Register an edge resolver for ``(source_type, edge_name)``."""
    _EDGE_RESOLVERS[(source, name)] = resolver


# ── Element access helpers ───────────────────────────────────

def _get_field(element: Any, name: str) -> Any:
    if isinstance(element, dict):
        return element.get(name)
    return getattr(element, name, None)


def _identity(element: Any) -> Any:
    if isinstance(element, dict):
        return element.get("id") or element.get("ts_id") or element
    return getattr(element, "id", None) or element


def _dedup(values: list[Any]) -> list[Any]:
    seen: set[Any] = set()
    out: list[Any] = []
    for v in values:
        k = _identity(v)
        if k not in seen:
            seen.add(k)
            out.append(v)
    return out


def _to_number(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str):
        s = v[1:] if v.startswith("d") else v
        try:
            return int(s)
        except ValueError:
            return None
    return getattr(v, "max_value", None)


def _coerce(value: Any, field_type: str | None) -> Any:
    """Coerce a filter value to its field's declared type.

    Decision: values are typed at authoring time (the wizard emits an int for an
    ``int`` field). This is a defensive normalisation for string-typed specs so
    ``result == "4"`` and ``result == 4`` behave the same, and so ordering
    operators compare numbers, not lexicographic strings.
    """
    if field_type == "int":
        try:
            return int(value)
        except (TypeError, ValueError):
            return value
    if field_type == "number":
        try:
            return float(value)
        except (TypeError, ValueError):
            return value
    return value


def _match(element: Any, step: FilterStep, field_type: str | None = None) -> bool:
    actual = _get_field(element, step.field)
    op, expected = step.operator, step.value
    if op == "==":
        return actual == _coerce(expected, field_type)
    if op == "!=":
        return actual != _coerce(expected, field_type)
    if op in (">", ">=", "<", "<="):
        lhs, rhs = _to_number(actual), _to_number(expected)
        if lhs is None or rhs is None:
            return False
        if op == ">":
            return lhs > rhs
        if op == ">=":
            return lhs >= rhs
        if op == "<":
            return lhs < rhs
        return lhs <= rhs
    if op == "in":
        return actual in expected
    if op == "contains":
        return expected in actual
    return False


def _aggregate(values: list[Any], fn: str, field_name: str | None) -> list[Any]:
    if fn == "count":
        return [len(values)]
    nums = [n for n in (_to_number(_get_field(v, field_name)) for v in values) if n is not None]
    if not nums:
        return []
    if fn == "min":
        return [min(nums)]
    if fn == "max":
        return [max(nums)]
    if fn == "mean":
        return [sum(nums) / len(nums)]
    if fn == "avg_floor":
        return [sum(nums) // len(nums)]
    if fn == "avg_ceil":
        return [-(-sum(nums) // len(nums))]
    return []


# ── The walker ───────────────────────────────────────────────

def resolve(spec: TargetSpec, context: TargetContext) -> Resolution:
    """Walk ``spec`` over ``context``, returning resolved values + step errors."""
    errors: list[TraceError] = []
    values: list[Any] = []
    current_type: ValueType | None = None

    for i, step in enumerate(spec.steps):
        if isinstance(step, SelectStep):
            col = tc.collection(step.collection)
            if col is None:
                errors.append(TraceError(i, f"unknown collection {step.collection!r}"))
                values, current_type = [], None
            elif step.collection == "self":
                values = [context.subject] if context.subject is not None else []
                current_type = ValueType(col.element, "one")
            elif step.collection not in context.collections:
                errors.append(TraceError(i, f"collection {step.collection!r} not provided by context"))
                values, current_type = [], None
            else:
                values = list(context.collections[step.collection])
                current_type = ValueType(col.element, "one" if col.singular else "many")

        elif isinstance(step, FilterStep):
            f = tc.field(current_type.element, step.field) if current_type is not None else None
            if current_type is None or f is None:
                src = current_type.element if current_type else "nothing"
                errors.append(TraceError(i, f"cannot filter on {src}.{step.field}"))
                values, current_type = [], None
            else:
                values = [v for v in values if _match(v, step, f.type)]
                # type unchanged

        elif isinstance(step, NavigateStep):
            if current_type is None:
                errors.append(TraceError(i, "navigate with no collection"))
                values, current_type = [], None
                continue
            e = tc.edge(current_type.element, step.edge)
            resolver = _EDGE_RESOLVERS.get((current_type.element, step.edge))
            if e is None or resolver is None:
                errors.append(TraceError(i, f"no edge/resolver for {current_type.element}.{step.edge}"))
                values, current_type = [], None
            elif len(e.target) != 1:
                errors.append(TraceError(i, f"union edge {current_type.element}.{step.edge} not yet resolvable"))
                values, current_type = [], None
            else:
                out: list[Any] = []
                for v in values:
                    out.extend(resolver(v, context))
                if step.dedup:
                    out = _dedup(out)
                cardinality = "many" if (current_type.cardinality == "many" or e.cardinality == "many") else "one"
                values, current_type = out, ValueType(e.target[0], cardinality)

        elif isinstance(step, AggregateStep):
            if current_type is None:
                errors.append(TraceError(i, "aggregate with no collection"))
                values, current_type = [], None
                continue
            agg = tc.aggregation(step.fn)
            if agg is None:
                errors.append(TraceError(i, f"unknown aggregation {step.fn!r}"))
                values, current_type = [], None
            elif not agg.needs_field:
                values, current_type = [len(values)], ValueType(agg.output, "one")
            elif step.field is None or tc.field(current_type.element, step.field) is None:
                errors.append(TraceError(i, f"aggregation {step.fn} needs a valid field"))
                values, current_type = [], None
            else:
                f = tc.field(current_type.element, step.field)
                values = _aggregate(values, step.fn, step.field)
                element = f.type if agg.output == "same" else agg.output
                current_type = ValueType(element, "one")

        elif isinstance(step, LiteralStep):
            if tc.element(step.element) is None:
                errors.append(TraceError(i, f"unknown literal element {step.element!r}"))
                values, current_type = [], None
            else:
                values = _lookup_literal(step.element, step.value, context)
                current_type = ValueType(step.element, "one")

    return Resolution(values, errors)


def _lookup_literal(element: str, value: str, ctx: TargetContext) -> list[Any]:
    """Resolve a ``literal`` step: fetch the object of ``element`` type by id."""
    repo = ctx.repo
    if repo is None or not value:
        return []
    if element in ("entity", "location", "universe"):
        return _maybe(repo.get_entity(value))
    if element == "trait":
        return _maybe(repo.get_trait(value))
    if element == "traitsetting":
        return _maybe(repo.get_traitsetting(value))
    if element == "traitset":
        return _maybe(repo.get_traitset_by_id(value))
    if element == "projection":
        return _maybe(repo.get_projection(value))
    return []


# ── Default edge resolvers (repo-backed) ─────────────────────

def _maybe(obj: Any) -> list[Any]:
    return [obj] if obj is not None else []


def _die_owner(die: Any, ctx: TargetContext) -> list[Any]:
    eid = die.get("owner_id") if isinstance(die, dict) else None
    ent = ctx.repo.get_entity(eid) if eid else None
    return [ent] if ent else ([ctx.subject] if ctx.subject is not None else [])


def register_default_edges() -> None:
    register_edge("die", "traitsetting", lambda d, ctx: _maybe(ctx.repo.get_traitsetting(d.get("ts_id"))))
    register_edge("die", "owner", _die_owner)

    register_edge("traitsetting", "trait", lambda ts, ctx: _maybe(ctx.repo.get_trait(ts.trait_id)))
    register_edge("traitsetting", "traitset", lambda ts, ctx: _maybe(ctx.repo.get_traitset_by_id(ts.traitset_id)))
    register_edge("traitsetting", "entity", lambda ts, ctx: _maybe(ctx.repo.get_entity(ts.entity_id)))
    register_edge("traitsetting", "projection",
                  lambda ts, ctx: _maybe(ctx.repo.get_projection(ts.projection_id)) if ts.projection_id else [])

    register_edge("entity", "location", lambda e, ctx: _maybe(ctx.repo.get_entity(e.current_location)))
    register_edge("entity", "universe", lambda e, ctx: _maybe(ctx.repo.get_entity(e.current_universe)))
    register_edge("entity", "projection",
                  lambda e, ctx: _maybe(ctx.repo.get_projection(e.current_projection)) if e.current_projection else [])
    register_edge("entity", "projections", lambda e, ctx: list(ctx.repo.get_projections_for_entity(e.id)))
    register_edge("entity", "traitsettings", lambda e, ctx: list(ctx.repo.get_traitsettings_for_entity(e.id)))

    register_edge("projection", "entity", lambda p, ctx: _maybe(ctx.repo.get_entity(p.entity_id)))
    register_edge("projection", "location", lambda p, ctx: _maybe(ctx.repo.get_entity(p.current_location)))

    register_edge("location", "universe", lambda l, ctx: _maybe(ctx.repo.get_entity(l.current_universe)))
    register_edge("location", "occupants", lambda l, ctx: list(ctx.repo.list_entities_by_location(l.id)))

    register_edge("traitset", "traits", lambda ts, ctx: list(ctx.repo.get_traits_by_traitset(ts.id)))
    register_edge("trait", "traitset", lambda t, ctx: _maybe(ctx.repo.get_traitset_by_id(t.traitset_id)))
    register_edge("trait", "universes",
                  lambda t, ctx: [ctx.repo.get_entity(u) for u in (t.universes or []) if ctx.repo.get_entity(u)])


register_default_edges()
