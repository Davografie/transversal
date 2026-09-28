"""A delayed part of a rule reports when it lands ([[B229]] item 2).

The author's rule: effects that happen *immediately* — at the same time — share one
splash screen, and a consecutive effect triggered at another time shows an
**intermediate update**. So the immediate batch of an activation is one note (the
engine emits it when the rule's effects land), and every later arrival is its own
shorter note.

The choke point is the central timer store's apply: it ran with an **empty context**,
so a deferred effect applied and said nothing anywhere. These tests pin the note it
now emits, and — just as important — that it stays quiet when nothing was recorded.
"""

from types import SimpleNamespace

import pytest

from transversal.domain import Effect, EffectTiming, ScheduledEvent

@pytest.fixture
def published(monkeypatch):
    """Capture what reaches the SSE bus, with one session listening."""
    out = []
    monkeypatch.setattr(
        "transversal.services.session_manager.session_manager.list_active",
        lambda: [SimpleNamespace(id="s1")],
    )
    monkeypatch.setattr(
        "transversal.api.sse.bus.event_bus.publish",
        lambda evt: out.append(evt),
    )
    return out


class _Repo:
    """Enough repository for the fire path: the target, its owner, the rule."""

    def __init__(self, *, entity=None, trait_setting=None, sfx=None):
        self._entity = entity
        self._trait_setting = trait_setting
        self._sfx = sfx

    def get_entity(self, entity_id):
        return self._entity if self._entity and self._entity.id == entity_id else None

    def get_traitsetting(self, ts_id):
        return self._trait_setting if self._trait_setting and self._trait_setting.id == ts_id else None

    def get_sfx(self, sfx_id):
        return self._sfx if self._sfx and self._sfx.id == sfx_id else None


def _event(**overrides):
    kwargs = dict(
        id="se-1", target_type="entity", target_id="char-1",
        effect=Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait",
                      action="step_up", target="t1"),
        timers=[], source_sfx_id="sfx-x",
    )
    kwargs.update(overrides)
    return ScheduledEvent(**kwargs)


@pytest.fixture
def recording_registry(monkeypatch):
    """A registry whose applier writes one note, as the real commit does."""
    from transversal.services.effects_applier.datatypes import EFFECT_NOTES_CONTEXT_KEY

    class Recorder:
        def apply(self, action, entity_id, universe, context):
            sink = context.get(EFFECT_NOTES_CONTEXT_KEY)
            if sink is not None:
                sink.append({"type": action.type, "action": action.action,
                             "target": action.target, "note": "stepped up to d8"})

    import transversal.services.effects_applier as applier
    original = applier.effect_registry
    applier.effect_registry = Recorder()
    try:
        yield
    finally:
        applier.effect_registry = original


def test_a_delayed_entity_change_reports_an_intermediate_update(published, recording_registry):
    from transversal.services.scheduled_events import _apply_event

    repo = _Repo(entity=SimpleNamespace(id="char-1", type=SimpleNamespace(value="character"), current_universe="earth"),
                 sfx=SimpleNamespace(id="sfx-x", name="Crimson Scars"))
    assert _apply_event(repo, _event()) == 1

    assert len(published) == 1
    evt = published[0]
    assert evt.event == "effects_changed"
    assert evt.data["entity_id"] == "char-1"
    assert evt.data["location_id"] == ""
    assert evt.data["title"] == "Crimson Scars"
    # The brief banner: this is one arrival, not the rule's whole course.
    assert evt.data["kind"] == "change"
    assert evt.data["lines"] == ["step_up: stepped up to d8"]


def test_a_delayed_change_to_a_place_reaches_everyone_standing_there(
        published, recording_registry):
    """`entity_id` would address one character's screen; a change to the place
    belongs to whoever is in it, which is what `location_id` is for."""
    from transversal.services.scheduled_events import _apply_event

    repo = _Repo(entity=SimpleNamespace(id="loc-1", type=SimpleNamespace(value="location"), current_universe="earth"))
    assert _apply_event(repo, _event(target_id="loc-1")) == 1

    assert len(published) == 1
    assert published[0].data["entity_id"] == ""
    assert published[0].data["location_id"] == "loc-1"


def test_a_trait_setting_target_resolves_through_its_owner(published, recording_registry):
    from transversal.services.scheduled_events import _apply_event

    repo = _Repo(
        entity=SimpleNamespace(id="char-1", type=SimpleNamespace(value="character"), current_universe="earth"),
        trait_setting=SimpleNamespace(id="char-1:t1", entity_id="char-1"),
    )
    assert _apply_event(repo, _event(target_type="trait_setting", target_id="char-1:t1")) == 1
    assert published[0].data["entity_id"] == "char-1"


def test_nothing_recorded_reports_nothing(published, monkeypatch):
    """A rule that never reaches the commit path (a razmerit op, a passthrough)
    has nothing to say, and must not splash an empty banner."""
    from transversal.services.scheduled_events import _apply_event

    class Silent:
        def apply(self, action, entity_id, universe, context):
            return None

    import transversal.services.effects_applier as applier
    original = applier.effect_registry
    applier.effect_registry = Silent()
    try:
        repo = _Repo(entity=SimpleNamespace(id="char-1", type=SimpleNamespace(value="character"), current_universe="earth"))
        assert _apply_event(repo, _event()) == 1
    finally:
        applier.effect_registry = original

    assert published == []


def test_an_orphaned_row_still_reports_nothing(published, recording_registry):
    """The target was deleted; there is nothing to apply and nothing to say."""
    from transversal.services.scheduled_events import _apply_event

    assert _apply_event(_Repo(), _event()) == 0
    assert published == []


def test_a_row_with_no_rule_leaves_the_title_to_the_surface(published, recording_registry):
    """An authored timer has no rule behind it, so there is no name to give."""
    from transversal.services.scheduled_events import _apply_event

    repo = _Repo(entity=SimpleNamespace(id="char-1", type=SimpleNamespace(value="character"), current_universe="earth"))
    _apply_event(repo, _event(source_sfx_id=None))
    assert published[0].data["title"] == ""
