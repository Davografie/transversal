"""Tests for the decomposed roll endpoints (P2.10d G5)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from transversal.api.rest.roll import router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _roll(client, path, dice):
    r = client.post(f"/api/v1{path}", json={
        "entity_id": "ghost-1",
        "universe": "earth",
        "dice": dice,
    })
    assert r.status_code == 200, r.text
    return r.json()


def test_cortex_roll_returns_rolls_and_hitches_only(client):
    data = _roll(client, "/cortex-roll", [["d8", "a"], ["d6", "b"], ["d8", "c"]])
    assert data["pipeline"] == "pool"
    assert len(data["rolls"]) == 3
    assert all("result" in r for r in data["rolls"])
    # No auto-picking: total/effect are the client's job.
    assert "total" not in data
    assert "effect_die" not in data
    assert "kept" not in data


def test_simplified_roll_derives_highest_tier_effect(client):
    data = _roll(client, "/simplified-roll", [["d8", "a"], ["d6", "b"]])
    assert data["pipeline"] == "simplified"
    assert data["highest"] == max(r["result"] for r in data["rolls"])
    assert "tier" in data and "effect_die" in data


def test_difficulty_roll_returns_rolls_only(client):
    data = _roll(client, "/difficulty-roll", [["d8", "diff"], ["d8", "diff"]])
    assert data["pipeline"] == "pool"
    assert len(data["rolls"]) == 2
    assert "hitches" not in data
    assert "botch" not in data
