"""Tests for the offer-negative trait endpoint."""

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from transversal.api.rest.scene_state import router as scene_state_router
from transversal.services import scene_state as ss_module
from transversal.services.scene_state import SceneStateStore


class FakeRepo:
    def __init__(self, trait, occupants):
        self.trait = trait
        self.occupants = occupants
        self.updated = []

    def get_traitsetting(self, ts_id):
        return self.trait if self.trait.id == ts_id else None

    def list_entities_by_location(self, location_id):
        return self.occupants

    def update_traitsetting(self, ts):
        self.updated.append(ts)


def _client(monkeypatch, trait, occupants):
    ss_module._store = SceneStateStore()
    monkeypatch.setattr("transversal.main._repo", FakeRepo(trait, occupants))
    app = FastAPI()
    app.include_router(scene_state_router)
    return TestClient(app)


def _trait(known_to):
    return SimpleNamespace(
        id="ts-neg-1", trait_id="trait-neg", entity_id="player", known_to=list(known_to),
    )


def _occupants(*ids):
    return [SimpleNamespace(id=i) for i in ids]


def test_offer_negative_reveals_and_fires_when_unknown(monkeypatch):
    fired = []
    monkeypatch.setattr(
        "transversal.services.state_events.fire_state_sfx",
        lambda entity_id, universe, event_type, context: fired.append((entity_id, event_type, context)),
    )
    trait = _trait(known_to=[])
    client = _client(monkeypatch, trait, _occupants("opponent", "bystander"))

    r = client.post(
        "/api/v1/locations/loc-1/pools/player/offer-negative",
        json={"opponent_id": "opponent", "trait_setting_id": "ts-neg-1", "dice": ["d8"], "label": "Fear"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data == {"offered": True, "removed": False, "newly_revealed": True}
    assert trait.known_to == ["opponent", "bystander"]
    assert fired == [
        ("player", "on_trait_offered", {
            "trait_id": "trait-neg",
            "trait_setting_id": "ts-neg-1",
            "owner": "player",
            "opponent": "opponent",
            "newly_revealed": "true",
        })
    ]

    # The trait dice land in the opponent's pool.
    pool = ss_module.get_scene_store().get_pool("loc-1", "opponent")
    assert len(pool) == 1
    assert pool[0]["ts_id"] == "ts-neg-1"


def test_offer_negative_no_payout_when_already_known(monkeypatch):
    fired = []
    monkeypatch.setattr(
        "transversal.services.state_events.fire_state_sfx",
        lambda entity_id, universe, event_type, context: fired.append((entity_id, event_type, context)),
    )
    trait = _trait(known_to=["opponent"])
    client = _client(monkeypatch, trait, _occupants("opponent"))

    r = client.post(
        "/api/v1/locations/loc-1/pools/player/offer-negative",
        json={"opponent_id": "opponent", "trait_setting_id": "ts-neg-1", "dice": ["d8"]},
    )
    data = r.json()
    assert data == {"offered": True, "removed": False, "newly_revealed": False}
    assert fired == []


def test_offer_negative_toggles_removal(monkeypatch):
    fired = []
    monkeypatch.setattr(
        "transversal.services.state_events.fire_state_sfx",
        lambda entity_id, universe, event_type, context: fired.append((entity_id, event_type, context)),
    )
    trait = _trait(known_to=[])
    client = _client(monkeypatch, trait, _occupants("opponent"))

    # First offer adds.
    client.post(
        "/api/v1/locations/loc-1/pools/player/offer-negative",
        json={"opponent_id": "opponent", "trait_setting_id": "ts-neg-1", "dice": ["d8"]},
    )
    # Second offer toggles it back out — no reveal, no reward.
    r = client.post(
        "/api/v1/locations/loc-1/pools/player/offer-negative",
        json={"opponent_id": "opponent", "trait_setting_id": "ts-neg-1", "dice": ["d8"]},
    )
    data = r.json()
    assert data == {"offered": False, "removed": True, "newly_revealed": False}
    assert ss_module.get_scene_store().get_pool("loc-1", "opponent") == []
