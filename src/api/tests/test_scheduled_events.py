"""Tests for the central scheduled-events (timed revert) system."""

from transversal.domain import (
    Effect,
    EffectDuration,
    EffectTiming,
    Entity,
    EntityType,
    ScheduledEvent,
    Timer,
    TimerCombine,
    TraitSetting,
)
from transversal.services.effect_refs import target_value
from transversal.services.scheduled_events import (
    advance_scheduled_events,
    build_revert,
    dispatch_event,
    schedule_deferred,
    schedule_event,
    schedule_revert,
    timing_to_timer,
)


def _entity(entity_id="kael"):
    return Entity(
        id=entity_id,
        type=EntityType.CHARACTER,
        name=entity_id,
        current_universe="earth",
    )


class FakeRepo:
    def __init__(self, entities=(), traitsettings=()):
        self.events = []
        self.entities = {e.id: e for e in entities}
        self.traitsettings = {ts.id: ts for ts in traitsettings}

    def create_scheduled_event(self, event):
        self.events.append(event)
        return event

    def list_all_scheduled_events(self):
        return list(self.events)

    def update_scheduled_event(self, event):
        for i, e in enumerate(self.events):
            if e.id == event.id:
                self.events[i] = event
                return event
        return event

    def delete_scheduled_event(self, event_id):
        self.events = [e for e in self.events if e.id != event_id]
        return True

    def get_entity(self, entity_id):
        return self.entities.get(entity_id)

    def get_traitsetting(self, ts_id):
        return self.traitsettings.get(ts_id)


def _ban_effect(remaining=1, event="scene", combine=TimerCombine.FIRST_TO_FIRE):
    return Effect(
        timing=EffectTiming.IMMEDIATE,
        type="entity",
        action="targeting_ban",
        target="",
        duration=EffectDuration(
            timers=[Timer(event=event, remaining=remaining)],
            combine=combine,
        ),
    )


def _apply_monkey(monkeypatch, fired):
    monkeypatch.setattr(
        "transversal.services.effects_applier.effect_registry.apply",
        lambda eff, eid, u, ctx: fired.append((eff.type, eff.action, eff.target, eid)),
    )


def test_schedule_revert_creates_central_event():
    repo = FakeRepo(entities=[_entity()])
    event = schedule_revert(repo, "entity", "kael", _ban_effect(remaining=1), target="guard")

    assert event is not None
    assert repo.events == [event]
    assert event.target_type == "entity"
    assert event.target_id == "kael"
    assert event.effect.type == "entity"
    assert event.effect.action == "remove_targeting_ban"
    assert event.effect.target == "guard"
    assert event.timers == [Timer(event="scene", remaining=1)]


def test_schedule_revert_ignores_missing_duration_or_inverse():
    repo = FakeRepo(entities=[_entity()])

    # No duration.
    plain = Effect(type="entity", action="targeting_ban", target="")
    assert schedule_revert(repo, "entity", "kael", plain) is None

    # Duration but no inverse registered.
    unknown = Effect(
        type="modify_trait", action="gain_or_step_up", target="t",
        duration=EffectDuration(timers=[Timer(event="scene", remaining=1)]),
    )
    assert schedule_revert(repo, "entity", "kael", unknown) is None
    assert repo.events == []


def test_advance_fires_revert_on_expiry(monkeypatch):
    repo = FakeRepo(entities=[_entity()])
    schedule_revert(repo, "entity", "kael", _ban_effect(remaining=1), target="guard")

    fired = []
    _apply_monkey(monkeypatch, fired)

    assert advance_scheduled_events(repo, "scene") == 1
    assert fired == [("entity", "remove_targeting_ban", "guard", "kael")]
    assert repo.events == []


def test_advance_only_decrements_matching_event(monkeypatch):
    repo = FakeRepo(entities=[_entity()])
    schedule_revert(repo, "entity", "kael", _ban_effect(remaining=2, event="scene"), target="guard")

    fired = []
    _apply_monkey(monkeypatch, fired)

    assert advance_scheduled_events(repo, "beat") == 0
    assert repo.events[0].timers[0].remaining == 2
    assert advance_scheduled_events(repo, "scene") == 0
    assert repo.events[0].timers[0].remaining == 1
    assert advance_scheduled_events(repo, "scene") == 1
    assert fired == [("entity", "remove_targeting_ban", "guard", "kael")]


