"""Tests for fog-of-war trait reveal."""

from types import SimpleNamespace

from transversal.services import scene_state as ss_module
from transversal.services.scene_state import SceneStateStore, get_scene_store
from transversal.services.trait_reveal import (
    reveal_pool_traits,
    reveal_trait_to,
    trait_setting_ids_from_pool,
)


def _die(ts_id=None, source_kind="trait", source_id=""):
    return {
        "die": "d8",
        "source_kind": source_kind,
        "source_id": source_id,
        "label": "x",
        "ts_id": ts_id,
    }


class FakeRepo:
    def __init__(self, occupants, traitsettings):
        self.occupants = occupants
        self.traitsettings = {ts.id: ts for ts in traitsettings}

    def list_entities_by_location(self, location_id):
        return self.occupants

    def get_traitsetting(self, ts_id):
        return self.traitsettings.get(ts_id)

    def update_traitsetting(self, ts):
        self.traitsettings[ts.id] = ts


def test_reveal_trait_to_is_idempotent():
    ts = SimpleNamespace(known_to=["a"])
    assert reveal_trait_to(ts, "a") is False
    assert reveal_trait_to(ts, "b") is True
    assert ts.known_to == ["a", "b"]
    assert reveal_trait_to(ts, "") is False


def test_trait_setting_ids_from_pool_filters_non_traits():
    dice = [
        _die("ts-1"),
        _die(source_kind="difficulty", source_id="difficulty"),
        _die("ts-1"),
        _die(source_kind="manual"),
    ]
    assert trait_setting_ids_from_pool(dice) == ["ts-1"]


def test_reveal_pool_traits_adds_occupants(monkeypatch):
    ss_module._store = SceneStateStore()
    get_scene_store().save_pool("loc-1", "owner", [_die("ts-1"), _die("ts-2")])

    ts1 = SimpleNamespace(id="ts-1", known_to=[])
    ts2 = SimpleNamespace(id="ts-2", known_to=["viewer-b"])
    repo = FakeRepo(
        occupants=[
            SimpleNamespace(id="owner"),
            SimpleNamespace(id="viewer-a"),
            SimpleNamespace(id="viewer-b"),
        ],
        traitsettings=[ts1, ts2],
    )

    changed, learners = reveal_pool_traits(repo, "loc-1", "owner")

    assert changed == ["ts-1", "ts-2"]
    assert learners == ["viewer-a", "viewer-b"]
    assert ts1.known_to == ["viewer-a", "viewer-b"]
    assert ts2.known_to == ["viewer-b", "viewer-a"]


def test_reveal_pool_traits_skips_when_no_trait_dice(monkeypatch):
    ss_module._store = SceneStateStore()
    get_scene_store().save_pool("loc-1", "owner", [_die(source_kind="manual")])

    repo = FakeRepo(
        occupants=[SimpleNamespace(id="viewer-a")],
        traitsettings=[],
    )
    changed, learners = reveal_pool_traits(repo, "loc-1", "owner")
    assert changed == []
    assert learners == []
