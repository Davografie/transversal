"""Consequence-menu contexts and the outcome variables they expose.

A *menu context* names the post-roll consequence menu shown to a side after a
specific outcome. It is distinct from an SFX ``trigger`` (which auto-fires).
Each context declares the outcome variables that are in scope when authoring
its options — these are the ``{variable}`` tokens the SFX editor may offer.

Each variable carries a type so the editor can present the right input and the
hitch menu can substitute the right value: ``number``, ``entity_id``, ``die``,
or ``string``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Variable:
    name: str
    type: str  # "number" | "entity" | "die" | "string"


# ── Menu contexts ────────────────────────────────────

MENU_CONTEXT_IDS: tuple[str, ...] = (
    "test_success",     # full Cortex test vs difficulty: binary success/fail
    "simplified_roll",  # simplified roll: tiered outcome (d4..d12)
    "contest_win",      # contest, winner side
    "contest_give_in",  # contest, loser who gave in
    "hitch",            # GM buying a player's hitches
)

MENU_CONTEXT_VARIABLES: dict[str, list[Variable]] = {
    "test_success": [Variable("effect_die", "die")],
    "simplified_roll": [Variable("effect_die", "die")],
    "contest_win": [
        Variable("contest_entity_opponent", "entity"),
        Variable("contest_projection_opponent", "entity"),
        Variable("effect_die", "die"),
    ],
    "contest_give_in": [
        Variable("contest_entity_opponent", "entity"),
        Variable("contest_projection_opponent", "entity"),
        Variable("effect_die", "die"),
    ],
    "hitch": [
        Variable("number_of_hitches", "number"),
        Variable("buying_entity", "entity"),
        Variable("hitch_entity", "entity"),
    ],
}

# ── Auto-fire trigger variables ──────────────────────
#
# The same vocabulary for triggers that auto-fire SFX (no menu).  Kept separate
# from menu contexts so an SFX can be trigger-driven or menu-driven.

TRIGGER_VARIABLES: dict[str, list[Variable]] = {
    "on_contest_win": [
        Variable("contest_entity_opponent", "entity"),
        Variable("contest_projection_opponent", "entity"),
        Variable("effect_die", "die"),
    ],
    "on_contest_loss": [
        Variable("contest_entity_opponent", "entity"),
        Variable("contest_projection_opponent", "entity"),
        Variable("effect_die", "die"),
    ],
    "on_give_in": [Variable("opponent_id", "entity"), Variable("gave_in", "string")],
    "on_push": [Variable("pushed", "string")],
    "on_taken_out": [Variable("opponent_id", "entity"), Variable("taken_out", "string")],
    "on_prevent_taken_out": [Variable("effect_die", "die"), Variable("prevented", "string")],
    "on_trait_learn": [
        Variable("trait_id", "string"),
        Variable("trait_setting_id", "string"),
        Variable("owner", "entity"),
        Variable("learner", "entity"),
    ],
}


def menu_context_variables(menu_context: str) -> list[Variable]:
    """Return the typed variables exposed by a menu context (empty when unknown)."""
    return list(MENU_CONTEXT_VARIABLES.get(menu_context, []))


def trigger_variables(trigger: str) -> list[Variable]:
    """Return the typed variables exposed by an auto-fire trigger (empty when unknown)."""
    return list(TRIGGER_VARIABLES.get(trigger, []))
