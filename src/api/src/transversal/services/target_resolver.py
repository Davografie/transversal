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
    bound_name,
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
    #: The **declared** source, kept as strings so a question raised mid-path can
    #: carry them back to the client: answering rebuilds this context from what the
    #: client echoes, and a path that starts `select source` cannot resolve without
    #: them. `source`/`source_element` are the resolved half, and are not enough —
    #: the kind cannot be recovered from the element (`trait_setting` is one kind
    #: whose element is `traitsetting`), so losing these silently resolved every
    #: `select source` to nobody.
    source_kind: str = ""
    source_id: str = ""


@dataclass(frozen=True)
class UniverseRef:
    """A universe as the catalog models it: **its handle**, plus a display name.

    A universe element *is* its handle — that is what an entity stores in
    ``current_universe``, what a location's universe compares to, and what a scope
    value carries — while the *entity* for it is keyed ``universe-earth``.
    """
    id: str
    name: str = ""


@dataclass(frozen=True)
class ContestRef:
    """A contest as the catalog models it: a **handle**, plus what a card can say.

    A contest has no id of its own — it is session state keyed
    ``(location, entity)`` in the contest tracker, and it vanishes on restart. So
    the element *is* a handle, like a pool and a universe: ``contest:<location>:<entity>``
    naming **one side's** contest state. The two sides of one challenge are two
    states that know about each other, so a path that lands on either can reach
    the other through ``contest → entities``.

    ``opponent_id`` is the other side; ``member_ids`` is both sides, which is what
    "who are the participants" reads.
    """
    id: str
    location_id: str
    entity_id: str
    opposition_id: str = ""
    initiative: str = ""
    pending: str = ""
    stakes: str = "low"          # "high" | "low"
    kind: str = "test"           # "test" | "contest"
    took_initiative: bool = False


def contest_handle(location_id: str, entity_id: str, state: Any = None) -> ContestRef:
    """The handle for one side's contest at a location.

    ``state`` is the tracker's ``ContestState`` when the caller has it; without it
    the handle still names the contest (an id is all a literal or a filter needs).
    """
    opp = getattr(state, "opposition_entity_id", "") or ""
    initiative = getattr(state, "initiative", "") or ""
    # `ContestState.kind` is a `RollKind` enum; the catalog compares against the
    # value, so carry the value (`"test"`), not the enum.
    kind = getattr(state, "kind", None)
    return ContestRef(
        id=f"contest:{location_id}:{entity_id}",
        location_id=location_id,
        entity_id=entity_id,
        opposition_id=opp,
        initiative=initiative,
        pending=getattr(state, "pending_decision", None) or "",
        stakes="high" if getattr(state, "high_stakes", False) else "low",
        kind=getattr(kind, "value", None) or (str(kind) if kind else "test"),
        # Who holds initiative — the side that set the difficulty to beat.
        took_initiative=bool(initiative) and initiative == entity_id,
    )


def _contest_state(location_id: str, entity_id: str) -> Any | None:
    """This side's ``ContestState``, from the tracker (session state)."""
    if not location_id or not entity_id:
        return None
    from transversal.services.contest_tracker import get_contest_tracker

    states = get_contest_tracker().get_contests_at(location_id)
    return states.get(entity_id)


def contest_of_side(location_id: str, entity_id: str) -> ContestRef | None:
    """The contest this entity is a party to at a location, or ``None``.

    A contest exists as soon as one entity is challenged (``set_opposition``), so
    this is also the answer to "is this entity in a contest".
    """
    if _contest_state(location_id, entity_id) is not None:
        return contest_handle(location_id, entity_id, _contest_state(location_id, entity_id))
    # The challenged side also has a state (``set_opposition`` creates both), but
    # a stale/partial table may only carry the challenger's — find it by reverse
    # lookup so an opponent still reads as being in the contest.
    from transversal.services.contest_tracker import get_contest_tracker

    for state in get_contest_tracker().get_contests_at(location_id).values():
        if getattr(state, "opposition_entity_id", None) == entity_id:
            return contest_handle(location_id, getattr(state, "entity_id", entity_id), state)
    return None


def _parse_contest_ref(value: Any) -> tuple[str, str] | None:
    """``contest:<location>:<entity>`` → ``(location, entity)``.

    Split from the front because a location id has no colons today but an entity
    id may (``character-20809:three_realms:trait-…`` is a *trait setting*, not an
    entity, but the convention keeps the tail free for one).
    """
    parts = str(value or "").split(":", 2)
    if len(parts) != 3 or parts[0] != "contest":
        return None
    return (parts[1], parts[2]) if parts[1] and parts[2] else None


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
    #: Per-step outcome of the walk, in path order. Carried for *inspection*
    #: (``resolveTargetSpec``): a step that means something other than what the
    #: author assumed has to be visible as a count that collapses, which a single
    #: final list hides. Firing paths ignore it.
    trace: list["StepResolution"] = field(default_factory=list)


@dataclass
class StepResolution:
    """What one step of a path did — its values, type, and any error.

    ``values`` holds everything the step produced, uncapped; callers that
    serialize cap their own output and read ``len(values)`` for the exact count.
    ``pending`` marks a ``choose`` step that stopped the walk: its ``values`` are
    empty by definition (nothing is chosen yet) and the candidate pool lives in
    :class:`PendingTargetChoice`.
    """
    index: int
    step_kind: str = ""
    element: str = ""
    cardinality: str = ""
    values: list[Any] = field(default_factory=list)
    pending: bool = False
    error: str = ""


@dataclass
class PendingTargetChoice:
    """A ``choose`` step's candidate set, awaiting a user selection.

    ``element`` is the catalog element type of the candidates; ``candidates``
    holds the resolved candidate objects (before serialization); ``count`` is
    how many the user should select (1 = one, ``None`` = as many as they like).
    ``step_index`` is where the ``choose`` was hit in the path.
    """
    element: str
    candidates: list[Any] = field(default_factory=list)
    count: int | None = 1
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
        # Resolves **stored-or-default** for the same reason a literal does: an
        # authored source may name a set-level setting that nothing has written
        # yet, and the pair is real either way (`services/traitset_settings`).
        from transversal.services.traitset_settings import resolve_stored_or_default
        obj = resolve_stored_or_default(repo, source_id)
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


