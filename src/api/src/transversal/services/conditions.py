"""Condition evaluation — automatically gate tables/entries/effects on entity state."""

from __future__ import annotations

from typing import TYPE_CHECKING

from transversal.domain import Condition, ConditionType, DieType, Entity

if TYPE_CHECKING:
    from transversal.db.repository import EntityRepository


def _resolve_condition_value(value, context: dict) -> str:
    """Resolve a ``{variable}`` token from context; return the literal otherwise."""
    if isinstance(value, str) and value.startswith("{") and value.endswith("}"):
        key = value[1:-1]
        resolved = (context or {}).get(key)
        return str(resolved) if resolved is not None else ""
    return value


def _resolve_subject(condition: Condition, default_entity, context: dict, repo) -> "Entity | None":
    """Resolve the entity a condition is evaluated against.

    Blank → the default entity (the current entity for the evaluation context).
    A ``{variable}`` → the entity referenced by that variable in ``context``.
    Anything else → a literal entity id.
    """
    subject = (condition.subject or "").strip()
    if not subject:
        return default_entity
    if subject.startswith("{") and subject.endswith("}"):
        key = subject[1:-1]
        eid = (context or {}).get(key)
        if not eid:
            return None
        return repo.get_entity(str(eid))
    return repo.get_entity(subject)


def _compare(a: int, op: str, b: int) -> bool:
    """Compare ``a`` against ``b`` using a numeric comparator (default ``>=``)."""
    if op == "<":
        return a < b
    if op == "<=":
        return a <= b
    if op == "==":
        return a == b
    if op == "!=":
        return a != b
    if op == ">":
        return a > b
    return a >= b


