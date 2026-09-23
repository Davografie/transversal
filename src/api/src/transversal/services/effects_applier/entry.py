"""Entry — split out of src/api/src/transversal/services/effects_applier.py."""

from __future__ import annotations

from transversal.domain import Effect
from transversal.domain import Entity
from transversal.services.conditions import evaluate_conditions
from transversal.services.effects_applier.datatypes import (
    PendingChoice,
    BINDINGS_CONTEXT_KEY,
    EffectsResult,
)
from transversal.services.effects_applier.handlers_change_die import (
    _apply_change_double,
    _apply_change_remove,
    _apply_play_as_rating,
    _apply_reroll_die,
    _apply_restore_die,
    _apply_change_set,
    _apply_change_split,
    _apply_change_step_down,
    _apply_change_step_up,
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
    _apply_remove_added_dice,
    _apply_resolve_pool,
    _apply_roll_pool,
    _apply_set_traitset_limit,
)
from transversal.services.effects_applier.handlers_outcome import (
    _apply_step_up_effect,
    _apply_step_up_outcome,
)
from transversal.services.effects_applier.handlers_sfx import (
    _apply_grant_sfx,
)
from transversal.services.effects_applier.handlers_traits import (
    _apply_change_trait,
    _apply_copy_trait,
    _apply_cortex_gain,
    _apply_discover,
    _apply_gain,
    _apply_gain_or_step_up,
    _apply_invert_polarity,
    _apply_move_trait,
    _apply_remove,
    _apply_reveal,
    _apply_set_polarity,
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
_MUTATION_HANDLERS = {
    ("modify_trait", "gain"): _apply_gain,
    # Same applier, three declared owners (see `EffectActionMeta.owner_elements`):
    # the subject entity, a relationship edge, or another trait instance. The
    # verbs differ in where they anchor, not in what gaining means.
    ("modify_trait", "gain_relationship"): _apply_gain,
    ("modify_trait", "gain_subtrait"): _apply_gain,
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
    ("modify_trait", "set_polarity"): _apply_set_polarity,
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
    ("modify_pool", "remove_added_dice"): _apply_remove_added_dice,
    ("modify_pool", "roll"): _apply_roll_pool,
    ("modify_pool", "resolve"): _apply_resolve_pool,
    # Changing a die — in a trait instance's rating *or* in an assembled pool.
    # Which one is the target's business (`rating:<i>:<ts>` / `die:<loc>:<owner>:<i>`),
    # so every verb dispatches on the locus and the two homes cannot drift.
    ("modify_roll", "set_die"): _apply_change_set,
    ("modify_roll", "step_up_die"): _apply_change_step_up,
    ("modify_roll", "step_down_die"): _apply_change_step_down,
    ("modify_roll", "double_die"): _apply_change_double,
    ("modify_roll", "split_die"): _apply_change_split,
    ("modify_roll", "remove_die"): _apply_change_remove,
    # Playing a trait at another size for the roll: the rating is temporarily that
    # die, so the pooled dice follow their trait.
    ("modify_roll", "play_as_rating"): _apply_play_as_rating,
    ("modify_roll", "reroll_die"): _apply_reroll_die,
    # The undo of a change-die effect, from the prior dice the handler recorded.
    ("modify_roll", "restore_die"): _apply_restore_die,
    ("modify_trait", "change"): _apply_change_trait,
    ("modify_trait", "invert_polarity"): _apply_invert_polarity,
    ("modify_trait", "reveal"): _apply_reveal,
    ("transfer_razmerit", "earn"): _apply_earn,
    ("transfer_razmerit", "spend"): _apply_spend,
    ("transfer_razmerit", "transfer"): _apply_transfer,
    ("life_path", "discover"): _apply_discover,
    # The roll's own result, changed after it is set — the one effect family that
    # acts on a committed result rather than on an entity (see handlers_outcome).
    ("modify_outcome", "step_up_effect"): _apply_step_up_effect,
    ("modify_outcome", "step_up_outcome"): _apply_step_up_outcome,
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

    A ``target_spec`` is resolved here too: the engine's firing paths resolve a
    spec before they reach the applier, but this entry point is also called
    directly (a life-path entry's effects), and an unresolved spec used to mean an
    effect that silently never happened. A spec that resolves to several targets
    applies once per target; one that stops at a ``choose`` step becomes a
    ``PendingChoice`` for that element.

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
        # A die named by a path (``result_spec``) is read here too, for the same
        # reason: this entry point is reached directly (a life-path entry) as well
        # as through the engine, and an unread die silently means "no die".
        effect = resolve_effect_result(effect, entity.id, repo, context)
        # And its *owner*, when the action anchors what it makes somewhere other
        # than the subject: a relationship edge, or another trait instance.
        effect = resolve_effect_owner(effect, entity.id, repo, context)
        if effect.target_spec is not None and effect.target_spec.steps:
            _apply_spec_effect(effect, entity, repo, result, bindings)
            continue
        handler = _MUTATION_HANDLERS.get((effect.type, effect.action))
        if handler is None:
            result.passthrough.append(effect)
            continue
        handler(entity, effect, repo, result)
    return result

def _apply_spec_effect(effect: Effect, entity: Entity, repo, result: EffectsResult,
                       bindings: dict) -> None:
    """Resolve an effect's target spec and apply it once per resolved target."""
    from transversal.services.effects_engine.refs import resolve_effect_spec_choices

    resolved, pending = resolve_effect_spec_choices(
        effect, "target", {}, entity, repo, bindings=bindings or {},
    )
    if pending:
        # A path that stopped at a `choose`: the caller answers it. The element is
        # what the picker presents; the engine's own paths carry the exact pool as
        # a structured choice, which this low-level entry point cannot.
        for choice in pending:
            result.pending_choices.append(
                PendingChoice(effect=effect, kind=choice.element, field="target"))
        return
    for concrete in resolved:
        handler = _MUTATION_HANDLERS.get((concrete.type, concrete.action))
        if handler is None:
            result.passthrough.append(concrete)
            continue
        handler(entity, concrete, repo, result)


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
    from transversal.services.effects_applier.datatypes import SOURCE_CONTEXT_KEY
    from transversal.services.effects_applier.datatypes import SOURCE_ELEMENT_CONTEXT_KEY
    from transversal.services.target_resolver import event_collections

    bindings = (context or {}).get(BINDINGS_CONTEXT_KEY) or {}
    # The event's own dice seed the path (an immediate effect reads the same
    # collections a condition does); an explicit argument still wins, because a
    # caller iterating one die means *that die* is the roll. `added_dice` is
    # narrowed by the rule's source, which the caller threaded into the context.
    source = (context or {}).get(SOURCE_CONTEXT_KEY)
    source_element = (context or {}).get(SOURCE_ELEMENT_CONTEXT_KEY)
    seeds = event_collections(
        context, getattr(source, "id", None), source_element)
    seeds.update(collections or {})
    resolved = _resolve_entity_spec(effect, entity, repo, bindings, seeds,
                                    source=source, source_element=source_element)
    return resolved if resolved is not None else effect


def resolve_effect_result(effect: Effect, entity_id: str, repo,
                          context: dict | None = None,
                          collections: dict | None = None) -> Effect:
    """Rewrite ``effect`` so its die is concrete, resolving ``result_spec``.

    ``result`` is a literal (``d6``) or a ``{variable}`` token, which covers a die
    anyone can name while authoring. A die that is a *fact in the world* — the
    capacity slot an agenda's next step fills — has no literal, so the author
    names it by a path and this reads it. Mirrors :func:`resolve_effect_entity`,
    including the event-scoped collections and the resolved activation source, so
    a ``select source`` path works on an automatic trigger.

    The resolved value is a die: a ``capacity_die`` (or ``rating_die``) carries it
    under ``rating``, and a raw die value is already the string. When the path
    names nothing, ``result`` is **cleared** rather than left standing — an author
    who named the die by a path left the literal as a placeholder, and applying it
    would invent a die the world did not name. The handler then reports "no die
    rating to add", which is the honest answer.
    """
    if effect.result_spec is None or not effect.result_spec.steps:
        return effect
    entity = repo.get_entity(entity_id) if repo is not None else None
    if entity is None:
        return effect
    from transversal.services.effects_applier.datatypes import SOURCE_CONTEXT_KEY
    from transversal.services.effects_applier.datatypes import SOURCE_ELEMENT_CONTEXT_KEY
    from transversal.services.target_resolver import TargetContext, event_collections, resolve

    bindings = (context or {}).get(BINDINGS_CONTEXT_KEY) or {}
    source = (context or {}).get(SOURCE_CONTEXT_KEY)
    source_element = (context or {}).get(SOURCE_ELEMENT_CONTEXT_KEY)
    seeds = event_collections(context, getattr(source, "id", None), source_element)
    seeds.update(collections or {})

    resolution = resolve(
        effect.result_spec,
        TargetContext(subject=entity, repo=repo, bindings=bindings,
                      collections=seeds, source=source, source_element=source_element),
    )
    for value in resolution.values:
        die = _die_from_spec_value(value)
        if die:
            return effect.model_copy(update={"result": die, "result_spec": None})
    return effect.model_copy(update={"result": None, "result_spec": None})


def _die_from_spec_value(value) -> str | None:
    """The die a resolved ``result_spec`` value names, if it names one."""
    raw = None
    if isinstance(value, dict):
        raw = value.get("rating") or value.get("die")
    if raw is None:
        raw = getattr(value, "rating", None) or getattr(value, "die", None)
    if raw is None and isinstance(value, str) and value[:1] == "d":
        raw = value  # a bare die value, e.g. an aggregate over a die field
    size = getattr(raw, "value", raw)
    return str(size) if size else None


def resolve_effect_owner(effect: Effect, entity_id: str, repo,
                         context: dict | None = None,
                         collections: dict | None = None) -> Effect:
    """Resolve ``effect.owner_spec`` to the ``(kind, id)`` the effect anchors to.

    The owner is *where what the effect makes lives*: the subject entity by
    default, a relationship edge for a tie to someone, or another trait instance
    for a facet of it. Only the first is implicit — the other two are facts you
    pick out of the world, so they travel as a path and land here.

    The pair is written into the effect **context** rather than onto two new
    domain fields: it is engine-resolved, not authored (the ``_``-prefixed
    convention ``_source`` already uses), and the handler is the only reader.

    A path that names nothing leaves the effect as authored, so the subject
    entity stays the owner — the same fail-open the other specs take, because
    "no owner path resolved" and "no owner path authored" are the same state.
    """
    if effect.owner_spec is None or not effect.owner_spec.steps:
        return effect
    from transversal.services.effects_applier.datatypes import (
        OWNER_ID_CONTEXT_KEY,
        SOURCE_CONTEXT_KEY, SOURCE_ELEMENT_CONTEXT_KEY,
    )
    from transversal.services.target_resolver import TargetContext, event_collections, resolve

    entity = repo.get_entity(entity_id) if repo is not None else None
    bindings = (context or {}).get(BINDINGS_CONTEXT_KEY) or {}
    source = (context or {}).get(SOURCE_CONTEXT_KEY)
    source_element = (context or {}).get(SOURCE_ELEMENT_CONTEXT_KEY)
    seeds = event_collections(context, getattr(source, "id", None), source_element)
    seeds.update(collections or {})

    resolution = resolve(
        effect.owner_spec,
        TargetContext(subject=entity, repo=repo, bindings=bindings,
                      collections=seeds, source=source, source_element=source_element),
    )
    for value in resolution.values:
        rid = value.get("id") if isinstance(value, dict) else getattr(value, "id", None)
        if not rid:
            continue
        # The *kind* is not guessed here: the action declares what this path may
        # land on (`owner_elements`), and the handler reads that declaration back.
        # One truth, so a value can never be interpreted as the wrong collection.
        return effect.model_copy(update={
            "owner_spec": None,
            "context": {
                **(effect.context or {}),
                OWNER_ID_CONTEXT_KEY: str(rid),
            },
        })
    return effect

def _resolve_entity_spec(effect: Effect, entity: Entity, repo, bindings: dict,
                         collections: dict | None = None,
                         source=None, source_element: str | None = None) -> Effect | None:
    """Resolve ``effect.entity_spec`` to a concrete id, or None if it resolves nothing.

    ``bindings`` is the activation scope (condition + earlier-effect outputs), so a
    path can pick up a variable a condition named — e.g. the d4 traits this roll
    matched, navigated on to their owning entities. ``source``/``source_element``
    are the activation's resolved source, without which a path that starts
    ``select source`` resolves to nobody (the same gap the immediate-target path
    had).
    """
    from transversal.services.target_resolver import TargetContext, resolve

    resolution = resolve(
        effect.entity_spec,
        TargetContext(subject=entity, repo=repo, bindings=bindings,
                      collections=dict(collections or {}),
                      source=source, source_element=source_element),
    )
    for value in resolution.values:
        rid = getattr(value, "id", None)
        if rid is None and isinstance(value, dict):
            rid = value.get("id") or value.get("ts_id")
        if rid:
            return effect.model_copy(update={"entity": rid, "entity_spec": None})
    return None
