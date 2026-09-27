"""Entry — split out of src/api/src/transversal/services/effects_applier.py."""

from __future__ import annotations

from transversal.domain import Effect
from transversal.domain import Entity
from transversal.services.conditions import evaluate_conditions
from transversal.services.effects_applier.datatypes import (
    AppliedEffect,
    PendingChoice,
    PendingBranch,
    BINDINGS_CONTEXT_KEY,
    EffectsResult,
)
from transversal.services.effects_applier.handlers_client import (
    _apply_open_sheet,
    _apply_toast,
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
    _apply_start_contest,
    _apply_step_up_effect,
    _apply_step_up_outcome,
)
from transversal.services.effects_applier.handlers_sfx import (
    _apply_grant_sfx,
)
from transversal.services.effects_applier.handlers_traits import (
    _apply_set_statement,
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
    _apply_set_rating_type,
    _apply_step_down,
    _apply_step_up,
)
from transversal.services.effects_applier.handlers_world import (
    _apply_clear_destination,
    _apply_learn,
    _apply_cancel_scheduled_event,
    _apply_create_projection,
    _apply_relationship_create,
    _apply_restore_projection,
    _apply_set_destination,
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
    ("modify_trait", "set_statement"): _apply_set_statement,
    ("modify_trait", "add_die"): _apply_add_die,
    ("modify_trait", "copy"): _apply_copy_trait,
    ("modify_trait", "move"): _apply_move_trait,
    ("modify_trait", "remove_die"): _apply_remove_die,
    ("modify_trait", "reduce_by_effect"): _apply_reduce_by_effect,
    ("modify_trait", "increase_by_effect"): _apply_increase_by_effect,
    ("modify_trait", "set"): _apply_set,
    ("modify_trait", "set_polarity"): _apply_set_polarity,
    ("modify_trait", "set_rating_type"): _apply_set_rating_type,
    ("modify_trait", "disable"): _apply_disable,
    ("modify_trait", "enable"): _apply_enable,
    ("modify_trait", "toggle"): _apply_toggle,
    ("entity", "cancel_scheduled_event"): _apply_cancel_scheduled_event,
    # Granting a rule to an owner (the teacher case) — see handlers_sfx.
    ("sfx", "grant"): _apply_grant_sfx,
    ("projection", "create"): _apply_create_projection,
    ("projection", "restore"): _apply_restore_projection,
    ("modify_traitset", "set_limit"): _apply_set_traitset_limit,
    # Directions: set them, and the inverse that ends them ([[Guided Route]]).
    ("set_destination", "set"): _apply_set_destination,
    ("set_destination", "clear"): _apply_clear_destination,
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
    # Starting a contest — the missing half of the contest vocabulary (B105).
    ("contest", "start"): _apply_start_contest,
    # Fog of war: the subject learns the resolved targets (B121).
    ("entity", "learn"): _apply_learn,
    # Client-directed, no world change (B132).
    ("client", "open_sheet"): _apply_open_sheet,
    ("client", "toast"): _apply_toast,
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
        # A ``{name}`` in a flat field resolves from the activation scope here too.
        # The engine's own paths substitute before dispatch, but this entry point is
        # reached directly — a roll-table entry's effects, a life-path consequence —
        # and without this a scope name worked in a *path* (the resolver's
        # `_bound_value`) but silently did nothing in a field like ``result``.
        if bindings:
            from transversal.services.effects_engine.refs import _substitute_effect_context

            effect = _substitute_effect_context(effect, context or {}, bindings)
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
        # A **choice node** is asked, never applied: it reports its options and the
        # work stops there for this effect (the caller presents them and resumes
        # with `resolve_branch_effects`). An authored branch with no options is a
        # defect, and says so rather than passing silently.
        if _is_branch(effect):
            options = branch_options(effect)
            if options:
                result.pending_branches.append(PendingBranch(effect=effect, options=options))
            else:
                result.applied.append(AppliedEffect(effect, "a choice with no options"))
            continue
        handler = _MUTATION_HANDLERS.get((effect.type, effect.action))
        if handler is None:
            result.passthrough.append(effect)
            continue
        handler(entity, effect, repo, result)
    return result


def _is_branch(effect: Effect) -> bool:
    return effect.type == "branch"


def branch_options(effect: Effect) -> list[tuple[str, str]]:
    """``(id, label)`` per option — what a picker presents.

    The id is the option's own when authored, else its position (1-based, so an
    early hand-written branch means the same thing); an unlabelled option reads as
    "Option N" rather than a blank button.
    """
    out: list[tuple[str, str]] = []
    for index, branch in enumerate(effect.branches or [], start=1):
        option_id = (getattr(branch, "id", "") or "").strip() or str(index)
        label = (getattr(branch, "label", "") or "").strip() or f"Option {index}"
        out.append((option_id, label))
    return out


def resolve_branch_effects(effect: Effect, option_id: str) -> list[Effect]:
    """The effects an answer runs: the chosen option's list, or nothing.

    Resolution is by the option's id, by its 1-based position, or by its label —
    a picker sends whichever it has, and a label is what a client most often has.
    An answer that names no option yields nothing, which is the honest reading of
    "the choice was not made" (the caller decides whether that is a default).
    """
    wanted = str(option_id or "").strip()
    if not wanted:
        return []
    for index, (oid, label) in enumerate(branch_options(effect), start=1):
        if wanted in (oid, str(index), label):
            return list((effect.branches or [])[index - 1].effects or [])
    return []

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
                          collections: dict | None = None,
                          pending_out: list | None = None) -> Effect:
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
                                    source=source, source_element=source_element,
                                    pending_out=pending_out)
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


