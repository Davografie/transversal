"""Conditions a path cannot express: contest side, and whether a session is running.

[[B3]], settled with the human (2026-09-24): *"during contest"* and *"during test"*
are already writable as a targeting path (`select self → navigate contest → filter
kind == …`), so only the conditions a **path cannot reach** are added here.

* **Contest side** is the case: a path can reach *a contest*, but not *the side I am
  on* — the tracker holds that relation, not the graph.
* **Session** had nothing to read at all; `on_session_start`/`on_session_end` are
  moments, not state.
"""

from types import SimpleNamespace as NS

import pytest

from transversal.domain import Condition, ConditionType, RollKind
from transversal.services import contest_tracker as ct_module
from transversal.services.conditions import CONDITION_TYPES, evaluate_condition
from transversal.services.contest_tracker import ContestTracker
from transversal.services.session_state import is_active, set_active
from transversal.services.sfx_text import condition_text

LOC = "loc-arena"


def _entity(eid="kael", location=LOC):
    return NS(id=eid, current_location=location, current_universe="earth",
              type="character")


@pytest.fixture(autouse=True)
def _reset_session():
    set_active(False)
    yield
    set_active(False)


def _contest(monkeypatch, challenger="kael", defendant="mira"):
    tracker = ContestTracker()
    tracker.set_opposition(LOC, challenger, defendant, "earth")
    monkeypatch.setattr(ct_module, "get_contest_tracker", lambda: tracker)
    return tracker


# ── Contest side ──────────────────────────────────────────────

def test_the_challenger_is_the_side_that_declared_it(monkeypatch):
    _contest(monkeypatch)
    chall = Condition(type=ConditionType.CONTEST_CHALLENGER)
    deff = Condition(type=ConditionType.CONTEST_DEFENDANT)

    assert evaluate_condition(_entity("kael"), chall, None) is True
    assert evaluate_condition(_entity("kael"), deff, None) is False

    # ...and the defendant's answer is the mirror, asked from its own state.
    assert evaluate_condition(_entity("mira"), deff, None) is True
    assert evaluate_condition(_entity("mira"), chall, None) is False


def test_a_plain_test_is_neither_side(monkeypatch):
    """A **test** has a contest state too — a pool save creates one. The
    opposition link is what makes it a contest, so neither side condition may pass
    on a test, or every roll would read as a challenge."""
    tracker = ContestTracker()
    state = tracker.get_or_create(LOC, "kael", "earth")
    assert state.kind == RollKind.TEST
    monkeypatch.setattr(ct_module, "get_contest_tracker", lambda: tracker)

    assert evaluate_condition(_entity("kael"), Condition(type=ConditionType.CONTEST_CHALLENGER), None) is False
    assert evaluate_condition(_entity("kael"), Condition(type=ConditionType.CONTEST_DEFENDANT), None) is False


def test_an_entity_with_no_contest_is_neither_side(monkeypatch):
    _contest(monkeypatch)
    stranger = _entity("nobody")
    for t in (ConditionType.CONTEST_CHALLENGER, ConditionType.CONTEST_DEFENDANT):
        assert evaluate_condition(stranger, Condition(type=t), None) is False


def test_an_unplaced_entity_is_not_in_a_contest(monkeypatch):
    """Contests are keyed `(location, entity)`, so there is nothing to look up."""
    _contest(monkeypatch)
    for t in (ConditionType.CONTEST_CHALLENGER, ConditionType.CONTEST_DEFENDANT):
        assert evaluate_condition(_entity("kael", location=""), Condition(type=t), None) is False


# ── Session ───────────────────────────────────────────────────

def test_session_active_and_inactive_are_the_same_condition():
    cond = lambda v: Condition(type=ConditionType.SESSION, target=v)
    set_active(True)
    assert evaluate_condition(_entity(), cond("active"), None) is True
    assert evaluate_condition(_entity(), cond("inactive"), None) is False

    set_active(False)
    assert evaluate_condition(_entity(), cond("inactive"), None) is True
    assert evaluate_condition(_entity(), cond("active"), None) is False
    # No target means "active", the reading an author expects by default.
    assert evaluate_condition(_entity(), Condition(type=ConditionType.SESSION), None) is False


def test_the_boundaries_set_the_state(monkeypatch):
    """The wiring, not just the flag: a session boundary is the only thing that
    should move it."""
    from transversal.services import roll_deferral, state_events

    monkeypatch.setattr(roll_deferral, "clear_global_armed", lambda: None)
    monkeypatch.setattr(state_events, "fire_global_state_sfx", lambda *a, **k: None)
    monkeypatch.setattr("transversal.main._get_repo",
                        lambda: NS(get_all_sfxs=lambda: []))

    state_events.fire_session_start()
    assert is_active() is True

    state_events.fire_session_end()
    assert is_active() is False


# ── The vocabulary and the card ───────────────────────────────

def test_all_three_are_offered_to_the_editor():
    by_name = {d.value: d for d in CONDITION_TYPES}
    assert by_name["CONTEST_CHALLENGER"].group == "Character state"
    assert by_name["CONTEST_DEFENDANT"].group == "Character state"
    session = by_name["SESSION"]
    assert session.group == "The moment it fires"
    assert list(session.target_options) == ["active", "inactive"]


def test_the_card_says_which_side_and_whether_a_session_is_running():
    assert condition_text(Condition(type=ConditionType.CONTEST_CHALLENGER)) == "you are the challenger"
    assert condition_text(Condition(type=ConditionType.CONTEST_DEFENDANT)) == "you are the defendant"
    assert condition_text(Condition(type=ConditionType.SESSION, target="active")) == "a session is running"
    assert condition_text(Condition(type=ConditionType.SESSION, target="inactive")) == "no session is running"
    # A condition with no target reads as the default, like the evaluator does.
    assert condition_text(Condition(type=ConditionType.SESSION)) == "a session is running"
