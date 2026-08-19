"""Tests for the manual contest REST endpoints (challenge / set / give-in)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from transversal.api.rest.contest_pools import router as contest_pools_router
from transversal.api.rest.scene_state import router as scene_state_router
from transversal.services import contest_tracker as ct_module
from transversal.services import scene_state as ss_module
from transversal.services.contest_tracker import ContestTracker
from transversal.services.scene_state import SceneStateStore


@pytest.fixture
def client():
    # Fresh tracker + scene store so state doesn't leak between tests.
    ct_module._contest_tracker = ContestTracker()
    ss_module._store = SceneStateStore()
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

    def test_push_blocked_when_not_pending_or_already_pushed(self, client):
        _save_pool(client, "loc-1", "kael", [("d10", "intelligence")])
        _save_pool(client, "loc-1", "guard", [("d8", "agility")])
        client.post("/api/v1/locations/loc-1/pools/kael/set-opposition", json={"opponent_id": "guard"})

        client.post("/api/v1/locations/loc-1/pools/kael/set", json={"total": 10, "effect_die": "d8", "pipeline": "pool"})
        client.post("/api/v1/locations/loc-1/pools/guard/set", json={"total": 14, "effect_die": "d6", "pipeline": "pool"})

        # The holder (guard) is not pending → push blocked.
        assert client.post("/api/v1/locations/loc-1/pools/guard/push").json()["status"] == "not_allowed"
        # Pending side pushes once.
        assert client.post("/api/v1/locations/loc-1/pools/kael/push").json()["status"] == "pushed"
        # ...and cannot push again.
        assert client.post("/api/v1/locations/loc-1/pools/kael/push").json()["status"] == "not_allowed"

    def test_tie_favors_initiative_holder(self, client):
        _save_pool(client, "loc-1", "kael", [("d10", "intelligence")])
        _save_pool(client, "loc-1", "guard", [("d8", "agility")])
        client.post("/api/v1/locations/loc-1/pools/kael/set-opposition", json={"opponent_id": "guard"})

        # Round 1 tie: challenger holds initiative, defendant must beat → challenger wins.
        client.post("/api/v1/locations/loc-1/pools/kael/set", json={"total": 12, "effect_die": "d8", "pipeline": "pool"})
        r = client.post("/api/v1/locations/loc-1/pools/guard/set", json={"total": 12, "effect_die": "d6", "pipeline": "pool"})
        assert r.json()["winner"] == "player"

