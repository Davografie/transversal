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
        store.save_pool("loc-1", "kael-1", dice)
        assert store.get_pool("loc-1", "kael-1") == dice
        assert store.get_pool("loc-1", "kael-2") == []

    def test_pool_is_keyed_by_entity(self, store):
        store.save_pool("loc-1", "kael-1", [_die()])
        # Same location, different entity → empty
        assert store.get_pool("loc-1", "kael-2") == []

    def test_list_entities_and_get_pools_at(self, store):
        store.save_pool("loc-1", "kael-1", [_die()])
        store.save_pool("loc-1", "guard-1", [_die(die="d6")])
        assert set(store.list_entities("loc-1")) == {"kael-1", "guard-1"}
        assert set(store.get_pools_at("loc-1").keys()) == {"kael-1", "guard-1"}
        assert store.get_pools_at("loc-2") == {}

    def test_list_all_pools_across_locations(self, store):
        store.save_pool("loc-1", "kael-1", [_die()])
        store.save_pool("loc-2", "guard-1", [_die(die="d6")])
        all_pools = store.list_all_pools()
        assert set(all_pools.keys()) == {"kael-1", "guard-1"}
        assert all_pools["kael-1"][0]["die"] == "d8"
        assert all_pools["guard-1"][0]["die"] == "d6"

    def test_clear_pool(self, store):
        store.save_pool("loc-1", "kael-1", [_die()])
        store.clear_pool("loc-1", "kael-1")
        assert store.get_pool("loc-1", "kael-1") == []

    def test_difficulty_roundtrip(self, store):
        assert store.get_difficulty("loc-1") is None
        store.set_difficulty("loc-1", 11)
        assert store.get_difficulty("loc-1") == 11

    def test_clear_difficulty(self, store):
        store.set_difficulty("loc-1", 11)
        store.clear_difficulty("loc-1")
        assert store.get_difficulty("loc-1") is None

    def test_clear_location(self, store):
        store.save_pool("loc-1", "kael-1", [_die()])
        store.set_difficulty("loc-1", 9)
        store.clear_location("loc-1")
        assert store.get_pool("loc-1", "kael-1") == []
        assert store.get_difficulty("loc-1") is None


class TestTraitResync:
    def test_resync_trait_die_updates_matching_die(self, store):
        store.save_pool("loc-1", "kael-1", [
            {"die": "d8", "source_kind": "trait", "source_id": "ts-x", "label": "Hacking", "ts_id": "ts-x"},
            {"die": "d6", "source_kind": "manual", "source_id": "", "label": "d6", "ts_id": None},
        ])
        touched = store.resync_trait_die("kael-1", "ts-x", ["d10"])
        assert touched == [("loc-1", "kael-1")]
        assert store.get_pool("loc-1", "kael-1")[0]["die"] == "d10"
        assert store.get_pool("loc-1", "kael-1")[1]["die"] == "d6"

    def test_resync_skips_other_entities(self, store):
        store.save_pool("loc-1", "kael-1", [{"die": "d8", "ts_id": "ts-x"}])
        store.save_pool("loc-1", "guard-1", [{"die": "d8", "ts_id": "ts-x"}])
        touched = store.resync_trait_die("kael-1", "ts-x", ["d10"])
        assert touched == [("loc-1", "kael-1")]
        assert store.get_pool("loc-1", "guard-1")[0]["die"] == "d8"

    def test_resync_multi_die_updates_each_matching_die_positionally(self, store):
        ss_module._store = store
        store.save_pool("loc-1", "kael-1", [
            {"die": "d8", "ts_id": "ts-x"},
            {"die": "d8", "ts_id": "ts-x"},
        ])
        ss_module.resync_pool_dice_for_trait("kael-1", "ts-x", ["d10", "d8"])
        assert [d["die"] for d in store.get_pool("loc-1", "kael-1")] == ["d10", "d8"]

    def test_resync_multi_die_maps_mixed_ratings(self, store):
        ss_module._store = store
        store.save_pool("loc-1", "kael-1", [
            {"die": "d10", "ts_id": "ts-x"},
            {"die": "d8", "ts_id": "ts-x"},
        ])
        ss_module.resync_pool_dice_for_trait("kael-1", "ts-x", ["d8", "d10"])
        assert [d["die"] for d in store.get_pool("loc-1", "kael-1")] == ["d8", "d10"]

    def test_resync_ignores_extra_matching_dice(self, store):
        ss_module._store = store
        store.save_pool("loc-1", "kael-1", [
            {"die": "d8", "ts_id": "ts-x"},
            {"die": "d8", "ts_id": "ts-x"},
        ])
        ss_module.resync_pool_dice_for_trait("kael-1", "ts-x", ["d10"])
        assert [d["die"] for d in store.get_pool("loc-1", "kael-1")] == ["d10", "d8"]


class TestSceneStateEndpoints:
    def test_pool_save_and_get(self, client):
        dice = [_die()]
        r = client.put("/api/v1/locations/loc-1/pools/kael-1", json={"dice": dice})
        assert r.status_code == 200, r.text

        r = client.get("/api/v1/locations/loc-1/pools/kael-1")
        assert r.status_code == 200, r.text
        assert r.json()["dice"] == dice

    def test_pool_is_entity_scoped(self, client):
        client.put("/api/v1/locations/loc-1/pools/kael-1", json={"dice": [_die()]})
        r = client.get("/api/v1/locations/loc-1/pools/kael-2")
        assert r.json()["dice"] == []

    def test_list_pools(self, client):
        client.put("/api/v1/locations/loc-1/pools/kael-1", json={"dice": [_die()]})
        client.put("/api/v1/locations/loc-1/pools/guard-1", json={"dice": [_die(die="d6")]})
        r = client.get("/api/v1/locations/loc-1/pools")
        assert r.status_code == 200, r.text
        assert set(r.json()["pools"].keys()) == {"kael-1", "guard-1"}

    def test_difficulty_save_and_get(self, client):
        r = client.put("/api/v1/locations/loc-1/difficulty", json={"difficulty": 12})
        assert r.status_code == 200, r.text
        r = client.get("/api/v1/locations/loc-1/difficulty")
        assert r.json()["difficulty"] == 12

    def test_difficulty_unset_is_null(self, client):
        r = client.get("/api/v1/locations/loc-1/difficulty")
        assert r.json()["difficulty"] is None

    def test_next_beat_clears_difficulty(self, client):
        client.put("/api/v1/locations/loc-1/difficulty", json={"difficulty": 12})
        r = client.post("/api/v1/locations/loc-1/next-beat")
        assert r.status_code == 200, r.text
        r = client.get("/api/v1/locations/loc-1/difficulty")
        assert r.json()["difficulty"] is None
