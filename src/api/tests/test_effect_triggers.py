"""The event→trigger map must stay a superset of the engine's own matching.

``triggers_for_event`` lets a caller drop candidates that cannot match an event
before reading them. If it were ever *narrower* than ``_trigger_matches``, an
SFX would silently stop firing — so this brute-forces every declared trigger
against every event type and compares the two directly.
"""

import pytest

from transversal.domain import OutcomeTier
from transversal.services.effects_engine import EffectsEngine, GameEvent
from transversal.services.effects_engine.triggers import triggers_for_event
from transversal.services.menu_contexts import TRIGGERS

EVENT_TYPES = [
    "manual", "on_roll", "on_result", "on_set", "contest", "location_changed",
    "trait_updated", "trait_learned", "trait_offered", "relationship_created",
    "character_created", "projection_created", "challenge_completed",
    "beat", "scene", "session_start", "session_end", "pool_changed",
]


class _Roll:
    hitches = []
    botch = False
    tier = OutcomeTier.SUCCESS


class _BotchRoll:
    hitches = []
    botch = True
    tier = OutcomeTier.FAIL


def _events():
    """One event per type: bare (a state event), then with a roll attached.

    The roll flavour matters — the roll-derived triggers are matched from the
    payload, so an event carrying a roll could match them whatever its type.
    """
    for et in EVENT_TYPES:
        for roll, ctx in ((None, {"contest_winner": "player"}),
                          (_Roll(), {"contest_winner": "player"}),
                          (_BotchRoll(), {"contest_winner": "opponent"})):
            yield et, GameEvent(
                type=et, entity_id="e1", universe="earth",
                context=dict(ctx), roll_result=roll)


def test_the_map_is_a_superset_of_the_engine_matching():
    engine = EffectsEngine()
    for et, event in _events():
        allowed = triggers_for_event(
            et,
            has_roll=event.roll_result is not None,
            has_contest="contest_winner" in (event.context or {}),
        )
        for declared in TRIGGERS:
            matched = engine._trigger_matches(_sfx(declared.value), event)
            if not matched:
                continue
            assert allowed is not None, f"{et}: matched {declared.value} but the map is None"
            assert declared.value in allowed, (
                f"event {et} can match trigger {declared.value!r}, "
                f"but triggers_for_event omits it — an SFX could be filtered out "
                f"before it ever fires"
            )


def test_an_unknown_event_type_is_not_narrowed():
    assert triggers_for_event("something_new") is None
    assert triggers_for_event("") is None


def test_roll_events_keep_every_derived_trigger():
    for et in ("on_roll", "on_result", "on_set"):
        allowed = triggers_for_event(et, has_roll=True)
        assert {"on_complication", "on_botch", "on_success", "on_failure"} <= allowed


def _sfx(trigger):
    from types import SimpleNamespace

    return SimpleNamespace(id=f"sfx-{trigger}", trigger=trigger, conditions=[])
