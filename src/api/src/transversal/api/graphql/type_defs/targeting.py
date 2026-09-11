"""Targeting — split out of src/api/src/transversal/api/graphql/types.py."""

import strawberry

from typing import Optional


@strawberry.type
class TargetCandidate:
    """A selectable target returned by the choose/random candidate resolver."""
    id: strawberry.ID
    name: str
    universe: str = ""
    subtitle: str = ""

@strawberry.type
class FilterFieldOption:
    """A candidate field the author may filter on, plus editor metadata."""
    field: str
    label: str
    value_type: str = "boolean"
    kinds: list[str] = strawberry.field(default_factory=list)
    options: list[str] = strawberry.field(default_factory=list)

@strawberry.type
class ScopeVariable:
    """A ``{variable}`` token an SFX author may use, plus its data type."""
    name: str
    type: str  # "number" | "entity" | "die" | "string"

@strawberry.type
class EffectVariable:
    """A typed output variable an effect exposes for later effects/steps."""
    name: str
    element: str
    cardinality: str = "one"  # "one" | "many"

@strawberry.type
class TriggerOption:
    """One activation trigger selectable in the SFX editor."""
    value: str
    label: str
    group: str = "auto"  # "auto" | "manual" | "menu"

@strawberry.type
class ConditionTypeOption:
    """One condition type selectable in the SFX editor, plus target hints."""
    value: str
    label: str
    needs_target: bool = False
    target_placeholder: str = ""
    target_kind: str = ""
    value_kind: str = ""
    operators: list[str] = strawberry.field(default_factory=list)
    target_options: list[str] = strawberry.field(default_factory=list)
    uses_spec: bool = False
    # Context keys this condition may read ("any of"): the editor keeps the
    # option out of a site that supplies none of them. The exact per-condition
    # answer is `conditionContextKeys` / `validate_sfx`.
    requires_context_any_of: list[str] = strawberry.field(default_factory=list)
    # Catalog elements ("traitsetting", …) the SFX's source must resolve to, or
    # the condition can never pass — the editor greys it out with the reason.
    requires_source_elements: list[str] = strawberry.field(default_factory=list)

@strawberry.type
class TargetCatalogElement:
    """A kind of game object a targeting spec can resolve to."""
    name: str
    label: str

@strawberry.type
class TargetCatalogEdge:
    """A named navigation hop from one element type to another."""
    name: str
    source: str
    targets: list[str]
    cardinality: str  # "one" | "many"
    label: str = ""

@strawberry.type
class TargetCatalogField:
    """A comparable/aggregatable scalar field on an element type."""
    element: str
    name: str
    type: str  # "int" | "number" | "die" | "string"
    options: list[str] = strawberry.field(default_factory=list)
    operators: list[str] = strawberry.field(default_factory=list)
    references: str = ""  # element type this id field points at (e.g. traitset)
    suggest: str = ""  # value source for a data-driven field (e.g. trait_tags)

@strawberry.type
class TargetCatalogAggregation:
    """A collapse of a collection to a scalar."""
    name: str
    label: str
    output: str  # "int" | "number" | "same"
    needs_field: bool

@strawberry.type
class TargetCatalogCollection:
    """A context collection a spec may seed from via ``select``."""
    name: str
    element: str
    label: str
    singular: bool = False

@strawberry.type
class SourceKindOption:
    """A declarative SFX source kind (owner type + its exposed variable)."""
    value: str
    label: str
    element: str
    variable: str
    owner_surface: str

@strawberry.type
class TargetCatalog:
    """The full declarative targeting catalog, consumed by the wizard."""
    elements: list[TargetCatalogElement]
    edges: list[TargetCatalogEdge]
    fields: list[TargetCatalogField]
    aggregations: list[TargetCatalogAggregation]
    collections: list[TargetCatalogCollection]
    source_kinds: list[SourceKindOption]

@strawberry.input
class TargetSpecStepInput:
    """One step of a targeting spec (kind discriminates the relevant fields)."""
    kind: str  # "select" | "filter" | "navigate" | "aggregate" | "random" | "choose" | "top"
    collection: Optional[str] = None
    variable: Optional[str] = None  # for kind == "select" + collection == "variable"
    output: Optional[str] = None  # bound variable name this step exposes
    field: Optional[str] = None
    operator: str = "=="
    value: Optional[strawberry.scalars.JSON] = None
    edge: Optional[str] = None
    dedup: bool = False
    fn: Optional[str] = None
    count: Optional[int] = None  # random/choose: elements to sample (default 1)
    direction: Optional[str] = None  # top: "desc" (highest/most recent) | "asc"

@strawberry.input
class TargetSpecInput:
    """An ordered pipeline of targeting steps."""
    steps: list[TargetSpecStepInput] = strawberry.field(default_factory=list)

@strawberry.type
class TargetTraceType:
    """The resolved value type after one spec step (empty = no valid type)."""
    element: str = ""
    cardinality: str = ""  # "one" | "many"

@strawberry.type
class TargetTraceError:
    """A step-level type error."""
    step_index: int
    message: str

@strawberry.type
class TargetTraceResult:
    """The type trace of a spec: the type after each step plus errors."""
    types: list[TargetTraceType]
    errors: list[TargetTraceError]
    valid: bool = False