def test_all_transpired_combine(monkeypatch):
    repo = FakeRepo(entities=[_entity()])
    effect = Effect(
        timing=EffectTiming.IMMEDIATE,
        type="entity",
        action="targeting_ban",
        target="",
        duration=EffectDuration(
            timers=[Timer(event="scene", remaining=1), Timer(event="beat", remaining=3)],
            combine=TimerCombine.ALL_TRANSPIRED,
        ),
    )
    schedule_revert(repo, "entity", "kael", effect, target="guard")

    fired = []
    _apply_monkey(monkeypatch, fired)

    assert advance_scheduled_events(repo, "scene") == 0
    assert repo.events[0].timers[0].remaining == 0
    assert advance_scheduled_events(repo, "beat") == 0
    assert advance_scheduled_events(repo, "beat") == 0
    assert repo.events[0].timers[1].remaining == 1
    assert advance_scheduled_events(repo, "beat") == 1
    assert fired == [("entity", "remove_targeting_ban", "guard", "kael")]


def test_build_revert_set_captures_prior():
    effect = Effect(type="modify_trait", action="set", target="trait-1", result="d8")
    revert = build_revert(effect, prior_result="d6")
    assert revert is not None
    assert revert.type == "modify_trait"
    assert revert.action == "set"
    assert target_value(revert) == "trait-1"
    assert revert.result == "d6"

    assert build_revert(effect).result == "d8"


def test_build_revert_no_inverse_returns_none():
    assert build_revert(Effect(type="modify_trait", action="gain_or_step_up", target="t")) is None


def test_trait_setting_target_fires_via_entity(monkeypatch):
    ts = TraitSetting(id="ts-1", entity_id="kael", trait_id="trait-1")
    repo = FakeRepo(entities=[_entity()], traitsettings=[ts])
    revert = Effect(type="modify_trait", action="set", target="trait-1", result="d6")
    schedule_event(repo, "trait_setting", "ts-1", revert, [Timer(event="beat", remaining=1)], TimerCombine.FIRST_TO_FIRE)

    fired = []
    _apply_monkey(monkeypatch, fired)

    assert advance_scheduled_events(repo, "beat") == 1
    assert fired == [("modify_trait", "set", "trait-1", "kael")]
    assert repo.events == []


def test_orphan_target_is_noop(monkeypatch):
    repo = FakeRepo(entities=[])  # no entity
    schedule_revert(repo, "entity", "ghost", _ban_effect(remaining=1), target="guard")

    fired = []
    _apply_monkey(monkeypatch, fired)

    assert advance_scheduled_events(repo, "scene") == 0
    assert fired == []
    assert repo.events == []  # fired + deleted


def test_entity_scoped_dispatch_only_ticks_matching_target(monkeypatch):
    repo = FakeRepo(entities=[_entity("kael"), _entity("other")])
    schedule_revert(repo, "entity", "kael", _ban_effect(remaining=1, event="location_changed"), target="a")
    schedule_revert(repo, "entity", "other", _ban_effect(remaining=1, event="location_changed"), target="b")

    fired = []
    _apply_monkey(monkeypatch, fired)

    # kael changes location → only kael's location_changed timer ticks.
    dispatch_event(repo, "location_changed", entity_id="kael", universe="earth")
    assert fired == [("entity", "remove_targeting_ban", "a", "kael")]
    # other's event survives.
    assert len(repo.events) == 1
    assert repo.events[0].target_id == "other"


def test_timing_to_timer():
    assert timing_to_timer(EffectTiming.END_OF_BEAT) == Timer(event="beat", remaining=1)
    assert timing_to_timer(EffectTiming.END_OF_SCENE) == Timer(event="scene", remaining=1)
    assert timing_to_timer(EffectTiming.END_OF_SESSION) == Timer(event="session", remaining=1)
    assert timing_to_timer(EffectTiming.AFTER_BEATS) == Timer(event="beat", remaining=3)
    assert timing_to_timer(EffectTiming.IMMEDIATE) is None
    assert timing_to_timer(EffectTiming.ON_CONDITION) is None


def test_schedule_deferred_creates_event():
    repo = FakeRepo(entities=[_entity()])
    effect = Effect(timing=EffectTiming.END_OF_BEAT, type="modify_trait", action="step_up", target="t")

    assert schedule_deferred(repo, "entity", "kael", effect) is True
    assert len(repo.events) == 1
    assert repo.events[0].timers == [Timer(event="beat", remaining=1)]

    assert schedule_deferred(
        repo, "entity", "kael",
        Effect(timing=EffectTiming.ON_CONDITION, type="modify_trait", action="step_up", target="t"),
    ) is False
