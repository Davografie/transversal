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

# ── Auto-fire triggers ──────────────────────────────
#
# Single source of truth for the trigger vocabulary. Each entry declares the
# trigger string, its editor label, and the ``{variable}`` tokens in scope when
# authoring its effects. The SFX editor renders this list (via GraphQL), so a
# new trigger is authored here and appears in the UI without frontend edits.

@dataclass(frozen=True)
class TriggerDef:
    value: str
    label: str
    variables: tuple[Variable, ...] = ()


TRIGGERS: tuple[TriggerDef, ...] = (
    TriggerDef("manual", "Manual (player activates)"),
    TriggerDef("on_roll", "On Roll"),
    TriggerDef("on_result", "On Result"),
    TriggerDef("on_complication", "On Complication (hitch)"),
    TriggerDef("on_botch", "On Botch"),
    TriggerDef("on_success", "On Success"),
    TriggerDef("on_failure", "On Failure"),
    TriggerDef("on_contest_win", "On Contest Win", (
        Variable("contest_entity_opponent", "entity"),
        Variable("contest_projection_opponent", "entity"),
        Variable("effect_die", "die"),
        Variable("high_stakes", "boolean"),
        Variable("taken_out", "boolean"),
    )),
    TriggerDef("on_contest_loss", "On Contest Loss", (
        Variable("contest_entity_opponent", "entity"),
        Variable("contest_projection_opponent", "entity"),
        Variable("effect_die", "die"),
        Variable("high_stakes", "boolean"),
        Variable("taken_out", "boolean"),
    )),
    TriggerDef("on_give_in", "On Give In", (
        Variable("opponent_id", "entity"),
        Variable("gave_in", "string"),
    )),
    TriggerDef("on_push", "On Push", (Variable("pushed", "string"),)),
    TriggerDef("on_taken_out", "On Taken Out", (
        Variable("opponent_id", "entity"),
        Variable("taken_out", "string"),
    )),
    TriggerDef("on_prevent_taken_out", "On Prevent Taken Out", (
        Variable("effect_die", "die"),
        Variable("prevented", "string"),
    )),
    TriggerDef("on_location_change", "On Location Change", (
        Variable("from_location", "location"),
        Variable("to_location", "location"),
        Variable("universe", "universe"),
    )),
    TriggerDef("on_trait_change", "On Trait Change", (
        Variable("trait_id", "string"),
        Variable("traitset_id", "string"),
    )),
    TriggerDef("on_trait_learn", "On Trait Learned", (
        Variable("trait_id", "string"),
        Variable("trait_setting_id", "string"),
        Variable("owner", "entity"),
        Variable("learner", "entity"),
    )),
    TriggerDef("on_trait_offered", "On Trait Offered", (
        Variable("trait_id", "string"),
        Variable("trait_setting_id", "string"),
        Variable("owner", "entity"),
        Variable("opponent", "entity"),
        Variable("newly_revealed", "string"),
    )),
    TriggerDef("on_relationship_create", "On Relationship Create", (
        Variable("target_entity", "entity"),
        Variable("relationship_type", "string"),
    )),
    TriggerDef("on_character_create", "On Character Created", (Variable("entity_created", "entity"),)),
)


def menu_context_variables(menu_context: str) -> list[Variable]:
    """Return the typed variables exposed by a menu context (empty when unknown)."""
    return list(MENU_CONTEXT_VARIABLES.get(menu_context, []))


def trigger_variables(trigger: str) -> list[Variable]:
    """Return the typed variables exposed by an auto-fire trigger (empty when unknown)."""
    for t in TRIGGERS:
        if t.value == trigger:
            return list(t.variables)
    return []
