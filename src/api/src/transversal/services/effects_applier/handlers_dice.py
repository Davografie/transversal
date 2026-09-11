"""Handlers dice — split out of src/api/src/transversal/services/effects_applier.py."""

from transversal.domain import DieType
from transversal.domain import Polarity
from transversal.domain import RatingType
from transversal.services.effects_applier.datatypes import (
    AppliedEffect,
)
from transversal.services.effects_applier.handlers_traits import (
    _maybe_complete_challenge,
)
from transversal.services.effects_applier.reverts import (
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
    _die_opt,
    _find_traitsetting_by_target,
    _new_traitsetting,
    _rating_type,
    _step_down_one,
    _step_up_trait,
    _steps,
    _trait_owner,
)


def _apply_add_die(entity, effect, repo, result):
    """Add a die to a trait setting's rating (any rating type).

    Appends ``effect.result`` (a die size, e.g. ``d6``) to the trait setting's
    ``dice`` list. Static/resource/challenge ratings are all a ``dice`` list, so
    this is type-agnostic; the duration revert removes the same die. A positive
    challenge pool is bounded by its ``capacity`` (the completion target).

    When the subject has no such trait yet this **seeds** it — that is how a
    resource trait accumulates (Crimson Scars: one hazard trait per location,
    one die per unchosen die). The revert deletes what it made, so a
    scene-scoped grant leaves nothing behind.

    ``effect.result`` may be a substituted variable, and must be a real die: a
    die whose tier has no effect die (a fail) substitutes empty, and adding
    silently as a d4 would invent a hazard the roll did not earn.
    """
    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)
    target = _resolve_target(subject, effect, result, "trait", repo)
    if target is None:
        return
    die = _die_opt(effect.result)
    if die is None:
        result.applied.append(AppliedEffect(effect, f"no die rating to add ({effect.result!r})"))
        return
    existing = _find_traitsetting_by_target(subject, effect, repo, target)
    if not existing:
        ts = _new_traitsetting(
            _trait_owner(subject, effect, repo), target, die, repo,
            negative=bool(effect.negative),
            rating_type=_rating_type(effect),
            statement=_ctx(effect, "statement"),
            notes=_ctx(effect, "notes"),
        )
        result.new_trait_settings.append(ts)
        result.applied.append(AppliedEffect(effect, f"gained {target} at {die.value}", ts.id))
        _queue_explicit(repo, subject, effect, "remove", target)
        return
    if (
        existing.rating_type == RatingType.CHALLENGE
        and existing.polarity == Polarity.POSITIVE
        and existing.capacity
        and len(existing.dice) >= len(existing.capacity)
    ):
        result.applied.append(AppliedEffect(effect, f"{target} is already at capacity"))
        return
    existing.dice.append(die)
    result.updated_trait_settings.append(existing)
    result.applied.append(AppliedEffect(effect, f"added {die.value} to {target}", existing.id))
    _queue_trait_revert(repo, existing, effect)
    _maybe_complete_challenge(existing, subject)

def _apply_remove_die(entity, effect, repo, result):
    """Remove a die from a trait setting's rating (any rating type).

    Removes the first die matching ``effect.result`` from the trait setting's
    ``dice`` list. The duration revert re-adds the same die.
    """
    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)
    target = _resolve_target(subject, effect, result, "trait", repo)
    if target is None:
        return
    existing = _find_traitsetting_by_target(subject, effect, repo, target)
    if not existing or not existing.dice:
        result.applied.append(AppliedEffect(effect, f"no trait {target} to remove a die from"))
        return
    die = _die(effect.result)
    for i, d in enumerate(existing.dice):
        if d == die:
            existing.dice.pop(i)
            break
    else:
        result.applied.append(AppliedEffect(effect, f"{target} has no {die.value} to remove"))
        return
    result.updated_trait_settings.append(existing)
    result.applied.append(AppliedEffect(effect, f"removed {die.value} from {target}", existing.id))
    _queue_trait_revert(repo, existing, effect)

def _apply_reduce_by_effect(entity, effect, repo, result):
    """Reduce a trait by the effect-die-vs-rating comparison.

    ``effect.context.effect_die`` is the winning effect die (``{effect_die}``
    substituted at fire time). If it is strictly larger than the trait's rating
    die the trait is removed; otherwise it steps down one step. Shared
    comparison via ``dice_resolver.compare_effect_die``.
    """
    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)
    target = _resolve_target(subject, effect, result, "trait", repo)
    if target is None:
        return
    existing = _find_traitsetting_by_target(subject, effect, repo, target)
    if not existing or not existing.dice:
        result.applied.append(AppliedEffect(effect, f"no trait {target} to reduce"))
        return

    raw_die = (effect.context or {}).get("effect_die")
    try:
        effect_die = DieType(str(raw_die).lower()) if raw_die else None
    except ValueError:
        effect_die = None
    if effect_die is None:
        result.applied.append(AppliedEffect(effect, "no effect die to compare"))
        return

    target_die = existing.dice[0]
    from transversal.services.dice_resolver import effect_die_beats
    if effect_die_beats(effect_die, target_die):
        result.removed_trait_settings.append(existing)
        result.applied.append(
            AppliedEffect(effect, f"removed {target} (effect die {effect_die.value} beats {target_die.value})", existing.id)
        )
    else:
        status = _step_down_one(existing)
        if status != "stepped":
            result.applied.append(AppliedEffect(effect, f"{target} has no dice to step down"))
            return
        result.updated_trait_settings.append(existing)
        result.applied.append(
            AppliedEffect(effect, f"stepped down {target} (effect die {effect_die.value} ≤ {target_die.value})", existing.id)
        )
        _queue_trait_revert(repo, existing, effect)