def evaluate_condition(entity: "Entity | None", condition: Condition, repo: "EntityRepository", context: dict | None = None, source=None, source_element: str | None = None, out_bindings: dict | None = None) -> bool:
    """Evaluate a single condition against the resolved subject's current state.

    ``source`` is the SFX's resolved activation/owner source (e.g. a
    ``TraitSetting``), so source-aware conditions (``SOURCE_RATING``,
    ``TARGET_PATH``) can gate on "the trait that owns/triggered this SFX".
    ``source_element`` is its catalog element type (drives ``select source``).

    ``out_bindings`` is the activation's shared variable scope. A
    ``TARGET_PATH`` condition both *reads* it (earlier conditions' outputs can be
    selected) and *writes* to it, so the things the gate found stay live for the
    SFX's effects — e.g. a condition naming the d4 traits in the roll, then an
    effect that walks those traits to their owning entity.
    """
    if condition.type in (ConditionType.ALWAYS, ConditionType.NARRATIVE):
        return True  # narrative limits are not auto-blocking

    # Outcome gates read trigger/roll context rather than entity state, so
    # evaluate them before resolving a subject (they may not need one).
    if condition.type == ConditionType.CONTEST_OUTCOME:
        wanted = condition.target_values()
        if "give_in" in wanted:
            return bool((context or {}).get("gave_in"))
        return (context or {}).get("contest_winner") in wanted

    if condition.type == ConditionType.HITCH:
        # The hitch-buying menu is active (assembled with context["hitch"]).
        return bool((context or {}).get("hitch"))

    if condition.type == ConditionType.HIGH_STAKES:
        # Whether the contest in play is high-stakes. ``target`` picks which side
        # of the flag the gate wants: "high" (default) or "low". The flag reaches
        # the context from the contest that fired the event, from the contest
        # tracker on a manual activation, and from the roll context at resolve.
        stakes = bool((context or {}).get("high_stakes"))
        # `high` is the default reading; asking for `low` asks for the other side.
        wanted = condition.target_values() or ["high"]
        return (any(w == "high" for w in wanted) if stakes
                else any(w == "low" for w in wanted))

    if condition.type == ConditionType.ARRIVAL_KIND:
        # How the entity arrived, carried on the location-change event (see
        # :class:`ArrivalKind`). Unset — a fire that isn't an arrival, or an older
        # caller — matches nothing, so a gate on "arrived through a portal" can't
        # pass on a roll.
        wanted = (condition.target or "").strip()
        return bool(wanted) and (context or {}).get("arrival_kind") == wanted

    if condition.type == ConditionType.MARGIN:
        # The signed distance this roll beat its opposition by — the relative
        # reading the books use for *heroic* / *extraordinary* success, sitting
        # beside the absolute ``ROLL_TIER`` rather than replacing it. No
        # opposition on the roll means no margin, and the gate does not pass.
        margin = (context or {}).get("margin")
        if margin is None or not condition.value:
            return False
        try:
            threshold = int(condition.value)
        except (TypeError, ValueError):
            return False
        return _compare(int(margin), condition.operator or ">=", threshold)

    if condition.type == ConditionType.ROLL_TIER:
        from transversal.domain import OutcomeTier

        tier = (context or {}).get("tier")
        if not tier or not condition.value:
            return False
        try:
            order = list(OutcomeTier)
            actual = order.index(OutcomeTier(tier))
            threshold = order.index(OutcomeTier(condition.value))
        except (ValueError, KeyError):
            return False
        return _compare(actual, condition.operator or ">=", threshold)

    if condition.type == ConditionType.TEST_OUTCOME:
        # Binary test result: success = any non-fail tier (marginal counts).
        tier = (context or {}).get("tier")
        if not tier:
            return False  # no result in the context: neither success nor failure
        wanted = condition.target_values()
        failed = tier == "fail"
        return (not failed and "success" in wanted) or (failed and "fail" in wanted)

    if condition.type == ConditionType.USER_ROLE:
        # The acting human's role: prefer the fire/menu context, else resolve
        # the entity's controlling player via the agency relationship.
        role = (context or {}).get("role")
        if role is None and entity is not None:
            from transversal.services.role_resolver import resolve_role
            role = resolve_role(entity.id, repo)
        return role in condition.target_values()

    if condition.type == ConditionType.SOURCE_RATING:
        # The source trait-setting's rating (its dice) vs a die threshold.
        if source is None:
            return False
        threshold = DieType(condition.value) if condition.value else None
        if threshold is None:
            return False
        dice = getattr(source, "dice", None) or []
        if not dice:
            return False
        return any(_compare(d.max_value, condition.operator or ">=", threshold.max_value) for d in dice)

    if condition.type == ConditionType.TARGET_PATH:
        # Resolve the authored targeting path (seeded by `select source` / `select
        # self` / catalog collections); passes iff it resolves non-empty and
        # error-free. All comparison lives in the path's filter/navigate steps.
        if condition.spec is None or not condition.spec.steps:
            return False
        from transversal.services.target_resolver import TargetContext, event_collections, resolve

        # Event-scoped seeds: a roll-bearing trigger (on_roll / on_result) carries
        # its dice in the context, so a path can inspect *this* roll — and, at the
        # pool-save moment, the other side's as well (``opposing_dice``).
        # `added_dice` is read from the rule's own point of view — the dice its
        # source contributed — so the source goes with the context.
        collections = event_collections(
            context, getattr(source, "id", None), source_element)

        target_context = TargetContext(
            subject=entity, repo=repo, source=source,
            source_element=source_element,
            collections=collections,
            bindings=out_bindings if out_bindings is not None else {},
        )
        resolution = resolve(condition.spec, target_context)
        # Publish the path's named outputs into the activation scope, so effects
        # can target what the gate matched (not just that it matched something).
        # Step outputs land on the resolution *context*, not the resolution.
        if out_bindings is not None and target_context.bindings:
            out_bindings.update(target_context.bindings)
        if resolution.errors:
            return False
        # An `evaluate` step yields an explicit boolean; otherwise the condition
        # is the classic "non-empty" check.
        if resolution.values and isinstance(resolution.values[0], bool):
            return resolution.values[0]
        return bool(resolution.values)

    subject = _resolve_subject(condition, entity, context or {}, repo)
    if subject is None:
        return False
    target = _resolve_condition_value(condition.target, context or {})

    if condition.type == ConditionType.AT_LOCATION:
        return subject.current_location == target

    if condition.type == ConditionType.HAS_TRAIT:
        for ts in repo.get_traitsettings_for_entity(subject.id):
            if ts.trait_id == target:
                return True
        return False

    if condition.type == ConditionType.HAS_EFFECTIVE_TRAIT:
        # Possession AND not disabled. A disabled trait still counts as
        # HAS_TRAIT (owned), but is not effective (contributes no dice).
        for ts in repo.get_traitsettings_for_entity(subject.id):
            if ts.trait_id == target:
                return ts.enabled
        return False

    if condition.type == ConditionType.HAS_TRAIT_IN_TRAITSET:
        for ts in repo.get_traitsettings_for_entity(subject.id):
            # The set is the registry trait's; the setting does not record one.
            trait = repo.get_trait(ts.trait_id)
            if trait is not None and trait.traitset_id == target:
                return True
        return False

    if condition.type == ConditionType.TRAIT_RATING:
        threshold = DieType(condition.value) if condition.value else None
        if threshold is None:
            return False
        for ts in repo.get_traitsettings_for_entity(subject.id):
            if ts.trait_id == target and ts.dice:
                if any(_compare(d.max_value, condition.operator or ">=", threshold.max_value) for d in ts.dice):
                    return True
        return False

    if condition.type == ConditionType.HAS_RELATIONSHIP:
        return any(
            r.get("id") == target
            for r in repo.get_related_entities(subject.id)
        )

    if condition.type == ConditionType.UNPLACED:
        return subject.current_location in (None, "")

    if condition.type in (ConditionType.CONTEST_CHALLENGER, ConditionType.CONTEST_DEFENDANT):
        # Which *side* of a contest this entity is on. The tracker models it:
        # the challenger is the state carrying `opposition_entity_id` (declaring a
        # challenge is what sets it), and the defendant is whoever that points at.
        # `get_contestants` answers from either side, so one call covers both.
        #
        # The opposition link is what separates a contest from a **test**: a plain
        # test has a state too, and an entity in one is neither side of anything.
        from transversal.services.contest_tracker import get_contest_tracker

        location = getattr(subject, "current_location", "") or ""
        if not location:
            return False
        challenger, defendant = get_contest_tracker().get_contestants(location, subject.id)
        if condition.type == ConditionType.CONTEST_CHALLENGER:
            return bool(challenger is not None and challenger.entity_id == subject.id
                        and challenger.opposition_entity_id)
        return bool(challenger is not None and defendant is not None
                    and challenger.opposition_entity_id == subject.id)

    if condition.type == ConditionType.SESSION:
        from transversal.services.session_state import is_active

        wanted = (target or "active").strip().lower()
        return is_active() is (wanted != "inactive")

    if condition.type == ConditionType.IN_UNIVERSE:
        return subject.current_universe == target

    if condition.type == ConditionType.HAS_RAZMERIT:
        try:
            threshold = int(condition.value or "0")
        except ValueError:
            return False
        return _compare(subject.razmerit, condition.operator or ">=", threshold)

    if condition.type == ConditionType.ENTITY_TYPE:
        return subject.type.value in condition.target_values()

    if condition.type == ConditionType.PHASE:
        # Phase predicates read the trigger context (e.g. "on adding"), not
        # entity state — so they only gate at trigger time.
        return (context or {}).get("phase") in condition.target_values()

    return False


