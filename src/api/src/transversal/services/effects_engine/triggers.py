"""Which triggers an event could match — the availability prefilter's map.

``EffectsEngine._trigger_matches`` decides whether an SFX fires, one SFX at a
time, *after* every candidate has been read from the database. This module
answers the cheaper, coarser question a caller can ask first: for an event of
this type, which triggers are even in play? A candidate whose trigger is not in
the set cannot match, so it never needs loading or evaluating.

The map is deliberately a **superset**: it must never exclude a trigger that
``_trigger_matches`` could accept, or an SFX would silently stop firing. That
property is pinned by a test which brute-forces every declared trigger against
every event type and compares the two
(``tests/test_effect_triggers.py``) — so this table cannot drift from the
matching itself.

Unknown event types return ``None`` (no prefilter), so a new event type is
merely unfiltered rather than broken.
"""

from __future__ import annotations

# Direct matches: an event whose type *is* the trigger name. ``_trigger_matches``
# also maps a handful of event types onto a differently-named trigger (below).
_DIRECT_EVENTS: dict[str, frozenset[str]] = {
    "manual": frozenset({"manual", "on_activate"}),
    "trait_updated": frozenset({"on_trait_change"}),
    "trait_learned": frozenset({"on_trait_learn"}),
    "trait_offered": frozenset({"on_trait_offered"}),
    "relationship_created": frozenset({"on_relationship_create"}),
    "character_created": frozenset({"on_character_create"}),
    "projection_created": frozenset({"on_projection_create"}),
    "challenge_completed": frozenset({"on_challenge_completed"}),
    "location_changed": frozenset({"on_location_change"}),
    "pool_changed": frozenset({"on_pool_change"}),
    "beat": frozenset({"on_beat"}),
    "scene": frozenset({"on_scene"}),
    "session_start": frozenset({"on_session_start"}),
    "session_end": frozenset({"on_session_end"}),
}

# Roll events: the direct trigger plus the ones derived from a roll's result
# (a hitch, a botch, a tier). The result decides whether they actually fire, but
# all of them must survive the prefilter for the engine to get the chance.
_ROLL_TRIGGERS = frozenset({"on_roll", "on_complication", "on_botch", "on_success", "on_failure"})
_ROLL_EVENTS = ("on_roll", "on_result", "on_set")

# A contest event carries the winner in its context and is matched by either
# side's trigger.
_CONTEST_TRIGGERS = frozenset({"on_contest_win", "on_contest_loss", "on_contest"})


def triggers_for_event(event_type: str, *, has_roll: bool = False,
                       has_contest: bool = False) -> frozenset[str] | None:
    """The triggers an event of ``event_type`` could match, or ``None``.

    The two flags describe the event's *payload*, because that is what the
    matching reads for some triggers: a hitch/botch/tier comes from a
    ``roll_result``, and a contest win/loss from ``context["contest_winner"]``.
    Either can therefore match an event of *any* type that carries one. State
    events carry neither, which is why they can be narrowed hardest.

    ``None`` means "unknown event type, don't prefilter" — the caller must treat
    it as unrestricted.
    """
    if not event_type:
        return None
    if event_type in _ROLL_EVENTS:
        base, has_roll = _ROLL_TRIGGERS | {event_type}, True
    elif event_type == "contest":
        base, has_contest = _CONTEST_TRIGGERS, True
    elif event_type in _DIRECT_EVENTS:
        base = _DIRECT_EVENTS[event_type] | {event_type}
    else:
        return None
    if has_roll:
        base = base | _ROLL_TRIGGERS
    if has_contest:
        base = base | _CONTEST_TRIGGERS
    return base
