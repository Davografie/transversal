"""A boundary choice node parks until it is answered ([[B5]]).

The author's requirement for the session-end choice: *persistence, so the player
doesn't skip it*. So a due choice node is asked rather than applied, its row keeps
the question, and only an answer ends it. An unanswered/unknown answer runs nothing
— which is the *default branch* (the step-down stands), not a failure.
"""

from types import SimpleNamespace as NS

from transversal.domain import (
    Effect, EffectBranch, EffectDuration, EffectTiming, ScheduledEvent, Timer, TimerCombine,
)
from transversal.services import scheduled_events as se


class Repo:
    def __init__(self, event, entity=None, sfx=None):
        self.events = {event.id: event}
        self.entity = entity
        self.sfx = sfx
        self.deleted = []

    def list_all_scheduled_events(self):
        return list(self.events.values())

    def get_scheduled_event(self, eid):
        return self.events.get(eid)

    def update_scheduled_event(self, event):
        self.events[event.id] = event
        return event

    def delete_scheduled_event(self, eid):
        self.deleted.append(eid)
        self.events.pop(eid, None)
        return True

    def get_entity(self, eid):
        return self.entity

    def get_sfx(self, sid):
        return self.sfx


def _entity():
    return NS(id="char-1", current_universe="earth", current_location="loc-1",
              current_projection=None, life_paths=[], pending_term=None, razmerit=0)


def _branch_event():
    effect = Effect(
        timing=EffectTiming.END_OF_SESSION, type="branch", action="choose",
        branches=[EffectBranch(id="keep", label="Let it stand"),
                  EffectBranch(id="change", label="Change the statement",
                               effects=[Effect(type="modify_trait", action="set_statement",
                                               target="ts-1", result="redefined")])],
    )
    return ScheduledEvent(
        id="ev-1", target_type="entity", target_id="char-1", kind="pending",
        effect=effect, timers=[Timer(event="session", remaining=1)],
        combine=TimerCombine.FIRST_TO_FIRE, source_sfx_id="sfx-challenge-statement",
    )


def test_a_due_choice_parks_instead_of_applying(monkeypatch):
    event = _branch_event()
    repo = Repo(event, entity=_entity(), sfx=NS(name="Challenge Statement", description=""))
    emitted = []
    monkeypatch.setattr("transversal.services.roll_orchestrator._emit_pending_choices",
                        lambda *a, **k: emitted.append(a))

    fired = se.advance_scheduled_events(repo, "session")

    assert fired == 0, "a choice node applies nothing by arriving"
    assert repo.events["ev-1"].kind == "awaiting_choice", "the row keeps the question"
    assert repo.deleted == [], "and is not deleted"
    assert emitted and emitted[0][2][0].kind == "branch", "the picker is told, as a branch"


def test_a_parked_choice_does_not_re_ask_on_the_next_tick(monkeypatch):
    event = _branch_event()
    repo = Repo(event, entity=_entity())
    monkeypatch.setattr("transversal.services.roll_orchestrator._emit_pending_choices",
                        lambda *a, **k: None)
    se.advance_scheduled_events(repo, "session")

    emitted = []
    monkeypatch.setattr("transversal.services.roll_orchestrator._emit_pending_choices",
                        lambda *a, **k: emitted.append(a))
    se.advance_scheduled_events(repo, "session")
    assert emitted == [], "the prompt is not re-broadcast every tick"
    assert repo.events["ev-1"].kind == "awaiting_choice"


def test_answering_runs_the_chosen_option_and_ends_the_row(monkeypatch):
    event = _branch_event()
    repo = Repo(event, entity=_entity())
    monkeypatch.setattr("transversal.services.roll_orchestrator._emit_pending_choices",
                        lambda *a, **k: None)
    se.advance_scheduled_events(repo, "session")

    applied = []
    monkeypatch.setattr("transversal.services.effects_commit.commit_effects",
                        lambda entity, effects, repo_, context=None, **k: (
                            applied.extend(effects),
                            NS(applied=[NS(summary="restated it")]))[1])
    summaries = se.resolve_parked_branch(repo, "ev-1", "change")

    assert [e.action for e in applied] == ["set_statement"]
    assert summaries == ["restated it"]
    assert repo.deleted == ["ev-1"], "the question is over"


def test_the_default_branch_runs_nothing_and_still_ends_the_row(monkeypatch):
    """Unanswered or 'keep': the step-down stands because nothing changed. The row
    still clears, so the prompt cannot follow the player forever."""
    event = _branch_event()
    repo = Repo(event, entity=_entity())
    monkeypatch.setattr("transversal.services.roll_orchestrator._emit_pending_choices",
                        lambda *a, **k: None)
    se.advance_scheduled_events(repo, "session")

    applied = []
    monkeypatch.setattr("transversal.services.effects_commit.commit_effects",
                        lambda *a, **k: applied.append(a) or NS(applied=[]))
    assert se.resolve_parked_branch(repo, "ev-1", "keep") == []
    assert applied == [], "the default branch applies nothing"
    assert repo.deleted == ["ev-1"]


def test_only_a_parked_choice_can_be_answered():
    repo = Repo(_branch_event(), entity=_entity())
    assert se.resolve_parked_branch(repo, "ev-1", "change") == [], "not parked yet"
    assert se.resolve_parked_branch(repo, "nope", "change") == []
