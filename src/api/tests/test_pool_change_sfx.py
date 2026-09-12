"""``on_pool_change`` — the moment an assembled dice pool is saved.

The server moment a rule can read a pool as the player built it: every die still
carries its ``ts_id``, so a path can walk back to the trait that produced it —
and, when a contest is under way, the other side is in the context too (see
[[Elements and Spiritual Roots]], where the cycle rules need exactly this).

Covers the trigger's declaration, the event map narrowing to it, and what the
fire site puts in the context (with and without a contest).
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from transversal.api.rest.scene_state import router as scene_state_router
from transversal.services import contest_tracker as ct_module
from transversal.services import scene_state as ss_module
from transversal.services import state_events
from transversal.services.conditions import context_keys_for
from transversal.services.contest_tracker import ContestTracker
from transversal.services.effects_engine import EffectsEngine, GameEvent
from transversal.services.effects_engine.triggers import triggers_for_event
from transversal.services.menu_contexts import trigger_card, trigger_variables
from transversal.services.scene_state import SceneStateStore


@pytest.fixture
def fresh_scene():
    """A clean tracker + scene store, so one test's contest can't leak."""
    ct_module._contest_tracker = ContestTracker()
    ss_module._store = SceneStateStore()
    yield
    ct_module._contest_tracker = ContestTracker()
    ss_module._store = SceneStateStore()


@pytest.fixture
def captured(monkeypatch):
    """Capture what the fire site hands the engine, instead of firing it."""
    seen: dict = {}

    def _capture(entity_id, universe, event_type, context=None):
        seen.update(entity_id=entity_id, universe=universe,
                    event_type=event_type, context=context or {})

    monkeypatch.setattr(state_events, "fire_state_sfx", _capture)
    return seen


# ── The trigger and its event ─────────────────────────

def test_the_trigger_is_declared_and_reads_as_the_moment():
    assert trigger_card("on_pool_change") == "Whenever your dice pool changes"
    assert [v.name for v in trigger_variables("on_pool_change")] == ["dice_pool", "contest_entity_opponent"]


def test_the_engine_matches_a_pool_change_event():
    engine = EffectsEngine()
    sfx = type("S", (), {"id": "sfx-pool", "trigger": "on_pool_change", "conditions": []})()
    assert engine._trigger_matches(sfx, GameEvent(type="pool_changed", entity_id="e1", universe="earth"))
    assert not engine._trigger_matches(sfx, GameEvent(type="location_changed", entity_id="e1", universe="earth"))


def test_the_event_map_narrows_to_it():
    # Narrowed to this trigger (plus the event type itself, which the engine's
    # direct match accepts) — so a rule with any other trigger is never read.
    assert triggers_for_event("pool_changed") == frozenset({"on_pool_change", "pool_changed"})


def test_the_moment_supplies_both_sides_dice_as_context():
    keys = context_keys_for(trigger="on_pool_change")
    assert {"rolls", "opposing_rolls"} <= keys


# ── What the fire site carries ────────────────────────

def test_a_save_without_a_contest_carries_only_your_own_dice(fresh_scene, captured):
    state_events.fire_pool_change_sfx("loc-1", "kael", [{"die": "d10", "ts_id": "kael:martial"}])

    assert captured["event_type"] == "pool_changed"
    assert captured["entity_id"] == "kael"
    assert [d["die"] for d in captured["context"]["rolls"]] == ["d10"]
    assert "contest_entity_opponent" not in captured["context"]
    assert "opposing_rolls" not in captured["context"]


def test_a_contest_puts_the_opponent_and_their_pool_in_the_context(fresh_scene, captured):
    from transversal.services.contest_tracker import get_contest_tracker
    from transversal.services.scene_state import get_scene_store

    get_scene_store().save_pool("loc-1", "guard", [{"die": "d8", "ts_id": "guard:metal"}])
    get_contest_tracker().set_opposition("loc-1", "kael", "guard", "earth")

    state_events.fire_pool_change_sfx("loc-1", "kael", [{"die": "d10", "ts_id": "kael:fire"}])

    assert captured["context"]["contest_entity_opponent"] == "guard"
    assert [d["die"] for d in captured["context"]["opposing_rolls"]] == ["d8"]
    assert [d["die"] for d in captured["context"]["rolls"]] == ["d10"]


def test_the_defendant_also_sees_the_challenger(fresh_scene, captured):
    """Either side's save is a pool-change moment; the other side is the opponent."""
    from transversal.services.contest_tracker import get_contest_tracker

    get_contest_tracker().set_opposition("loc-1", "kael", "guard", "earth")
    state_events.fire_pool_change_sfx("loc-1", "guard", [{"die": "d8"}])

    assert captured["context"]["contest_entity_opponent"] == "kael"


