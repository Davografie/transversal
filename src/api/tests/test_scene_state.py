"""Tests for the in-memory scene-state store and its REST endpoints."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from transversal.api.rest.scene_state import router as scene_state_router
from transversal.services import scene_state as ss_module
from transversal.services.scene_state import SceneStateStore


@pytest.fixture
def store():
    # Fresh store so state doesn't leak between tests.
    return SceneStateStore()


@pytest.fixture
def client():
    ss_module._store = SceneStateStore()
    app = FastAPI()
    app.include_router(scene_state_router)
    return TestClient(app)


def _die(die="d8", kind="trait", sid="ts-hacking", label="Hacking", ts_id="ts-hacking"):
    return {"die": die, "source_kind": kind, "source_id": sid, "label": label, "ts_id": ts_id}


class TestSceneStateStore:
    def test_pool_save_get_roundtrip(self, store):
        dice = [_die(), _die(die="d6", kind="difficulty", label="2d6", ts_id=None)]
        store.save_pool("loc-1", "player-1", dice)
        assert store.get_pool("loc-1", "player-1") == dice
        assert store.get_pool("loc-1", "player-2") == []

    def test_pool_is_keyed_by_player_not_entity(self, store):
        store.save_pool("loc-1", "player-1", [_die()])
        # Same location, different player → empty
        assert store.get_pool("loc-1", "player-2") == []

    def test_clear_pool(self, store):
        store.save_pool("loc-1", "player-1", [_die()])
        store.clear_pool("loc-1", "player-1")
        assert store.get_pool("loc-1", "player-1") == []

    def test_difficulty_roundtrip(self, store):
        assert store.get_difficulty("loc-1") is None
        store.set_difficulty("loc-1", 11)
        assert store.get_difficulty("loc-1") == 11

    def test_clear_location(self, store):
        store.save_pool("loc-1", "player-1", [_die()])
        store.set_difficulty("loc-1", 9)
        store.clear_location("loc-1")
        assert store.get_pool("loc-1", "player-1") == []
        assert store.get_difficulty("loc-1") is None


class TestSceneStateEndpoints:
    def test_pool_save_and_get(self, client):
        dice = [_die()]
        r = client.put("/api/v1/locations/loc-1/players/player-1/pool", json={"dice": dice})
        assert r.status_code == 200, r.text

        r = client.get("/api/v1/locations/loc-1/players/player-1/pool")
        assert r.status_code == 200, r.text
        assert r.json()["dice"] == dice

    def test_pool_is_player_scoped(self, client):
        client.put("/api/v1/locations/loc-1/players/player-1/pool", json={"dice": [_die()]})
        r = client.get("/api/v1/locations/loc-1/players/player-2/pool")
        assert r.json()["dice"] == []

    def test_difficulty_save_and_get(self, client):
        r = client.put("/api/v1/locations/loc-1/difficulty", json={"difficulty": 12})
        assert r.status_code == 200, r.text
        r = client.get("/api/v1/locations/loc-1/difficulty")
        assert r.json()["difficulty"] == 12

    def test_difficulty_unset_is_null(self, client):
        r = client.get("/api/v1/locations/loc-1/difficulty")
        assert r.json()["difficulty"] is None
