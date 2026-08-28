"""Target spec — the structured targeting pipeline and its type-checker.

A ``TargetSpec`` is an ordered list of steps (``select`` / ``filter`` /
``navigate`` / ``aggregate``) that resolves a reference against the game state.
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

from pydantic import BaseModel, Field

from transversal.services import target_catalog as tc


# ── Steps ─────────────────────────────────────────────────────

class SelectStep(BaseModel):
    kind: Literal["select"] = "select"
    collection: str


class FilterStep(BaseModel):
    kind: Literal["filter"] = "filter"
    field: str
    operator: Literal["==", "!=", ">", ">=", "<", "<=", "in", "contains"] = "=="
    value: Any = None


class NavigateStep(BaseModel):
    kind: Literal["navigate"] = "navigate"
    edge: str
    dedup: bool = False  # collapse N→1 by identity (type-neutral)


class AggregateStep(BaseModel):
    kind: Literal["aggregate"] = "aggregate"
    fn: str
    field: str | None = None  # required for min/max/mean/avg_*


class LiteralStep(BaseModel):
    kind: Literal["literal"] = "literal"
    element: str = ""  # element type name (entity/trait/location/…)
    value: str = ""    # the concrete id


TargetStep = Annotated[
    Union[SelectStep, FilterStep, NavigateStep, AggregateStep, LiteralStep],
    Field(discriminator="kind"),
]


class TargetSpec(BaseModel):
    steps: list[TargetStep] = Field(default_factory=list)


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


# ── Type-checker ──────────────────────────────────────────────

def trace(spec: TargetSpec, source_element: str | None = None) -> tuple[list[ValueType | None], list[TraceError]]:
    """Walk a spec, returning the type after each step plus any errors.

    ``types[i]`` is the collection type after ``spec.steps[i]``. ``errors`` are
    step-level failures (unknown collection/edge/field/aggregation, or a
    malformed aggregation). ``types[i]`` is None where a step failed.

    ``source_element`` is the catalog element type of the SFX's declared
    ``source_kind``; ``select source`` uses it (and errors without it).
    """
    types: list[ValueType | None] = []
    errors: list[TraceError] = []
    current: ValueType | None = None

    for i, step in enumerate(spec.steps):
        if isinstance(step, SelectStep):
            if step.collection == "source":
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
            # type unchanged

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
            if agg is None:
                errors.append(TraceError(i, f"unknown aggregation {step.fn!r}"))
                current = None
            elif not agg.needs_field:
                current = ValueType(agg.output, "one")
            elif step.field is None:
                errors.append(TraceError(i, f"aggregation {step.fn} needs a field"))
                current = None
            else:
                f = tc.field(current.element, step.field)
                if f is None:
                    errors.append(TraceError(i, f"unknown field {current.element}.{step.field}"))
                    current = None
                elif agg.output == "same":
                    current = ValueType(f.type, "one")
                else:
                    current = ValueType(agg.output, "one")

        elif isinstance(step, LiteralStep):
            if tc.element(step.element) is None:
                errors.append(TraceError(i, f"unknown literal element {step.element!r}"))
                current = None
            else:
                current = ValueType(step.element, "one")

        types.append(current)

    return types, errors


def final_type(spec: TargetSpec, source_element: str | None = None) -> ValueType | None:
    """The type a valid spec resolves to, or None if it errors."""
    types, errors = trace(spec, source_element)
    if errors or not types:
        return None
    return types[-1]


def check(spec: TargetSpec, destination: ValueType, source_element: str | None = None) -> tuple[bool, list[TraceError]]:
    """True when ``spec`` type-checks and its final type matches ``destination``."""
    types, errors = trace(spec, source_element)
    if errors:
        return False, errors
    final = types[-1] if types else None
    if final is None:
        return False, [TraceError(-1, "spec resolves to nothing")]
    if not final.matches(destination):
        return False, [TraceError(
            len(types) - 1,
            f"spec resolves to {final.element}/{final.cardinality}, not {destination.element}/{destination.cardinality}",
        )]
    return True, []
