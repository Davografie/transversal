"""Handlers traits — split out of src/api/src/transversal/services/effects_applier.py."""

from __future__ import annotations

from transversal.domain import Effect
from transversal.domain import Entity
from transversal.domain import TraitSetting
from transversal.services.trait_change import (
    TraitChangeError,
    repoint_trait_setting,
)
from transversal.services.trait_reveal import reveal_trait_to
from typing import Optional
from transversal.services.effects_applier.datatypes import (
    AppliedEffect,
    EffectsResult,
)
from transversal.services.effects_applier.reverts import (
    _queue_entity_revert,
    _queue_explicit,
    _queue_trait_revert,
)
from transversal.services.effects_applier.targeting import (
    _effect_subject,
    _resolve_target,
    _track_subject,
)
from transversal.services.effects_applier.trait_helpers import (
    _ctx,
    _die,
    _find_conflicting_traitsetting,
    _find_traitsetting_by_target,
    _has_steps,
    _new_traitsetting,
    _rating_type,
    _step_down_one,
    _step_up_trait,
    _steps,
    _trait_owner,
)


def _apply_gain(entity, effect, repo, result):
    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)
    target = _resolve_target(subject, effect, result, repo)
    if target is None:
        return
    owner = _trait_owner(subject, effect, repo)
    statement = _ctx(effect, "statement")
    if _find_conflicting_traitsetting(subject, effect, repo, target, statement):
        result.applied.append(AppliedEffect(effect, f"trait {target} already present"))
        return
    die = _die(effect.result)
    ts = _new_traitsetting(owner, target, die, repo, negative=bool(effect.negative),
                           rating_type=_rating_type(effect), statement=statement, notes=_ctx(effect, "notes"))
    result.new_trait_settings.append(ts)
    result.applied.append(AppliedEffect(effect, f"gained {target} at {die.value}", ts.id))
    _queue_entity_revert(repo, subject, effect, target=target)

def _replicate_traitsetting(src: TraitSetting, subject: Entity, repo, effect: Effect,
                            result: EffectsResult, *, carry_grants: bool = False) -> Optional[TraitSetting]:
    """The instance ``src`` becomes on ``subject``, or ``None`` when refused.

    Shared by copy and move: both re-anchor an instance to another entity, and
    both honour the recipient's trait-set rules — a set that forbids duplicates
    refuses outright, a set that allows them refuses only a same-statement
    instance (statement is what distinguishes duplicates). ``carry_grants`` is
    for a *move*, where the instance keeps its SFX grants, spent dice and
    visibility: it is the same trait changing hands, not a fresh one.
    """
    get_traitset = getattr(repo, "get_traitset_by_id", None)
    traitset = get_traitset(src.traitset_id) if src.traitset_id and get_traitset else None
    allow_duplicates = bool(getattr(traitset, "allow_duplicates", False))
    if repo.find_traitsetting_collision(subject.id, src.trait_id, src.statement, allow_duplicates):
        result.applied.append(
            AppliedEffect(effect, f"{subject.name or subject.id} already has {src.trait_id}"))
        return None
    ts = TraitSetting(
        id=repo.resolve_traitsetting_id(subject.id, src.trait_id, src.statement, allow_duplicates),
        entity_id=subject.id,
        trait_id=src.trait_id,
        traitset_id=src.traitset_id,
        rating_type=src.rating_type,
        dice=list(src.dice),
        capacity=list(src.capacity) if src.capacity else None,
        polarity=src.polarity,
        statement=src.statement,
        notes=src.notes,
        tags=list(src.tags),
    )
    if carry_grants:
        ts.sfx_ids = list(src.sfx_ids)
        ts.enabled = src.enabled
        ts.spent_dice = list(src.spent_dice)
        ts.known_to = list(src.known_to)
    return ts

