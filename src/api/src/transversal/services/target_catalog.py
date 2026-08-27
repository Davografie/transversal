"""Declarative targeting catalog.

The single source of truth for the spec pipeline (``select`` / ``filter`` /
``navigate`` / ``aggregate``): which element types exist, which navigation
edges connect them, which scalar fields are comparable/aggregatable, which
aggregations collapse a collection to a scalar, and which context collections
a spec may seed from.

Both the resolver and the authoring wizard read this catalog, so they can only
compose valid, type-checked steps. Adding a new element type, edge, field,
aggregation, or collection is a declaration here plus a repo read in the
resolver — nothing else changes.
"""

from __future__ import annotations

from dataclasses import dataclass


# ── Element types ──────────────────────────────────────────────

@dataclass(frozen=True)
class ElementType:
    """A kind of game object a spec can resolve to."""
    name: str
    label: str


ELEMENT_TYPES: dict[str, ElementType] = {
    "die": ElementType("die", "Die"),
    "traitsetting": ElementType("traitsetting", "Trait instance"),
    "trait": ElementType("trait", "Trait"),
    "traitset": ElementType("traitset", "Trait set"),
    "entity": ElementType("entity", "Entity"),
    "projection": ElementType("projection", "Projection"),
    "location": ElementType("location", "Location"),
    "universe": ElementType("universe", "Universe"),
}


# ── Scalar fields (comparable / aggregatable) ─────────────────

@dataclass(frozen=True)
class ScalarField:
    """A scalar value on an element, usable in a filter or an aggregation."""
    element: str
    name: str
    type: str  # "int" | "number" | "die" | "string"


# A "die" field is comparable (d4 < d6 < … < d12); numeric for mean after
# converting to its max value (resolver's job).
SCALAR_FIELDS: dict[str, dict[str, ScalarField]] = {
    "die": {
        "result": ScalarField("die", "result", "int"),
        "rating": ScalarField("die", "rating", "die"),
        "effect_die": ScalarField("die", "effect_die", "die"),
        "tier": ScalarField("die", "tier", "string"),
        "role": ScalarField("die", "role", "string"),
    },
    "traitsetting": {
        "rating": ScalarField("traitsetting", "rating", "die"),
        "rating_type": ScalarField("traitsetting", "rating_type", "string"),
    },
    "trait": {
        "default_die_type": ScalarField("trait", "default_die_type", "die"),
    },
    "entity": {
        "razmerit": ScalarField("entity", "razmerit", "int"),
        "type": ScalarField("entity", "type", "string"),
    },
    "projection": {
        "type": ScalarField("projection", "type", "string"),
    },
    "location": {
        "type": ScalarField("location", "type", "string"),
    },
}


# ── Navigation edges ───────────────────────────────────────────

@dataclass(frozen=True)
class Edge:
    """A named hop from one element type to another.

    ``target`` is a tuple of possible element types (union-capable). Most edges
    are single-typed (length 1); a polymorphic hop like ``traitsetting._from``
    can later declare ``("entity", "projection")`` without a schema change.
    """
    name: str
    source: str
    target: tuple[str, ...]
    cardinality: str  # "one" (1→1) or "many" (1→N)
    label: str = ""


EDGES: tuple[Edge, ...] = (
    # die → its trait instance (ts_id) and its pool/roll owner
    Edge("traitsetting", "die", ("traitsetting",), "one", "Owning trait instance"),
    Edge("owner", "die", ("entity",), "one", "Pool owner"),

    # traitsetting → registry trait / traitset / owners
    # (the polymorphic `_from` anchor is split into already-distinct fields)
    Edge("trait", "traitsetting", ("trait",), "one", "Registry trait"),
    Edge("traitset", "traitsetting", ("traitset",), "one", "Trait set"),
    Edge("entity", "traitsetting", ("entity",), "one", "Owning entity"),
    Edge("projection", "traitsetting", ("projection",), "one", "Owning projection"),

    # entity → location / universe / projections / its trait instances
    Edge("location", "entity", ("location",), "one", "Current location"),
    Edge("universe", "entity", ("universe",), "one", "Current universe"),
    Edge("projection", "entity", ("projection",), "one", "Current projection"),
    Edge("projections", "entity", ("projection",), "many", "All projections"),
    Edge("traitsettings", "entity", ("traitsetting",), "many", "Trait instances"),

    # projection → owning entity / current location
    Edge("entity", "projection", ("entity",), "one", "Owning entity"),
    Edge("location", "projection", ("location",), "one", "Current location"),

    # location → universe / occupants
    Edge("universe", "location", ("universe",), "one", "Universe"),
    Edge("occupants", "location", ("entity",), "many", "Occupants"),

    # traitset ↔ trait, trait → universes
    Edge("traits", "traitset", ("trait",), "many", "Traits"),
    Edge("traitset", "trait", ("traitset",), "one", "Trait set"),
    Edge("universes", "trait", ("universe",), "many", "Universes"),
)


