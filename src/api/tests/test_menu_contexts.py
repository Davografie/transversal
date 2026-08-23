"""Tests for the trigger/menu-context variable contract."""

from transversal.services.menu_contexts import (
    MENU_CONTEXT_IDS,
    TRIGGERS,
    menu_context_variables,
    trigger_variables,
)


def _names(vs):
    return [v.name for v in vs]


def test_menu_context_ids_declared():
    assert set(MENU_CONTEXT_IDS) == {
        "test_success", "simplified_roll", "contest_win", "contest_give_in", "hitch",
    }


def test_hitch_variables_are_typed():
    vs = menu_context_variables("hitch")
    assert {v.name: v.type for v in vs} == {
        "number_of_hitches": "number",
        "buying_entity": "entity",
        "hitch_entity": "entity",
    }


def test_contest_win_variables():
    vs = _names(menu_context_variables("contest_win"))
    assert "contest_entity_opponent" in vs
    assert "contest_projection_opponent" in vs
    assert "effect_die" in vs


def test_unknown_menu_context_is_empty():
    assert menu_context_variables("nope") == []


def test_trigger_variables_for_contests():
    assert "effect_die" in _names(trigger_variables("on_contest_win"))
    assert trigger_variables("on_roll") == []


def test_trigger_variables_for_state_events():
    vs = _names(trigger_variables("on_give_in"))
    assert "opponent_id" in vs
    assert "gave_in" in vs
    assert "pushed" in _names(trigger_variables("on_push"))
    assert "effect_die" in _names(trigger_variables("on_prevent_taken_out"))


def test_on_character_create_exposes_created_entity():
    vs = trigger_variables("on_character_create")
    assert {v.name: v.type for v in vs} == {"entity_created": "entity"}


def test_triggers_registry_declares_labels_and_variables():
    by_value = {t.value: t for t in TRIGGERS}
    # Every trigger the editor renders has a human label.
    assert all(t.label for t in TRIGGERS)
    # The auto-fire vocabulary matches the engine's matching rules.
    assert "on_character_create" in by_value
    assert by_value["on_character_create"].label == "On Character Created"
    assert _names(list(by_value["on_character_create"].variables)) == ["entity_created"]
    # Variables live beside their trigger in the same registry.
    assert "effect_die" in _names(list(by_value["on_contest_win"].variables))


def _fake_fire(monkeypatch, get_entity):
    """Patch the app singletons so ``fire_state_sfx``/``fire_contest_outcome_sfx``
    capture their GameEvent instead of mutating state."""
    from types import SimpleNamespace

    captured = []

    class FakeEngine:
        def process_event_outcome(self, event, sfx_ids, razmerit, repo=None):
            captured.append(event)
            return SimpleNamespace(applied=[], pending=[])

    monkeypatch.setattr("transversal.main._get_engine", lambda: FakeEngine())
    monkeypatch.setattr("transversal.main._get_repo", lambda: SimpleNamespace(get_entity=get_entity))
    monkeypatch.setattr("transversal.services.sfx_owner.get_available_sfx_ids", lambda *a, **k: [])
    return captured


def test_state_fire_sites_populate_declared_variables(monkeypatch):
    """Every trigger variable a state trigger declares is actually populated."""
    from transversal.services import state_events

    # event_type → trigger string (mirrors EffectsEngine._trigger_matches).
    event_trigger = {
        "character_created": "on_character_create",
        "location_changed": "on_location_change",
        "trait_updated": "on_trait_change",
        "relationship_created": "on_relationship_create",
    }
    cases = {
        "character_created": {"entity_created": "c1"},
        "location_changed": {"from_location": "a", "to_location": "b", "universe": "earth"},
        "trait_updated": {"trait_id": "t1", "traitset_id": "ts1"},
        "relationship_created": {"target_entity": "e2", "relationship_type": "ally"},
        "on_trait_learn": {"trait_id": "t1", "trait_setting_id": "s1", "owner": "o", "learner": "l"},
        "on_trait_offered": {"trait_id": "t1", "trait_setting_id": "s1", "owner": "o", "opponent": "p", "newly_revealed": "true"},
        "on_give_in": {"gave_in": True, "opponent_id": "x"},
        "on_push": {"pushed": True},
        "on_taken_out": {"taken_out": True, "opponent_id": "x"},
        "on_prevent_taken_out": {"prevented": True, "effect_die": "d6"},
    }

    from types import SimpleNamespace

    captured = _fake_fire(
        monkeypatch,
        lambda eid: SimpleNamespace(razmerit=0, current_universe="earth"),
    )
    for event_type, context in cases.items():
        captured.clear()
        state_events.fire_state_sfx("e1", "earth", event_type, context)
        assert len(captured) == 1, event_type
        trigger = event_trigger.get(event_type, event_type)
        declared = {v.name for v in trigger_variables(trigger)}
        missing = declared - set(captured[0].context)
        assert not missing, f"{trigger}: declared {sorted(missing)} but fire site did not populate them"


def test_contest_fire_site_populates_declared_variables(monkeypatch):
    """Contest triggers declare variables the contest fire site actually produces."""
    from types import SimpleNamespace

    from transversal.services import state_events

    captured = _fake_fire(
        monkeypatch,
        lambda eid: SimpleNamespace(razmerit=0, current_universe="earth", current_projection=None),
    )
    state_events.fire_contest_outcome_sfx(
        "winner", "loser", "earth", effect_die="d6", high_stakes=True, taken_out=False
    )

    declared = {v.name for v in trigger_variables("on_contest_win")}
    assert len(captured) == 2  # winner + loser
    for event in captured:
        missing = declared - set(event.context)
        assert not missing, f"contest: declared {sorted(missing)} but fire site did not populate them"