def _apply_copy_trait(entity, effect, repo, result):
    """Give the subject a copy of another trait instance (teach / gift).

    The copy carries the *instance*: its dice, rating type, polarity, statement
    and notes. Teaching hands over what the teacher has, not the trait's default
    — which is the whole point, and why this is its own action rather than a
    `gain` whose fields someone had to keep in sync by hand.

    Anchored to the recipient entity rather than mirroring the source's
    projection anchor, and left without ``sfx_ids`` so the repo seeds the
    trait's default grants when it creates the instance.
    """
    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)
    ref = (effect.refs or {}).get("trait")
    src_id = (getattr(ref, "value", "") or "") if ref else ""
    src = repo.get_traitsetting(src_id) if src_id else None
    if src is None:
        result.applied.append(AppliedEffect(effect, f"no trait instance to copy ({src_id or 'unset'})"))
        return
    ts = _replicate_traitsetting(src, subject, repo, effect, result)
    if ts is None:
        return
    result.new_trait_settings.append(ts)
    result.applied.append(AppliedEffect(effect, f"copied {src.trait_id} to {subject.id}", ts.id))

def _apply_change_trait(entity, effect, repo, result):
    """Point a trait instance at a different registry trait.

    The repointing itself lives in :func:`transversal.services.trait_change.
    repoint_trait_setting`, shared with the sheet's trait editor so the two cannot
    drift: the instance keeps everything that is *its own* — its owner, dice,
    rating type, polarity, statement, notes and grants — and changes what it **is**.
    The Arango registry pointer (``_to``) is not touched here: the repository derives
    it from ``trait_id`` on every write (``trait_settings.update_traitsetting``), so
    committing the updated instance rewrites the pointer itself.  The instance's set
    follows the new definition for the same reason it does there.

    The undo is this action pointed back at the prior definition: the handler
    captures it on apply (``prior_result``) and the revert carries it in ``result``,
    which is why the definition is read from the reference *or* from ``result``.
    With a duration that revert is scheduled on the timer; without one it is booked
    as a hold inside a cancelable activation — the same two paths `set` uses.
    """
    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)
    target = _resolve_target(subject, effect, result, repo)
    if target is None:
        return
    existing = _find_traitsetting_by_target(subject, effect, repo, target)
    if existing is None:
        result.applied.append(AppliedEffect(effect, f"no trait instance {target} to change"))
        return

    ref = (effect.refs or {}).get("trait")
    # The Change To *reference* is the author's answer; a revert has no reference
    # and carries the definition it restores in `result` instead.
    wanted_id = (getattr(ref, "value", "") or "") if ref else ""
    wanted_id = wanted_id or (effect.result or "")

    # A refused change (the container rule, a collision) must not abort the rest of
    # the activation: like the "already that trait" case below, it is reported and
    # the remaining effects still apply.
    try:
        change = repoint_trait_setting(existing, wanted_id, repo)
    except TraitChangeError as exc:
        result.applied.append(AppliedEffect(effect, str(exc)))
        return

    if not change.changed:
        detail = (f"no trait definition to change to ({wanted_id or 'unset'})"
                  if change.reason == "missing" else f"{target} is already {wanted_id}")
        result.applied.append(AppliedEffect(effect, detail))
        return

    was = change.was_trait_id
    result.updated_trait_settings.append(existing)
    result.applied.append(AppliedEffect(effect, f"changed {was} into {change.is_trait_id}", existing.id))
    # Addressed to the instance: the authored target may be a registry trait id,
    # which no longer names this instance once the pointer has moved.
    _queue_trait_revert(repo, existing, effect, target=existing.id, prior_result=was)


def _apply_move_trait(entity, effect, repo, result):
    """Take a trait instance from another entity and give it to this one (steal).

    The instance keeps its dice, grants, spent dice and visibility — it is the
    same trait changing hands. A trait setting's id is keyed to its owner
    (``{entity}:{trait}``), so a move is a create on the recipient plus a delete
    of the source, not a field edit.
    """
    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)
    ref = (effect.refs or {}).get("trait")
    src_id = (getattr(ref, "value", "") or "") if ref else ""
    src = repo.get_traitsetting(src_id) if src_id else None
    if src is None:
        result.applied.append(AppliedEffect(effect, f"no trait instance to move ({src_id or 'unset'})"))
        return
    if src.entity_id == subject.id:
        result.applied.append(AppliedEffect(effect, f"{src.trait_id} is already on {subject.id}"))
        return
    ts = _replicate_traitsetting(src, subject, repo, effect, result, carry_grants=True)
    if ts is None:
        return
    result.new_trait_settings.append(ts)
    result.removed_trait_settings.append(src)
    result.applied.append(
        AppliedEffect(effect, f"moved {src.trait_id} from {src.entity_id} to {subject.id}", ts.id))

