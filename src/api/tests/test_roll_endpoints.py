"""Tests for the stateful roll endpoints (P2.10d G5)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from transversal.api.rest.roll import router as roll_router
from transversal.api.rest.scene_state import router as scene_router
from transversal.services import scene_state as ss_module
from transversal.services.scene_state import SceneStateStore


@pytest.fixture
def client():
    ss_module._store = SceneStateStore()
    app = FastAPI()
    app.include_router(scene_router)
    app.include_router(roll_router)
    return TestClient(app)


def _save(client, location_id, entity_id, dice):
    r = client.put(f"/api/v1/locations/{location_id}/pools/{entity_id}", json={"dice": dice})
    assert r.status_code == 200, r.text


def _die(die, sid="trait"):
    return {"die": die, "source_kind": "trait", "source_id": sid, "label": sid}


def test_cortex_roll_enriches_pool_with_result_and_hitch(client):
    _save(client, "loc-1", "e1", [_die("d8"), _die("d6"), _die("d8")])
    r = client.post("/api/v1/locations/loc-1/pools/e1/cortex-roll")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["pipeline"] == "pool"
    assert len(data["rolls"]) == 3
    for d in data["rolls"]:
        assert "result" in d and isinstance(d["result"], int)
        assert "hitch" in d
        assert "role" in d and d["role"] is None
        assert "tier" in d
        assert "effect_die" in d
        # The tier maps the raw result per the Outcome Tiers table.
        if d["result"] <= 2:
            assert d["tier"] == "fail" and d["effect_die"] is None
        elif d["result"] <= 5:
            assert d["tier"] == "marginal" and d["effect_die"] == "d4"
        elif d["result"] <= 8:
            assert d["tier"] == "success" and d["effect_die"] == "d6"
        elif d["result"] <= 11:
            assert d["tier"] == "exceptional" and d["effect_die"] == "d8"
        else:
            assert d["tier"] == "perfect" and d["effect_die"] == "d10"
    assert "total" not in data
    assert "effect_die" not in data


def test_cortex_roll_flags_hitch(client):
    _save(client, "loc-1", "e1", [_die("d4")])
    # A d4 roll of 1 is a hitch — retry until we observe one deterministically.
    r = client.post("/api/v1/locations/loc-1/pools/e1/cortex-roll")
    data = r.json()
    for d in data["rolls"]:
        assert d["hitch"] == (d["result"] == 1)


def test_simplified_roll_derives_highest_tier_effect(client):
    _save(client, "loc-1", "e1", [_die("d8"), _die("d6")])
    r = client.post("/api/v1/locations/loc-1/pools/e1/simplified-roll")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["pipeline"] == "simplified"
    assert data["highest"] == max(d["result"] for d in data["rolls"])
    assert "tier" in data and "effect_die" in data


def test_difficulty_roll_uses_location_as_entity_key(client):
    _save(client, "loc-1", "loc-1", [_die("d6", "difficulty"), _die("d6", "difficulty")])
    r = client.post("/api/v1/locations/loc-1/pools/loc-1/difficulty-roll")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["pipeline"] == "pool"
    assert len(data["rolls"]) == 2
    assert all("result" in d for d in data["rolls"])


def test_select_flags_result_and_effect_dice(client):
    _save(client, "loc-1", "e1", [_die("d8"), _die("d6"), _die("d8")])
    client.post("/api/v1/locations/loc-1/pools/e1/cortex-roll")
    r = client.post(
        "/api/v1/locations/loc-1/pools/e1/select",
        json={"total_indices": [0, 2], "effect_index": 1},
    )
    assert r.status_code == 200, r.text
    roles = [d["role"] for d in r.json()["dice"]]
    assert roles == ["total", "effect", "total"]


def test_select_resets_previous_roles(client):
    _save(client, "loc-1", "e1", [_die("d8"), _die("d6"), _die("d8")])
    client.post("/api/v1/locations/loc-1/pools/e1/cortex-roll")
    client.post("/api/v1/locations/loc-1/pools/e1/select", json={"total_indices": [0, 2], "effect_index": 1})
    r = client.post("/api/v1/locations/loc-1/pools/e1/select", json={"total_indices": [1, 2]})
    roles = [d["role"] for d in r.json()["dice"]]
    assert roles == [None, "total", "total"]


def test_mark_hitches_bought_flags_dice(client):
    _save(client, "loc-1", "e1", [_die("d8"), _die("d6"), _die("d8")])
    client.post("/api/v1/locations/loc-1/pools/e1/cortex-roll")
    r = client.post("/api/v1/locations/loc-1/pools/e1/hitches/mark-bought", json={"indices": [0, 2]})
    assert r.status_code == 200, r.text
    dice = r.json()["dice"]
    assert dice[0]["bought"] is True
    assert dice[1]["bought"] is False
    assert dice[2]["bought"] is True


def test_list_all_pools_is_global(client):
    _save(client, "loc-1", "a", [_die("d8")])
    _save(client, "loc-2", "b", [_die("d6")])
    r = client.get("/api/v1/pools")
    assert r.status_code == 200, r.text
    assert set(r.json()["pools"].keys()) == {"a", "b"}


def test_activity_returns_grouped_pools_and_difficulties(client):
    from transversal.services.contest_tracker import get_contest_tracker
    get_contest_tracker().clear_all()
    _save(client, "loc-1", "a", [_die("d8")])
    _save(client, "loc-2", "b", [_die("d6")])
    client.put("/api/v1/locations/loc-1/difficulty", json={"difficulty": 12})
    r = client.get("/api/v1/activity")
    assert r.status_code == 200, r.text
    data = r.json()
    assert set(data["pools"].keys()) == {"loc-1", "loc-2"}
    assert data["pools"]["loc-1"]["a"][0]["die"] == "d8"
    assert data["pools"]["loc-2"]["b"][0]["die"] == "d6"
    assert data["difficulties"] == {"loc-1": 12}
    assert data["contests"] == []


class TestManualRoll:
    """[[B17]]: the faces come from physical dice, not the server."""

    def test_records_the_given_faces_and_enriches_the_pool(self, client):
        _save(client, "loc-1", "e1", [_die("d8"), _die("d6"), _die("d4")])
        r = client.post("/api/v1/locations/loc-1/pools/e1/manual-roll",
                        json={"results": [7, 1, 4]})
        assert r.status_code == 200, r.text
        data = r.json()

        assert data["pipeline"] == "pool"
        assert [d["result"] for d in data["rolls"]] == [7, 1, 4]
        # A 1 is a hitch, and the tier table maps the face exactly as a server roll would.
        assert [d["hitch"] for d in data["rolls"]] == [False, True, False]
        assert data["rolls"][0]["tier"] == "success" and data["rolls"][0]["effect_die"] == "d6"
        assert data["rolls"][2]["tier"] == "marginal" and data["rolls"][2]["effect_die"] == "d4"
        assert [d["role"] for d in data["rolls"]] == [None, None, None]
        assert [h["result"] for h in data["hitches"]] == [1]

    def test_the_pool_is_persisted_with_the_recorded_faces(self, client):
        _save(client, "loc-1", "e1", [_die("d10")])
        client.post("/api/v1/locations/loc-1/pools/e1/manual-roll", json={"results": [9]})

        stored = ss_module.get_scene_store().get_pool("loc-1", "e1")
        assert stored[0]["result"] == 9
        assert stored[0]["tier"] == "exceptional"

    def test_a_face_larger_than_its_die_is_refused(self, client):
        _save(client, "loc-1", "e1", [_die("d4"), _die("d8")])
        r = client.post("/api/v1/locations/loc-1/pools/e1/manual-roll",
                        json={"results": [5, 3]})
        assert r.status_code == 400
        assert "cannot show" in r.json()["detail"]
        # Nothing was recorded — a rejected entry must not half-apply.
        assert ss_module.get_scene_store().get_pool("loc-1", "e1")[0].get("result") is None

    def test_a_missing_face_is_refused(self, client):
        _save(client, "loc-1", "e1", [_die("d6"), _die("d6")])
        r = client.post("/api/v1/locations/loc-1/pools/e1/manual-roll",
                        json={"results": [3, None]})
        assert r.status_code == 400

    def test_a_count_mismatch_is_refused(self, client):
        _save(client, "loc-1", "e1", [_die("d6"), _die("d6")])
        r = client.post("/api/v1/locations/loc-1/pools/e1/manual-roll",
                        json={"results": [3]})
        assert r.status_code == 400
        assert "2 dice" in r.json()["detail"]

    def test_hitches_can_be_switched_off_for_a_difficulty_pool(self, client):
        _save(client, "loc-1", "loc-1", [_die("d6", "difficulty")])
        r = client.post("/api/v1/locations/loc-1/pools/loc-1/manual-roll",
                        json={"results": [1], "hitches": False})
        assert r.json()["hitches"] == [] and r.json()["botch"] is False
        assert r.json()["rolls"][0]["result"] == 1

    def test_no_pool_is_refused(self, client):
        r = client.post("/api/v1/locations/loc-1/pools/e1/manual-roll", json={"results": []})
        assert r.status_code == 400


class TestHitchRangeReachesTheRollEndpoints:
    """A widened hitch range is read from the entity, not sent by the client.

    The roller is a *view* of the rules ([[B231]]), so the endpoint has to ask the
    entity. These use ``manual-roll`` because it takes the faces outright — a
    server roll could not assert anything deterministic about a 2.
    """

    @staticmethod
    def _with_threshold(monkeypatch, threshold):
        """Pin the entity read, and stub the SFX firing that follows a roll.

        The roll endpoints fire roll SFX *after* enriching the dice, and those
        fire sites need a full repository. What is under test here is the hitch
        marking, so the firing is stubbed rather than mocked out a repository at a
        time — its own tests cover it.
        """
        from types import SimpleNamespace

        from transversal.domain import Entity, EntityType

        entities = {}

        def get_entity(eid):
            if eid not in entities:
                entities[eid] = Entity(
                    id=eid, type=EntityType.CHARACTER, name=eid,
                    current_universe="earth", hitch_threshold=threshold,
                )
            return entities[eid]

        monkeypatch.setattr(
            "transversal.main._get_repo",
            lambda: SimpleNamespace(get_entity=get_entity),
        )
        monkeypatch.setattr(
            "transversal.api.rest.roll._fire_entity_roll_sfx",
            lambda *a, **k: None,
        )
        # Saving the pool fires `on_pool_change`, which reaches the same repository.
        monkeypatch.setattr(
            "transversal.services.state_events.fire_pool_change_sfx",
            lambda *a, **k: None,
        )

    def test_a_two_hitches_when_the_entity_says_so(self, client, monkeypatch):
        self._with_threshold(monkeypatch, 2)
        _save(client, "loc-1", "e1", [_die("d6"), _die("d8"), _die("d8")])
        r = client.post("/api/v1/locations/loc-1/pools/e1/manual-roll",
                        json={"results": [2, 5, 6]})
        assert r.status_code == 200, r.text
        assert [d["result"] for d in r.json()["hitches"]] == [2]
        assert [d["hitch"] for d in r.json()["rolls"]] == [True, False, False]

    def test_a_two_is_ordinary_at_the_base_rule(self, client, monkeypatch):
        self._with_threshold(monkeypatch, 1)
        _save(client, "loc-1", "e1", [_die("d6"), _die("d8"), _die("d8")])
        r = client.post("/api/v1/locations/loc-1/pools/e1/manual-roll",
                        json={"results": [2, 5, 6]})
        assert r.json()["hitches"] == []
        assert [d["hitch"] for d in r.json()["rolls"]] == [False, False, False]

    def test_all_twos_are_not_a_botch(self, client, monkeypatch):
        """A widened range makes 2s buyable, not botching — a botch is all 1s."""
        self._with_threshold(monkeypatch, 2)
        _save(client, "loc-1", "e1", [_die("d6"), _die("d6")])
        r = client.post("/api/v1/locations/loc-1/pools/e1/manual-roll",
                        json={"results": [2, 2]})
        assert r.json()["botch"] is False
        assert len(r.json()["hitches"]) == 2

    def test_the_cortex_roll_reads_the_same_entity_field(self, client, monkeypatch):
        """The auto-roll path marks hitches by the same read (no client value)."""
        self._with_threshold(monkeypatch, 2)
        _save(client, "loc-1", "e1", [_die("d4"), _die("d4"), _die("d4")])
        r = client.post("/api/v1/locations/loc-1/pools/e1/cortex-roll")
        assert r.status_code == 200, r.text
        for d in r.json()["rolls"]:
            assert d["hitch"] == (d["result"] <= 2)