def evaluate_conditions(entity: "Entity | None", conditions: list[Condition], repo: "EntityRepository", context: dict | None = None, source=None, source_element: str | None = None, out_bindings: dict | None = None) -> bool:
    """All conditions must pass (empty list is always true).

    ``source``/``source_element`` are threaded to each condition so source-aware
    conditions resolve against the SFX's activation/owner source.

    ``out_bindings`` is the activation's shared variable scope; each condition may
    read it and publish its own named outputs into it (see
    :func:`evaluate_condition`).
    """
    return all(
        evaluate_condition(entity, c, repo, context, source, source_element, out_bindings)
        for c in conditions
    )


def _has_variable(value) -> bool:
    return bool(value) and "{" in value and "}" in value


def _spec_is_static(spec) -> bool:
    """A ``TARGET_PATH`` spec is static (availability-evaluable) unless it seeds
    from the roll context (``rolled_dice``) or a bound output variable.

    ``select source`` / ``select self`` / catalog collections all resolve from
    entity + source state, which availability can provide.
    """
    if spec is None:
        return False
    for step in spec.steps:
        if step.kind == "select" and step.collection in ("rolled_dice", "variable"):
            return False
    return True


def static_conditions(conditions: list[Condition]) -> list[Condition]:
    """Conditions evaluable without trigger/menu context.

    Used by availability resolution to gate *listing* on entity state
    (``entity_type``, ``in_universe``, ``source_rating``, …) while leaving
    context/variable-gated conditions to fire/menu time.

    "Reads no context" is answered by :func:`condition_context_keys` — the
    declaration the catalog's own type definitions drive — plus the
    variable-token test. It used to be a hand-maintained ``_CONTEXT_TYPES``
    membership test, and that set was wrong in **both** directions ([[B195]]):

    * it **omitted** ``arrival_kind``, which declares ``arrival_kind`` as context.
      Such a condition survived this filter, was then evaluated with no context,
      matched nothing, and so made a gated rule — or a gated life path ([[B194]])
      — **permanently unavailable, silently**, with no error anywhere;
    * it **listed** ``user_role``, which reads *no* context (it prefers
      ``context["role"]`` but falls back to the entity's controlling player). It
      was therefore dropped here and **never evaluated at all**, so a role gate
      was silently ignored — a rule or path offered to everyone.

    Deriving the set from the declaration cannot drift either way: a condition
    type declares what it reads and this follows.
    """
    out: list[Condition] = []
    for c in (conditions or []):
        if condition_context_keys(c):
            continue
        if c.type == ConditionType.TARGET_PATH and not _spec_is_static(c.spec):
            continue
        if _has_variable(c.subject) or _has_variable(c.target) or _has_variable(c.value):
            continue
        out.append(c)
    return out


