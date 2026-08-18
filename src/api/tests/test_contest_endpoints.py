"""Tests for the contest-pool REST endpoints.

Verifies the resolve endpoint returns the full ContestResult (rolls +
effect dice + stakes), not a stripped summary.  Pools are stored via the
scene-state endpoint; contest endpoints own opposition + resolution.
"""

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


def _add_dice(client, location_id, entity_id, dice):
    """Save a full pool via the scene-state endpoint."""
    wire = [
        {"die": die, "source_kind": "manual", "source_id": source, "label": source, "ts_id": None}
        for die, source in dice
    ]
    r = client.put(f"/api/v1/locations/{location_id}/pools/{entity_id}", json={"dice": wire})
    assert r.status_code == 200, r.text


class TestResolveEndpoint:
    def test_resolve_returns_full_rolls_and_effect_dice(self, client):
        _add_dice(client, "loc-1", "kael", [
            ("d10", "intelligence"),
            ("d8", "hacking"),
            ("d8", "distinction"),
        ])
        _add_dice(client, "loc-1", "guard", [
            ("d8", "agility"),
            ("d6", "awareness"),
            ("d6", "wary"),
        ])
        r = client.post(
            "/api/v1/locations/loc-1/pools/kael/set-opposition",
            json={"opponent_id": "guard"},
        )
        assert r.status_code == 200, r.text

        r = client.post("/api/v1/locations/loc-1/pools/kael/resolve")
        assert r.status_code == 200, r.text
        data = r.json()

        assert data["kind"] == "contest"
        assert data["winner"] in ("player", "opponent")
        assert "stakes" in data

        for side in ("player_result", "opponent_result"):
            side_data = data[side]
            assert side_data["pipeline"] == "pool"
            assert len(side_data["rolls"]) == 3
            assert side_data["total"] is not None
            assert side_data["effect_die"] in ("d4", "d6", "d8", "d10", "d12")

    def test_resolve_409_without_both_pools(self, client):
        _add_dice(client, "loc-1", "kael", [("d10", "intelligence")])
        client.post(
            "/api/v1/locations/loc-1/pools/kael/set-opposition",
            json={"opponent_id": "guard"},
        )
        r = client.post("/api/v1/locations/loc-1/pools/kael/resolve")
        assert r.status_code == 409
