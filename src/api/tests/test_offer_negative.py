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
            "trait": "trait-neg",
            "trait_setting": "ts-neg-1",
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


def test_offer_negative_broadcasts_actor(monkeypatch):
    monkeypatch.setattr(
        "transversal.services.state_events.fire_state_sfx",
        lambda entity_id, universe, event_type, context: None,
    )
    calls = []
    monkeypatch.setattr(
        "transversal.api.rest.scene_state.broadcast_pool_change",
        lambda location_id, entity_id, dice=None, phase="adding", actor_id=None: calls.append({
            "entity_id": entity_id, "actor_id": actor_id, "dice": dice,
        }),
    )
    trait = _trait(known_to=[])
    client = _client(monkeypatch, trait, _occupants("opponent"))

    r = client.post(
        "/api/v1/locations/loc-1/pools/player/offer-negative",
        json={"opponent_id": "opponent", "trait_setting_id": "ts-neg-1", "dice": ["d8"]},
    )
    assert r.status_code == 200, r.text
    assert calls == [{"entity_id": "opponent", "actor_id": "player", "dice": [
        {"die": "d8", "source_kind": "trait", "source_id": "ts-neg-1", "label": "d8", "ts_id": "ts-neg-1"},
    ]}]


def test_offer_negative_to_difficulty_lands_the_die_but_earns_nothing(monkeypatch):
    """No contest to feed — the negative lands in the difficulty (location) pool.

    The reveal still happens (the table learns the complication), but the
    `on_trait_offered` reward must not fire: a location id is never in
    `known_to`, so `newly_revealed` is true on every click and the seeded
    +1 razmerit would be farmable by clicking twice.
    """
    fired = []
    monkeypatch.setattr(
        "transversal.services.state_events.fire_state_sfx",
        lambda entity_id, universe, event_type, context: fired.append((entity_id, event_type, context)),
    )
    trait = _trait(known_to=[])
    client = _client(monkeypatch, trait, _occupants("player", "bystander"))

    r = client.post(
        "/api/v1/locations/loc-1/pools/player/offer-negative",
        json={
            "opponent_id": "loc-1", "trait_setting_id": "ts-neg-1",
            "dice": ["d4"], "label": "Damaged", "award": False,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"offered": True, "removed": False, "newly_revealed": True}
    assert trait.known_to == ["player", "bystander"]
    assert fired == []

    pool = ss_module.get_scene_store().get_pool("loc-1", "loc-1")
    assert [d["ts_id"] for d in pool] == ["ts-neg-1"]


def test_offer_negative_difficulty_pays_nothing_across_repeated_toggles(monkeypatch):
    """Offer → remove → offer must not pay out on the re-offer either."""
    fired = []
    monkeypatch.setattr(
        "transversal.services.state_events.fire_state_sfx",
        lambda entity_id, universe, event_type, context: fired.append((entity_id, event_type, context)),
    )
    trait = _trait(known_to=[])
    client = _client(monkeypatch, trait, _occupants("player"))
    body = {
        "opponent_id": "loc-1", "trait_setting_id": "ts-neg-1",
        "dice": ["d4"], "award": False,
    }

    for _ in range(3):
        r = client.post("/api/v1/locations/loc-1/pools/player/offer-negative", json=body)
        assert r.status_code == 200, r.text

    assert fired == []
    # Odd number of toggles: offer, remove, offer — it ends up in the pool,
    # and none of the three clicks paid out.
    assert [d["ts_id"] for d in ss_module.get_scene_store().get_pool("loc-1", "loc-1")] == ["ts-neg-1"]


def test_offer_negative_remove_only_never_offers(monkeypatch):
    """A retraction must not become an offer.

    Removing a trait group from the sheet retracts the group's negative baggage.
    If the die turns out not to be in the target pool (a stale client view), a
    plain toggle would *add* it — `remove_only` reports the miss and leaves the
    pool alone.
    """
    fired = []
    monkeypatch.setattr(
        "transversal.services.state_events.fire_state_sfx",
        lambda entity_id, universe, event_type, context: fired.append((entity_id, event_type, context)),
    )
    trait = _trait(known_to=[])
    client = _client(monkeypatch, trait, _occupants("player"))

    r = client.post(
        "/api/v1/locations/loc-1/pools/player/offer-negative",
        json={
            "opponent_id": "loc-1", "trait_setting_id": "ts-neg-1",
            "dice": [], "remove_only": True,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"offered": False, "removed": False, "newly_revealed": False}
    assert ss_module.get_scene_store().get_pool("loc-1", "loc-1") == []
    assert fired == []


def test_offer_negative_remove_only_retracts_something_that_is_there(monkeypatch):
    """The retraction path still works when the die IS in the target pool."""
    monkeypatch.setattr(
        "transversal.services.state_events.fire_state_sfx",
        lambda entity_id, universe, event_type, context: None,
    )
    trait = _trait(known_to=[])
    client = _client(monkeypatch, trait, _occupants("player"))

    client.post(
        "/api/v1/locations/loc-1/pools/player/offer-negative",
        json={"opponent_id": "loc-1", "trait_setting_id": "ts-neg-1", "dice": ["d4"], "award": False},
    )
    assert [d["ts_id"] for d in ss_module.get_scene_store().get_pool("loc-1", "loc-1")] == ["ts-neg-1"]

    r = client.post(
        "/api/v1/locations/loc-1/pools/player/offer-negative",
        json={
            "opponent_id": "loc-1", "trait_setting_id": "ts-neg-1",
            "dice": [], "remove_only": True,
        },
    )
    assert r.json() == {"offered": False, "removed": True, "newly_revealed": False}
    assert ss_module.get_scene_store().get_pool("loc-1", "loc-1") == []