def _apply_gain_or_step_up(entity, effect, repo, result):
    """Create at ``result`` if absent, then step up; or step up an existing trait.

    Without an explicit ``steps`` this preserves the historical behavior (create
    at ``result``, or step up once). With ``steps`` set, both paths step up that
    many times — ``result`` is then the base die (e.g. d4 + ``steps``).
    """
    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)
    target = _resolve_target(subject, effect, result, repo)
    if target is None:
        return
    owner = _trait_owner(subject, effect, repo)
    statement = _ctx(effect, "statement")
    existing = _find_conflicting_traitsetting(subject, effect, repo, target, statement)
    steps = _steps(effect)
    if existing:
        if _step_up_trait(subject, existing, target, effect, result, repo, steps=steps):
            result.updated_trait_settings.append(existing)
            result.applied.append(AppliedEffect(effect, f"stepped up {target}", existing.id))
            _queue_explicit(repo, existing, effect, "step_down", target)
            _maybe_complete_challenge(existing, subject)
        return
    die = _die(effect.result)
    ts = _new_traitsetting(owner, target, die, repo, negative=bool(effect.negative),
                           rating_type=_rating_type(effect), statement=statement, notes=_ctx(effect, "notes"))
    if _has_steps(effect):
        _step_up_trait(subject, ts, target, effect, result, repo, steps=steps)
    result.new_trait_settings.append(ts)
    final_die = ts.dice[0] if ts.dice else die
    result.applied.append(AppliedEffect(effect, f"gained {target} at {final_die.value}", ts.id))
    _queue_explicit(repo, subject, effect, "remove", target)

def _apply_cortex_gain(entity, effect, repo, result):
    """Cortex-style trait application: create at the effect die if absent.

    If the trait already exists, compare the effect die against the current
    rating: a higher effect die jumps the rating straight up to it (d8→d12 is
    legal); otherwise step up one step.  Polarity comes from ``effect.negative``
    (only used when the trait is first created).
    """
    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)
    target = _resolve_target(subject, effect, result, repo)
    if target is None:
        return
    owner = _trait_owner(subject, effect, repo)
    die = _die(effect.result)
    negative = bool(effect.negative)
    statement = _ctx(effect, "statement")
    existing = _find_conflicting_traitsetting(subject, effect, repo, target, statement)
    if existing:
        if not existing.dice:
            existing.dice = [die]
            result.updated_trait_settings.append(existing)
            result.applied.append(AppliedEffect(effect, f"gained {target} at {die.value}", existing.id))
            return
        # Single-die rating assumption (Cortex traits/complications); choosing
        # one die from a multi-die rating is deferred.
        rating = existing.dice[0]
        if die.max_value > rating.max_value:
            existing.dice = [die]
            result.updated_trait_settings.append(existing)
            result.applied.append(AppliedEffect(effect, f"{target} jumped to {die.value}", existing.id))
        elif _step_up_trait(subject, existing, target, effect, result, repo):
            result.updated_trait_settings.append(existing)
            result.applied.append(AppliedEffect(effect, f"stepped up {target}", existing.id))
        return
    ts = _new_traitsetting(owner, target, die, repo, negative=negative,
                           rating_type=_rating_type(effect), statement=statement, notes=_ctx(effect, "notes"))
    result.new_trait_settings.append(ts)
    result.applied.append(AppliedEffect(effect, f"gained {target} at {die.value}", ts.id))

