"""Target spec — the structured targeting pipeline and its type-checker.

A ``TargetSpec`` is an ordered list of steps (``select`` / ``filter`` /
``navigate`` / ``aggregate`` / ``literal`` / ``choose`` / ``top`` /
``evaluate``) that resolves a reference against the game state. Random sampling
is an *aggregation* over a collection (``aggregate fn="random"``), not a step of
its own — one vocabulary, not two spellings that can drift.
This module owns the *shape* of the spec and the *type-checker* that walks a
spec against the [[target_catalog]] to verify it can reach a destination type.
(The runtime *resolver* — turning a valid spec into actual game objects — is a
separate layer.)

The type-checker is pure and catalog-driven, so the authoring wizard and the
resolver share one source of truth: a step is valid only if the catalog says
the hop/field/aggregation exists, and a spec is valid only if its final type
matches the effect field's declared type.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field, model_validator

from transversal.services import target_catalog as tc


# ── Steps ─────────────────────────────────────────────────────

class SelectStep(BaseModel):
    kind: Literal["select"] = "select"
    collection: str
    variable: str = ""  # for collection == "variable": the bound variable name
    output: str | None = None


class FilterStep(BaseModel):
    kind: Literal["filter"] = "filter"
    field: str
    operator: Literal["==", "!=", ">", ">=", "<", "<=", "in", "not in", "contains"] = "=="
    value: Any = None
    output: str | None = None


class NavigateStep(BaseModel):
    kind: Literal["navigate"] = "navigate"
    edge: str
    dedup: bool = False  # collapse N→1 by identity (type-neutral)
    output: str | None = None


class AggregateStep(BaseModel):
    kind: Literal["aggregate"] = "aggregate"
    fn: str
    field: str | None = None  # required for min/max/mean/avg_*
    #: Sample size for ``fn="random"``: 1 collapses ``many → one``, more keeps the
    #: collection cardinality (a random subset). Ignored by the other functions.
    count: int = 1
    output: str | None = None


class LiteralStep(BaseModel):
    kind: Literal["literal"] = "literal"
    element: str = ""  # element type name (entity/trait/location/…)
    value: str = ""    # the concrete id
    output: str | None = None


class ChooseStep(BaseModel):
    """Collapse a many-cardinality collection by user selection.

    ``count`` 1 collapses ``many → one`` (pick a single candidate);
    ``count > 1`` keeps the cardinality ``many`` (a user-selected subset).
    Element type is unchanged. This is the interactive resolution mode — the
    resolver emits a pending choice carrying the candidate set rather than
    picking automatically (the non-interactive counterpart is ``random``).

    Phase 2 implements the *terminal* case only: a ``choose`` step stops
    resolution at the candidate set. Mid-path ``choose`` (resumable, suffix
    resolution) is deferred to Phase 3.
    """
    kind: Literal["choose"] = "choose"
    count: int = 1
    output: str | None = None


class EvaluateStep(BaseModel):
    """Terminal boolean test over the current collection/scalar.

    ``operator="exists"`` passes when the collection is non-empty (no LHS/value).
    For a comparison, ``field`` names the left-hand side:
      - ``"count"`` — the number of elements in the collection (the default);
      - a scalar field name (e.g. ``"rating"``) — a single object's field, or a
        scalar element's value;
      - ``""`` — legacy implicit: ``count`` for a ``many`` collection, the scalar
        value for ``int``/``number``/``die``, or identity for a single object.
    ``value`` is the right-hand side. Produces ``boolean/one``.
    """
    kind: Literal["evaluate"] = "evaluate"
    operator: Literal["exists", "==", "!=", ">", ">=", "<", "<="] = "exists"
    field: str = ""  # LHS: "count" | a scalar field name | "" (legacy implicit)
    value: Any = None


TargetStep = Annotated[
    Union[SelectStep, FilterStep, NavigateStep, AggregateStep, LiteralStep, ChooseStep, EvaluateStep],
    Field(discriminator="kind"),
]


class TargetSpec(BaseModel):
    steps: list[TargetStep] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _fold_legacy_random_step(cls, data):
        """A stored ``{"kind": "random"}`` step reads as ``aggregate fn="random"``.

        Random sampling became an aggregation; specs authored before that keep
        resolving, and both spellings can never drift because only one survives
        parsing.
        """
        if not isinstance(data, dict):
            return data
        steps = data.get("steps")
        if not isinstance(steps, list):
            return data
        folded = []
        for s in steps:
            if not isinstance(s, dict):
                folded.append(s)
                continue
            kind = s.get("kind")
            if kind == "random":
                folded.append({**s, "kind": "aggregate", "fn": "random"})
            elif kind == "top":
                # The old `top` step is an aggregate function now (argmax/argmin).
                rest = {k: v for k, v in s.items() if k != "direction"}
                folded.append({**rest, "kind": "aggregate",
                               "fn": "bottom" if s.get("direction") == "asc" else "top"})
            else:
                folded.append(s)
        return {**data, "steps": folded}


# ── Value type ────────────────────────────────────────────────

@dataclass(frozen=True)
class ValueType:
    """A resolved value's type: an element type (or scalar) × cardinality."""
    element: str        # element type name, or a scalar ("int" | "number" | "die" | "string")
    cardinality: str    # "one" | "many"

    def matches(self, other: "ValueType") -> bool:
        return self.element == other.element and self.cardinality == other.cardinality