# ── Authoring metadata ───────────────────────────────
#
# Single source of truth for the condition-type vocabulary the SFX editor
# renders (via GraphQL). ``value`` is the GraphQL enum name; ``needs_target`` /
# ``target_placeholder`` drive the target field in the editor. Adding a new
# condition type here (plus its evaluator branch above) makes it appear in the
# UI without frontend edits.

from dataclasses import dataclass


@dataclass(frozen=True)
class ConditionTypeDef:
    value: str
    label: str
    needs_target: bool = False
    target_placeholder: str = ""
    target_kind: str = ""  # "" | "location" | "trait" | "entity" | "universe" | "traitset"
    value_kind: str = ""  # "" | "die" | "number"
    operators: tuple[str, ...] = ()  # numeric comparators (HAS_RAZMERIT)
    target_options: tuple[str, ...] = ()  # fixed select options for the target (ENTITY_TYPE)
    uses_spec: bool = False  # renders a targeting-path builder instead of a flat target
    # Which band of the picker this condition belongs to (see
    # ``CONDITION_GROUP_ORDER``). Declared here, next to the type it describes,
    # so the editor never carries a list of its own.
    group: str = ""
    # Catalog elements the SFX's source must resolve to for this condition to be
    # able to pass ("" = any). "Source rating" on an entity-source SFX is a
    # silent no-op, so the editor greys the option out with the reason instead of
    # letting a gate that can never fire be authored.
    requires_source_elements: tuple[str, ...] = ()
    # Context keys this condition may read, as "any of" — one type can read a
    # different key per configuration (a contest outcome reads `contest_winner`,
    # or `gave_in` when it targets a give-in). The editor keeps the option out of
    # a site that supplies none of them; `condition_context_keys` gives the exact
    # per-condition answer, which is what `validate_sfx` reports.
    requires_context_any_of: tuple[str, ...] = ()



# Triggers and effect timings that fire at a time boundary. Both carry no
# fire-time context: the beat/scene/session walk passes none, and a stored
# boundary effect is applied with an empty context.
BOUNDARY_TRIGGERS = frozenset({"on_beat", "on_scene", "on_session_start", "on_session_end"})
BOUNDARY_TIMINGS = frozenset({"end_of_beat", "end_of_scene", "end_of_session", "after_beats"})


# ── Fire-time context capability (the map) ──────────
#
# The rule that stops a gate being authored into a site that can never satisfy
# it: every condition declares which context keys it *reads*, every evaluation
# point which keys it *supplies*. Both are data here, so the editor can keep an
# option out of a site that lacks its keys and ``validate_sfx`` can say exactly
# which key is missing — one implementation instead of a list of special cases.
#
# The map only ever *forbids*: a site it does not model supplies ``None``
# (unrestricted), because hiding a working gate is worse than offering a dead
# one. Keys are read off the fire sites: ``fire_roll_sfx`` / ``fire_result_sfx``
# (roll_orchestrator), ``fire_state_sfx`` / ``fire_contest_outcome_sfx``
# (state_events), the manual trigger endpoint, the consequence/hitch menu
# assembly, and the armed/scheduled paths.