def _candidate_label(element: str, value: Any, field_name: str, repo=None) -> str:
    """Extract a display label field from a resolved candidate.

    Read through :func:`_read_field`, not the raw attribute, so a declared field
    whose value is *derived* (a pool die's ``rating``, a trait instance's ``tags``)
    labels its candidate instead of rendering blank.
    """
    if not field_name:
        return ""
    raw = _read_field(value, field_name, element, repo)
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
            name = _candidate_label(element, value, name_field, repo)
            subtitle = _candidate_label(element, value, subtitle_field, repo)
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


def _bound_value(value: Any, context: TargetContext | None, as_set: bool = False) -> Any:
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
    name = bound_name(value)
    if name is None:
        return value
    bindings = getattr(context, "bindings", None) or {}
    binding = bindings.get(name)
    if binding is None:
        return value  # unknown name: leave it, so the step plainly matches nothing
    if as_set and getattr(binding, "cardinality", "") == "many":
        # A `many` binding *is* the set the author declared, and `in` / `not in` is
        # where this language promises one-or-several. Without this the set was thrown
        # away and only its first id tested: `filter id in {locations}` degraded to
        # `id == <first>`, so fifteen of sixteen locations failed to match ([[B292]]).
        return list(getattr(binding, "values", None) or [])
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
    if op in ("contains", "not contains"):
        # A list value means *any of* — the same one-or-several reading an enum
        # filter gets from `in`, for a field that is itself a list (a trait's
        # tags: "tagged fire or water"). `not contains` is its negation, so several
        # values there mean *none of* (De Morgan), and an absent list contains
        # nothing — which is what makes "nobody knows this one" sayable.
        actual_list = actual or []
        if isinstance(expected, list):
            hit = any(item in actual_list for item in expected)
        else:
            hit = expected in actual_list
        return hit if op == "contains" else not hit
    return False