def _apply_step_up(entity, effect, repo, result):
    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)
    target = _resolve_target(subject, effect, result, repo)
    if target is None:
        return
    existing = _find_traitsetting_by_target(subject, effect, repo, target)
    if not existing:
        result.applied.append(AppliedEffect(effect, f"no trait {target} to step up"))
        return
    if _step_up_trait(subject, existing, target, effect, result, repo, steps=_steps(effect)):
        result.updated_trait_settings.append(existing)
        result.applied.append(AppliedEffect(effect, f"stepped up {target}", existing.id))
        _queue_trait_revert(repo, existing, effect)
        _maybe_complete_challenge(existing, subject)

def _apply_step_down(entity, effect, repo, result):
    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)
    target = _resolve_target(subject, effect, result, repo)
    if target is None:
        return
    existing = _find_traitsetting_by_target(subject, effect, repo, target)
    if not existing:
        result.applied.append(AppliedEffect(effect, f"no trait {target} to step down"))
        return
    for _ in range(_steps(effect)):
        status = _step_down_one(existing)
        if status == "stepped":
            continue
        result.applied.append(AppliedEffect(effect, f"{target} has no dice to step down"))
        return
    result.updated_trait_settings.append(existing)
    result.applied.append(AppliedEffect(effect, f"stepped down {target}", existing.id))
    _queue_trait_revert(repo, existing, effect)

def _maybe_complete_challenge(ts: TraitSetting, subject: Entity) -> None:
    """Fire the completion event when a positive challenge reaches capacity."""
    from transversal.services.challenge_pools import fire_challenge_completed
    universe = subject.current_universe if subject else ""
    fire_challenge_completed(ts, universe)

def _apply_discover(entity, effect, repo, result):
    target = _resolve_target(entity, effect, result, repo)
    if target is None:
        return
    if entity.discovered_life_paths is None:
        entity.discovered_life_paths = []
    if target not in entity.discovered_life_paths:
        entity.discovered_life_paths.append(target)
        result.applied.append(AppliedEffect(effect, f"discovered life path {target}"))
    else:
        result.applied.append(AppliedEffect(effect, f"life path {target} already discovered"))

def _apply_remove(entity, effect, repo, result):
    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)
    target = _resolve_target(subject, effect, result, repo)
    if target is None:
        return
    existing = _find_traitsetting_by_target(subject, effect, repo, target)
    if not existing:
        result.applied.append(AppliedEffect(effect, f"no trait {target} to remove"))
        return
    result.removed_trait_settings.append(existing)
    result.applied.append(AppliedEffect(effect, f"removed {target}", existing.id))

def _resolve_learner(entity: Entity, effect: Effect, result: EffectsResult) -> Optional[str]:
    """Resolve who learns a revealed trait.

    ``effect.context.learner`` defaults to ``"self"`` (the entity the effect
    is applied to — the activating entity for a manual SFX). A literal entity id
    passes through; a ``{token}`` does not, because a learner chosen at fire time
    would have to be a targeting path (the owner entity is the intended dynamic
    piece for spying).
    """
    learner = (effect.context or {}).get("learner") or "self"
    learner = (learner or "").strip()
    if learner in ("", "self"):
        return entity.id
    if learner.startswith("{") and learner.endswith("}"):
        result.applied.append(AppliedEffect(effect, f"learner token not supported: {learner}"))
        return None
    return learner

def _apply_reveal(entity, effect, repo, result):
    """Add the learner to a trait setting's ``known_to`` (fog of war)."""
    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)
    target = _resolve_target(subject, effect, result, repo)
    if target is None:
        return
    ts = _find_traitsetting_by_target(subject, effect, repo, target)
    if ts is None:
        result.applied.append(AppliedEffect(effect, f"no trait {target} to reveal"))
        return
    learner = _resolve_learner(entity, effect, result)
    if learner is None:
        return
    if reveal_trait_to(ts, learner):
        result.revealed.append((ts, learner))
        result.applied.append(AppliedEffect(effect, f"revealed {target} to {learner}", ts.id))
    else:
        result.applied.append(AppliedEffect(effect, f"{learner} already knows {target}"))
