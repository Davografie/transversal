"""Tests for the Blue Book records tests and contests write ([[B177]]).

The contest entry is the interesting one: a push clears the pusher's committed
result, so before this the round before a push was simply gone. These tests pin
that the rounds survive, that they stack in one entry, and that a side which did
not re-roll is carried forward as ``standing`` rather than shown rolling twice.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from transversal.api.rest.contest_pools import router as contest_pools_router
from transversal.api.rest.roll import router as roll_router
from transversal.api.rest.scene_state import router as scene_state_router
from transversal.services import contest_history
from transversal.services import contest_tracker as ct_module
from transversal.services import scene_state as ss_module
from transversal.services.contest_tracker import ContestTracker
from transversal.services.scene_state import SceneStateStore

NAMES = {"kael": "Kael Drift", "guard": "Viktor Antonov", "loc-1": "Krasnoyarsk-45"}


class _Entity:
    def __init__(self, name):
        self.name = name


class RecordingRepo:
    """Minimal repository double — keeps every Blue Book write."""

    def __init__(self):
        self.records = []

    def add_historical_record(self, entity_id, record_type, data, universe="", session_id="", after_ids=None):
        self.records.append(
            {
                "entity_id": entity_id,
                "record_type": record_type.value if hasattr(record_type, "value") else record_type,
                "data": data,
                "universe": universe,
            }
        )

    def get_entity(self, entity_id):
        return _Entity(NAMES.get(entity_id, entity_id))

    def for_entity(self, entity_id):
        return [r for r in self.records if r["entity_id"] == entity_id]


@pytest.fixture
def repo():
    return RecordingRepo()


@pytest.fixture
def client(repo):
    ct_module._contest_tracker = ContestTracker()
    ss_module._store = SceneStateStore()
    contest_history._repo_getter = lambda: repo
    app = FastAPI()
    app.include_router(scene_state_router)
    app.include_router(contest_pools_router)
    app.include_router(roll_router)
    yield TestClient(app)
    contest_history._repo_getter = None


def _roll_pool(location_id, entity_id, dice):
    """Seed a rolled pool in the scene store: (die, label, result, role)."""
    ss_module.get_scene_store().save_pool(
        location_id,
        entity_id,
        [
            {
                "die": die,
                "source_kind": "trait",
                "source_id": label,
                "label": label,
                "result": result,
                "hitch": result == 1,
                "role": role,
                "resource": False,
            }
            for die, label, result, role in dice
        ],
    )


def _set(client, entity_id, total, effect_die="d8", location_id="loc-1"):
    r = client.post(
        f"/api/v1/locations/{location_id}/pools/{entity_id}/set",
        json={"total": total, "effect_die": effect_die, "pipeline": "pool"},
    )
    assert r.status_code == 200, r.text
    return r.json()


def _challenge(client, challenger="kael", opponent="guard", location_id="loc-1"):
    r = client.post(
        f"/api/v1/locations/{location_id}/pools/{challenger}/set-opposition",
        json={"opponent_id": opponent},
    )
    assert r.status_code == 200, r.text


class TestContestEntry:
    def test_each_participant_gets_their_own_entry(self, client, repo):
        _roll_pool(
            "loc-1",
            "kael",
            [("d10", "Intelligence", 7, "total"), ("d8", "Hacking", 5, "total"), ("d8", "Distinction", 1, None)],
        )
        _roll_pool("loc-1", "guard", [("d8", "Agility", 6, "total"), ("d6", "Awareness", 4, "total")])
        _challenge(client)

        _set(client, "kael", 12, "d8")
        _set(client, "guard", 10, "d6")

        kael, guard = repo.for_entity("kael"), repo.for_entity("guard")
        assert len(kael) == 1 and len(guard) == 1
        assert kael[0]["record_type"] == "contest"

        entry = kael[0]["data"]
        assert entry["kind"] == "contest"
        assert entry["own_entity_id"] == "kael"
        assert entry["own_name"] == "Kael Drift"
        assert entry["opposition_entity_id"] == "guard"
        assert entry["opposition_name"] == "Viktor Antonov"
        assert entry["location_name"] == "Krasnoyarsk-45"
        assert entry["result"] == "win"
        assert entry["effect_die"] == "d8"

        assert len(entry["rounds"]) == 1
        own = entry["rounds"][0]["own"]
        assert own["total"] == 12
        assert [d["result"] for d in own["dice"]] == [7, 5, 1]
        # The kept dice and the effect die come from the pool's server-side roles.
        assert [d["role"] for d in own["dice"]] == ["total", "total", None]
        assert own["dice"][2]["hitch"] is True
        assert [d["label"] for d in own["dice"]] == ["Intelligence", "Hacking", "Distinction"]

        # The opponent's entry reads the other way round, from their own side.
        other = guard[0]["data"]
        assert other["result"] == "loss"
        assert other["own_entity_id"] == "guard"
        assert other["opposition_entity_id"] == "kael"
        assert other["rounds"][0]["own"]["total"] == 10
        assert other["rounds"][0]["opposition"]["total"] == 12

    def test_a_push_stacks_rounds_and_carries_the_standing_roll(self, client, repo):
        _roll_pool("loc-1", "kael", [("d10", "Intelligence", 6, "total"), ("d8", "Hacking", 4, "total")])
        _roll_pool("loc-1", "guard", [("d8", "Agility", 8, "total"), ("d6", "Awareness", 6, "total")])
        _challenge(client)

        # Round 1: guard beats kael → kael is pending.
        _set(client, "kael", 10, "d8")
        _set(client, "guard", 14, "d6")
        assert client.post("/api/v1/locations/loc-1/pools/kael/push").json()["status"] == "pushed"

        # Round 2: only kael re-rolls; guard's 14 stands as the number to beat.
        _roll_pool("loc-1", "kael", [("d10", "Intelligence", 9, "total"), ("d8", "Hacking", 8, "total")])
        compare = _set(client, "kael", 17, "d8")
        assert compare["status"] == "compare"
        assert compare["pending"] == "guard"

        # Guard concedes, so the entry is finalised with both rounds on it.
        assert client.post("/api/v1/locations/loc-1/pools/guard/give-in").status_code == 200

        entry = repo.for_entity("kael")[0]["data"]
        assert [r["round"] for r in entry["rounds"]] == [1, 2]

        first, second = entry["rounds"]
        assert first["own"]["total"] == 10
        assert first["opposition"]["total"] == 14
        assert first["opposition"]["standing"] is False
        # Round 2 keeps its own dice — the round the push would previously have lost.
        assert second["own"]["total"] == 17
        assert [d["result"] for d in second["own"]["dice"]] == [9, 8]
        assert second["own"]["standing"] is False
        # And the opponent's round-1 roll is carried forward, not re-rolled.
        assert second["opposition"]["total"] == 14
        assert second["opposition"]["standing"] is True

    def test_give_in_before_a_compare_records_the_initiators_roll(self, client, repo):
        _roll_pool("loc-1", "kael", [("d10", "Intelligence", 9, "total"), ("d8", "Hacking", 6, "total")])
        _challenge(client)

        # The initiator commits, nobody opposes, then the opponent concedes —
        # no compare ever ran, so the roll has to be frozen on the give-in path.
        _set(client, "kael", 15, "d8")
        assert client.post("/api/v1/locations/loc-1/pools/guard/give-in").status_code == 200

        entry = repo.for_entity("kael")[0]["data"]
        assert entry["result"] == "win"
        assert len(entry["rounds"]) == 1
        assert entry["rounds"][0]["own"]["total"] == 15
        assert entry["rounds"][0]["decision"] == "gave_in"

        # The conceding side still gets an entry, with an empty own half.
        conceded = repo.for_entity("guard")[0]["data"]
        assert conceded["result"] == "gave_in"
        assert conceded["rounds"][0]["own"]["dice"] == []
        assert conceded["rounds"][0]["opposition"]["total"] == 15

    def test_a_repeated_set_does_not_write_the_entry_twice(self, client, repo):
        _roll_pool("loc-1", "kael", [("d10", "Intelligence", 7, "total")])
        _roll_pool("loc-1", "guard", [("d8", "Agility", 6, "total")])
        _challenge(client)

        _set(client, "kael", 12, "d8")
        _set(client, "guard", 10, "d6")
        assert len(repo.for_entity("kael")) == 1

        # A stray re-commit on an already-resolved contest must not append again.
        _set(client, "kael", 12, "d8")
        assert len(repo.for_entity("kael")) == 1


class TestTestEntry:
    def test_a_resolved_test_records_the_difficulty_it_was_rolled_against(self, client, repo):
        _roll_pool("loc-1", "kael", [("d10", "Intelligence", 8, "total"), ("d8", "Hacking", 6, "total")])
        r = client.put("/api/v1/locations/loc-1/difficulty", json={"difficulty": 11})
        assert r.status_code == 200, r.text

        assert client.post("/api/v1/locations/loc-1/pools/kael/resolve").status_code == 200

        records = repo.for_entity("kael")
        assert len(records) == 1
        assert records[0]["record_type"] == "test"

        data = records[0]["data"]
        assert data["kind"] == "test"
        assert data["result"] == "win"
        assert data["own_name"] == "Kael Drift"
        # The opposition is a place, not a person.
        assert data["opposition_entity_id"] == ""
        assert data["opposition_name"] == "Krasnoyarsk-45"

        round_one = data["rounds"][0]
        assert round_one["own"]["total"] == 14
        assert [d["role"] for d in round_one["own"]["dice"]] == ["total", "total"]
        assert round_one["opposition"]["difficulty"] == 11
        assert round_one["opposition"]["total"] == 11

    def test_a_failed_test_reads_as_a_loss(self, client, repo):
        _roll_pool("loc-1", "kael", [("d10", "Intelligence", 4, "total")])
        client.put("/api/v1/locations/loc-1/difficulty", json={"difficulty": 11})
        client.post("/api/v1/locations/loc-1/pools/kael/resolve")

        assert repo.for_entity("kael")[0]["data"]["result"] == "loss"

    def test_a_test_with_no_difficulty_is_unopposed(self, client, repo):
        _roll_pool("loc-1", "kael", [("d10", "Intelligence", 9, "total")])
        client.post("/api/v1/locations/loc-1/pools/kael/resolve")

        data = repo.for_entity("kael")[0]["data"]
        assert data["result"] == "unopposed"
        assert data["rounds"][0]["opposition"]["difficulty"] is None
