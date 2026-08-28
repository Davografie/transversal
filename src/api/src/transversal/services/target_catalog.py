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
    "traitsetsetting": ElementType("traitsetsetting", "Trait set instance"),
    "trait": ElementType("trait", "Trait"),
    "traitset": ElementType("traitset", "Trait set"),
    "entity": ElementType("entity", "Entity"),
    "projection": ElementType("projection", "Projection"),
    "location": ElementType("location", "Location"),
    "universe": ElementType("universe", "Universe"),
    "pool": ElementType("pool", "Dice pool"),
}


# ── Scalar fields (comparable / aggregatable) ─────────────────

@dataclass(frozen=True)
class ScalarField:
    """A scalar value on an element, usable in a filter or an aggregation.

    ``options`` lists the accepted values for enum-like string fields so the
    wizard can render a dropdown instead of a free-text input. ``operators``
    overrides the operators valid for this field (default derived from ``type``).
    ``references`` names the element type the field points at (e.g. ``traitset_id``
    → ``traitset``), so the wizard can render a picker for id-reference fields.
    """
    element: str
    name: str
    type: str  # "int" | "number" | "die" | "string"
    options: tuple[str, ...] = ()
    operators: tuple[str, ...] = ()
    references: str = ""


# Operators valid per field type. Ordering operators only make sense on
# comparable (numeric/die) fields; strings only support equality/membership.
_ORDERED_OPERATORS = ("==", "!=", ">", ">=", "<", "<=", "in")
_STRING_OPERATORS = ("==", "!=", "in")


def operators_for(field: ScalarField) -> tuple[str, ...]:
    """The operators valid for a field (explicit override, else by type)."""
    if field.operators:
        return field.operators
    if field.type in ("int", "number", "die"):
        return _ORDERED_OPERATORS
    return _STRING_OPERATORS


