"""Handlers economy — split out of src/api/src/transversal/services/effects_applier.py."""

from __future__ import annotations

from transversal.services.effects_applier.datatypes import (
    AppliedEffect,
)
from transversal.services.effects_applier.targeting import (
    _effect_subject,
    _resolve_target,
    _track_subject,
)


def _apply_earn(entity, effect, repo, result):
    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)
    amount = int(effect.result or "0")
    subject.razmerit += amount
    result.applied.append(AppliedEffect(effect, f"earned {amount} razmerit"))
    # A gain is refundable until the activation commits (the take-back pays it back).
    from transversal.services.effects_applier.reverts import book_undo
    book_undo(repo, subject.id, effect)

def _apply_spend(entity, effect, repo, result):
    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)
    amount = int(effect.result or "0")
    subject.razmerit -= amount
    result.applied.append(AppliedEffect(effect, f"spent {amount} razmerit"))
    # A cost is refundable until the activation commits.
    from transversal.services.effects_applier.reverts import book_undo
    book_undo(repo, subject.id, effect)

def _apply_transfer(entity, effect, repo, result):
    target = _resolve_target(entity, effect, result, repo)
    if target is None:
        return
    amount = int(effect.result or "0")
    recipient = repo.get_entity(target)
    if recipient is None:
        result.applied.append(AppliedEffect(effect, f"transfer target {target} not found"))
        return
    entity.razmerit -= amount
    recipient.razmerit += amount
    result.entities_to_update.append(recipient)
    result.applied.append(AppliedEffect(effect, f"transferred {amount} razmerit to {target}"))
