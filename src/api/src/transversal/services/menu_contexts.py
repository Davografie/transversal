"""Consequence-menu contexts and the outcome variables they expose.

A *menu context* names the post-roll consequence menu shown to a side after a
specific outcome. It is distinct from an SFX ``trigger`` (which auto-fires).
Each context declares the outcome variables that are in scope when authoring
its options — these are the ``{variable}`` tokens the SFX editor may offer.

The declared variable names are the contract the contest/test payloads grow
into; the contest event context currently carries ``opponent_id`` / ``effect_die``
and is unified toward this vocabulary.
"""

from __future__ import annotations

# ── Menu contexts ────────────────────────────────────

MENU_CONTEXT_IDS: tuple[str, ...] = (
    "test_success",     # full Cortex test vs difficulty: binary success/fail
    "simplified_roll",  # simplified roll: tiered outcome (d4..d12)
    "contest_win",      # contest, winner side
    "contest_give_in",  # contest, loser who gave in
)

MENU_CONTEXT_VARIABLES: dict[str, list[str]] = {
    "test_success": ["effect_die"],
    "simplified_roll": ["effect_die"],
    "contest_win": ["contest_entity_opponent", "contest_projection_opponent", "effect_die"],
    "contest_give_in": ["contest_entity_opponent", "contest_projection_opponent", "effect_die"],
}

# ── Auto-fire trigger variables ──────────────────────
#
# The same vocabulary for triggers that auto-fire SFX (no menu).  Kept separate
# from menu contexts so an SFX can be trigger-driven or menu-driven.

TRIGGER_VARIABLES: dict[str, list[str]] = {
    "on_contest_win": ["contest_entity_opponent", "contest_projection_opponent", "effect_die"],
    "on_contest_loss": ["contest_entity_opponent", "contest_projection_opponent", "effect_die"],
    "on_give_in": ["opponent_id", "gave_in"],
    "on_push": ["pushed"],
    "on_taken_out": ["opponent_id", "taken_out"],
    "on_prevent_taken_out": ["effect_die", "prevented"],
}


def menu_context_variables(menu_context: str) -> list[str]:
    """Return the variables exposed by a menu context (empty when unknown)."""
    return list(MENU_CONTEXT_VARIABLES.get(menu_context, []))


def trigger_variables(trigger: str) -> list[str]:
    """Return the variables exposed by an auto-fire trigger (empty when unknown)."""
    return list(TRIGGER_VARIABLES.get(trigger, []))
