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


def evaluate_condition(entity: "Entity | None", condition: Condition, repo: "EntityRepository", context: dict | None = None) -> bool:
    """Evaluate a single condition against the resolved subject's current state."""
    if condition.type in (ConditionType.ALWAYS, ConditionType.NARRATIVE):
        return True  # narrative limits are not auto-blocking

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
                if any(d.max_value >= threshold.max_value for d in ts.dice):
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

    return False


def evaluate_conditions(entity: "Entity | None", conditions: list[Condition], repo: "EntityRepository", context: dict | None = None) -> bool:
    """All conditions must pass (empty list is always true)."""
    return all(evaluate_condition(entity, c, repo, context) for c in conditions)


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
    target_kind: str = ""  # "" | "location" | "trait" | "entity" | "universe"


CONDITION_TYPES: tuple[ConditionTypeDef, ...] = (
    ConditionTypeDef(ConditionType.ALWAYS.name, "Always"),
    ConditionTypeDef(ConditionType.AT_LOCATION.name, "At location", needs_target=True, target_placeholder="location id", target_kind="location"),
    ConditionTypeDef(ConditionType.HAS_TRAIT.name, "Has trait", needs_target=True, target_placeholder="trait id", target_kind="trait"),
    ConditionTypeDef(ConditionType.HAS_TRAIT_IN_TRAITSET.name, "Has trait in traitset", needs_target=True, target_placeholder="traitset id"),
    ConditionTypeDef(ConditionType.HAS_RELATIONSHIP.name, "Has relationship", needs_target=True, target_placeholder="entity id", target_kind="entity"),
    ConditionTypeDef(ConditionType.TRAIT_RATING.name, "Trait rating", needs_target=True, target_placeholder="trait id", target_kind="trait"),
    ConditionTypeDef(ConditionType.UNPLACED.name, "Unplaced (no location)"),
    ConditionTypeDef(ConditionType.IN_UNIVERSE.name, "In universe", needs_target=True, target_placeholder="universe key", target_kind="universe"),
    ConditionTypeDef(ConditionType.NARRATIVE.name, "Narrative"),
)
