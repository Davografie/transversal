"""Condition evaluation — automatically gate tables/entries/effects on entity state."""

from __future__ import annotations

from typing import TYPE_CHECKING

from transversal.domain import Condition, ConditionType, Entity

if TYPE_CHECKING:
    from transversal.db.repository import EntityRepository


def evaluate_condition(entity: Entity, condition: Condition, repo: "EntityRepository") -> bool:
    """Evaluate a single condition against an entity's current state."""
    if condition.type in (ConditionType.ALWAYS, ConditionType.NARRATIVE):
        return True  # narrative limits are not auto-blocking

    if condition.type == ConditionType.RANK_MIN:
        return entity.current_rank >= int(condition.value or 0)

    if condition.type == ConditionType.AT_LOCATION:
        return entity.current_location == condition.target

    if condition.type == ConditionType.HAS_TRAIT:
        for ts in repo.get_traitsettings_for_entity(entity.id):
            if ts.trait_id == condition.target:
                return True
        return False

    if condition.type == ConditionType.HAS_RELATIONSHIP:
        return any(
            r.get("id") == condition.target
            for r in repo.get_related_entities(entity.id)
        )

    return False


def evaluate_conditions(entity: Entity, conditions: list[Condition], repo: "EntityRepository") -> bool:
    """All conditions must pass (empty list is always true)."""
    return all(evaluate_condition(entity, c, repo) for c in conditions)
