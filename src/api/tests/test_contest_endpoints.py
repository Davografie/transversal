"""Tests for the contest-pool REST endpoints.

Verifies the resolve endpoint returns the full ContestResult (rolls +
effect dice + stakes), not a stripped summary.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from transversal.api.rest.contest_pools import router as contest_pools_router
from transversal.services import contest_tracker as ct_module
from transversal.services.contest_tracker import ContestTracker


@pytest.fixture
def client():
    # Fresh tracker so pool state doesn't leak between tests.
    ct_module._contest_tracker = ContestTracker()
    app = FastAPI()
    app.include_router(contest_pools_router)
    return TestClient(app)


def _add_dice(client, location_id, entity_id, dice):
    for die, source in dice:
        r = client.post(
            f"/api/v1/locations/{location_id}/pools/{entity_id}/add-die",
            json={"die": die, "source": source},
        )
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
        assert data["winner"] in ("player", "opponent", "tie_defender")
        assert "stakes" in data

        for side in ("player_result", "opponent_result"):
            side_data = data[side]
            assert side_data["pipeline"] == "pool"
            assert len(side_data["rolls"]) == 3
            assert side_data["total"] is not None
            assert side_data["effect_die"] in ("d4", "d6", "d8", "d10", "d12")