_EMPTY = frozenset()

# What the roll brings: ``fire_armed``'s roll context at ``/resolve``, and the
# contest ``/set`` (which carries the committed scalars).
_ROLL_KEYS = frozenset({"rolls", "effect_die", "total", "tier", "high_stakes"})

# The consequence / hitch menu: ``_outcome_context`` maps a menu context to its
# outcome key (``contest_winner`` / ``gave_in`` / ``tier``) plus the acting role,
# and the hitch assembly adds ``hitch``.
_MENU_KEYS = frozenset({"role", "contest_winner", "gave_in", "tier", "hitch"})

TRIGGER_CONTEXT_KEYS: dict[str, frozenset[str]] = {
    # The sheet/button path: the client sends the phase; the endpoint fills the
    # stakes in from the contest tracker.
    "manual": frozenset({"phase", "high_stakes"}),
    # Roll-match triggers share one event, which carries the dice and — when the
    # resolver produced one — the roll's outcome tier (``fire_roll_sfx`` passes
    # it, since the trigger match already reads it). The 3+ die pool path decides
    # its tier later, so a tier gate there has nothing to read; the map offers it
    # rather than hiding a gate that works on the common path.
    "on_roll": frozenset({"rolls", "tier"}),
    "on_result": frozenset({"rolls", "effect_die", "total"}),
    "on_complication": frozenset({"rolls", "tier"}),
    "on_botch": frozenset({"rolls", "tier"}),
    "on_success": frozenset({"rolls", "tier"}),
    "on_failure": frozenset({"rolls", "tier"}),
    "on_contest_win": frozenset({"contest_winner", "effect_die", "high_stakes"}),
    "on_contest_loss": frozenset({"contest_winner", "effect_die", "high_stakes"}),
    "on_give_in": frozenset({"gave_in", "high_stakes"}),
    # The pool-save moment: it carries the actor's dice, and — when a contest has
    # an opponent recorded at this location — the other side's as well. Only a
    # `targeting path` condition reads dice, so only it is gated by these keys.
    "on_pool_change": frozenset({"rolls", "opposing_rolls", "added_dice"}),
    # The same moment; the *add* trigger narrows it to the rule's own trait.
    "on_pool_add": frozenset({"rolls", "opposing_rolls", "added_dice"}),
    "on_location_change": frozenset({"from_location", "to_location", "universe", "arrival_kind"}),
    "on_beat": _EMPTY,
    "on_scene": _EMPTY,
    "on_session_start": _EMPTY,
    "on_session_end": _EMPTY,
}

TIMING_CONTEXT_KEYS: dict[str, frozenset[str]] = {
    "on_roll": frozenset({"rolls"}),
    "on_set": _ROLL_KEYS,
    "on_result": _ROLL_KEYS,
    "on_contest_win": _ROLL_KEYS,
    "on_contest_loss": _ROLL_KEYS,
    "on_success": _ROLL_KEYS,
    "on_failure": _ROLL_KEYS,
    "end_of_beat": _EMPTY,
    "end_of_scene": _EMPTY,
    "end_of_session": _EMPTY,
    "after_beats": _EMPTY,
}


def context_keys_for(trigger: str = "", timing: str = "",
                     placement: Optional[str] = None) -> Optional[frozenset[str]]:
    """The context keys an evaluation point supplies (``None`` = unrestricted).

    ``timing`` is an effect's timing when the point is that effect's own fire:
    roll/outcome timings bring the roll, boundary timings bring nothing. An
    immediate effect — and any SFX-level condition — is evaluated at activation,
    where the trigger decides. A menu rule is gated by the menu assembly instead,
    which supplies the outcome keys — and a menu rule is either
    ``trigger="menu"`` or a legacy ``placement="menu"`` override, so both count.
    """
    if timing and timing != "immediate":
        return TIMING_CONTEXT_KEYS.get(timing)
    if placement == "menu":
        return _MENU_KEYS
    if trigger:
        from transversal.domain.traits import derive_placement
        if derive_placement(trigger) == "menu":
            return _MENU_KEYS
    return TRIGGER_CONTEXT_KEYS.get(trigger or "")


