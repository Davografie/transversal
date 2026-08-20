"""Tests for the trigger/menu-context variable contract."""

from transversal.services.menu_contexts import (
    MENU_CONTEXT_IDS,
    menu_context_variables,
    trigger_variables,
)


def test_menu_context_ids_declared():
    assert set(MENU_CONTEXT_IDS) == {"test_success", "simplified_roll", "contest_win", "contest_give_in"}


def test_contest_win_variables():
    vs = menu_context_variables("contest_win")
    assert "contest_entity_opponent" in vs
    assert "contest_projection_opponent" in vs
    assert "effect_die" in vs


def test_unknown_menu_context_is_empty():
    assert menu_context_variables("nope") == []


def test_trigger_variables_for_contests():
    assert "effect_die" in trigger_variables("on_contest_win")
    assert trigger_variables("on_roll") == []


def test_trigger_variables_for_state_events():
    assert "opponent_id" in trigger_variables("on_give_in")
    assert "gave_in" in trigger_variables("on_give_in")
    assert "pushed" in trigger_variables("on_push")
    assert "effect_die" in trigger_variables("on_prevent_taken_out")
