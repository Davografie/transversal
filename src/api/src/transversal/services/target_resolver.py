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

import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from transversal.services.target_spec import (
    AggregateStep,
    ChooseStep,
    EvaluateStep,
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
    source: Any = None                     # the SFX's activation source (for `select source`)
    source_element: str | None = None      # its catalog element type (drives the source's type)
    bindings: dict[str, "Binding"] = field(default_factory=dict)  # typed output variables (for `select variable`)


@dataclass
class Binding:
    """A typed output variable bound in a per-activation scope.

    ``value`` is the resolved id string (the first value); ``values`` is the
    full ordered list of ids when ``cardinality`` is ``"many"``. ``element`` is
    the catalog element type (e.g. ``traitsetting``) so ``select variable`` can
    type-check and navigate.
    """
    value: str = ""
    values: list[str] = field(default_factory=list)
    element: str = ""
    cardinality: str = "one"  # "one" | "many"


@dataclass
class Resolution:
    values: list[Any] = field(default_factory=list)   # resolved elements (or a scalar)
    errors: list[TraceError] = field(default_factory=list)
    pending_choices: list["PendingTargetChoice"] = field(default_factory=list)


@dataclass
class PendingTargetChoice:
    """A ``choose`` step's candidate set, awaiting a user selection.

    ``element`` is the catalog element type of the candidates; ``candidates``
    holds the resolved candidate objects (before serialization); ``count`` is
    how many the user should select (1 = single, >1 = subset). ``step_index``
    is where the ``choose`` was hit in the path.
    """
    element: str
    candidates: list[Any] = field(default_factory=list)
    count: int = 1
    step_index: int = 0


@dataclass(frozen=True)
class CandidateDisplay:
    """A serialized candidate for the choose-picker (id + element + labels)."""
    id: str
    element: str
    name: str = ""
    subtitle: str = ""
    rating: str = ""  # die size ("d6") for traitsetting candidates; "" elsewhere


EdgeResolver = Callable[[Any, TargetContext], list[Any]]
_EDGE_RESOLVERS: dict[tuple[str, str], EdgeResolver] = {}


def register_edge(source: str, name: str, resolver: EdgeResolver) -> None:
    """Register an edge resolver for ``(source_type, edge_name)``."""
    _EDGE_RESOLVERS[(source, name)] = resolver


def resolve_source(source_kind: str, source_id: str | None, repo) -> tuple[Any, str] | None:
    """Resolve a declared ``source_kind`` + ``source_id`` to ``(object, element)``.

    Maps every declared kind to its instance object: ``trait_setting`` →
    ``traitsetting``, ``traitset_setting`` → ``traitsetsetting``, ``entity`` →
    ``entity``, ``projection`` → ``projection``. The entity/projection split is
    as-authored today (distinct kinds); if the redesign merges them, only the
    ``entity``/``projection`` rows in ``SOURCE_KINDS`` + this dispatch change.
    """
    if not source_kind or not source_id or repo is None:
        return None
    element = tc.source_element(source_kind)
    if element == "traitsetting":
        obj = repo.get_traitsetting(source_id)
        return (obj, element) if obj is not None else None
    if element == "traitsetsetting":
        obj = repo.get_traitsetsetting(source_id)
        return (obj, element) if obj is not None else None
    if element == "entity":
        obj = repo.get_entity(source_id)
        return (obj, element) if obj is not None else None
    if element == "location":
        # A place source: the object is the location itself, so a path may walk
        # straight to its occupants (`select source → occupants`).
        obj = repo.get_entity(source_id)
        return (obj, element) if obj is not None else None
    if element == "projection":
        obj = repo.get_projection(source_id)
        return (obj, element) if obj is not None else None
    return None


# ── Element access helpers ───────────────────────────────────

def _get_field(element: Any, name: str) -> Any:
    if isinstance(element, dict):
        return element.get(name)
    return getattr(element, name, None)


# ── Derived fields ───────────────────────────────────────────
#
# Most catalog fields are plain attributes of the element. A few are not: a
# trait *instance*'s tags are a **union** of the labels set on the instance and
# the ones on the registry trait it points at, so neither attribute alone is the
# answer. A derived reader is registered per ``(element_type, field_name)``
# so the catalog stays declarative and the resolver stays the one place that
# knows how a value is actually read.

FieldResolver = Callable[[Any, Any], Any]  # (element, repo) -> value
_DERIVED_FIELDS: dict[tuple[str, str], FieldResolver] = {}


def register_derived_field(element: str, name: str, resolver: FieldResolver) -> None:
    """Register a repo-backed reader for a catalog field that is not an attribute."""
    _DERIVED_FIELDS[(element, name)] = resolver


def _read_field(element: Any, name: str, element_type: str | None = None, repo=None) -> Any:
    """Read a catalog field's value: its derived reader when one is registered,
    else the element's own attribute."""
    if element_type:
        resolver = _DERIVED_FIELDS.get((element_type, name))
        if resolver is not None:
            return resolver(element, repo)
    return _get_field(element, name)


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


def _sample(values: list[Any], count: int) -> list[Any]:
    """Randomly sample ``count`` elements without replacement.

    Sampling the whole set (or more) returns the set unchanged, so ``random``
    degrades gracefully when the candidate set is smaller than the count.
    """
    if count <= 0:
        return []
    if count >= len(values):
        return list(values)
    return random.sample(values, count)


def _candidate_id(element: str, value: Any) -> str:
    """A stable string id for a resolved candidate (dict or object)."""
    if isinstance(value, dict):
        return value.get("ts_id") or value.get("id") or str(value)
    return getattr(value, "ts_id", None) or getattr(value, "id", None) or str(value)


def _candidate_label(element: str, value: Any, field_name: str) -> str:
    """Extract a display label field from a resolved candidate."""
    if not field_name:
        return ""
    raw = _get_field(value, field_name)
    if raw is None:
        return ""
    return str(raw)


def serialize_candidates(element: str, values: list[Any], repo=None) -> list[CandidateDisplay]:
    """Turn resolved candidates into picker-ready display records.

    Labels are data-driven from ``target_catalog.DISPLAY_FIELDS``: each element
    type declares which field carries its primary and secondary label. A ``pool``
    handle renders its kind as a friendly label (difficulty / dice pool).
    ``traitsetting`` is special-cased: its label is ``statement`` falling back to
    the registry ``trait.name`` (via ``repo``), and its rating is exposed as a
    die size string for the picker to render as an icon.
    """
    display = tc.display_fields(element)
    name_field = display.name_field if display else ""
    subtitle_field = display.subtitle_field if display else ""

    out: list[CandidateDisplay] = []
    for value in values:
        cid = _candidate_id(element, value)
        if element == "pool":
            kind = _get_field(value, "kind")
            name = "Difficulty pool" if kind == "difficulty" else "Dice pool"
            subtitle = ""
            rating = ""
        elif element == "traitsetting":
            statement = _get_field(value, "statement") or ""
            trait_id = _get_field(value, "trait_id") or ""
            trait_name = ""
            if repo is not None and trait_id:
                get_trait = getattr(repo, "get_trait", None)
                trait = get_trait(trait_id) if get_trait else None
                trait_name = (getattr(trait, "name", "") or "") if trait is not None else ""
            name = statement or trait_name or trait_id
            rating_die = _get_field(value, "rating")
            rating = getattr(rating_die, "value", rating_die) if rating_die is not None else ""
            subtitle = ""
        else:
            name = _candidate_label(element, value, name_field)
            subtitle = _candidate_label(element, value, subtitle_field)
            rating = ""
        out.append(CandidateDisplay(id=cid, element=element, name=name, subtitle=subtitle, rating=rating))
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
            pass
        # A timestamp orders by when it happened. Naive and aware values are both
        # accepted and normalised to UTC so the two can't sort against each other
        # inconsistently.
        try:
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
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


#: Distinguishes "no override" from a legitimate ``None`` in :func:`_match`.
_UNSET: Any = object()


def _bound_value(value: Any, context: TargetContext | None) -> Any:
    """A step's comparison value, resolving a ``{name}`` reference to its binding.

    This is what lets a step compare against something decided elsewhere in the
    activation — e.g. *the who's projection whose universe is the one just
    chosen* (``filter universe == {chosen_universe}``). Without it a step's value
    could only ever be a literal, so a path could not be joined to a choice made
    in another path. Names come from the activation scope: a condition's or
    earlier step's ``output``, or a reference value (see ``resolve_refs``).
    """
    if not isinstance(value, str) or not (value.startswith("{") and value.endswith("}")):
        return value
    name = value[1:-1].strip()
    bindings = getattr(context, "bindings", None) or {}
    binding = bindings.get(name)
    if binding is None:
        return value  # unknown name: leave it, so the step plainly matches nothing
    return getattr(binding, "value", binding)


def _match(element: Any, step: FilterStep, field_type: str | None = None,
           expected: Any = _UNSET, element_type: str | None = None, repo=None) -> bool:
    actual = _read_field(element, step.field, element_type, repo)
    op = step.operator
    if expected is _UNSET:
        expected = step.value
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
    if op in ("in", "not in"):
        # One-or-several: the editor stores a single pick as a scalar and several
        # as a list. `in` = is one of them; `not in` = is none of them.
        wanted = expected if isinstance(expected, list) else [expected]
        hit = actual in wanted
        return hit if op == "in" else not hit
    if op == "contains":
        # A list value means *any of* — the same one-or-several reading an enum
        # filter gets from `in`, for a field that is itself a list (a trait's
        # tags: "tagged fire or water").
        if isinstance(expected, list):
            return any(item in (actual or []) for item in expected)
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


def resolved_id(value) -> str | None:
    """The id an effect is applied with, from a resolved spec value.

    A die in a pool is identified by *where it is*, not by the trait it came from:
    two dice of the same trait are different dice, and the effect that steps one
    down has to name which. :func:`_pool_dice` stamps that provenance on every die
    it hands out, and this turns it back into ``die:<location>:<owner>:<index>``.

    **One implementation, both paths** — the immediate one (``effects_engine``)
    and the deferred one (``roll_deferral``) each carried a copy, and they drifted:
    a fix to one left the other handing a trait id to an action that wanted a die.
    """
    if isinstance(value, dict):
        if value.get("pool_owner"):
            return f"die:{value.get('pool_location', '')}:{value['pool_owner']}:{value.get('pool_index')}"
        return value.get("ts_id") or value.get("id")
    return getattr(value, "ts_id", None) or getattr(value, "id", None)


def dice_from_source(added: list[Any] | None, source_id: str | None,
                     source_element: str | None = None) -> list[Any]:
    """The dice a pool save added that came from *this rule's own source*.

    A rule reads the moment from where it stands, and a trait instance can
    contribute more than one die — a ``2d8`` rating is **two** dice, and both
    arrived. So this is a list, never a die, and a rule on a fire technique sees
    the two dice its own technique just put in, not everything the save added.

    Narrowing needs a source that can *contribute* dice; for anything else (an
    entity rule, a table rule, no source at all) there is nothing to narrow by,
    and the whole of what was added is the honest answer.
    """
    everything = list(added or [])
    if not source_id or source_element != "traitsetting":
        return everything
    return [d for d in everything
            if d.get("ts_id") == source_id or d.get("source_id") == source_id]


def event_collections(context: dict | None, source_id: str | None = None,
                      source_element: str | None = None) -> dict[str, list[Any]]:
    """The dice collections a fire event carries, as resolver seeds.

    One rule for every caller: an event that carries dice exposes them under the
    names the catalog declares, so a path seeded from ``rolled_dice`` — or from
    the other side's ``opposing_dice`` — resolves wherever the context is
    threaded through (conditions, immediate effects, deferred effects). Absent
    keys seed nothing, which is a real state at a moment with no contest.

    ``added_dice`` is the one seed that is *about the rule*: it is narrowed to the
    dice that came from the rule's own source (see :func:`dice_from_source`), so
    "the die I just added" needs no filter — and a ``2d8`` trait brings two.
    """
    ctx = context or {}
    seeds: dict[str, list[Any]] = {}
    if ctx.get("rolls"):
        seeds["rolled_dice"] = ctx["rolls"]
    if ctx.get("opposing_rolls"):
        seeds["opposing_dice"] = ctx["opposing_rolls"]
    if ctx.get("added_dice"):
        seeds["added_dice"] = dice_from_source(ctx["added_dice"], source_id, source_element)
    return seeds


def _seed_collection(name: str, ctx: TargetContext) -> list[Any] | None:
    """Lazily seed a catalog collection from the subject/repo.

    Callers provide event-scoped seeds (``rolled_dice``); the subject-derived
    seeds (``occupants``, ``self_traitsettings``) and the full catalogs
    (``locations``, ``entities``) are resolved on demand here so every path
    shares one seeding rule. Returns ``None`` when the collection can't be
    seeded (unknown or no repo).
    """
    if ctx.repo is None:
        return None
    if name == "occupants":
        if ctx.subject is None:
            return []
        loc = getattr(ctx.subject, "current_location", None)
        return list(ctx.repo.list_entities_by_location(loc)) if loc else []
    if name == "self_traitsettings":
        if ctx.subject is None:
            return []
        return list(ctx.repo.get_traitsettings_for_entity(ctx.subject.id))
    if name == "locations":
        from transversal.domain import EntityType
        return list(ctx.repo.list_entities_by_type(EntityType.LOCATION))
    if name == "entities":
        return list(ctx.repo.list_all_entities())
    if name == "sfxs":
        # The rule registry, as a collection a path can walk into and filter.
        # Read-only: nothing navigates out of an SFX yet, so this is a seed plus
        # the scalar fields above.
        getter = getattr(ctx.repo, "get_all_sfxs", None)
        return list(getter()) if callable(getter) else []
    return None


# ── The walker ───────────────────────────────────────────────

def _bind_step_outputs(step, values: list[Any], current_type: ValueType | None, context: TargetContext) -> None:
    """Bind a step's declared ``output`` into the running scope.

    When the step resolves to ``many``, the full ordered list of ids is bound
    (``cardinality="many"``); otherwise the first resolved value is bound as a
    scalar (``cardinality="one"``). No-op when the step has no output or no
    value/type.
    """
    name = getattr(step, "output", None)
    if not name or not values or current_type is None or not current_type.element:
        return
    if current_type.cardinality == "many":
        ids = []
        for v in values:
            rid = _candidate_id(current_type.element, v)
            if rid:
                ids.append(rid)
        if not ids:
            return
        context.bindings[name] = Binding(
            value=ids[0], values=ids, element=current_type.element, cardinality="many",
        )
        return
    rid = _candidate_id(current_type.element, values[0])
    if not rid:
        return
    context.bindings[name] = Binding(
        value=rid, values=[rid], element=current_type.element, cardinality="one",
    )


def _evaluate_step(values: list[Any], current_type: ValueType | None, step: EvaluateStep,
                   context: TargetContext | None = None) -> bool:
    """Terminal boolean test for an ``evaluate`` step.

    ``exists`` = non-empty. A comparison tests a named left-hand side
    (``step.field``) against ``step.value``:
      - ``"count"`` — number of elements in the collection;
      - a scalar field name — a single object's field, or a scalar element's value;
      - ``""`` — legacy implicit (count for ``many``, scalar for a scalar element,
        identity for a single object).
    """
    if step.operator == "exists":
        return bool(values)
    if current_type is None:
        return False

    field = (step.field or "").strip()

    if field == "count":
        lhs, rhs = len(values), _to_number(_bound_value(step.value, context))
    elif field:
        # Named field: scalar element → the scalar itself; single object → its field.
        if current_type.element in ("int", "number", "die"):
            lhs = _to_number(values[0]) if values else None
            rhs = _to_number(_bound_value(step.value, context))
        elif current_type.cardinality == "one" and values:
            f = tc.field(current_type.element, field)
            raw = _read_field(values[0], field, current_type.element,
                              context.repo if context is not None else None)
            if step.operator in ("==", "!="):
                expected = _coerce(_bound_value(step.value, context), f.type if f else None)
                return (raw == expected) if step.operator == "==" else (raw != expected)
            lhs, rhs = _to_number(raw), _to_number(_bound_value(step.value, context))
            if lhs is None or rhs is None:
                return False
            if step.operator == ">":
                return lhs > rhs
            if step.operator == ">=":
                return lhs >= rhs
            if step.operator == "<":
                return lhs < rhs
            return lhs <= rhs
        else:
            return False
    elif current_type.cardinality == "many":
        lhs, rhs = len(values), _to_number(_bound_value(step.value, context))
    elif current_type.element in ("int", "number", "die"):
        lhs = _to_number(values[0]) if values else None
        rhs = _to_number(_bound_value(step.value, context))
    else:
        # Legacy identity comparison for a single object.
        rid = _candidate_id(current_type.element, values[0]) if values else ""
        target = str(_bound_value(step.value, context) or "")
        if step.operator == "==":
            return bool(values) and rid == target
        if step.operator == "!=":
            return bool(values) and rid != target
        return False

    if lhs is None or rhs is None:
        return False
    if step.operator == "==":
        return lhs == rhs
    if step.operator == "!=":
        return lhs != rhs
    if step.operator == ">":
        return lhs > rhs
    if step.operator == ">=":
        return lhs >= rhs
    if step.operator == "<":
        return lhs < rhs
    return lhs <= rhs


def resolve(spec: TargetSpec, context: TargetContext, answers: dict[int, list[str]] | None = None) -> Resolution:
    """Walk ``spec`` over ``context``, returning resolved values + step errors.

    ``answers`` maps a ``choose`` step's index to the candidate ids the user
    selected; when present the step injects those candidates (in pick order) and
    continues instead of emitting a pending choice. This makes the resolver
    resumable across mid-path ``choose`` steps without backend-side state.
    """
    errors: list[TraceError] = []
    values: list[Any] = []
    pending_choices: list[PendingTargetChoice] = []
    current_type: ValueType | None = None

    for i, step in enumerate(spec.steps):
        if isinstance(step, SelectStep):
            if step.collection == "variable":
                binding = context.bindings.get(step.variable) if context.bindings else None
                if binding is None or not binding.element:
                    errors.append(TraceError(i, f"variable {step.variable!r} not bound or untyped"))
                    values, current_type = [], None
                elif binding.cardinality == "many":
                    many_values: list[Any] = []
                    for rid in binding.values:
                        many_values.extend(_lookup_literal(binding.element, rid, context))
                    values = many_values
                    current_type = ValueType(binding.element, "many")
                else:
                    values = _lookup_literal(binding.element, binding.value, context)
                    current_type = ValueType(binding.element, "one")
            elif step.collection == "source":
                if context.source_element is None:
                    errors.append(TraceError(i, "select source requires a declared source_kind"))
                    values, current_type = [], None
                else:
                    values = [context.source] if context.source is not None else []
                    current_type = ValueType(context.source_element, "one")
            else:
                col = tc.collection(step.collection)
                if col is None:
                    errors.append(TraceError(i, f"unknown collection {step.collection!r}"))
                    values, current_type = [], None
                elif step.collection == "self":
                    values = [context.subject] if context.subject is not None else []
                    current_type = ValueType(col.element, "one")
                elif step.collection not in context.collections:
                    seeded = _seed_collection(step.collection, context)
                    if seeded is None:
                        errors.append(TraceError(i, f"collection {step.collection!r} not provided by context"))
                        values, current_type = [], None
                    else:
                        values = seeded
                        current_type = ValueType(col.element, "one" if col.singular else "many")
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
                values = [v for v in values
                          if _match(v, step, f.type, _bound_value(step.value, context),
                                    current_type.element, context.repo)]
                # A type-proving filter narrows the element, so the next step may
                # be one only the narrower element has (see
                # ``target_catalog.narrowed_element``).
                narrowed = tc.narrowed_element(current_type.element, step.field, step.operator, step.value)
                if narrowed:
                    current_type = ValueType(narrowed, current_type.cardinality)
                # type otherwise unchanged

        elif isinstance(step, NavigateStep):
            if current_type is None:
                errors.append(TraceError(i, "navigate with no collection"))
                values, current_type = [], None
            else:
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
            else:
                agg = tc.aggregation(step.fn)
                field = tc.field(current_type.element, step.field) if step.field else None
                allowed = tc.aggregations_for(field.type if field else None)
                if agg is None:
                    errors.append(TraceError(i, f"unknown aggregation {step.fn!r}"))
                    values, current_type = [], None
                elif step.field and field is None:
                    errors.append(TraceError(i, f"unknown field {current_type.element}.{step.field}"))
                    values, current_type = [], None
                elif agg not in allowed:
                    what = f"a {field.type} field" if field else "a whole collection"
                    errors.append(TraceError(i, f"{step.fn} cannot run on {what}"))
                    values, current_type = [], None
                elif agg.name == "random":
                    if step.count < 1:
                        errors.append(TraceError(i, "random count must be >= 1"))
                        values, current_type = [], None
                    elif current_type.cardinality != "many":
                        errors.append(TraceError(i, "random requires a many-cardinality collection"))
                        values, current_type = [], None
                    else:
                        values = _sample(values, step.count)
                        current_type = ValueType(
                            current_type.element, "one" if step.count == 1 else "many")
                elif agg.output == "element":
                    # top/bottom: keep the element carrying the extreme value, so
                    # a later step can walk from the thing itself (the old `top`).
                    if current_type.cardinality != "many":
                        errors.append(TraceError(i, f"{step.fn} requires a many-cardinality collection"))
                        values, current_type = [], None
                    elif not values:
                        current_type = ValueType(current_type.element, "one")
                    else:
                        ranked = [(_to_number(_get_field(v, step.field)), v) for v in values]
                        usable = [(n, v) for n, v in ranked if n is not None]
                        if not usable:
                            values, current_type = [], ValueType(current_type.element, "one")
                        else:
                            _, chosen = (max if agg.name == "top" else min)(
                                usable, key=lambda pair: pair[0])
                            values = [chosen]
                            current_type = ValueType(current_type.element, "one")
                elif agg.name == "count":
                    values, current_type = [len(values)], ValueType("int", "one")
                else:
                    values = _aggregate(values, step.fn, step.field)
                    element = field.type if agg.output == "same" else agg.output
                    current_type = ValueType(element, "one")

        elif isinstance(step, LiteralStep):
            if tc.element(step.element) is None:
                errors.append(TraceError(i, f"unknown literal element {step.element!r}"))
                values, current_type = [], None
            else:
                values = _lookup_literal(step.element, step.value, context)
                current_type = ValueType(step.element, "one")

        elif isinstance(step, ChooseStep):
            if current_type is None:
                errors.append(TraceError(i, "choose has no collection to pick from"))
                values, current_type = [], None
            elif step.count < 1:
                errors.append(TraceError(i, "choose count must be >= 1"))
                values, current_type = [], None
            elif current_type.cardinality != "many":
                errors.append(TraceError(i, "choose requires a many-cardinality collection"))
                values, current_type = [], None
            elif (answers or {}).get(i):
                # Resumable mid-path choose: the user already answered this step.
                # Inject the chosen candidates (in pick order) and keep walking.
                chosen: list[Any] = []
                for cid in answers[i]:
                    for v in values:
                        if _candidate_id(current_type.element, v) == cid:
                            chosen.append(v)
                            break
                values = chosen
                cardinality = "one" if step.count == 1 else "many"
                current_type = ValueType(current_type.element, cardinality)
            else:
                pending_choices.append(PendingTargetChoice(
                    element=current_type.element,
                    candidates=list(values),
                    count=step.count,
                    step_index=i,
                ))
                # The user's selection supplies the value; nothing resolved yet.
                values, current_type = [], None
                break

        elif isinstance(step, EvaluateStep):
            values = [_evaluate_step(values, current_type, step, context)]
            current_type = ValueType("boolean", "one")

        _bind_step_outputs(step, values, current_type, context)

    return Resolution(values, errors, pending_choices)


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
    if element == "pool":
        return _maybe(_pool_from_id(value, repo))
    if element == "die":
        return _maybe(_die_from_ref(value, repo))
    return []


# ── Default edge resolvers (repo-backed) ─────────────────────

def _maybe(obj: Any) -> list[Any]:
    return [obj] if obj is not None else []


def _die_owner(die: Any, ctx: TargetContext) -> list[Any]:
    eid = die.get("owner_id") if isinstance(die, dict) else None
    ent = ctx.repo.get_entity(eid) if eid else None
    return [ent] if ent else ([ctx.subject] if ctx.subject is not None else [])


# A resolved ``pool`` element is a lightweight handle the ``add_dice`` applier
# can turn into a concrete (location_id, owner_id) pool key.  ``id`` is the
# composite id the spec resolver hands back to ``_resolved_id``.
def _pool_handle(owner_id: str, location_id: str, kind: str) -> dict:
    return {"id": f"{kind}:{owner_id}", "owner_id": owner_id, "location_id": location_id, "kind": kind}


def _pool_dice(pool: Any, ctx: TargetContext) -> list[Any]:
    """The dice currently assembled in this pool.

    A ``pool`` element is a handle (owner + location + kind); the dice themselves
    live in the scene store, which is the one place that knows what a player has
    actually put in. Reading it here is what lets a path walk *whose pool* →
    *which dice* → *the trait behind one of them* (the opponent's water
    technique, say).

    Each die is returned as a copy carrying its **provenance** (``pool_location``
    / ``pool_owner`` / ``pool_index``), because a die in a pool has no id of its
    own: two dice from the same trait are different dice, and an effect that
    steps one down has to say *which* one. The store's own dicts are never
    touched.

    The GM difficulty pool answers with nothing on purpose: it is a *number* in
    the store, not a set of dice, so there is nothing for a path to walk into.
    """
    owner_id = _get_field(pool, "owner_id")
    location_id = _get_field(pool, "location_id")
    if not owner_id or not location_id or _get_field(pool, "kind") == "difficulty":
        return []
    try:
        from transversal.services.scene_state import get_scene_store

        dice = list(get_scene_store().get_pool(location_id, owner_id))
    except Exception:  # no store (a bare test context) → no dice, fail closed
        return []
    return [
        {**die, "pool_location": location_id, "pool_owner": owner_id, "pool_index": i}
        for i, die in enumerate(dice)
    ]


def _die_from_ref(value: str, repo) -> dict | None:
    """Reconstitute the die a reference names (``die:<location>:<owner>:<index>``).

    The mirror of :func:`_pool_from_id`. A die in a pool has no id — two dice from
    the same trait are different dice — so the reference carries *where it sits*
    and this reads the pool back. That is what makes a **bound** die usable in a
    path: a binding that names a die (the pool's `added_dice`, say) is exactly such
    a reference, and without this a rule could hold the right die and still resolve
    to nobody.
    """
    parts = (value or "").split(":")
    if len(parts) != 4 or parts[0] != "die":
        return None
    _, location_id, owner_id, index = parts
    if not location_id or not owner_id:
        return None
    try:
        want = int(index)
    except ValueError:
        return None
    dice = _pool_dice(
        {"id": f"pool:{owner_id}", "owner_id": owner_id,
         "location_id": location_id, "kind": "pool"},
        TargetContext(repo=repo),
    )
    for die in dice:
        if die.get("pool_index") == want:
            return die
    return None


def _pool_from_id(value: str, repo) -> Any | None:
    """Reconstitute a pool handle from its composite id (literal ``pool`` step)."""
    v = (value or "").strip()
    if not v:
        return None
    if v.startswith("difficulty:"):
        loc = v[len("difficulty:"):]
        return _pool_handle(loc, loc, "difficulty")
    if v.startswith("pool:"):
        owner_id = v[len("pool:"):]
        owner = repo.get_entity(owner_id) if repo else None
        return _pool_handle(owner_id, owner.current_location if owner else "", "pool")
    return None


def _traitsetting_tags(ts: Any, repo) -> list[str]:
    """A trait *instance*'s tags: its own, plus its registry trait's (B116).

    The two are unioned rather than one overriding the other, so a tag on the
    registry trait stays true of every instance (a violent trait is still
    violent), while an instance can add context of its own. Existing data has no
    instance tags, so this is identical to the old read-through.
    """
    if repo is None:
        return []
    own = [t for t in (getattr(ts, "tags", None) or []) if t]
    trait_id = _get_field(ts, "trait_id")
    trait = repo.get_trait(trait_id) if trait_id else None
    inherited = [t for t in (getattr(trait, "tags", None) or []) if t]
    return own + [t for t in inherited if t not in own]


def register_default_fields() -> None:
    register_derived_field("traitsetting", "tags", _traitsetting_tags)


def register_default_edges() -> None:
    register_edge("die", "traitsetting", lambda d, ctx: _maybe(ctx.repo.get_traitsetting(d.get("ts_id"))))
    register_edge("die", "owner", _die_owner)

    register_edge("traitsetting", "trait", lambda ts, ctx: _maybe(ctx.repo.get_trait(ts.trait_id)))
    register_edge("traitsetting", "traitset", lambda ts, ctx: _maybe(ctx.repo.get_traitset_by_id(ts.traitset_id)))
    register_edge("traitsetting", "entity", lambda ts, ctx: _maybe(ctx.repo.get_entity(ts.entity_id)))
    register_edge("traitsetting", "projection",
                  lambda ts, ctx: _maybe(ctx.repo.get_projection(ts.projection_id)) if ts.projection_id else [])
    # The instances nested under this one (elemental roots under Spiritual Power).
    # One repo read: sub-traits share the traitsettings collection, anchored to
    # the parent and marked `from_type == 'traitsetting'`.
    register_edge("traitsetting", "subtraits",
                  lambda ts, ctx: list(ctx.repo.get_sub_traitsettings(ts.id)))

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
    register_edge("location", "difficulty_pool",
                  lambda l, ctx: [_pool_handle(l.id, l.id, "difficulty")])

    register_edge("entity", "pool",
                  lambda e, ctx: [_pool_handle(e.id, e.current_location or "", "pool")])
    register_edge("pool", "dice", _pool_dice)

    register_edge("traitset", "traits", lambda ts, ctx: list(ctx.repo.get_traits_by_traitset(ts.id)))
    register_edge("trait", "traitset", lambda t, ctx: _maybe(ctx.repo.get_traitset_by_id(t.traitset_id)))
    register_edge("trait", "universes",
                  lambda t, ctx: [ctx.repo.get_entity(u) for u in (t.universes or []) if ctx.repo.get_entity(u)])


register_default_edges()
register_default_fields()