def _aggregate(values: list[Any], fn: str, field_name: str | None) -> list[Any]:
    if fn == "count":
        return [len(values)]
    if fn == "tier":
        # A **cast**: read the die itself, because every function below this line
        # would have already turned it into its side count (`"d8"` → 8) — the
        # value an ordering/mean wants, not the one an amount wants.
        from transversal.domain.rating import die_tier

        for v in values:
            tier = die_tier(_get_field(v, field_name))
            if tier is not None:
                return [tier]
        return []
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

    A **rating die** is addressed the same way but from the other locus:
    ``rating:<index>:<ts_id>``, since a trait's rating is a list and the effect
    has to name which die of it. The index comes *first* there because a
    traitsetting id contains colons (``kael:spiritual-power``), so the tail is the
    only unambiguous place for it. Both forms are what ``_parse_die_ref`` (pool)
    and ``handlers_change_die._parse_rating_ref`` (rating) read.
    """
    if isinstance(value, dict):
        if value.get("locus") == "rating":
            return f"rating:{value.get('index')}:{value.get('ts_id', '')}"
        if value.get("locus") == "capacity":
            # A capacity *slot*, addressed the same way as a rating die: the index
            # first, because a traitsetting id contains colons.
            return f"capacity:{value.get('index')}:{value.get('ts_id', '')}"
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
    if name == "self_traitsetsettings":
        if ctx.subject is None:
            return []
        return list(ctx.repo.get_traitsetsettings_for_entity(ctx.subject.id))
    if name == "locations":
        from transversal.domain import EntityType
        return list(ctx.repo.list_entities_by_type(EntityType.LOCATION))
    if name == "entities":
        return list(ctx.repo.list_all_entities())
    if name == "traits":
        # Every trait *definition* in the registry — the seed an action that
        # creates or teaches ranges over when it is naming what, not whose.
        getter = getattr(ctx.repo, "get_all_traits", None)
        return list(getter()) if callable(getter) else []
    if name == "universes":
        from transversal.domain import EntityType
        return [
            UniverseRef(id=_universe_handle(u), name=getattr(u, "name", "") or _universe_handle(u))
            for u in ctx.repo.list_entities_by_type(EntityType.UNIVERSE)
        ]
    if name == "sfxs":
        # The rule registry, as a collection a path can walk into and filter.
        # Read-only: nothing navigates out of an SFX yet, so this is a seed plus
        # the scalar fields above.
        getter = getattr(ctx.repo, "get_all_sfxs", None)
        return list(getter()) if callable(getter) else []
    if name == "traitsets":
        getter = getattr(ctx.repo, "get_all_traitsets", None)
        return list(getter()) if callable(getter) else []
    if name == "life_paths":
        getter = getattr(ctx.repo, "list_all_lifepaths", None)
        return list(getter()) if callable(getter) else []
    if name == "roll_tables":
        return list(ctx.repo.list_roll_tables())
    if name == "die_types":
        # A static vocabulary, not a repo read: the sizes a die can be. Each value
        # carries its size as both id and rating so a candidate has a stable id
        # ("d8") and a label that renders it.
        from transversal.domain import DieType
        return [{"id": d.value, "rating": d.value} for d in DieType]
    return None


# ── The walker ───────────────────────────────────────────────

def bind_named(name: str, values: list[Any], current_type: ValueType | None,
               context: TargetContext) -> None:
    """Bind ``name`` to a resolved value in the running scope.

    The one home for *what a bound name is*: a ``many`` result binds the full
    ordered list (``cardinality="many"``), a ``one`` result binds a scalar. Two
    callers read it — a step's inline ``output`` (the 💡) and an SFX-level
    declared bound variable — so they cannot disagree about cardinality, or about
    which id a value carries.

    No-op when there is no name, no value, or no type: an *unbound* name is the
    honest state for "resolved to nothing", and it is what makes a downstream path
    resolve to nobody rather than to a blank id.
    """
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


def _bind_step_outputs(step, values: list[Any], current_type: ValueType | None, context: TargetContext) -> None:
    """Bind a step's declared ``output`` into the running scope (the 💡)."""
    bind_named(getattr(step, "output", None), values, current_type, context)


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
    trace: list[StepResolution] = []
    stopped = False
    current_type: ValueType | None = None

    for i, step in enumerate(spec.steps):
        if isinstance(step, SelectStep):
            if step.collection == "variable":
                binding = context.bindings.get(step.variable) if context.bindings else None
                if binding is None or not binding.element:
                    errors.append(TraceError(i, f"variable {step.variable!r} not bound or untyped"))
                    values, current_type = [], None
                elif not binding.value and not binding.values:
                    # A declared type with nothing bound under it would resolve to
                    # an empty path, which reads exactly like "nothing matched" —
                    # the ambiguity this trace exists to remove. Say it instead.
                    errors.append(TraceError(i, f"variable {step.variable!r} has no value bound"))
                    values, current_type = [], None
                elif binding.cardinality == "many":
                    many_values: list[Any] = []
                    # Each **id** once. A binding is a set of ids, and several
                    # distinct values can share one: a rating's dice are bound by
                    # the instance that holds them (`_candidate_id`), so a
                    # four-die rating binds one id four times. Looking it up per
                    # entry returned that instance's four dice four times over —
                    # sixteen dice where four were named ([[B307]]).
                    for rid in dict.fromkeys(binding.values):
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
                          if _match(v, step, f.type, _bound_value(step.value, context, as_set=step.operator in ("in", "not in")),
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
                elif agg.needs_single and current_type.cardinality != "one":
                    errors.append(TraceError(
                        i, f"{step.fn} reads a single value — narrow the collection first"))
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
            elif step.count is not None and step.count < 1:
                errors.append(TraceError(i, "choose count must be >= 1 or null"))
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
                stopped = True

        elif isinstance(step, EvaluateStep):
            values = [_evaluate_step(values, current_type, step, context)]
            current_type = ValueType("boolean", "one")

        _bind_step_outputs(step, values, current_type, context)
        element = current_type.element if current_type is not None else ""
        cardinality = current_type.cardinality if current_type is not None else ""
        if stopped and pending_choices:
            # A pending ``choose`` resolved nothing yet, but what it is *about* is
            # known — reporting "" here would read as a broken path rather than an
            # unanswered one.
            element = pending_choices[-1].element
            cardinality = "one" if pending_choices[-1].count == 1 else "many"
        trace.append(StepResolution(
            index=i,
            step_kind=getattr(step, "kind", ""),
            element=element,
            cardinality=cardinality,
            values=list(values),
            pending=stopped,
            error="; ".join(e.message for e in errors if e.step_index == i),
        ))
        if stopped:
            break

    return Resolution(values, errors, pending_choices, trace)


def _lookup_literal(element: str, value: str, ctx: TargetContext) -> list[Any]:
    """Resolve a ``literal`` step: fetch the object of ``element`` type by id."""
    repo = ctx.repo
    if repo is None or not value:
        return []
    if element == "universe":
        return _maybe(_universe_record(value, repo))
    if element in ("entity", "location"):
        return _maybe(repo.get_entity(value))
    if element == "trait":
        return _maybe(repo.get_trait(value))
    if element == "traitsetting":
        return _maybe(repo.get_traitsetting(value))
    if element == "traitsetsetting":
        # Addressed by the **derived** pair id (`{entity}:{traitset}`), so a
        # literal naming a set-level setting resolves before anything has written
        # one — a setting is an override, and its absence means "nothing
        # overridden", not "no such target" (`services/traitset_settings`).
        from transversal.services.traitset_settings import resolve_stored_or_default
        return _maybe(resolve_stored_or_default(repo, value))
    if element == "traitset":
        return _maybe(repo.get_traitset_by_id(value))
    if element == "projection":
        return _maybe(repo.get_projection(value))
    if element == "relationship":
        # An edge, by its own key: what a created tie is exposed as, and how a path
        # filters a specific edge without picking it by its contact.
        return _maybe(repo.get_relationship_by_key(value))
    if element == "life_path":
        return _maybe(repo.get_lifepath(value))
    if element == "roll_table":
        return _maybe(repo.get_roll_table(value))
    if element == "scheduled_event":
        return _maybe(repo.get_scheduled_event(value))
    if element == "pool":
        return _maybe(_pool_from_id(value, repo))
    if element == "die":
        return _maybe(_die_from_ref(value, repo))
    # A die of a rating or a capacity is addressed by the **instance that holds
    # it** — that is what `_candidate_id` binds for these elements, and what the
    # upward edge reads — so looking one up yields that instance's dice, exactly as
    # walking the `rating_dice` / `capacity_dice` edge does. Without this a
    # `select variable` over a rating returned *nothing*: the name was bound, typed
    # and usable in a filter, but unreadable as a collection ([[B307]]).
    if element == "rating_die":
        ts = repo.get_traitsetting(value)
        return _traitsetting_rating_dice(ts, ctx) if ts is not None else []
    if element == "capacity_die":
        ts = repo.get_traitsetting(value)
        return _traitsetting_capacity_dices(ts, ctx) if ts is not None else []
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
        {**die, "pool_location": location_id, "pool_owner": owner_id, "pool_index": i,
         "locus": "pool"}
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


def _traitsetting_parent(ts: Any, ctx: TargetContext) -> list[Any]:
    """The container a nested instance hangs under, or nothing.

    A sub-trait is anchored by ``parent_traitsetting_id`` (see
    ``repository.resolve_subtrait_id``), so this is a straight read. `subtraits`
    is the downward half; a rule that completes a child and then acts on the
    container needs this one.
    """
    parent_id = _get_field(ts, "parent_traitsetting_id")
    if not parent_id or ctx.repo is None:
        return []
    parent = ctx.repo.get_traitsetting(parent_id)
    return _maybe(parent)


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


def _traitsetting_traitset_id(ts: Any, repo) -> str:
    """The set this instance is in, read through its **registry trait** ([[B209]]).

    The setting used to carry a copy, which could only drift the moment a trait
    moved between sets; the copy went and the *reader* was never written, so the
    catalog advertised a filter that matched nothing whatever the value. One live
    rule had been authored against it (`sfx-heal`: "a complication on the chosen
    occupant") and had been silently doing nothing.
    """
    if repo is None:
        return ""
    trait_id = _get_field(ts, "trait_id")
    trait = repo.get_trait(trait_id) if trait_id else None
    return getattr(trait, "traitset_id", "") or ""


def _all_universe_handles(repo) -> list[str]:
    """Every universe handle in the registry — what "no universes declared" means."""
    if repo is None:
        return []
    from transversal.domain import EntityType

    getter = getattr(repo, "list_entities_by_type", None)
    if not callable(getter):
        return []
    return [_universe_handle(u) for u in getter(EntityType.UNIVERSE)]


def _traitsetting_universes(ts: Any, repo) -> list[str]:
    """The universes a trait *instance* is available in: its set ∩ its definition.

    A registry trait **narrows** the set it belongs to — assets is available in
    Earth and the Three Realms, *Radio* is not — and an instance records neither
    side, so both are read through ``trait_id``, the same route
    ``traitsetting → traitset`` takes ([[B209]]).

    A side that declares **no** universes is *unrestricted*, and that is
    materialised as every universe rather than returned as the empty list: an
    empty list contains nothing, so ``filter universes contains {world}`` would
    reject a universal set — the opposite of what "no restriction" says.
    """
    if repo is None:
        return []
    trait_id = _get_field(ts, "trait_id")
    trait = repo.get_trait(trait_id) if trait_id else None
    if trait is None:
        return []
    traitset = repo.get_traitset_by_id(getattr(trait, "traitset_id", "") or "")
    of_set = [u for u in (getattr(traitset, "universes", None) or []) if u]
    of_trait = [u for u in (getattr(trait, "universes", None) or []) if u]
    if of_set and of_trait:
        return [u for u in of_set if u in of_trait]
    return of_trait or of_set or _all_universe_handles(repo)


def _die_rating(die: Any, repo) -> Any:
    """A die's own size.

    The catalog calls this field ``rating``, but a *pool* die carries its size
    under ``die`` (that is the key the scene store and the pool handlers use),
    so reading the attribute alone silently returned ``None`` — which made
    ``filter rating == d8`` and ``aggregate max rating`` over dice match nothing.
    One reader, so a rating means the same thing on either locus.
    """
    if isinstance(die, dict):
        return die.get("rating") or die.get("die")
    return getattr(die, "rating", None) or getattr(die, "die", None)


def _traitsetting_rating_dice(ts: Any, ctx: TargetContext) -> list[dict]:
    """The dice that make up a trait instance's *rating*.

    A rating is a list (``TraitSetting.dice``): a static trait holds one die, a
    resource trait its unspent remainder, a challenge its ledger. Each die is a
    candidate for a ``Change a Die`` effect, addressed by its position — which is
    what makes "step up *that* die of the rating" expressible.

    The dict deliberately mirrors a pool die's shape (``die``/``ts_id``/
    ``source_kind``) so one set of handlers reads both loci; ``locus`` is what
    tells them apart, and :func:`resolved_id` turns it back into a reference.
    """
    ts_id = _get_field(ts, "id") or ""
    out: list[dict] = []
    for i, d in enumerate(getattr(ts, "dice", None) or []):
        size = getattr(d, "value", d)
        out.append({
            "locus": "rating",
            "die": size,
            "rating": size,
            "ts_id": ts_id,
            "index": i,
            "source_kind": "trait",
            "source_id": ts_id,
        })
    return out


def _traitsetting_capacity_dices(ts: Any, ctx: TargetContext) -> list[dict]:
    """The dice that make up a trait instance's *capacity*.

    A capacity is a list (``TraitSetting.capacity``) on a positive challenge: the
    target the pool fills toward, as opposed to ``rating_dice``, which are the
    dice it has already banked. Everything that is not a positive challenge has
    none, so this is empty rather than a guess.

    Each slot is addressed by its **1-based** position, which is the whole point:
    an agenda's sub-trait carries ``order`` (1-based) and fills the capacity die
    at the matching position, so the author writes ``filter index == {order}``
    and no arithmetic is needed anywhere.
    """
    ts_id = _get_field(ts, "id") or ""
    out: list[dict] = []
    for i, d in enumerate(getattr(ts, "capacity", None) or [], start=1):
        size = getattr(d, "value", d)
        out.append({
            "locus": "capacity",
            "die": size,
            "rating": size,
            "ts_id": ts_id,
            "index": i,
        })
    return out


def _capacity_die_traitsetting(slot: Any, ctx: TargetContext) -> list[Any]:
    """The challenge a capacity slot belongs to (the upward half)."""
    if not isinstance(slot, dict) or ctx.repo is None:
        return []
    ts_id = slot.get("ts_id") or ""
    return _maybe(ctx.repo.get_traitsetting(ts_id)) if ts_id else []


def _location_universe(value: Any, repo) -> Any:
    """A location's universe.

    The catalog calls the field ``universe`` while an ``Entity`` stores it as
    ``current_universe``, so the raw attribute read returned ``None`` — which
    blanked the location picker's subtitle and made ``filter universe == earth``
    match nothing. One reader, so the field, the picker and a filter agree.
    """
    if isinstance(value, dict):
        return value.get("universe") or value.get("current_universe")
    return getattr(value, "universe", None) or getattr(value, "current_universe", None)


def _universe_locations(u: Any, ctx: TargetContext) -> list[Any]:
    """The locations in a universe.

    A universe element *is* its handle (``earth``), and a location's
    ``current_universe`` holds that handle — so this is the reverse of the
    ``location → universe`` hop, read through the same repo call the location
    picker uses.
    """
    from transversal.domain import EntityType

    if ctx.repo is None:
        return []
    handle = getattr(u, "id", None) or (u.get("id") if isinstance(u, dict) else None)
    return list(ctx.repo.list_entities_by_type(EntityType.LOCATION, universe=handle or None))


def _location_subtree(l: Any, ctx: TargetContext) -> list[Any]:
    """A location plus everything under it, as entities.

    ``list_location_descendants`` is the app's own hierarchy walk (the one the
    canvas draws), so a path and the map cannot disagree about what is inside a
    place. The location itself is included: "everyone in Iron Roots" means the
    place *and* its zones, not only its zones.
    """
    if ctx.repo is None:
        return []
    lid = getattr(l, "id", None) or (l.get("id") if isinstance(l, dict) else None)
    if not lid:
        return []
    return list(ctx.repo.get_entities_by_ids(
        [lid] + list(ctx.repo.list_location_descendants(lid))))


def _universe_handle(u: Any) -> str:
    """The handle a universe entity *is* (``earth``, not its key ``universe-earth``)."""
    if isinstance(u, dict):
        return u.get("current_universe") or u.get("id") or ""
    return getattr(u, "current_universe", "") or getattr(u, "id", "") or ""


def _universe_record(handle: str, repo) -> "UniverseRef | None":
    """A universe as the catalog models it: **its handle**, plus a display name.

    A universe element *is* its handle — that is what an entity stores in
    ``current_universe``, what a location filters on, and what a scope value
    carries — while the *entity* for it is keyed ``universe-earth``. Returning the
    entity made every binding and every ``universe → locations`` hop carry the key
    instead of the handle, which quietly matched nothing.
    """
    universe = _universe_by_handle(handle, repo)
    if universe is None:
        return None
    return UniverseRef(id=handle, name=getattr(universe, "name", "") or handle)


def _universe_by_handle(handle: str, repo) -> Any:
    """Resolve a universe *handle* (``earth``) to the universe entity.

    An entity stores the handle in ``current_universe``, and in live content the
    handle is **not** the universe entity's key — those are ``universe-earth``,
    ``universe-valhalla``, … So a plain ``get_entity(handle)`` finds nothing, which
    silently emptied every ``navigate universe`` hop (the filter or reader that
    compared the *string* kept working, which is why the gap stayed hidden).

    Tries the key first — a deployment that keys universes by handle still
    resolves — then matches the handle the universe carries.
    """
    if not handle or repo is None:
        return None
    direct = repo.get_entity(handle)
    if direct is not None:
        return direct
    from transversal.domain import EntityType

    for universe in repo.list_entities_by_type(EntityType.UNIVERSE):
        if handle in (getattr(universe, "id", ""), _universe_handle(universe)):
            return universe
    return None


def _entity_to_universe(e: Any, ctx: TargetContext) -> list[Any]:
    """The universe an entity is in, resolved from the *handle* it stores."""
    return _maybe(_universe_record(getattr(e, "current_universe", ""), ctx.repo))


def _location_to_universe(l: Any, ctx: TargetContext) -> list[Any]:
    """The universe a place is in (naming apart from the `location.universe` reader)."""
    return _maybe(_universe_record(getattr(l, "current_universe", ""), ctx.repo))


def _location_projections(l: Any, ctx: TargetContext) -> list[Any]:
    """Every projection whose body is at this place (the place itself, not its zones).

    A subtree reach is written as `navigate subtree → navigate projections`, which
    keeps this hop honest: "here" means here.
    """
    if ctx.repo is None:
        return []
    lid = getattr(l, "id", None) or (l.get("id") if isinstance(l, dict) else None)
    if not lid:
        return []
    return [p for p in ctx.repo.list_all_projections()
            if getattr(p, "current_location", None) == lid]


def _entity_factions(e: Any, ctx: TargetContext) -> list[Any]:
    """The orgs this entity is on the roster of (the inverse of ``members``)."""
    if ctx.repo is None:
        return []
    return [
        f for f in (ctx.repo.get_entity(fid) for fid in ctx.repo.get_entity_factions(e.id))
        if f is not None
    ]


def _entity_life_paths(e: Any, ctx: TargetContext) -> list[Any]:
    """The life paths this entity may start someone on (a faction's own paths)."""
    if ctx.repo is None:
        return []
    ids = getattr(e, "suitable_life_path_ids", None) or []
    return [lp for lp in (ctx.repo.get_lifepath(i) for i in ids) if lp is not None]


def _life_path_roll_tables(lp: Any, ctx: TargetContext) -> list[Any]:
    """The roll tables that follow this life path — the ones its steps wrap."""
    if ctx.repo is None:
        return []
    lid = getattr(lp, "id", None) or (lp.get("id") if isinstance(lp, dict) else None)
    steps = getattr(lp, "steps", None) or []
    tables = {t.id: t for t in ctx.repo.list_roll_tables()}
    ids = [s.table_id for s in steps]
    if not ids:
        # Pre-wrapper content: the path reached its tables by entry + ownership.
        entry = getattr(lp, "entry_table_id", "") or ""
        ids = ([entry] if entry else []) + [t.id for t in tables.values() if t.life_path == lid]
    out: list[Any] = []
    seen: set[str] = set()
    for tid in ids:
        if tid in tables and tid not in seen:
            seen.add(tid)
            out.append(tables[tid])
    return out


def _roll_table_life_path(table: Any, ctx: TargetContext) -> list[Any]:
    """The life path this roll table is being played in ([[B164]], [[B266]]).

    A table is the *source* of its entries' effects, so this is how an effect reads
    the path it is being played in — and from the path, via the entity's
    enrollment, the faction the term is being served in.

    Under the wrapper a table no longer *belongs* to a path: several may wrap it,
    or none. The answer is therefore the path the **term is actually in**, read
    from the acting entity's checkpoint — not a fact about the table. With no live
    term a path is reported only when exactly one wraps the table; when several
    do, the question has no single answer, and picking one would silently pick a
    faction.
    """
    if ctx.repo is None:
        return []
    tid = getattr(table, "id", None)

    pt = getattr(ctx.subject, "pending_term", None)
    path_id = getattr(pt, "path_id", "") if pt else ""
    if path_id:
        lp = ctx.repo.get_lifepath(path_id)
        if lp is not None and (
            any(s.table_id == tid for s in (getattr(lp, "steps", None) or []))
            or getattr(lp, "entry_table_id", "") == tid
        ):
            return [lp]

    wrapping = [
        lp for lp in ctx.repo.list_all_lifepaths()
        if any(s.table_id == tid for s in (getattr(lp, "steps", None) or []))
        or getattr(lp, "entry_table_id", "") == tid
    ]
    return wrapping if len(wrapping) == 1 else []


def _entity_scheduled_events(e: Any, ctx: TargetContext) -> list[Any]:
    """Every timer counting down on this entity.

    Two homes, one answer: a duration can be scheduled on the entity itself or on
    one of its trait instances (a complication that clears after a scene), so both
    are read and the second is filtered to the settings this entity owns.
    """
    if ctx.repo is None:
        return []
    events = list(ctx.repo.list_scheduled_events(target_type="entity", target_id=e.id))
    for event in ctx.repo.list_scheduled_events(target_type="trait_setting"):
        ts = ctx.repo.get_traitsetting(event.target_id)
        if ts is not None and ts.entity_id == e.id:
            events.append(event)
    return events


def _scheduled_event_label(e: Any, repo) -> str:
    """A timer's primary label: its effect's action and target."""
    eff = e.effect
    target = (eff.target or "").strip()
    label = eff.action
    if target and target != "self":
        label = f"{eff.action} {target}"
    if e.source_sfx_id:
        label = f"{label} ({e.source_sfx_id})"
    return label or e.id


def _scheduled_event_subtitle(e: Any, repo) -> str:
    """A timer's countdown string (e.g. ``2 scenes``)."""
    parts = []
    for t in (e.timers or []):
        unit = t.event if t.remaining == 1 else f"{t.event}s"
        parts.append(f"{t.remaining} {unit}")
    return " · ".join(parts)


def _trait_traitset_name(t: Any, repo) -> str:
    """The name of the trait set a registry trait belongs to (its picker subtitle)."""
    traitset_id = getattr(t, "traitset_id", "") or (t.get("traitset_id") if isinstance(t, dict) else "")
    if repo is None or not traitset_id:
        return traitset_id
    getter = getattr(repo, "get_traitset_by_id", None)
    traitset = getter(traitset_id) if callable(getter) else None
    name = getattr(traitset, "name", "") if traitset is not None else ""
    return name or traitset_id


def _projection_name(p: Any, repo) -> str:
    """A projection's own name, falling back to the entity whose body it is."""
    name = getattr(p, "name", "") or (p.get("name") if isinstance(p, dict) else "")
    if name or repo is None:
        return name or ""
    entity_id = getattr(p, "entity_id", None) or (p.get("entity_id") if isinstance(p, dict) else None)
    entity = repo.get_entity(entity_id) if entity_id else None
    return getattr(entity, "name", "") if entity is not None else ""


def register_default_fields() -> None:
    register_derived_field("traitsetting", "tags", _traitsetting_tags)
    # The two facts an instance does not record: the set it is in ([[B209]]) and
    # the universes it is available in. Both live on the registry trait, so both
    # are read through it — see `_traitsetting_universes` for why "no universes
    # declared" has to come back as *every* universe rather than an empty list.
    register_derived_field("traitsetting", "traitset_id", _traitsetting_traitset_id)
    register_derived_field("traitsetting", "universes", _traitsetting_universes)
    register_derived_field("die", "rating", _die_rating)
    register_derived_field("location", "universe", _location_universe)
    # A contest's *phase* belongs to the dice pool, not to the contest record: the
    # tracker knows who is fighting and what is at stake, the scene store knows
    # whether they are still assembling dice or have rolled. One reader joins them.
    register_derived_field("contest", "phase", _contest_phase)
    # A registry trait's picker subtitle is its trait set's *name* — the raw
    # `traitset_id` is a second id where a word belongs.
    register_derived_field("trait", "traitset_name", _trait_traitset_name)
    # Most projections have no name of their own, so the label falls back to the
    # entity they are a body of.
    register_derived_field("projection", "name", _projection_name)
    # A pending timer's label and countdown are assembled from the effect it
    # carries (action + target, and its remaining timers), not stored on it.
    register_derived_field("scheduled_event", "label", _scheduled_event_label)
    register_derived_field("scheduled_event", "subtitle", _scheduled_event_subtitle)


def _contest_phase(contest: Any, repo) -> str:
    """Whether this contest is still assembling dice, or past that.

    The tracker records *who* is contesting; the scene store records where the
    dice are. A contest with no pool yet reads ``"adding"`` — the phase a fresh
    contest is always in — so a gate on "dice already rolled" cannot pass early.
    """
    location_id = _get_field(contest, "location_id")
    entity_id = _get_field(contest, "entity_id")
    if not location_id or not entity_id:
        return "adding"
    from transversal.services.scene_state import get_scene_store

    return get_scene_store().get_phase(location_id, entity_id)


def _pool_contest(pool: Any, ctx: TargetContext) -> list[Any]:
    """The contest this pool belongs to, if the pool's owner is a party.

    The short route, and the one the moment speaks: a pool exists during
    assembly and roll, which is exactly when "am I in a contest" is being asked.
    A pool with no contest (a test rolled alone) resolves to nothing — which is
    how a rule tells a test from a contest without a separate flag.
    """
    location_id = _get_field(pool, "location_id")
    owner_id = _get_field(pool, "owner_id")
    ref = contest_of_side(location_id or "", owner_id or "")
    return [ref] if ref is not None else []


def _entity_contest(entity: Any, ctx: TargetContext) -> list[Any]:
    """The contest this entity is currently in, if any.

    The tracker is keyed ``(location, entity)``, so "in a contest" is a lookup
    rather than a scan over the world: no location, no contest. `select self →
    navigate contest` is therefore "the contest I am in".
    """
    entity_id = getattr(entity, "id", None) or (entity.get("id") if isinstance(entity, dict) else "")
    location_id = getattr(entity, "current_location", None) or ""
    if not location_id and isinstance(entity, dict):
        location_id = entity.get("current_location") or ""
    ref = contest_of_side(location_id or "", entity_id or "")
    return [ref] if ref is not None else []


def _contest_parties(contest: Any, ctx: TargetContext) -> list[Any]:
    """Both sides of the contest, as entities — "who are the participants".

    The challenger's state carries the opponent, and ``set_opposition`` creates
    the other side's state too, so the pair is derivable from either handle.
    """
    location_id = _get_field(contest, "location_id")
    entity_id = _get_field(contest, "entity_id")
    if not location_id or not entity_id:
        return []
    from transversal.services.contest_tracker import get_contest_tracker

    challenger, defendant = get_contest_tracker().get_contestants(location_id, entity_id)
    ids = [getattr(s, "entity_id", None) for s in (challenger, defendant) if s is not None]
    out = []
    for eid in dict.fromkeys(i for i in ids if i):
        entity = ctx.repo.get_entity(eid) if ctx.repo else None
        if entity is not None:
            out.append(entity)
    return out


def _contest_pools(contest: Any, ctx: TargetContext) -> list[Any]:
    """Each side's pool, as pool handles — the dice they are fighting with."""
    location_id = _get_field(contest, "location_id")
    entity_id = _get_field(contest, "entity_id")
    if not location_id or not entity_id:
        return []
    from transversal.services.contest_tracker import get_contest_tracker

    challenger, defendant = get_contest_tracker().get_contestants(location_id, entity_id)
    out = []
    for state in (challenger, defendant):
        side = getattr(state, "entity_id", None) if state is not None else None
        if side:
            out.append(_pool_handle(side, location_id, "pool"))
    return out


def _location_contests(location: Any, ctx: TargetContext) -> list[Any]:
    """Every contest running at this location — "is this place running one".

    One read of the location's contest table; empty when the place is quiet.
    """
    location_id = getattr(location, "id", None) or (location.get("id") if isinstance(location, dict) else "")
    if not location_id:
        return []
    from transversal.services.contest_tracker import get_contest_tracker

    states = get_contest_tracker().get_contests_at(location_id)
    # One handle per *contest*, not per state. The tracker keeps a state for each
    # side, but only the challenger's carries ``opposition_entity_id`` — the
    # defendant's is a bare record — so the challenger is what names the contest,
    # and `get_contestants` is what pairs the two reliably.
    seen: set[str] = set()
    out = []
    for entity_id in list(states):
        challenger, _defendant = get_contest_tracker().get_contestants(location_id, entity_id)
        side = getattr(challenger, "entity_id", None) if challenger is not None else None
        if not side or side in seen:
            continue
        seen.add(side)
        out.append(contest_handle(location_id, side, states.get(side) or challenger))
    return out


def _traitsetting_traitsetsetting(ts, ctx) -> list[Any]:
    """The set-level setting governing this instance's set, for its own entity.

    The set belongs to the *definition*, so it is read through the trait — the
    same route the ``traitsetting → traitset`` hop uses. **Stored-or-default**:
    the pair is real whether or not anything has been written against it, and this
    is the hop that lets a rule land on a set nobody has overridden yet.
    """
    from transversal.services.traitset_settings import resolve

    trait = ctx.repo.get_trait(getattr(ts, "trait_id", ""))
    traitset_id = getattr(trait, "traitset_id", "") if trait is not None else ""
    if not traitset_id:
        return []
    return [resolve(ctx.repo, ts.entity_id, traitset_id)]


def _traitset_traitsetsettings(ts, ctx) -> list[Any]:
    """A set's **stored** overrides, across the entities that have one."""
    return list(ctx.repo.get_traitsetsettings_for_traitset(ts.id))


def register_default_edges() -> None:
    # A contest is reached from the two things that know about one: a *pool* (the
    # dice being assembled — the shortest route, and the one that speaks the
    # moment) and an *entity* (who is in one). `pool → contest` deliberately comes
    # first so "the contest for this pool of dice" is one hop rather than
    # pool → entity → contest.
    register_edge("pool", "contest", _pool_contest)
    register_edge("entity", "contest", _entity_contest)
    register_edge("contest", "entities", _contest_parties)
    # The two sides fight *with* their pools, so a contest reaches each side's pool
    # (and through it, the dice).
    register_edge("contest", "pools", _contest_pools)
    register_edge("location", "contests", _location_contests)
    register_edge("die", "traitsetting", lambda d, ctx: _maybe(ctx.repo.get_traitsetting(d.get("ts_id"))))
    register_edge("die", "owner", _die_owner)

    register_edge("traitsetting", "trait", lambda ts, ctx: _maybe(ctx.repo.get_trait(ts.trait_id)))
    # The set belongs to the *trait*, so it is reached through it.
    register_edge("traitsetting", "traitset",
                  lambda ts, ctx: _maybe(ctx.repo.get_traitset_by_id(
                      getattr(ctx.repo.get_trait(ts.trait_id), "traitset_id", ""))))
    register_edge("traitsetting", "entity", lambda ts, ctx: _maybe(ctx.repo.get_entity(ts.entity_id)))
    register_edge("traitsetting", "projection",
                  lambda ts, ctx: _maybe(ctx.repo.get_projection(ts.projection_id)) if ts.projection_id else [])
    # The set-level setting: one hop from an instance to the override governing
    # its set, plus the two ends of the pair it is *about*. The singular hop
    # resolves stored-or-default (a set-level rule is routinely the first thing to
    # touch a pair); the plural hops are stored rows only, because the defaults
    # are addressable but enumerating them would be thousands of rows whose
    # content is "nothing". See `services/traitset_settings`.
    register_edge("traitsetting", "traitsetsetting", _traitsetting_traitsetsetting)
    register_edge("entity", "traitsetsettings",
                  lambda e, ctx: list(ctx.repo.get_traitsetsettings_for_entity(e.id)))
    register_edge("traitset", "traitsetsettings", _traitset_traitsetsettings)
    # The reverse of the entity hop above: the pair records the entity it belongs
    # to, so one attribute read gives the setting back its owner — the step that
    # lets a rule carried by a *set* name the character it is acting for.
    register_edge("traitsetsetting", "entity",
                  lambda tss, ctx: _maybe(ctx.repo.get_entity(tss.entity_id)))
    # ...and back down: a set-level setting reaches the instances it governs — the
    # entity's traits in that set. This is what lets a rule attached **once** to a
    # set behave like one attached to each of its traits (`sfx-gift`), and it reads
    # through the registry because an instance no longer records its set ([[B209]]).
    register_edge("traitsetsetting", "traitsettings",
                  lambda tss, ctx: list(ctx.repo.get_traitsettings_for_entity_and_traitset(
                      tss.entity_id, tss.traitset_id)))
    # The instances nested under this one (elemental roots under Spiritual Power).
    # One repo read: sub-traits share the traitsettings collection, anchored to
    # the parent and marked `from_type == 'traitsetting'`.
    register_edge("traitsetting", "subtraits",
                  lambda ts, ctx: list(ctx.repo.get_sub_traitsettings(ts.id)))
    # The upward half: the container this instance is nested under. One read, and
    # nothing when the instance is top-level (an empty hop is honest here — a
    # top-level trait has no container).
    register_edge("traitsetting", "parent", _traitsetting_parent)
    # The dice of this instance's rating — the persistent locus of a change-die
    # effect, as opposed to the assembled pool's dice below.
    register_edge("traitsetting", "rating_dice", _traitsetting_rating_dice)
    register_edge("rating_die", "traitsetting",
                  lambda d, ctx: _maybe(ctx.repo.get_traitsetting(d.get("ts_id"))))

    # The un-filled ceiling, as addressable slots. A challenge's capacity is the
    # target it fills toward, and an agenda's sub-traits each own one slot — so
    # reaching *the slot my position names* is an index filter, not a dance.
    register_edge("traitsetting", "capacity_dice", _traitsetting_capacity_dices)
    register_edge("capacity_die", "traitsetting", _capacity_die_traitsetting)

    # A *location pointer* is optional, and its absence is a normal state — an
    # unplaced body, an entity in the unplaced dock — so the hop yields nothing.
    # Handing the driver ``None`` instead raises out of the Arango client and takes
    # the whole effect down with it: every one of Phaos's eight projections is
    # unplaced, and `travel`'s `navigate location` is what reached them ([[B261]]).
    register_edge("entity", "location",
                  lambda e, ctx: _maybe(ctx.repo.get_entity(e.current_location)) if e.current_location else [])
    register_edge("entity", "universe", _entity_to_universe)
    register_edge("entity", "projection",
                  lambda e, ctx: _maybe(ctx.repo.get_projection(e.current_projection)) if e.current_projection else [])
    register_edge("entity", "projections", lambda e, ctx: list(ctx.repo.get_projections_for_entity(e.id)))
    register_edge("entity", "traitsettings", lambda e, ctx: list(ctx.repo.get_traitsettings_for_entity(e.id)))
    # entity → its relationship edges → the trait instances anchored to one. A
    # trait instance can live on the edge rather than on the entity (your standing
    # with a faction), and this is the route that reaches it.
    register_edge("entity", "relationships",
                  lambda e, ctx: list(ctx.repo.list_relationships_for_entity(e.id)))
    register_edge("relationship", "traitsettings",
                  lambda r, ctx: list(ctx.repo.get_relationship_traitsettings(r.get("id"))))
    register_edge("relationship", "entity",
                  lambda r, ctx: _maybe(ctx.repo.get_entity(r.get("owner_id"))))
    # The far end of the same edge: the other party. `list_relationships_for_entity`
    # already resolves the contact alongside the owner (one read, so a path need
    # not look it up again) — this is the hop that lets "the main I support" and
    # "my rival" be written as a path instead of a dead-end scalar read.
    register_edge("relationship", "contact",
                  lambda r, ctx: _maybe(ctx.repo.get_entity(r.get("contact_id"))))
    register_edge("traitsetting", "relationship",
                  lambda ts, ctx: _maybe(ctx.repo.get_relationship_by_key(ts.entity_id))
                  if getattr(ts, "from_type", "") == "relationship" else [])

    register_edge("projection", "entity", lambda p, ctx: _maybe(ctx.repo.get_entity(p.entity_id)))
    # Same optional location pointer as `entity → location`: a projection that has
    # never been placed has no location to navigate to.
    register_edge("projection", "location",
                  lambda p, ctx: _maybe(ctx.repo.get_entity(p.current_location)) if p.current_location else [])
    # The body's **current** universe — `universe`, not `origin_universe`: travel
    # mutates the first and never the second, and a path asking "the world this
    # body is in" means where it is now.
    register_edge("projection", "universe",
                  lambda p, ctx: _maybe(_universe_record(getattr(p, "universe", ""), ctx.repo)))

    register_edge("location", "universe", _location_to_universe)
    register_edge("location", "occupants", lambda l, ctx: list(ctx.repo.list_entities_by_location(l.id)))
    register_edge("location", "difficulty_pool",
                  lambda l, ctx: [_pool_handle(l.id, l.id, "difficulty")])
    # A world's places: the same repo call the location picker uses, scoped by the
    # universe's own id (a universe *is* its handle), so a path and a picker can
    # never disagree about what is in a world.
    register_edge("universe", "locations", _universe_locations)

    register_edge("entity", "pool",
                  lambda e, ctx: [_pool_handle(e.id, e.current_location or "", "pool")])
    register_edge("pool", "dice", _pool_dice)

    register_edge("traitset", "traits", lambda ts, ctx: list(ctx.repo.get_traits_by_traitset(ts.id)))
    register_edge("trait", "traitset", lambda t, ctx: _maybe(ctx.repo.get_traitset_by_id(t.traitset_id)))
    register_edge("trait", "universes",
                  lambda t, ctx: [ctx.repo.get_entity(u) for u in (t.universes or []) if ctx.repo.get_entity(u)])
    # Definition → instances, one read. Every definition-based reach selector
    # needs this hop: a `trait`/`traitset` definition has no surface to own a
    # rule, so the path steps down to the settings that do. The read is the
    # existing `get_traitsettings_by_trait` (all instances, sub-traits included)
    # — the same one that provisions a trait's default SFX onto its instances.
    register_edge("trait", "traitsettings",
                  lambda t, ctx: list(ctx.repo.get_traitsettings_by_trait(t.id)))

    # The hierarchy and the roster hops: a place's whole subtree, a faction's
    # members and the inverse, and the registry things a faction owns — the reach
    # that lets a flat "which targets" scope be written as a path.
    register_edge("location", "subtree", _location_subtree)
    register_edge("location", "projections", _location_projections)
    register_edge("entity", "members",
                  lambda e, ctx: list(ctx.repo.list_faction_members(e.id)))
    register_edge("entity", "factions", _entity_factions)
    register_edge("entity", "life_paths", _entity_life_paths)
    register_edge("life_path", "roll_tables", _life_path_roll_tables)
    register_edge("roll_table", "life_path", _roll_table_life_path)
    register_edge("entity", "scheduled_events", _entity_scheduled_events)


register_default_edges()
register_default_fields()