def condition_context_keys(condition: Condition) -> frozenset[str]:
    """The context keys this condition reads (empty = pure entity state).

    ``USER_ROLE`` reads none: it prefers ``context["role"]`` but falls back to
    the entity's controlling player, so it works without one. ``TARGET_PATH``
    reads ``rolls`` only when its path seeds from ``rolled_dice``.
    ``SOURCE_RATING`` reads the SFX's *source*, not the context — that is
    ``requires_source_elements``' business.
    """
    ctype = condition.type
    if ctype == ConditionType.CONTEST_OUTCOME:
        if (condition.target or "").strip() == "give_in":
            return frozenset({"gave_in"})
        return frozenset({"contest_winner"})
    if ctype in (ConditionType.ROLL_TIER, ConditionType.TEST_OUTCOME):
        return frozenset({"tier"})
    if ctype == ConditionType.MARGIN:
        return frozenset({"margin"})
    if ctype == ConditionType.PHASE:
        return frozenset({"phase"})
    if ctype == ConditionType.HIGH_STAKES:
        return frozenset({"high_stakes"})
    if ctype == ConditionType.HITCH:
        return frozenset({"hitch"})
    if ctype == ConditionType.ARRIVAL_KIND:
        return frozenset({"arrival_kind"})
    if ctype == ConditionType.TARGET_PATH:
        spec = condition.spec
        if spec is None:
            return frozenset()
        read: set[str] = set()
        for step in spec.steps:
            if step.kind != "select":
                continue
            if step.collection == "rolled_dice":
                read.add("rolls")
            elif step.collection == "opposing_dice":
                read.add("opposing_rolls")
            elif step.collection == "added_dice":
                read.add("added_dice")
        return frozenset(read)
    return frozenset()


# ── The picker's bands ───────────────────────────────
#
# The condition picker is ~22 entries, which is past the point where a flat list
# can be scanned. Every type names its band here (declared next to the type) and
# this tuple gives the bands their order — so the editor renders grouping it was
# *told about*, rather than carrying a taxonomy of its own that would drift.
#
# The bands are the author's question, not the implementation's: a gate is about
# the character, about the moment it fires, about the rule itself, or it is not
# a gate at all.
GROUP_CHARACTER = "Character state"
# What is true *when it fires* — including who is driving (a user role only
# resolves at an activation, so it belongs with the moment, not the character).
GROUP_MOMENT = "The moment it fires"
GROUP_RULE = "This rule"
GROUP_NONE = "No gate"

CONDITION_GROUP_ORDER: tuple[str, ...] = (
    GROUP_CHARACTER,
    GROUP_MOMENT,
    GROUP_RULE,
    GROUP_NONE,
)

