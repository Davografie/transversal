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


def test_triggers_registry_declares_labels_and_variables():
    by_value = {t.value: t for t in TRIGGERS}
    # Every trigger the editor renders has a human label.
    assert all(t.label for t in TRIGGERS)
    # The auto-fire vocabulary matches the engine's matching rules.
    assert "on_character_create" in by_value
    assert by_value["on_character_create"].label == "On Character Created"
    assert by_value["on_character_create"].variables == ()
    # Variables live beside their trigger in the same registry.
    assert "effect_die" in _names(list(by_value["on_contest_win"].variables))
