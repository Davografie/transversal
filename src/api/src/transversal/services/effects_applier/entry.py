"""Entry — split out of src/api/src/transversal/services/effects_applier.py."""

from __future__ import annotations

from transversal.domain import Effect
from transversal.domain import Entity
from transversal.services.conditions import evaluate_conditions
from transversal.services.effects_applier.datatypes import (
    BINDINGS_CONTEXT_KEY,
    EffectsResult,
)
from transversal.services.effects_applier.handlers_dice import (
    _apply_add_die,
    _apply_disable,
    _apply_enable,
    _apply_increase_by_effect,
    _apply_reduce_by_effect,
    _apply_remove_die,
    _apply_set,
    _apply_toggle,
)
from transversal.services.effects_applier.handlers_economy import (
    _apply_earn,
    _apply_spend,
    _apply_transfer,
)
from transversal.services.effects_applier.handlers_pools import (
    _apply_add_dice,
    _apply_add_trait_rating,
    _apply_dice_limit,
    _apply_resolve_pool,
    _apply_roll_pool,
    _apply_set_traitset_limit,
)
from transversal.services.effects_applier.handlers_sfx import (
    _apply_grant_sfx,
)
from transversal.services.effects_applier.handlers_traits import (
    _apply_copy_trait,
    _apply_cortex_gain,
    _apply_discover,
    _apply_gain,
    _apply_gain_or_step_up,
    _apply_move_trait,
    _apply_remove,
    _apply_reveal,
    _apply_step_down,
    _apply_step_up,
)
from transversal.services.effects_applier.handlers_world import (
    _apply_cancel_scheduled_event,
    _apply_create_projection,
    _apply_relationship_create,
    _apply_restore_projection,
    _apply_set_location,
    _apply_travel,
)
from transversal.services.effects_applier.targeting import (
    _scope_choice,
)


_MUTATION_HANDLERS = {
    ("modify_trait", "gain"): _apply_gain,
    ("modify_trait", "remove"): _apply_remove,
    ("modify_trait", "gain_or_step_up"): _apply_gain_or_step_up,
    ("modify_trait", "cortex_gain"): _apply_cortex_gain,
    ("modify_trait", "step_up"): _apply_step_up,
    ("modify_trait", "step_down"): _apply_step_down,
    ("modify_trait", "add_die"): _apply_add_die,
    ("modify_trait", "copy"): _apply_copy_trait,
    ("modify_trait", "move"): _apply_move_trait,
    ("modify_trait", "remove_die"): _apply_remove_die,
    ("modify_trait", "reduce_by_effect"): _apply_reduce_by_effect,
    ("modify_trait", "increase_by_effect"): _apply_increase_by_effect,
    ("modify_trait", "set"): _apply_set,
    ("modify_trait", "disable"): _apply_disable,
    ("modify_trait", "enable"): _apply_enable,
    ("modify_trait", "toggle"): _apply_toggle,
    ("entity", "cancel_scheduled_event"): _apply_cancel_scheduled_event,
    # Granting a rule to an owner (the teacher case) — see handlers_sfx.
    ("sfx", "grant"): _apply_grant_sfx,
    ("projection", "create"): _apply_create_projection,
    ("projection", "restore"): _apply_restore_projection,
    ("modify_traitset", "set_limit"): _apply_set_traitset_limit,
    ("modify_dice_limit", "increase"): _apply_dice_limit,
    ("modify_dice_limit", "decrease"): _apply_dice_limit,
    ("modify_pool", "add_dice"): _apply_add_dice,
    ("modify_pool", "add_trait_rating"): _apply_add_trait_rating,
    ("modify_pool", "roll"): _apply_roll_pool,
    ("modify_pool", "resolve"): _apply_resolve_pool,
    ("modify_trait", "reveal"): _apply_reveal,
    ("transfer_razmerit", "earn"): _apply_earn,
    ("transfer_razmerit", "spend"): _apply_spend,
    ("transfer_razmerit", "transfer"): _apply_transfer,
    ("life_path", "discover"): _apply_discover,
    ("relationship", "create"): _apply_relationship_create,
    ("travel", "move"): _apply_travel,
    ("location", "set"): _apply_set_location,
}

