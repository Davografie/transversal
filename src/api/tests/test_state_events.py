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


def test_contest_context_carries_opponent_entity_projection_and_effect_dice(monkeypatch):
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
    assert winner_event.context["effect_dice"] == ["d8"]

    loser_event = engine.events[1]
    assert loser_event.entity_id == "loser"
    assert loser_event.context["contest_winner"] == "opponent"
    assert loser_event.context["contest_entity_opponent"] == "winner"
    assert loser_event.context["contest_projection_opponent"] == "proj-w"
