"""Tests for the persisted scheduled-events (timed revert) system."""

from types import SimpleNamespace

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
from transversal.services.scheduled_events import (
    advance_events,
    advance_traitsetting_events,
    build_revert,
    dispatch_event,
    schedule_revert,
)


def _entity(entity_id="kael", scheduled=None):
    return Entity(
        id=entity_id,
        type=EntityType.CHARACTER,
        name=entity_id,
        current_universe="earth",
        scheduled_events=scheduled or [],
    )


class FakeRepo:
    def __init__(self, entities):
        self.entities = list(entities)

    def list_all_entities(self):
        return list(self.entities)

    def update_entity(self, entity):
        for i, existing in enumerate(self.entities):
            if existing.id == entity.id:
                self.entities[i] = entity
                return


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


def test_schedule_revert_appends_event():
    entity = _entity()
    repo = FakeRepo([entity])
    effect = _ban_effect(remaining=1)

    assert schedule_revert(entity, effect, repo, target="guard") is True

    assert len(entity.scheduled_events) == 1
    se = entity.scheduled_events[0]
    assert se.effect.type == "entity"
    assert se.effect.action == "remove_targeting_ban"
    assert se.effect.target == "guard"
    assert se.timers == [Timer(event="scene", remaining=1)]


def test_schedule_revert_ignores_missing_duration_or_inverse():
    entity = _entity()
    repo = FakeRepo([entity])

    # No duration.
    plain = Effect(type="entity", action="targeting_ban", target="")
    assert schedule_revert(entity, plain, repo) is False

    # Duration but no inverse registered.
    unknown = Effect(
        type="modify_trait", action="gain", target="t",
        duration=EffectDuration(timers=[Timer(event="scene", remaining=1)]),
    )
    assert schedule_revert(entity, unknown, repo) is False
    assert entity.scheduled_events == []


def test_advance_events_fires_revert_on_expiry(monkeypatch):
    entity = _entity()
    repo = FakeRepo([entity])
    effect = _ban_effect(remaining=1)
    schedule_revert(entity, effect, repo, target="guard")

    fired = []
    monkeypatch.setattr(
        "transversal.services.effects_applier.effect_registry.apply",
        lambda eff, eid, u, ctx: fired.append((eff.type, eff.action, eff.target)),
    )

    # First scene: decrements 1→0 but first_to_fire fires once it hits 0.
    changed = advance_events(repo, "scene")
    assert changed == 1
    assert fired == [("entity", "remove_targeting_ban", "guard")]
    assert entity.scheduled_events == []


def test_advance_events_only_decrements_matching_event(monkeypatch):
    entity = _entity()
    repo = FakeRepo([entity])
    schedule_revert(entity, _ban_effect(remaining=2, event="scene"), repo, target="guard")

    fired = []
    monkeypatch.setattr(
        "transversal.services.effects_applier.effect_registry.apply",
        lambda eff, eid, u, ctx: fired.append(eff.action),
    )

    # A beat doesn't decrement a scene timer.
    assert advance_events(repo, "beat") == 0
    assert entity.scheduled_events[0].timers[0].remaining == 2
    # First scene: 2→1, still active.
    assert advance_events(repo, "scene") == 0
    assert entity.scheduled_events[0].timers[0].remaining == 1
    # Second scene: 1→0, fires.
    assert advance_events(repo, "scene") == 1
    assert fired == ["remove_targeting_ban"]


def test_all_transpired_combine(monkeypatch):
    entity = _entity()
    repo = FakeRepo([entity])
    effect = Effect(
        timing=EffectTiming.IMMEDIATE,
        type="entity",
        action="targeting_ban",
        target="",
        duration=EffectDuration(
            timers=[
                Timer(event="scene", remaining=1),
                Timer(event="beat", remaining=3),
            ],
            combine=TimerCombine.ALL_TRANSPIRED,
        ),
    )
    schedule_revert(entity, effect, repo, target="guard")

    fired = []
    monkeypatch.setattr(
        "transversal.services.effects_applier.effect_registry.apply",
        lambda eff, eid, u, ctx: fired.append(eff.action),
    )

    # scene timer hits 0, beat timer still 3 → not all transpired.
    assert advance_events(repo, "scene") == 0
    assert entity.scheduled_events[0].timers[0].remaining == 0
    # beat ×2 → 1 remaining, still not all.
    assert advance_events(repo, "beat") == 0
    assert advance_events(repo, "beat") == 0
    assert entity.scheduled_events[0].timers[1].remaining == 1
    # final beat → all transpired.
    assert advance_events(repo, "beat") == 1
    assert fired == ["remove_targeting_ban"]


def test_build_revert_set_captures_prior():
    effect = Effect(type="modify_trait", action="set", target="trait-1", result="d8")
    revert = build_revert(effect, prior_result="d6")
    assert revert is not None
    assert revert.type == "modify_trait"
    assert revert.action == "set"
    assert revert.target == "trait-1"
    assert revert.result == "d6"  # prior value, not d8

    # Without prior result it falls back to the forward result.
    fallback = build_revert(effect)
    assert fallback.result == "d8"


def test_build_revert_no_inverse_returns_none():
    assert build_revert(Effect(type="modify_trait", action="gain", target="t")) is None


class TraitRepo:
    def __init__(self, traitsettings):
        self.traitsettings = list(traitsettings)
        self.updated = []

    def list_all_traitsettings(self):
        return list(self.traitsettings)

    def update_traitsetting(self, ts):
        self.updated.append(ts.id)
        for i, existing in enumerate(self.traitsettings):
            if existing.id == ts.id:
                self.traitsettings[i] = ts
                return


def test_advance_traitsetting_events(monkeypatch):
    revert = Effect(type="modify_trait", action="set", target="trait-1", result="d6")
    ts = TraitSetting(
        id="ts-1", entity_id="kael", trait_id="trait-1", traitset_id="tset",
        scheduled_events=[ScheduledEvent(id="se-1", effect=revert, timers=[Timer(event="beat", remaining=1)])],
    )
    repo = TraitRepo([ts])

    fired = []
    monkeypatch.setattr(
        "transversal.services.effects_applier.effect_registry.apply",
        lambda eff, eid, u, ctx: fired.append((eff.action, eid, eff.target)),
    )

    assert advance_traitsetting_events(repo, "beat") == 1
    assert fired == [("set", "kael", "trait-1")]
    assert ts.scheduled_events == []