def _apply_increase_by_effect(entity, effect, repo, result):
    """Raise a trait by the effect-die-vs-rating comparison.

    The positive mirror of ``_apply_reduce_by_effect``: ``effect.context.effect_die``
    is the winning effect die (``{effect_die}`` substituted at fire time). If it is
    strictly larger than the trait's rating die the rating is *set* to it; equal or
    smaller, the trait steps up one step. Shared predicate via
    ``dice_resolver.effect_die_beats``.
    """
    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)
    target = _resolve_target(subject, effect, result, "trait", repo)
    if target is None:
        return
    existing = _find_traitsetting_by_target(subject, effect, repo, target)
    if not existing or not existing.dice:
        result.applied.append(AppliedEffect(effect, f"no trait {target} to increase"))
        return

    raw_die = (effect.context or {}).get("effect_die")
    try:
        effect_die = DieType(str(raw_die).lower()) if raw_die else None
    except ValueError:
        effect_die = None
    if effect_die is None:
        result.applied.append(AppliedEffect(effect, "no effect die to compare"))
        return

    target_die = existing.dice[0]
    from transversal.services.dice_resolver import effect_die_beats
    if effect_die_beats(effect_die, target_die):
        prior = target_die.value
        existing.dice = [effect_die]
        result.updated_trait_settings.append(existing)
        result.applied.append(
            AppliedEffect(effect, f"set {target} to {effect_die.value} (effect die {effect_die.value} beats {target_die.value})", existing.id)
        )
        _queue_trait_revert(repo, existing, effect, prior_result=prior)
        return

    # Equal or smaller: one step up. ``_step_up_trait`` reports its own refusal
    # (already at d12, a negative trait taken out) — don't double up on it.
    if not _step_up_trait(subject, existing, target, effect, result, repo, steps=_steps(effect)):
        return
    result.updated_trait_settings.append(existing)
    result.applied.append(
        AppliedEffect(effect, f"stepped up {target} (effect die {effect_die.value} ≤ {target_die.value})", existing.id)
    )
    _queue_trait_revert(repo, existing, effect)
    _maybe_complete_challenge(existing, subject)

def _apply_set(entity, effect, repo, result):
    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)
    target = _resolve_target(subject, effect, result, "trait", repo)
    if target is None:
        return
    existing = _find_traitsetting_by_target(subject, effect, repo, target)
    if not existing:
        result.applied.append(AppliedEffect(effect, f"no trait {target} to set"))
        return
    die = _die(effect.result)
    prior = existing.dice[0].value if existing.dice else None
    existing.dice = [die]
    result.updated_trait_settings.append(existing)
    result.applied.append(AppliedEffect(effect, f"set {target} to {die.value}", existing.id))
    _queue_trait_revert(repo, existing, effect, prior_result=prior)

def _apply_disable(entity, effect, repo, result):
    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)
    target = _resolve_target(subject, effect, result, "trait", repo)
    if target is None:
        return
    ts = _find_traitsetting_by_target(subject, effect, repo, target)
    if ts is None:
        result.applied.append(AppliedEffect(effect, f"no trait {target} to disable"))
        return
    if not ts.enabled:
        result.applied.append(AppliedEffect(effect, f"{target} already disabled"))
        return
    ts.enabled = False
    result.updated_trait_settings.append(ts)
    result.applied.append(AppliedEffect(effect, f"disabled {target}", ts.id))
    _queue_trait_revert(repo, ts, effect)

def _apply_enable(entity, effect, repo, result):
    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)
    target = _resolve_target(subject, effect, result, "trait", repo)
    if target is None:
        return
    ts = _find_traitsetting_by_target(subject, effect, repo, target)
    if ts is None:
        result.applied.append(AppliedEffect(effect, f"no trait {target} to enable"))
        return
    if ts.enabled:
        result.applied.append(AppliedEffect(effect, f"{target} already enabled"))
        return
    ts.enabled = True
    result.updated_trait_settings.append(ts)
    result.applied.append(AppliedEffect(effect, f"enabled {target}", ts.id))

def _apply_toggle(entity, effect, repo, result):
    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)
    target = _resolve_target(subject, effect, result, "trait", repo)
    if target is None:
        return
    ts = _find_traitsetting_by_target(subject, effect, repo, target)
    if ts is None:
        result.applied.append(AppliedEffect(effect, f"no trait {target} to toggle"))
        return
    ts.enabled = not ts.enabled
    result.updated_trait_settings.append(ts)
    state = "enabled" if ts.enabled else "disabled"
    result.applied.append(AppliedEffect(effect, f"toggled {target} → {state}", ts.id))
    _queue_trait_revert(repo, ts, effect)