CONDITION_TYPES: tuple[ConditionTypeDef, ...] = (
    ConditionTypeDef(ConditionType.ALWAYS.name, "Always", group=GROUP_NONE),
    ConditionTypeDef(ConditionType.AT_LOCATION.name, "At location", needs_target=True, target_placeholder="location id", target_kind="location", group=GROUP_CHARACTER),
    ConditionTypeDef(ConditionType.HAS_TRAIT.name, "Has trait", needs_target=True, target_placeholder="trait id", target_kind="trait", group=GROUP_CHARACTER),
    ConditionTypeDef(ConditionType.HAS_EFFECTIVE_TRAIT.name, "Has effective trait", needs_target=True, target_placeholder="trait id", target_kind="trait", group=GROUP_CHARACTER),
    ConditionTypeDef(ConditionType.HAS_TRAIT_IN_TRAITSET.name, "Has trait in traitset", needs_target=True, target_placeholder="traitset id", target_kind="traitset", group=GROUP_CHARACTER),
    ConditionTypeDef(ConditionType.HAS_RELATIONSHIP.name, "Has relationship", needs_target=True, target_placeholder="entity id", target_kind="entity", group=GROUP_CHARACTER),
    ConditionTypeDef(ConditionType.TRAIT_RATING.name, "Trait rating", needs_target=True, target_placeholder="trait id", target_kind="trait", value_kind="die", operators=("<", "<=", "==", "!=", ">=", ">"), group=GROUP_CHARACTER),
    ConditionTypeDef(ConditionType.HAS_RAZMERIT.name, "Has razmerit", value_kind="number", operators=("<", "<=", "==", "!=", ">=", ">"), group=GROUP_CHARACTER),
    ConditionTypeDef(ConditionType.ENTITY_TYPE.name, "Entity type", needs_target=True, target_placeholder="entity type", target_options=("character", "gmc", "asset"), group=GROUP_CHARACTER),
    ConditionTypeDef(ConditionType.USER_ROLE.name, "User role", needs_target=True, target_placeholder="role", target_options=("player", "architect"), group=GROUP_MOMENT),
    ConditionTypeDef(ConditionType.UNPLACED.name, "Unplaced (no location)", group=GROUP_CHARACTER),
    # A contest's two sides. Not expressible as a path: the tracker holds the
    # relation, and a path can reach "a contest" but not "the side I am on".
    ConditionTypeDef(ConditionType.CONTEST_CHALLENGER.name, "In a contest as the challenger",
                     group=GROUP_CHARACTER),
    ConditionTypeDef(ConditionType.CONTEST_DEFENDANT.name, "In a contest as the defendant",
                     group=GROUP_CHARACTER),
    ConditionTypeDef(ConditionType.IN_UNIVERSE.name, "In universe", needs_target=True, target_placeholder="universe key", target_kind="universe", group=GROUP_CHARACTER),
    ConditionTypeDef(ConditionType.PHASE.name, "Phase", needs_target=True, target_placeholder="phase", target_options=("adding", "rolling", "picking", "resolved"), requires_context_any_of=("phase",), group=GROUP_MOMENT),
    ConditionTypeDef(ConditionType.CONTEST_OUTCOME.name, "Contest outcome", needs_target=True, target_placeholder="outcome", target_options=("player", "opponent", "give_in"), requires_context_any_of=("contest_winner", "gave_in"), group=GROUP_MOMENT),
    ConditionTypeDef(ConditionType.HITCH.name, "Hitch", requires_context_any_of=("hitch",), group=GROUP_MOMENT),
    ConditionTypeDef(ConditionType.HIGH_STAKES.name, "High stakes", needs_target=True, target_placeholder="stakes", target_options=("high", "low"), requires_context_any_of=("high_stakes",), group=GROUP_MOMENT),
    ConditionTypeDef(ConditionType.SESSION.name, "Session", needs_target=True,
                     target_placeholder="state", target_options=("active", "inactive"),
                     group=GROUP_MOMENT),
    ConditionTypeDef(ConditionType.ARRIVAL_KIND.name, "Arrival kind", needs_target=True, target_placeholder="arrival", target_options=("transversal", "hierarchy", "move", "effect"), requires_context_any_of=("arrival_kind",), group=GROUP_MOMENT),
    ConditionTypeDef(ConditionType.ROLL_TIER.name, "Roll tier", value_kind="tier", operators=(">=", ">", "==", "!=", "<=", "<"), requires_context_any_of=("tier",), group=GROUP_MOMENT),
    ConditionTypeDef(ConditionType.MARGIN.name, "Margin", value_kind="number", operators=("<", "<=", "==", "!=", ">=", ">"), requires_context_any_of=("margin",), group=GROUP_MOMENT),
    ConditionTypeDef(ConditionType.TEST_OUTCOME.name, "Test outcome", needs_target=True, target_placeholder="outcome", target_options=("success", "fail"), requires_context_any_of=("tier",), group=GROUP_MOMENT),
    ConditionTypeDef(ConditionType.SOURCE_RATING.name, "Source rating", value_kind="die", operators=("<", "<=", "==", "!=", ">=", ">"), requires_source_elements=("traitsetting",), group=GROUP_RULE),
    ConditionTypeDef(ConditionType.TARGET_PATH.name, "Targeting path", uses_spec=True, group=GROUP_RULE),
    ConditionTypeDef(ConditionType.NARRATIVE.name, "Narrative", group=GROUP_NONE),
)


def ordered_condition_types() -> list[ConditionTypeDef]:
    """The vocabulary in the order the editor shows it: grouped, then declared.

    The picker is ~22 entries, which is past the point where a flat list can be
    read — so each type declares its band and this puts them in band order,
    keeping the declaration order *within* a band (which is where related types
    already sit next to each other). The editor renders one ``optgroup`` per
    consecutive band, so a new type only has to name its group.
    """
    rank = {name: i for i, name in enumerate(CONDITION_GROUP_ORDER)}
    return sorted(
        CONDITION_TYPES,
        key=lambda c: (rank.get(c.group, len(rank)), list(CONDITION_TYPES).index(c)),
    )