def apply_effects(entity: Entity, effects: list[Effect], repo, context: dict | None = None, source=None, source_element: str | None = None) -> EffectsResult:
    """Apply operational effects to an entity's in-memory state (no persistence).

    Mutates ``entity`` in place for entity-level fields (razmerit, rank, discovered
    paths) and collects new/updated TraitSetting objects, relationship edges, and
    cross-entity mutations into the returned EffectsResult. Persistence and SSE
    broadcast are the caller's responsibility.

    Unresolved targets (``{choose_*}` or empty-when-required) become PendingChoice.
    Effects without a mutation handler (resolver-context and flow effects) become
    passthrough. An effect whose ``conditions`` fail against ``context`` is skipped.
    """
    result = EffectsResult()
    bindings = (context or {}).get(BINDINGS_CONTEXT_KEY) or {}
    for raw_effect in effects:
        effect = raw_effect
        if effect.conditions and not evaluate_conditions(entity, effect.conditions, repo, context, source=source, source_element=source_element):
            continue
        # Resolve an ``entity_spec`` here too when this list was applied directly
        # (the engine resolves first on its own path); handlers then see a
        # concrete ``entity`` id, matching the engine's ``target_spec`` rewrite.
        effect = resolve_effect_entity(effect, entity.id, repo, context)
        scope_choice = _scope_choice(effect)
        if scope_choice is not None:
            result.pending_choices.append(scope_choice)
            continue
        handler = _MUTATION_HANDLERS.get((effect.type, effect.action))
        if handler is None:
            result.passthrough.append(effect)
            continue
        handler(entity, effect, repo, result)
    return result

def resolve_effect_entity(effect: Effect, entity_id: str, repo, context: dict | None = None,
                          collections: dict | None = None) -> Effect:
    """Rewrite ``effect`` so its entity is a concrete id, resolving ``entity_spec``.

    ``entity_spec`` is resolved against the activation's variable scope (carried
    in ``context`` under :data:`BINDINGS_CONTEXT_KEY`), so an authored path can
    pick up a variable a condition bound — e.g. "the d4 traits this roll matched,"
    navigated on to their owning entities. Effects without a spec pass through
    untouched, and a spec that resolves to nothing leaves the effect as authored
    so the existing "resolved to nothing" report still fires.

    ``collections`` *overrides* the path's event-scoped collections, which are
    seeded from the event context (``rolls`` / ``opposing_rolls``) so an
    immediate effect can read the same dice a condition can. Callers that are
    already iterating one die should pass ``{"rolled_dice": [die]}`` — inside a
    per-die effect, the die being processed *is* the roll the path should read.
    """
    if effect.entity_spec is None or not effect.entity_spec.steps:
        return effect
    entity = repo.get_entity(entity_id) if repo is not None else None
    if entity is None:
        return effect
    from transversal.services.target_resolver import event_collections

    bindings = (context or {}).get(BINDINGS_CONTEXT_KEY) or {}
    # The event's own dice seed the path (an immediate effect reads the same
    # collections a condition does); an explicit argument still wins, because a
    # caller iterating one die means *that die* is the roll.
    seeds = event_collections(context)
    seeds.update(collections or {})
    resolved = _resolve_entity_spec(effect, entity, repo, bindings, seeds)
    return resolved if resolved is not None else effect

def _resolve_entity_spec(effect: Effect, entity: Entity, repo, bindings: dict,
                         collections: dict | None = None) -> Effect | None:
    """Resolve ``effect.entity_spec`` to a concrete id, or None if it resolves nothing.

    ``bindings`` is the activation scope (condition + earlier-effect outputs), so a
    path can pick up a variable a condition named — e.g. the d4 traits this roll
    matched, navigated on to their owning entities.
    """
    from transversal.services.target_resolver import TargetContext, resolve

    resolution = resolve(
        effect.entity_spec,
        TargetContext(subject=entity, repo=repo, bindings=bindings,
                      collections=dict(collections or {})),
    )
    for value in resolution.values:
        rid = getattr(value, "id", None)
        if rid is None and isinstance(value, dict):
            rid = value.get("id") or value.get("ts_id")
        if rid:
            return effect.model_copy(update={"entity": rid, "entity_spec": None})
    return None