# A "die" field is comparable (d4 < d6 < … < d12); numeric for mean after
# converting to its max value (resolver's job).
SCALAR_FIELDS: dict[str, dict[str, ScalarField]] = {
    "die": {
        "result": ScalarField("die", "result", "int"),
        "rating": ScalarField("die", "rating", "die", ("d4", "d6", "d8", "d10", "d12")),
        "effect_die": ScalarField("die", "effect_die", "die", ("d4", "d6", "d8", "d10", "d12")),
        "tier": ScalarField("die", "tier", "string", ("fail", "marginal", "success", "exceptional", "perfect")),
        "role": ScalarField("die", "role", "string"),
        "source_kind": ScalarField("die", "source_kind", "string", ("trait", "difficulty", "manual", "entity", "projection", "location", "resource", "challenge")),
        "ts_id": ScalarField("die", "ts_id", "string"),
        # A list of SFX ids stamped on the die; filtered via the `contains` operator.
        "armed_sfx_ids": ScalarField("die", "armed_sfx_ids", "string", operators=("contains", "==", "!=")),
    },
    "traitsetting": {
        "rating": ScalarField("traitsetting", "rating", "die", ("d4", "d6", "d8", "d10", "d12")),
        "rating_type": ScalarField("traitsetting", "rating_type", "string", ("static", "resource", "challenge", "empty")),
        "polarity": ScalarField("traitsetting", "polarity", "string", ("positive", "negative")),
        "trait_id": ScalarField("traitsetting", "trait_id", "string", references="trait"),
        "traitset_id": ScalarField("traitsetting", "traitset_id", "string", references="traitset"),
        "entity_id": ScalarField("traitsetting", "entity_id", "string", references="entity"),
        "projection_id": ScalarField("traitsetting", "projection_id", "string", references="projection"),
        "from_type": ScalarField("traitsetting", "from_type", "string", ("entity", "projection")),
    },
    "traitsetsetting": {
        "entity_id": ScalarField("traitsetsetting", "entity_id", "string", references="entity"),
        "traitset_id": ScalarField("traitsetsetting", "traitset_id", "string", references="traitset"),
        "projection_id": ScalarField("traitsetsetting", "projection_id", "string", references="projection"),
        "from_type": ScalarField("traitsetsetting", "from_type", "string", ("entity", "projection")),
        "limit": ScalarField("traitsetsetting", "limit", "int"),
    },
    "trait": {
        "id": ScalarField("trait", "id", "string"),
        "traitset_id": ScalarField("trait", "traitset_id", "string", references="traitset"),
        "default_die_type": ScalarField("trait", "default_die_type", "die"),
    },
    "traitset": {
        "id": ScalarField("traitset", "id", "string"),
        "name": ScalarField("traitset", "name", "string"),
    },
    "entity": {
        "id": ScalarField("entity", "id", "string"),
        "razmerit": ScalarField("entity", "razmerit", "int"),
        "type": ScalarField("entity", "type", "string", ("character", "location", "faction", "asset", "gmc", "universe", "subtrait", "relation")),
        "current_location": ScalarField("entity", "current_location", "string", references="location"),
        "current_universe": ScalarField("entity", "current_universe", "string", references="universe"),
    },
    "projection": {
        "type": ScalarField("projection", "type", "string"),
        "entity_id": ScalarField("projection", "entity_id", "string", references="entity"),
        "current_location": ScalarField("projection", "current_location", "string", references="location"),
    },
    "location": {
        "id": ScalarField("location", "id", "string"),
        "name": ScalarField("location", "name", "string"),
        "type": ScalarField("location", "type", "string"),
        "universe": ScalarField("location", "universe", "string"),
    },
    "universe": {
        "id": ScalarField("universe", "id", "string"),
        "name": ScalarField("universe", "name", "string"),
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

    # entity / location → their dice pool (pool-assembly target for add_dice)
    Edge("pool", "entity", ("pool",), "one", "Dice pool"),
    Edge("difficulty_pool", "location", ("pool",), "one", "GM difficulty pool"),

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


# ── Source kinds (SFX activation origin) ────────────────────
#
# The declarative owner type an SFX can state. Each entry maps an author-facing
# ``source_kind`` to the catalog element its ``{variable}`` resolves to, the
# variable token name, and the owner surface it must attach to. This is the
# single seam for the entity/projection question: if those two ever merge, only
# the ``entity``/``projection`` rows here (and the runtime resolver) change.

@dataclass(frozen=True)
class SourceKind:
    value: str          # source_kind stored on SFX
    label: str          # editor dropdown label
    element: str        # catalog element the source variable resolves to
    variable: str       # the ``{variable}`` token exposed to effect authoring
    owner_surface: str  # SfxOwnerKind value this SFX must attach to


SOURCE_KINDS: tuple[SourceKind, ...] = (
    SourceKind("trait_setting", "Trait setting", "traitsetting", "trait_setting", "trait_instance"),
    SourceKind("traitset_setting", "Trait set setting", "traitsetsetting", "traitset_setting", "trait_set"),
    SourceKind("entity", "Entity", "entity", "entity", "entity"),
    SourceKind("projection", "Projection", "projection", "projection", "projection"),
)

_SOURCE_KINDS_BY_VALUE: dict[str, SourceKind] = {s.value: s for s in SOURCE_KINDS}


def source_kind(value: str) -> SourceKind | None:
    """The declared ``SourceKind`` for ``value``, or None when unknown/unset."""
    return _SOURCE_KINDS_BY_VALUE.get(value)


def source_variable(value: str) -> str | None:
    """The ``{variable}`` token a ``source_kind`` exposes (None when unset)."""
    sk = _SOURCE_KINDS_BY_VALUE.get(value)
    return sk.variable if sk else None


def source_element(value: str) -> str | None:
    """The catalog element type a ``source_kind``'s source resolves to."""
    sk = _SOURCE_KINDS_BY_VALUE.get(value)
    return sk.element if sk else None


def bind_source(source_kind: str, source_id: str | None, context: dict) -> dict:
    """Inject the declared source variable into a fire-time context.

    Maps ``source_kind`` → its ``{variable}`` token and binds ``source_id``
    under that key, so ``_substitute_effect_context`` replaces ``{trait_setting}``
    etc. with the concrete id. No-op when ``source_kind`` is unset/unknown or
    ``source_id`` is empty. This is the runtime half of the seam: the *type* is
    declared on the SFX, the *id* arrives from the activation (client click).
    """
    if not source_id:
        return context
    sk = _SOURCE_KINDS_BY_VALUE.get(source_kind)
    if sk is None:
        return context
    return {**context, sk.variable: source_id}


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

    for sk in SOURCE_KINDS:
        if sk.element not in ELEMENT_TYPES:
            problems.append(f"source_kind {sk.value}: unknown element {sk.element!r}")

    return problems
