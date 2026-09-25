"""Tests for the manual contest REST endpoints (challenge / set / give-in)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from transversal.api.rest.contest_pools import router as contest_pools_router
from transversal.api.rest.scene_state import router as scene_state_router
from transversal.services import contest_history
from transversal.services import contest_tracker as ct_module
from transversal.services import scene_state as ss_module
from transversal.services.contest_tracker import ContestTracker
from transversal.services.scene_state import SceneStateStore


@pytest.fixture
def client():
    # Fresh tracker + scene store so state doesn't leak between tests.
    ct_module._contest_tracker = ContestTracker()
    ss_module._store = SceneStateStore()
    # These tests are about the contest flow, not the Blue Book: a getter that
    # returns None keeps the recording path ([[B177]]) off the live database.
    # The record payloads are asserted in test_contest_history.py.
    contest_history._repo_getter = lambda: None
    app = FastAPI()
    app.include_router(scene_state_router)
    app.include_router(contest_pools_router)
    return TestClient(app)


def _save_pool(client, location_id, entity_id, dice):
    wire = [
        {"die": die, "source_kind": "manual", "source_id": source, "label": source, "ts_id": None}
        for die, source in dice
    ]
    r = client.put(f"/api/v1/locations/{location_id}/pools/{entity_id}", json={"dice": wire})
    assert r.status_code == 200, r.text


class TestManualContestFlow:
    def test_challenge_then_set_both_resolves(self, client):
        _save_pool(client, "loc-1", "kael", [("d10", "intelligence"), ("d8", "hacking"), ("d8", "distinction")])
        _save_pool(client, "loc-1", "guard", [("d8", "agility"), ("d6", "awareness"), ("d6", "wary")])

        r = client.post("/api/v1/locations/loc-1/pools/kael/set-opposition", json={"opponent_id": "guard"})
        assert r.status_code == 200, r.text

        # Challenger commits first → waiting.
        r = client.post("/api/v1/locations/loc-1/pools/kael/set", json={"total": 15, "effect_die": "d8", "pipeline": "pool"})
        assert r.status_code == 200, r.text
        assert r.json() == {"status": "waiting"}

        # Defendant commits → auto-resolves.
        r = client.post("/api/v1/locations/loc-1/pools/guard/set", json={"total": 10, "effect_die": "d6", "pipeline": "pool"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["winner"] == "player"  # 15 > 10, challenger wins
        assert data["challenger"]["total"] == 15
        assert data["defendant"]["total"] == 10
        assert data["defendant"]["effect_die"] == "d6"

    def test_give_in(self, client):
        _save_pool(client, "loc-1", "kael", [("d10", "intelligence")])
        _save_pool(client, "loc-1", "guard", [("d8", "agility")])
        client.post("/api/v1/locations/loc-1/pools/kael/set-opposition", json={"opponent_id": "guard"})

        # Give-in is gated on the initiator having committed.
        client.post("/api/v1/locations/loc-1/pools/kael/set", json={"total": 15, "effect_die": "d8", "pipeline": "pool"})
        r = client.post("/api/v1/locations/loc-1/pools/guard/give-in")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["winner"] == "player"  # defendant gave in → challenger wins
        assert data["gave_in"] == "opponent"
        # Conceding still carries the winner's effect die for the complication.
        assert data["effect_die"] == "d8"
        assert data["taken_out"] is False

    def test_give_in_steps_down_effect_when_not_larger(self, client):
        _save_pool(client, "loc-1", "kael", [("d10", "intelligence")])
        _save_pool(client, "loc-1", "guard", [("d8", "agility")])
        client.post("/api/v1/locations/loc-1/pools/kael/set-opposition", json={"opponent_id": "guard"})

        # Both commit (post-compare give-in), then the defendant concedes.
        client.post("/api/v1/locations/loc-1/pools/kael/set", json={"total": 10, "effect_die": "d8", "pipeline": "pool"})
        client.post("/api/v1/locations/loc-1/pools/guard/set", json={"total": 14, "effect_die": "d8", "pipeline": "pool"})
        r = client.post("/api/v1/locations/loc-1/pools/kael/give-in")
        assert r.status_code == 200, r.text
        data = r.json()
        # Winner (guard) d8 is not strictly larger than the conceder's d8,
        # so low-stakes step-down applies: the complication lands at d6.
        assert data["winner"] == "opponent"
        assert data["gave_in"] == "player"
        assert data["effect_die"] == "d6"

    def test_give_in_blocked_before_initiator_sets(self, client):
        _save_pool(client, "loc-1", "kael", [("d10", "intelligence")])
        _save_pool(client, "loc-1", "guard", [("d8", "agility")])
        client.post("/api/v1/locations/loc-1/pools/kael/set-opposition", json={"opponent_id": "guard"})

        r = client.post("/api/v1/locations/loc-1/pools/guard/give-in")
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "not_ready"
        r = client.post("/api/v1/locations/loc-1/pools/kael/give-in")
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "not_ready"

    def test_new_challenge_resets_stale_committed(self, client):
        _save_pool(client, "loc-1", "kael", [("d10", "intelligence")])
        _save_pool(client, "loc-1", "guard", [("d8", "agility")])

        client.post("/api/v1/locations/loc-1/pools/kael/set-opposition", json={"opponent_id": "guard"})
        client.post("/api/v1/locations/loc-1/pools/kael/set", json={"total": 15, "effect_die": "d8", "pipeline": "pool"})

        # Re-challenge: a new contest must not leak the prior committed result.
        client.post("/api/v1/locations/loc-1/pools/kael/set-opposition", json={"opponent_id": "guard"})
        r = client.post("/api/v1/locations/loc-1/pools/kael/give-in")
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "not_ready"  # stale committed was cleared

    def test_set_without_challenge_returns_waiting(self, client):
        _save_pool(client, "loc-1", "kael", [("d10", "intelligence")])
        r = client.post("/api/v1/locations/loc-1/pools/kael/set", json={"total": 9, "pipeline": "pool"})
        assert r.status_code == 200, r.text
        # No opponent designated → still waiting (can't resolve).
        assert r.json() == {"status": "waiting"}

    def test_defendant_beats_challenger_produces_compare(self, client):
        _save_pool(client, "loc-1", "kael", [("d10", "intelligence")])
        _save_pool(client, "loc-1", "guard", [("d8", "agility")])
        client.post("/api/v1/locations/loc-1/pools/kael/set-opposition", json={"opponent_id": "guard"})

        client.post("/api/v1/locations/loc-1/pools/kael/set", json={"total": 10, "effect_die": "d8", "pipeline": "pool"})
        r = client.post("/api/v1/locations/loc-1/pools/guard/set", json={"total": 14, "effect_die": "d6", "pipeline": "pool"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "compare"
        assert data["pending"] == "kael"          # challenger is now losing
        assert data["initiative"] == "guard"      # defendant holds the difficulty
        assert data["challenger"]["total"] == 10
        assert data["defendant"]["total"] == 14
        assert "winner" not in data

    def test_push_then_beat_flips_initiative(self, client):
        _save_pool(client, "loc-1", "kael", [("d10", "intelligence")])
        _save_pool(client, "loc-1", "guard", [("d8", "agility")])
        client.post("/api/v1/locations/loc-1/pools/kael/set-opposition", json={"opponent_id": "guard"})

        client.post("/api/v1/locations/loc-1/pools/kael/set", json={"total": 10, "effect_die": "d8", "pipeline": "pool"})
        client.post("/api/v1/locations/loc-1/pools/guard/set", json={"total": 14, "effect_die": "d6", "pipeline": "pool"})

        assert client.post("/api/v1/locations/loc-1/pools/kael/push").json()["status"] == "pushed"
        r = client.post("/api/v1/locations/loc-1/pools/kael/set", json={"total": 16, "effect_die": "d8", "pipeline": "pool"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "compare"
        assert data["pending"] == "guard"         # defendant now losing
        assert data["initiative"] == "kael"

    def test_push_then_fail_resolves_holder_win(self, client):
        _save_pool(client, "loc-1", "kael", [("d10", "intelligence")])
        _save_pool(client, "loc-1", "guard", [("d8", "agility")])
        client.post("/api/v1/locations/loc-1/pools/kael/set-opposition", json={"opponent_id": "guard"})

        client.post("/api/v1/locations/loc-1/pools/kael/set", json={"total": 10, "effect_die": "d8", "pipeline": "pool"})
        client.post("/api/v1/locations/loc-1/pools/guard/set", json={"total": 14, "effect_die": "d6", "pipeline": "pool"})
        client.post("/api/v1/locations/loc-1/pools/kael/push")

        r = client.post("/api/v1/locations/loc-1/pools/kael/set", json={"total": 12, "effect_die": "d8", "pipeline": "pool"})
        assert r.status_code == 200, r.text
        assert r.json()["winner"] == "opponent"    # guard (holder) wins

    def test_push_blocked_when_not_pending(self, client):
        _save_pool(client, "loc-1", "kael", [("d10", "intelligence")])
        _save_pool(client, "loc-1", "guard", [("d8", "agility")])
        client.post("/api/v1/locations/loc-1/pools/kael/set-opposition", json={"opponent_id": "guard"})

        client.post("/api/v1/locations/loc-1/pools/kael/set", json={"total": 10, "effect_die": "d8", "pipeline": "pool"})
        client.post("/api/v1/locations/loc-1/pools/guard/set", json={"total": 14, "effect_die": "d6", "pipeline": "pool"})

        # The holder (guard) is not pending → push blocked.
        assert client.post("/api/v1/locations/loc-1/pools/guard/push").json()["status"] == "not_allowed"
        # The pending side pushes.
        assert client.post("/api/v1/locations/loc-1/pools/kael/push").json()["status"] == "pushed"
        # No fresh compare since → pushing again is blocked for being not-pending, not for a repeat cap.
        assert client.post("/api/v1/locations/loc-1/pools/kael/push").json()["status"] == "not_allowed"

    def test_push_can_repeat_when_pending_again(self, client):
        _save_pool(client, "loc-1", "kael", [("d10", "intelligence")])
        _save_pool(client, "loc-1", "guard", [("d8", "agility")])
        client.post("/api/v1/locations/loc-1/pools/kael/set-opposition", json={"opponent_id": "guard"})

        # Round 1: guard beats kael → kael is pending and pushes.
        client.post("/api/v1/locations/loc-1/pools/kael/set", json={"total": 10, "effect_die": "d8", "pipeline": "pool"})
        client.post("/api/v1/locations/loc-1/pools/guard/set", json={"total": 14, "effect_die": "d6", "pipeline": "pool"})
        assert client.post("/api/v1/locations/loc-1/pools/kael/push").json()["status"] == "pushed"

        # Round 2: kael beats guard → guard is pending and pushes.
        client.post("/api/v1/locations/loc-1/pools/kael/set", json={"total": 16, "effect_die": "d8", "pipeline": "pool"})
        assert client.post("/api/v1/locations/loc-1/pools/guard/push").json()["status"] == "pushed"

        # Round 3: guard beats kael again → kael is pending a second time and may push again.
        client.post("/api/v1/locations/loc-1/pools/guard/set", json={"total": 18, "effect_die": "d6", "pipeline": "pool"})
        assert client.post("/api/v1/locations/loc-1/pools/kael/push").json()["status"] == "pushed"

    def test_tie_favors_initiative_holder(self, client):
        _save_pool(client, "loc-1", "kael", [("d10", "intelligence")])
        _save_pool(client, "loc-1", "guard", [("d8", "agility")])
        client.post("/api/v1/locations/loc-1/pools/kael/set-opposition", json={"opponent_id": "guard"})

        # Round 1 tie: challenger holds initiative, defendant must beat → challenger wins.
        client.post("/api/v1/locations/loc-1/pools/kael/set", json={"total": 12, "effect_die": "d8", "pipeline": "pool"})
        r = client.post("/api/v1/locations/loc-1/pools/guard/set", json={"total": 12, "effect_die": "d6", "pipeline": "pool"})
        assert r.json()["winner"] == "player"



def test_an_outcome_effect_steps_the_result_the_contest_resolves_on(client, monkeypatch):
    """The set endpoint's order: store → fire effects → compare once.

    A Step Up Effect firing on ``on_set`` must land on the committed result *before*
    the compare, so the resolution uses the stepped effect die. Staged here by
    applying the real effect from inside the fired callback, which is what the
    engine does on that path.
    """
    from transversal.domain import CommittedResult
    from transversal.domain import DieType
    from transversal.domain import Entity
    from transversal.domain import EntityType
    from transversal.domain import Effect
    from transversal.domain import EffectTiming
    from transversal.services.effects_applier import apply_effects
    from transversal.services.state_events import fire_state_sfx

    from transversal.services import contest_tracker as ct_module
    from transversal.services import state_events as se_module

    _save_pool(client, "loc-1", "kael", [("d10", "intelligence")])
    client.post("/api/v1/locations/loc-1/pools/kael/set-opposition", json={"opponent_id": "guard"})

    real_fire = fire_state_sfx

    def fire_then_step(entity_id, universe, event, context=None, **kw):
        real_fire(entity_id, universe, event, context, **kw)
        if event != "on_set":
            return
        # The committed result is already stored, so the effect can step it.
        kael = Entity(id="kael", type=EntityType.CHARACTER, name="Kael",
                      current_universe="earth", current_location="loc-1")
        apply_effects(kael, [Effect(timing=EffectTiming.IMMEDIATE, type="modify_outcome",
                                    action="step_up_effect")], None)

    monkeypatch.setattr(se_module, "fire_state_sfx", fire_then_step)

    r = client.post("/api/v1/locations/loc-1/pools/kael/set",
                    json={"total": 12, "effect_die": "d6", "pipeline": "pool"})
    assert r.status_code == 200, r.text

    ct = ct_module.get_contest_tracker()
    kael_state, _ = ct.get_contestants("loc-1", "kael")
    # The stored result carries the stepped die, not the one the client sent.
    assert kael_state.committed.effect_die == DieType.D8


class TestCancelContest:
    """The empty-pool exit for a mis-started contest ([[B118]])."""

    def test_initiator_can_cancel_before_adding_dice(self, client):
        _save_pool(client, "loc-1", "guard", [("d8", "agility")])
        client.post("/api/v1/locations/loc-1/pools/kael/set-opposition", json={"opponent_id": "guard"})

        r = client.post("/api/v1/locations/loc-1/pools/kael/cancel")
        assert r.status_code == 200, r.text
        assert r.json() == {"status": "cancelled"}

        # A contest is shared state: the opponent must not be left holding a
        # challenge to nothing, or the pair still reads as an active contest.
        ct = ct_module.get_contest_tracker()
        assert ct.get("loc-1", "kael") is None
        assert ct.get("loc-1", "guard") is None
        # The opponent's assembled dice are not the canceller's to throw away.
        assert ss_module.get_scene_store().get_pool("loc-1", "guard")

    def test_only_the_initiator_may_cancel(self, client):
        _save_pool(client, "loc-1", "kael", [])
        client.post("/api/v1/locations/loc-1/pools/kael/set-opposition", json={"opponent_id": "guard"})

        r = client.post("/api/v1/locations/loc-1/pools/guard/cancel")
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "not_allowed"
        assert ct_module.get_contest_tracker().get("loc-1", "kael") is not None

    def test_cancel_blocked_once_dice_are_added(self, client):
        _save_pool(client, "loc-1", "kael", [("d10", "intelligence")])
        client.post("/api/v1/locations/loc-1/pools/kael/set-opposition", json={"opponent_id": "guard"})

        # With dice on the table there is a contest to resolve, not to cancel —
        # give-in is how a side leaves that one.
        r = client.post("/api/v1/locations/loc-1/pools/kael/cancel")
        assert r.json()["status"] == "not_allowed"
        assert ct_module.get_contest_tracker().get("loc-1", "kael") is not None

    def test_cancel_without_a_contest_is_a_no_op(self, client):
        r = client.post("/api/v1/locations/loc-1/pools/kael/cancel")
        assert r.json() == {"status": "no_contest"}