@dataclass(frozen=True)
class TraceError:
    step_index: int
    message: str


def _coerce_variables(variables) -> dict[str, ValueType]:
    """Normalize a bound-variable scope to ``name → ValueType``.

    Accepts ``None``, a ``name → element`` string map (cardinality defaults to
    ``"one"``), a ``name → ValueType`` map, or a ``name → {element,
    cardinality}`` dict map. This keeps callers that only know the element type
    working while letting the typed scope carry cardinality.
    """
    if not variables:
        return {}
    out: dict[str, ValueType] = {}
    for name, v in variables.items():
        if isinstance(v, ValueType):
            out[name] = v
        elif isinstance(v, dict):
            out[name] = ValueType(v.get("element", ""), v.get("cardinality", "one"))
        elif isinstance(v, str):
            out[name] = ValueType(v, "one")
        else:
            out[name] = ValueType("", "one")
    return out


# ── Type-checker ──────────────────────────────────────────────

def trace(spec: TargetSpec, source_element: str | None = None,
          variables=None) -> tuple[list[ValueType | None], list[TraceError]]:
    """Walk a spec, returning the type after each step plus any errors.

    ``types[i]`` is the collection type after ``spec.steps[i]``. ``errors`` are
    step-level failures (unknown collection/edge/field/aggregation, or a
    malformed aggregation). ``types[i]`` is None where a step failed.

    ``source_element`` is the catalog element type of the SFX's declared
    ``source_kind``; ``select source`` uses it (and errors without it).
    ``variables`` maps a bound output-variable name to its type (element string
    or ``ValueType``); ``select variable`` uses it. See :func:`_coerce_variables`.
    """
    types: list[ValueType | None] = []
    errors: list[TraceError] = []
    current: ValueType | None = None
    scope: dict[str, ValueType] = _coerce_variables(variables)  # accumulates step outputs too

    for i, step in enumerate(spec.steps):
        if isinstance(step, SelectStep):
            if step.collection == "variable":
                vt = scope.get(step.variable)
                if not step.variable or vt is None:
                    errors.append(TraceError(i, f"unknown variable {step.variable!r}"))
                    current = None
                elif tc.element(vt.element) is None:
                    errors.append(TraceError(i, f"unknown element {vt.element!r} for variable {step.variable!r}"))
                    current = None
                else:
                    current = ValueType(vt.element, vt.cardinality)
            elif step.collection == "source":
                if source_element is None:
                    errors.append(TraceError(i, "select source requires a declared source_kind"))
                    current = None
                elif tc.element(source_element) is None:
                    errors.append(TraceError(i, f"unknown source element {source_element!r}"))
                    current = None
                else:
                    current = ValueType(source_element, "one")
            else:
                col = tc.collection(step.collection)
                if col is None:
                    errors.append(TraceError(i, f"unknown collection {step.collection!r}"))
                    current = None
                else:
                    current = ValueType(col.element, "one" if col.singular else "many")

        elif isinstance(step, FilterStep):
            if current is None:
                errors.append(TraceError(i, "filter has no collection to narrow"))
            elif tc.field(current.element, step.field) is None:
                errors.append(TraceError(i, f"unknown field {current.element}.{step.field}"))
            else:
                # A filter can *prove* the element a step narrower (a type test),
                # which is what lets a location-only hop follow an entity filter.
                narrowed = tc.narrowed_element(current.element, step.field, step.operator, step.value)
                if narrowed:
                    current = ValueType(narrowed, current.cardinality)
            # type otherwise unchanged

        elif isinstance(step, NavigateStep):
            if current is None:
                errors.append(TraceError(i, "navigate has no source collection"))
                current = None
                continue
            e = tc.edge(current.element, step.edge)
            if e is None:
                errors.append(TraceError(i, f"no edge {current.element}.{step.edge}"))
                current = None
            elif len(e.target) != 1:
                # Union resolution is deferred (see plan); flag rather than guess.
                errors.append(TraceError(i, f"edge {current.element}.{step.edge} is a union; not yet resolvable"))
                current = None
            else:
                cardinality = "many" if (current.cardinality == "many" or e.cardinality == "many") else "one"
                current = ValueType(e.target[0], cardinality)

        elif isinstance(step, AggregateStep):
            if current is None:
                errors.append(TraceError(i, "aggregate has no collection to collapse"))
                current = None
                continue
            agg = tc.aggregation(step.fn)
            field = tc.field(current.element, step.field) if step.field else None
            allowed = tc.aggregations_for(field.type if field else None)
            if agg is None:
                errors.append(TraceError(i, f"unknown aggregation {step.fn!r}"))
                current = None
            elif step.field and field is None:
                errors.append(TraceError(i, f"unknown field {current.element}.{step.field}"))
                current = None
            elif agg not in allowed:
                # The field decides the functions (a datetime cannot be averaged).
                what = f"a {field.type} field" if field else "a whole collection"
                errors.append(TraceError(i, f"{step.fn} cannot run on {what}"))
                current = None
            elif agg.name == "random":
                if step.count < 1:
                    errors.append(TraceError(i, "random count must be >= 1"))
                    current = None
                elif current.cardinality != "many":
                    errors.append(TraceError(i, "random requires a many-cardinality collection"))
                    # type unchanged (element preserved; caller sees the error)
                else:
                    current = ValueType(current.element, "one" if step.count == 1 else "many")
            elif agg.output == "element":
                # top/bottom keep the element carrying the extreme value.
                if current.cardinality != "many":
                    errors.append(TraceError(i, f"{step.fn} requires a many-cardinality collection"))
                current = ValueType(current.element, "one")
            else:
                element = field.type if (agg.output == "same" and field) else agg.output
                current = ValueType(element, "one")

        elif isinstance(step, LiteralStep):
            if tc.element(step.element) is None:
                errors.append(TraceError(i, f"unknown literal element {step.element!r}"))
                current = None
            else:
                current = ValueType(step.element, "one")

        elif isinstance(step, ChooseStep):
            if current is None:
                errors.append(TraceError(i, "choose has no collection to pick from"))
                current = None
            elif step.count < 1:
                errors.append(TraceError(i, "choose count must be >= 1"))
                current = None
            elif current.cardinality != "many":
                errors.append(TraceError(i, "choose requires a many-cardinality collection"))
                # type unchanged (element preserved; caller sees the error)
            else:
                cardinality = "one" if step.count == 1 else "many"
                current = ValueType(current.element, cardinality)

        elif isinstance(step, EvaluateStep):
            if current is None:
                errors.append(TraceError(i, "evaluate has nothing to test"))
                current = None
            elif step.operator == "exists":
                current = ValueType("boolean", "one")
            else:
                field_name = (step.field or "").strip()
                if field_name and field_name != "count":
                    if current.element in ("int", "number", "die"):
                        current = ValueType("boolean", "one")
                    elif current.cardinality == "many":
                        errors.append(TraceError(i, f"evaluate on {field_name!r} needs a single value — add an aggregate step first"))
                        current = ValueType("boolean", "one")
                    else:
                        f = tc.field(current.element, field_name)
                        if f is None:
                            errors.append(TraceError(i, f"unknown field {current.element}.{field_name}"))
                        elif f.type not in ("int", "number", "die", "string"):
                            errors.append(TraceError(i, f"{current.element}.{field_name} is not a comparable scalar"))
                        current = ValueType("boolean", "one")
                else:
                    current = ValueType("boolean", "one")

        if getattr(step, "output", None) and current is not None and current.element:
            scope[step.output] = current

        types.append(current)

    return types, errors


