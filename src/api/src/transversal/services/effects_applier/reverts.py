"""Reverts — split out of src/api/src/transversal/services/effects_applier.py."""

from __future__ import annotations




def _queue_trait_revert(repo, ts, effect, prior_result=None, context_extra=None):
    """Schedule the inverse of ``effect`` on a trait setting in the central store."""
    from transversal.services.scheduled_events import schedule_revert

    schedule_revert(repo, "trait_setting", ts.id, effect, prior_result=prior_result,
                    context_extra=context_extra)

def _queue_entity_revert(repo, entity, effect, target=None, prior_result=None, context_extra=None):
    """Schedule the inverse of ``effect`` on an entity in the central store."""
    from transversal.services.scheduled_events import schedule_revert

    schedule_revert(repo, "entity", entity.id, effect, target=target,
                    prior_result=prior_result, context_extra=context_extra)


def book_undo(repo, entity_id: str, effect):
    """Book the undo of an applied effect against its subject entity.

    The one way in for economy effects: the registry's razmerit operations and the
    applier's earn/spend handlers both call it, so a cost is cancellable wherever
    it was applied. A no-op outside a cancelable activation (the booking context
    is what makes it a hold) and without a repo/entity.
    """
    if repo is None or not entity_id:
        return None
    entity = repo.get_entity(entity_id)
    if entity is None:
        return None
    return _queue_entity_revert(repo, entity, effect)

def _queue_explicit(repo, owner, effect, action, target):
    """Schedule an explicit inverse action (for compound actions like gain_or_step_up)."""
    if not effect.duration or not effect.duration.timers:
        return
    from transversal.domain import Effect as _Effect, EffectTiming as _ET
    from transversal.services.scheduled_events import schedule_event

    target_type = "trait_setting" if hasattr(owner, "trait_id") else "entity"
    schedule_event(
        repo, target_type, owner.id,
        _Effect(timing=_ET.IMMEDIATE, type="modify_trait", action=action, target=target),
        effect.duration.timers,
        effect.duration.combine,
    )