# ── Aggregations ───────────────────────────────────────────────

@dataclass(frozen=True)
class Aggregation:
    """Collapses a collection to a scalar.

    ``output`` is ``"int"`` (count), ``"number"`` (mean/avg_*), or ``"same"``
    (min/max — the field's own type). ``needs_field`` is False only for count.
    """
    name: str
    label: str
    output: str
    needs_field: bool


AGGREGATIONS: tuple[Aggregation, ...] = (
    Aggregation("count", "Count", "int", False),
    Aggregation("min", "Minimum", "same", True),
    Aggregation("max", "Maximum", "same", True),
    Aggregation("mean", "Mean", "number", True),
    Aggregation("avg_floor", "Average (floor)", "number", True),
    Aggregation("avg_ceil", "Average (ceil)", "number", True),
)


# ── Starting collections (the `select` step's options) ────────

@dataclass(frozen=True)
class Collection:
    """A context collection a spec may seed from via ``select``."""
    name: str
    element: str
    label: str
    singular: bool = False  # True for singleton seeds like "self"


COLLECTIONS: tuple[Collection, ...] = (
    Collection("self", "entity", "The acting entity", singular=True),
    Collection("rolled_dice", "die", "Dice in the current roll"),
    Collection("occupants", "entity", "Entities at the current location"),
    Collection("locations", "location", "All locations"),
    Collection("entities", "entity", "All entities"),
    Collection("self_traitsettings", "traitsetting", "The acting entity's trait instances"),
)


# ── Query helpers ──────────────────────────────────────────────

def element(name: str) -> ElementType | None:
    return ELEMENT_TYPES.get(name)


def edge(source: str, name: str) -> Edge | None:
    for e in EDGES:
        if e.source == source and e.name == name:
            return e
    return None


def edges_from(source: str) -> list[Edge]:
    return [e for e in EDGES if e.source == source]


def fields_for(element: str) -> list[ScalarField]:
    return list(SCALAR_FIELDS.get(element, {}).values())


def field(element: str, name: str) -> ScalarField | None:
    return SCALAR_FIELDS.get(element, {}).get(name)


def aggregation(name: str) -> Aggregation | None:
    for a in AGGREGATIONS:
        if a.name == name:
            return a
    return None


def collection(name: str) -> Collection | None:
    for c in COLLECTIONS:
        if c.name == name:
            return c
    return None


# ── Validation ─────────────────────────────────────────────────

def validate() -> list[str]:
    """Return internal-consistency problems (empty = valid)."""
    problems: list[str] = []
    seen_edges: set[tuple[str, str]] = set()
    for e in EDGES:
        if e.source not in ELEMENT_TYPES:
            problems.append(f"edge {e.source}.{e.name}: unknown source type")
        for t in e.target:
            if t not in ELEMENT_TYPES:
                problems.append(f"edge {e.source}.{e.name}: unknown target type {t!r}")
        if e.cardinality not in ("one", "many"):
            problems.append(f"edge {e.source}.{e.name}: bad cardinality {e.cardinality!r}")
        key = (e.source, e.name)
        if key in seen_edges:
            problems.append(f"duplicate edge {e.source}.{e.name}")
        seen_edges.add(key)

    for element_name, fields in SCALAR_FIELDS.items():
        if element_name not in ELEMENT_TYPES:
            problems.append(f"scalar fields for unknown element {element_name!r}")
        for f in fields.values():
            if f.type not in ("int", "number", "die", "string"):
                problems.append(f"field {element_name}.{f.name}: bad type {f.type!r}")

    for a in AGGREGATIONS:
        if a.output not in ("int", "number", "same"):
            problems.append(f"aggregation {a.name}: bad output {a.output!r}")

    for c in COLLECTIONS:
        if c.element not in ELEMENT_TYPES:
            problems.append(f"collection {c.name}: unknown element {c.element!r}")

    return problems
