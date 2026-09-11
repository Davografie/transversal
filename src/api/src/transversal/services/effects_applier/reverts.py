"""Reverts — split out of src/api/src/transversal/services/effects_applier.py."""




def _queue_trait_revert(repo, ts, effect, prior_result=None):
    """Schedule the inverse of ``effect`` on a trait setting in the central store."""
    from transversal.services.scheduled_events import schedule_revert

    schedule_revert(repo, "trait_setting", ts.id, effect, prior_result=prior_result)

def _queue_entity_revert(repo, entity, effect, target=None, prior_result=None):
    """Schedule the inverse of ``effect`` on an entity in the central store."""
    from transversal.services.scheduled_events import schedule_revert

    schedule_revert(repo, "entity", entity.id, effect, target=target, prior_result=prior_result)

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
