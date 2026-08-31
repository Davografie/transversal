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


def evaluate_condition(entity: "Entity | None", condition: Condition, repo: "EntityRepository", context: dict | None = None, source=None, source_element: str | None = None) -> bool:
    """Evaluate a single condition against the resolved subject's current state.

    ``source`` is the SFX's resolved activation/owner source (e.g. a
    ``TraitSetting``), so source-aware conditions (``SOURCE_RATING``,
    ``TARGET_PATH``) can gate on "the trait that owns/triggered this SFX".
    ``source_element`` is its catalog element type (drives ``select source``).
    """
    if condition.type in (ConditionType.ALWAYS, ConditionType.NARRATIVE):
        return True  # narrative limits are not auto-blocking

    # Outcome gates read trigger/roll context rather than entity state, so
    # evaluate them before resolving a subject (they may not need one).
    if condition.type == ConditionType.CONTEST_OUTCOME:
        return (context or {}).get("contest_winner") == (condition.target or "").strip()

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
        wanted = (condition.target or "").strip()
        if wanted == "success":
            return tier not in (None, "", "fail")
        if wanted == "fail":
            return tier == "fail"
        return False

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
        from transversal.services.target_resolver import TargetContext, resolve

        resolution = resolve(
            condition.spec,
            TargetContext(subject=entity, repo=repo, source=source, source_element=source_element),
        )
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
            if ts.traitset_id == target:
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

    if condition.type == ConditionType.IN_UNIVERSE:
        return subject.current_universe == target

    if condition.type == ConditionType.HAS_RAZMERIT:
        try:
            threshold = int(condition.value or "0")
        except ValueError:
            return False
        return _compare(subject.razmerit, condition.operator or ">=", threshold)

    if condition.type == ConditionType.ENTITY_TYPE:
        return subject.type.value == target

    if condition.type == ConditionType.PHASE:
        # Phase predicates read the trigger context (e.g. "on adding"), not
        # entity state — so they only gate at trigger time.
        return (context or {}).get("phase") == target

    return False


def evaluate_conditions(entity: "Entity | None", conditions: list[Condition], repo: "EntityRepository", context: dict | None = None, source=None, source_element: str | None = None) -> bool:
    """All conditions must pass (empty list is always true).

    ``source``/``source_element`` are threaded to each condition so source-aware
    conditions resolve against the SFX's activation/owner source.
    """
    return all(evaluate_condition(entity, c, repo, context, source, source_element) for c in conditions)


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


# Condition types that read trigger/roll context rather than entity state, and
# therefore can never be evaluated for availability (listing) without a context.
_CONTEXT_TYPES = frozenset({
    ConditionType.PHASE,
    ConditionType.CONTEST_OUTCOME,
    ConditionType.ROLL_TIER,
    ConditionType.TEST_OUTCOME,
})


def static_conditions(conditions: list[Condition]) -> list[Condition]:
    """Conditions evaluable without trigger/menu context.

    Excludes context-dependent types (``phase`` / ``contest_outcome`` /
    ``roll_tier`` / ``test_outcome``) by type, and variable-gated conditions by
    token presence. Used by availability resolution to gate *listing* on entity
    state (``entity_type``, ``in_universe``, ``source_rating``, …) while leaving
    context/variable-gated conditions to fire/menu time.
    """
    out: list[Condition] = []
    for c in (conditions or []):
        if c.type in _CONTEXT_TYPES:
            continue
        if c.type == ConditionType.TARGET_PATH:
            if _spec_is_static(c.spec):
                out.append(c)
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


CONDITION_TYPES: tuple[ConditionTypeDef, ...] = (
    ConditionTypeDef(ConditionType.ALWAYS.name, "Always"),
    ConditionTypeDef(ConditionType.AT_LOCATION.name, "At location", needs_target=True, target_placeholder="location id", target_kind="location"),
    ConditionTypeDef(ConditionType.HAS_TRAIT.name, "Has trait", needs_target=True, target_placeholder="trait id", target_kind="trait"),
    ConditionTypeDef(ConditionType.HAS_EFFECTIVE_TRAIT.name, "Has effective trait", needs_target=True, target_placeholder="trait id", target_kind="trait"),
    ConditionTypeDef(ConditionType.HAS_TRAIT_IN_TRAITSET.name, "Has trait in traitset", needs_target=True, target_placeholder="traitset id", target_kind="traitset"),
    ConditionTypeDef(ConditionType.HAS_RELATIONSHIP.name, "Has relationship", needs_target=True, target_placeholder="entity id", target_kind="entity"),
    ConditionTypeDef(ConditionType.TRAIT_RATING.name, "Trait rating", needs_target=True, target_placeholder="trait id", target_kind="trait", value_kind="die", operators=("<", "<=", "==", "!=", ">=", ">")),
    ConditionTypeDef(ConditionType.HAS_RAZMERIT.name, "Has razmerit", value_kind="number", operators=("<", "<=", "==", "!=", ">=", ">")),
    ConditionTypeDef(ConditionType.ENTITY_TYPE.name, "Entity type", needs_target=True, target_placeholder="entity type", target_options=("character", "gmc", "asset")),
    ConditionTypeDef(ConditionType.UNPLACED.name, "Unplaced (no location)"),
    ConditionTypeDef(ConditionType.IN_UNIVERSE.name, "In universe", needs_target=True, target_placeholder="universe key", target_kind="universe"),
    ConditionTypeDef(ConditionType.PHASE.name, "Phase", needs_target=True, target_placeholder="phase", target_options=("adding", "rolling", "picking", "resolved")),
    ConditionTypeDef(ConditionType.CONTEST_OUTCOME.name, "Contest outcome", needs_target=True, target_placeholder="outcome", target_options=("player", "opponent")),
    ConditionTypeDef(ConditionType.ROLL_TIER.name, "Roll tier", value_kind="tier", operators=(">=", ">", "==", "!=", "<=", "<")),
    ConditionTypeDef(ConditionType.TEST_OUTCOME.name, "Test outcome", needs_target=True, target_placeholder="outcome", target_options=("success", "fail")),
    ConditionTypeDef(ConditionType.SOURCE_RATING.name, "Source rating", value_kind="die", operators=("<", "<=", "==", "!=", ">=", ">")),
    ConditionTypeDef(ConditionType.TARGET_PATH.name, "Targeting path", uses_spec=True),
    ConditionTypeDef(ConditionType.NARRATIVE.name, "Narrative"),
)
