"""Outcome effects — Step Up Effect / Step Up Outcome.

These are the only effects that act on a roll that has already been set, so the
tests pin the two things that make that coherent:

- the effect die (and, for a simplified roll, the tier) is **stepped**, and
- the comparison is made **once, on the stepped value** — the set endpoint
  compares after the effects fire, because `_compare` flips initiative and is
  therefore not idempotent.
"""

import pytest

from transversal.domain import CommittedResult
from transversal.domain import DieType
from transversal.domain import Effect
from transversal.domain import EffectTiming
from transversal.domain import EntityType
from transversal.domain import Entity
from transversal.domain import OutcomeTier
from transversal.services.contest_tracker import ContestTracker
from transversal.services.effects_applier import apply_effects


@pytest.fixture
def tracker(monkeypatch):
    """A fresh tracker installed as the module singleton the handler reaches for."""
    from transversal.services import contest_tracker as ct_module

    fresh = ContestTracker()
    monkeypatch.setattr(ct_module, "_contest_tracker", fresh)
    return fresh


def _entity(eid="kael", location="loc-1"):
    return Entity(id=eid, type=EntityType.CHARACTER, name=eid,
                  current_universe="earth", current_location=location)


def _committed(effect_die=DieType.D6, total=10, tier=None):
    return CommittedResult(total=total, effect_die=effect_die, tier=tier, pipeline="pool")


def _effect(action):
    return Effect(timing=EffectTiming.IMMEDIATE, type="modify_outcome", action=action)


def _contest(tracker, entity_id="kael", committed=None):
    """A contest with opposition and one side already committed."""
    state = tracker.get_or_create("loc-1", entity_id, "earth")
    state.opposition_entity_id = "guard"
    state.committed = committed or _committed()
    tracker.get_or_create("loc-1", "guard", "earth")
    return state


# ── The handlers ─────────────────────────────────────

def test_step_up_effect_steps_the_committed_effect_die(tracker):
    state = _contest(tracker, committed=_committed(effect_die=DieType.D6))
    result = apply_effects(_entity(), [_effect("step_up_effect")], None)
    assert state.committed.effect_die == DieType.D8
    assert "d6 → d8" in result.applied[0].summary


def test_step_up_effect_saturates_at_d12(tracker):
    state = _contest(tracker, committed=_committed(effect_die=DieType.D12))
    result = apply_effects(_entity(), [_effect("step_up_effect")], None)
    assert state.committed.effect_die == DieType.D12
    assert "already" in result.applied[0].summary


def test_step_up_effect_without_a_committed_result_says_so(tracker):
    result = apply_effects(_entity(), [_effect("step_up_effect")], None)
    assert "no committed result" in result.applied[0].summary


def test_step_up_outcome_steps_a_simplified_tier(tracker):
    """A simplified side carries a real tier, so that is what moves."""
    state = _contest(tracker, committed=_committed(tier=OutcomeTier.SUCCESS))
    result = apply_effects(_entity(), [_effect("step_up_outcome")], None)
    assert state.committed.tier == OutcomeTier.EXCEPTIONAL
    assert "exceptional" in result.applied[0].summary


def test_step_up_outcome_on_a_pool_roll_steps_the_effect_die_instead(tracker):
    """Only a simplified side has a server-side tier, so the rung's own effect die
    is what moves — the visible outcome still changes."""
    state = _contest(tracker, committed=_committed(effect_die=DieType.D6, tier=None))
    result = apply_effects(_entity(), [_effect("step_up_outcome")], None)
    assert state.committed.effect_die == DieType.D8
    assert state.committed.tier is None
    assert "outcome's effect die" in result.applied[0].summary


# ── The ordering that makes it resolve ───────────────

def test_the_compare_runs_once_on_the_stepped_value(tracker):
    """The endpoint's order: store, fire the effect, compare **once**.

    The compare reads the committed result, so the step-up has to land on it
    *before* the compare — that is why the endpoint stores first and compares last.
    """
    kael = tracker.get_or_create("loc-1", "kael", "earth")
    kael.opposition_entity_id = "guard"
    kael.committed = _committed(effect_die=DieType.D6, total=12)
    guard = tracker.get_or_create("loc-1", "guard", "earth")
    guard.committed = _committed(effect_die=DieType.D6, total=10)

    apply_effects(_entity(), [_effect("step_up_effect")], None)
    assert kael.committed.effect_die == DieType.D8

    outcome = tracker.compare_if_ready("loc-1", "kael")
    # The outcome the table sees carries the stepped die, not the committed one.
    assert outcome is not None
    assert outcome.effect_die == DieType.D8


def test_comparing_twice_is_not_the_same_as_comparing_once(tracker):
    """Why the endpoint compares exactly once: `_compare` flips initiative.

    If it compared at commit *and* again after the effect, the second compare
    would resolve the following round — a different attacker — instead of the round
    that was just rolled. Measured: the same committed results give a *compare*
    first and an *outcome* the second time.
    """
    from transversal.domain import ContestCompare
    from transversal.domain import ContestOutcome

    kael = tracker.get_or_create("loc-1", "kael", "earth")
    kael.opposition_entity_id = "guard"
    kael.committed = _committed(effect_die=DieType.D6, total=10)
    guard = tracker.get_or_create("loc-1", "guard", "earth")
    guard.committed = _committed(effect_die=DieType.D6, total=12)

    first = tracker.compare_if_ready("loc-1", "kael")
    second = tracker.compare_if_ready("loc-1", "kael")
    assert isinstance(first, ContestCompare) and first.pending == "kael"
    assert isinstance(second, ContestOutcome) and second.winner.value == "opponent"
    assert kael.initiative == "guard"