#: The ladder's sizes, as the numbers a die-typed field reads back as.
_DIE_SIZES = frozenset({4, 6, 8, 10, 12})


def _die_from_spec_value(value) -> str | None:
    """The die a resolved ``result_spec`` value names, if it names one.

    A die-typed field read through the resolver arrives as its **size**, not its
    name — ``aggregate max effect_die`` over a roll yields ``8`` — and an int was
    refused here, so "create the hazard at that die's effect die" ([[B98]]) could
    not be written even though the path resolved the right number. A size on the
    ladder *is* the die, so it is named back; anything else (a card value, a count
    of 3) still names no die, which is what keeps a wrong path from inventing one.
    """
    raw = None
    if isinstance(value, dict):
        raw = value.get("rating") or value.get("die")
    else:
        raw = getattr(value, "rating", None) or getattr(value, "die", None)
        if raw is None and isinstance(value, (str, int, float)):
            # The value *is* the die: a bare name ("d8"), or the size a die-typed
            # field reads back as (8).
            raw = value
    if raw is None:
        return None
    size = getattr(raw, "value", raw)
    if size is None:
        return None
    try:
        number = int(size)
    except (TypeError, ValueError):
        return str(size)
    return f"d{number}" if number in _DIE_SIZES else None


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
        OWNER_KIND_CONTEXT_KEY,
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
        # The *kind* travels with the id: the path landed on a specific element —
        # an edge, a trait instance, a body — and that is what the anchor is. The
        # action still declares what it may land on (`owner_elements`), and
        # ``_trait_owner`` refuses a kind outside that declaration, so one truth
        # is kept without guessing.
        landing = resolution.trace[-1] if resolution.trace else None
        kind = getattr(landing, "element", "") or ""
        return effect.model_copy(update={
            "owner_spec": None,
            "context": {
                **(effect.context or {}),
                OWNER_ID_CONTEXT_KEY: str(rid),
                **({OWNER_KIND_CONTEXT_KEY: kind} if kind else {}),
            },
        })
    return effect

def _spec_value_id(value) -> str:
    """The id a resolved spec value names, whichever shape it arrived in."""
    rid = getattr(value, "id", None)
    if rid is None and isinstance(value, dict):
        rid = value.get("id") or value.get("ts_id")
    return rid or ""


def _resolve_entity_spec(effect: Effect, entity: Entity, repo, bindings: dict,
                         collections: dict | None = None,
                         source=None, source_element: str | None = None,
                         pending_out: list | None = None) -> Effect | None:
    """Resolve ``effect.entity_spec`` to a concrete id, or None if it resolves nothing.

    ``bindings`` is the activation scope (condition + earlier-effect outputs), so a
    path can pick up a variable a condition named — e.g. the d4 traits this roll
    matched, navigated on to their owning entities. ``source``/``source_element``
    are the activation's resolved source, without which a path that starts
    ``select source`` resolves to nobody (the same gap the immediate-target path
    had).

    A ``choose`` step stops the path *before* it names anyone — it returns a
    question and an empty value list. Two things follow, and both used to be
    wrong here: **nothing to choose between is not a question** (one candidate, or
    exactly as many as the step wants, is simply taken), and a real decision is
    **reported** through ``pending_out`` rather than dropped, so its caller can put
    it to the table instead of applying the effect to nobody.
    """
    from transversal.services.target_resolver import TargetContext, resolve

    resolution = resolve(
        effect.entity_spec,
        TargetContext(subject=entity, repo=repo, bindings=bindings,
                      collections=dict(collections or {}),
                      source=source, source_element=source_element),
    )
    if resolution.pending_choices:
        if all(len(pc.candidates) <= pc.count for pc in resolution.pending_choices):
            for pc in resolution.pending_choices:
                for candidate in pc.candidates:
                    rid = _spec_value_id(candidate)
                    if rid:
                        return effect.model_copy(update={"entity": rid, "entity_spec": None})
        if pending_out is not None:
            pending_out.extend(resolution.pending_choices)
        # No channel to ask through (an older caller): leave the effect as authored
        # so the existing "resolved to nothing" report still fires.
        return None
    for value in resolution.values:
        rid = _spec_value_id(value)
        if rid:
            return effect.model_copy(update={"entity": rid, "entity_spec": None})
    return None