# ── The endpoint fires it ─────────────────────────────

def test_saving_a_pool_fires_the_moment(fresh_scene, monkeypatch):
    fired: list = []
    monkeypatch.setattr(
        "transversal.services.state_events.fire_pool_change_sfx",
        lambda location_id, entity_id, dice, before=None: fired.append((location_id, entity_id, dice, before)),
    )
    client = TestClient(_app())

    r = client.put("/api/v1/locations/loc-1/pools/kael", json={"dice": [
        {"die": "d10", "source_kind": "manual", "source_id": "intelligence", "label": "intelligence"},
    ]})
    assert r.status_code == 200, r.text
    assert len(fired) == 1
    location_id, entity_id, dice, before = fired[0]
    assert (location_id, entity_id) == ("loc-1", "kael")
    assert [d["die"] for d in dice] == ["d10"]
    assert before == []   # the pool was empty before this save


def _app():
    app = FastAPI()
    app.include_router(scene_state_router)
    return app

# ── What changed, and the pool itself ─────────────────

def test_the_moment_carries_the_pool_and_what_this_save_added(fresh_scene, captured):
    """The client PUTs the whole pool, so the *previous* list is the only record
    of what changed — and this moment is the only place that has both."""
    state_events.fire_pool_change_sfx(
        "loc-1", "kael",
        [{"die": "d8", "ts_id": "kael:fire"}, {"die": "d10", "ts_id": "kael:metal"}],
        before=[{"die": "d8", "ts_id": "kael:fire"}],
    )

    ctx = captured["context"]
    assert ctx["dice_pool"] == "pool:kael"
    assert [d["ts_id"] for d in ctx["added_dice"]] == ["kael:metal"]
    # Stamped with where it is, so an effect can act on exactly that die.
    assert ctx["added_dice"][0]["pool_owner"] == "kael"
    assert ctx["added_dice"][0]["pool_index"] == 1


def test_a_resave_and_a_removal_both_add_nothing(fresh_scene, captured):
    dice = [{"die": "d8", "ts_id": "kael:fire"}]
    state_events.fire_pool_change_sfx("loc-1", "kael", dice, before=list(dice))
    assert captured["context"]["added_dice"] == []

    state_events.fire_pool_change_sfx("loc-1", "kael", [], before=list(dice))
    assert captured["context"]["added_dice"] == []


def test_the_added_dice_are_a_seed_a_path_can_start_from():
    from transversal.services.target_resolver import event_collections

    seeds = event_collections({"added_dice": [{"die": "d10", "ts_id": "kael:metal"}]})
    assert seeds["added_dice"][0]["ts_id"] == "kael:metal"
    # Absent when the moment carries none (a re-save, or a different event).
    assert "added_dice" not in event_collections({"rolls": []})


def test_the_pool_itself_is_a_typed_variable():
    """`{dice_pool}` names the thing being changed, so a path can start at it
    instead of walking `self → pool`."""
    from transversal.services.target_catalog import scope_seed_names

    seeds = scope_seed_names("on_pool_change", "trait_setting")
    assert seeds["dice_pool"] == "pool"


def test_the_added_dice_collection_is_declared_with_its_own_party():
    from transversal.services import target_catalog as tc

    c = tc.collection("added_dice")
    assert c is not None and c.element == "die"
    assert c.card_origin == "you added"     # the actor's own dice, not the opponent's