def final_type(spec: TargetSpec, source_element: str | None = None,
                variables=None) -> ValueType | None:
    """The type a valid spec resolves to, or None if it errors."""
    types, errors = trace(spec, source_element, variables)
    if errors or not types:
        return None
    return types[-1]


def check(spec: TargetSpec, destination, source_element: str | None = None,
          variables=None) -> tuple[bool, list[TraceError]]:
    """True when ``spec`` type-checks and its final type matches ``destination``.

    ``destination`` is a :class:`ValueType` or an iterable of them. A destination
    may be a **union** because an action can accept more than one kind of thing —
    a `Change a Die` effect lands on a die in a pool *or* a die of a trait's
    rating, and both are legal. The spec is valid when its final type matches any
    of them, and the refusal names every type that would have worked.
    """
    types, errors = trace(spec, source_element, variables)
    if errors:
        return False, errors
    final = types[-1] if types else None
    if final is None:
        return False, [TraceError(-1, "spec resolves to nothing")]
    wanted = (destination,) if isinstance(destination, ValueType) else tuple(destination)
    if not any(final.matches(w) for w in wanted):
        wanted_text = " or ".join(f"{w.element}/{w.cardinality}" for w in wanted)
        return False, [TraceError(
            len(types) - 1,
            f"spec resolves to {final.element}/{final.cardinality}, not {wanted_text}",
        )]
    return True, []


def spec_variables(spec: TargetSpec, source_element: str | None = None,
                   variables=None) -> dict[str, ValueType]:
    """The variable scope after tracing ``spec`` — the seed plus any step
    outputs typed by their resolved element and cardinality.

    Used to compute which typed variables an effect's specs expose, so later
    effects can ``select variable`` across the activation.
    """
    types, _errors = trace(spec, source_element, variables)
    scope = _coerce_variables(variables)
    for step, t in zip(spec.steps, types):
        if getattr(step, "output", None) and t is not None and t.element:
            scope[step.output] = t
    return scope
