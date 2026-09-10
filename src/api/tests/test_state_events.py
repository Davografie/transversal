"""Tests for contest-outcome SFX context enrichment."""

from types import SimpleNamespace

import transversal.services.state_events as se
from transversal.services.effects_engine import EventOutcome


class FakeRepo:
    def __init__(self, entities):
        self.entities = entities

    def get_entity(self, entity_id):
        return self.entities.get(entity_id)


class CaptureEngine:
    def __init__(self):
        self.events = []

    def process_event_outcome(self, event, sfx_ids, razmerit, repo=None):
        self.events.append(event)
        return EventOutcome()


def test_contest_context_carries_opponent_entity_projection_and_effect_die(monkeypatch):
    import transversal.main as main

    repo = FakeRepo({
        "winner": SimpleNamespace(current_universe="earth", current_projection="proj-w", razmerit=5),
        "loser": SimpleNamespace(current_universe="earth", current_projection="proj-l", razmerit=3),
    })
    engine = CaptureEngine()
    monkeypatch.setattr(main, "_repo", repo)
    monkeypatch.setattr(main, "_effects_engine", engine)
    monkeypatch.setattr(
        "transversal.services.sfx_owner.get_available_sfx_ids",
        lambda entity_id, universe, repo: [],
    )

    se.fire_contest_outcome_sfx("winner", "loser", "earth", effect_die="d8")

    assert len(engine.events) == 2

    winner_event = engine.events[0]
    assert winner_event.entity_id == "winner"
    assert winner_event.context["contest_winner"] == "player"
    assert winner_event.context["contest_entity_opponent"] == "loser"
    assert winner_event.context["contest_projection_opponent"] == "proj-l"
    assert winner_event.context["effect_die"] == "d8"

    loser_event = engine.events[1]
    assert loser_event.entity_id == "loser"
    assert loser_event.context["contest_winner"] == "opponent"
    assert loser_event.context["contest_entity_opponent"] == "winner"
    assert loser_event.context["contest_projection_opponent"] == "proj-w"


def test_fire_global_state_sfx_iterates_entities(monkeypatch):
    """Beat/scene advance fires the matching trigger for every entity."""
    import transversal.main as main

    repo = SimpleNamespace(
        list_all_entities=lambda: [
            SimpleNamespace(id="a", current_universe="earth", razmerit=2),
            SimpleNamespace(id="b", current_universe="three_realms", razmerit=0),
        ],
        get_all_sfxs=lambda: [SimpleNamespace(id="sfx-beat", trigger="on_beat")],
    )
    engine = CaptureEngine()
    monkeypatch.setattr(main, "_repo", repo)
    monkeypatch.setattr(main, "_effects_engine", engine)
    monkeypatch.setattr(
        "transversal.services.sfx_owner.build_sfx_availability_prefetch",
        lambda repo, entities, universes=None, sfx_docs=None: None,
    )
    monkeypatch.setattr(
        "transversal.services.sfx_owner.get_available_sfx_ids",
        lambda entity_id, universe, repo, prefetch=None: [],
    )
    monkeypatch.setattr(
        "transversal.services.roll_orchestrator._emit_pending_choices",
        lambda *a, **k: None,
    )

    se.fire_global_state_sfx("on_beat")

    assert [(e.entity_id, e.type, e.universe) for e in engine.events] == [
        ("a", "on_beat", "earth"),
        ("b", "on_beat", "three_realms"),
    ]


def test_fire_global_state_sfx_short_circuits_when_trigger_has_no_sfx(monkeypatch):
    """No SFX declares the trigger → skip the whole entity walk."""
    import transversal.main as main

    listed = []
    repo = SimpleNamespace(
        list_all_entities=lambda: listed.append(1) or [],
        get_all_sfxs=lambda: [SimpleNamespace(id="sfx-beat", trigger="on_beat")],
    )
    monkeypatch.setattr(main, "_repo", repo)

    se.fire_global_state_sfx("on_session_end")

    assert listed == []


def test_fire_session_start_arms_passive_rules(monkeypatch):
    import transversal.main as main
    import transversal.services.roll_deferral as roll_deferral
    from transversal.domain import Effect, EffectTiming, SFX

    roll_deferral.reset()

    sfx = SFX(
        id="sfx-one-trick", name="One Trick", trigger="on_session_start",
        effects=[Effect(timing=EffectTiming.ON_ROLL, type="modify_trait", action="step_down", target="self")],
    )
    repo = SimpleNamespace(get_all_sfxs=lambda: [sfx])
    monkeypatch.setattr(main, "_get_repo", lambda: repo)

    se.fire_session_start()

    assert len(roll_deferral.list_global_armed()) == 1
    roll_deferral.reset()
