"""Lifepath — split out of src/api/src/transversal/api/graphql/types.py."""

import strawberry

from transversal.domain import EntityType as DomainEntityType
from typing import Optional
from transversal.api.graphql.type_defs.conditions import (
    Condition,
    ConditionInput,
)
from transversal.api.graphql.type_defs.effects import (
    Effect,
    EffectInput,
)
from transversal.api.graphql.type_defs.entities import (
    PendingTerm,
)
from transversal.api.graphql.type_defs.sfx import (
    BoundVariable,
    BoundVariableInput,
)


@strawberry.type
class DiscoveryBlock:
    at_location: list[str]
    knows_entity: list[str]
    possesses_trait: list[str]
    has_trait_rating: strawberry.scalars.JSON  # dict[str, DieType]
    has_relationship: list[str]

@strawberry.type
class LifePathBinding:
    """A path's overlay on one row of a table it wraps — see the domain model.

    `next` is a **step id in this path** (not a table); `""` leaves the path, and
    `exitKind` then says what leaving means. Flow is structure here, not effects:
    the content decided it — all 15 muster/force_muster rows in the live tables
    carry nothing else and no `next_step`, so they are destinations, not effects.
    """
    key: str
    next: str = ""
    exit_kind: str = ""
    exit_path: str = ""
    enroll: bool = False
    effects: list[Effect] = strawberry.field(default_factory=list)

@strawberry.type
class LifePathStep:
    """One position in the path — a wrapped table, or effects and nothing else.

    The `id` is the step's, not the table's, so a path may wrap the same table
    twice and a step survives its table being re-pointed. An empty `table_id` is
    an **effects-only step** ([[B314]]): it applies its own effects and follows
    its own `next`.
    """
    id: str
    table_id: str = ""
    label: str = ""
    next: str = ""
    bindings: list[LifePathBinding] = strawberry.field(default_factory=list)
    #: Effects applied once per activation for this step, whatever row resolved —
    #: after the row's effects and the binding's delta, in the same scope. The
    #: effects counterpart of `next`, so an identical effect is authored once
    #: rather than on every binding.
    effects: list[Effect] = strawberry.field(default_factory=list)
    #: The names this step supplies to the tables it wraps ([[B290]]), resolved
    #: before the table's own so a shared table can read the context its caller
    #: gives it. Declarations only — a pathless one is half-typed and dropped.
    bound_variables: list[BoundVariable] = strawberry.field(default_factory=list)

@strawberry.input
class LifePathBindingInput:
    key: str
    next: str = ""
    exit_kind: str = ""
    exit_path: str = ""
    enroll: bool = False
    effects: list[EffectInput] = strawberry.field(default_factory=list)

@strawberry.input
class LifePathStepInput:
    #: Empty generates one (`s1`, `s2`, …) — the editor should not have to invent
    #: identities, but it must be able to preserve the ones it was given.
    id: str = ""
    #: Empty = no table: an **effects-only step** ([[B314]]).
    table_id: str = ""
    label: str = ""
    next: str = ""
    bindings: list[LifePathBindingInput] = strawberry.field(default_factory=list)
    effects: list[EffectInput] = strawberry.field(default_factory=list)
    bound_variables: list[BoundVariableInput] = strawberry.field(default_factory=list)

@strawberry.type
class LifePath:
    id: strawberry.ID
    name: str
    universe: str
    description: str
    entry_table_id: str
    #: The step a term begins at, and the steps it may walk.
    entry_step: str = ""
    steps: list[LifePathStep] = strawberry.field(default_factory=list)
    #: The names the **path** supplies to the tables its steps wrap ([[B290]]).
    #: Outermost layer: resolved before the step's and the table's, so a shared
    #: table reads whatever context this term gives it.
    bound_variables: list[BoundVariable] = strawberry.field(default_factory=list)
    discovery: Optional[DiscoveryBlock] = None
    conditions: list[Condition] = strawberry.field(default_factory=list)
    # Entity-scoped walkability ([[B194]]). `walkable` is null when the query was
    # not given an entity: "not evaluated" is not the same as "walkable", and
    # defaulting it true would let a client read a gate it never asked about.
    # `unwalkableReasons` carries why, because an unwalkable path is shown
    # **visible and disabled with a reason**, never hidden (the human, 2026-09-25).
    walkable: Optional[bool] = None
    unwalkable_reasons: list[str] = strawberry.field(default_factory=list)

    @strawberry.field
    def faction_ids(self, info: strawberry.Info) -> list[strawberry.ID]:
        """Faction entities that list this life path as suitable (offered)."""
        em = info.context["entity_manager"]
        factions = em.repo.list_entities_by_type(DomainEntityType.FACTION)
        return [
            strawberry.ID(f.id)
            for f in factions
            if str(self.id) in f.suitable_life_path_ids
        ]

@strawberry.type
class LifePathStepResult:
    """Result of resolving one roll-table step in a life path term."""
    done: bool
    applied: list[str]
    pending_choices: list[str]
    mustered: bool
    mishap_muster: bool
    pending_term: Optional[PendingTerm]
    scheduled: int = 0
    error: Optional[str] = None
    table_id: Optional[str] = None
    entry_label: Optional[str] = None
    #: The step's unanswered `{choose}` steps, with their candidates ([[B314]]).
    #: `pending_choices` names the element, which is not enough to answer with —
    #: these carry the effect, its field and the candidate pool, so the picker can
    #: render the question and echo the answer back through `resolve_step`'s
    #: `resolutions`.
    structured_choices: strawberry.scalars.JSON = strawberry.field(default_factory=list)
