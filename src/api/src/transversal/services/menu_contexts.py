"""The trigger vocabulary — auto-fire triggers and consequence menus.

A *trigger* is the single activation axis for an SFX: it either names an
auto-fire event (``on_*``), manual activation (``manual``), or a post-roll
consequence menu (``test_success``, ``contest_win``, ``hitch``, …). Menu
triggers are the same kind of thing as auto-fire triggers: they carry the
``{variable}`` tokens in scope when authoring their effects.

Each variable carries a type so the editor can present the right input and the
hitch menu can substitute the right value: ``number``, ``entity``, ``die``,
``string``, ``location``, ``universe``, …
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

# The subset of trigger values that are consequence-menu placements (used by
# menu assembly and by the editor to group the dropdown).
MENU_TRIGGERS: frozenset[str] = frozenset(MENU_CONTEXT_IDS)

_MENU_TRIGGER_LABELS: dict[str, str] = {
    "test_success": "Menu — Test Success",
    "simplified_roll": "Menu — Simplified Roll",
    "contest_win": "Menu — Contest Win",
    "contest_give_in": "Menu — Contest Give In",
    "hitch": "Menu — Hitch / Opportunity",
}

# ── The trigger vocabulary ──────────────────────────
#
# Single source of truth for every way an SFX can activate. Each entry declares
# the trigger string, its editor label, the ``{variable}`` tokens in scope when
# authoring its effects, and a group for the editor dropdown. The SFX editor
# renders this list (via GraphQL), so a new trigger is authored here and
# appears in the UI without frontend edits.

@dataclass(frozen=True)
class TriggerDef:
    value: str
    label: str
    variables: tuple[Variable, ...] = ()
    group: str = "auto"  # "auto" | "manual" | "menu"


TRIGGERS: tuple[TriggerDef, ...] = (
    TriggerDef("manual", "Manual (player activates)", group="manual"),
    TriggerDef("on_roll", "On Roll", group="dicepool"),
    TriggerDef("on_result", "On Result", (
        Variable("effect_die", "die"),
        Variable("total", "number"),
    ), group="dicepool"),
    TriggerDef("on_complication", "On Complication (hitch)", group="dicepool"),
    TriggerDef("on_botch", "On Botch", group="dicepool"),
    TriggerDef("on_success", "On Success", group="dicepool"),
    TriggerDef("on_failure", "On Failure", group="dicepool"),
    TriggerDef("on_contest_win", "On Contest Win", (
        Variable("contest_entity_opponent", "entity"),
        Variable("contest_projection_opponent", "entity"),
        Variable("effect_die", "die"),
        Variable("high_stakes", "boolean"),
        Variable("taken_out", "boolean"),
    ), group="dicepool"),
    TriggerDef("on_contest_loss", "On Contest Loss", (
        Variable("contest_entity_opponent", "entity"),
        Variable("contest_projection_opponent", "entity"),
        Variable("effect_die", "die"),
        Variable("high_stakes", "boolean"),
        Variable("taken_out", "boolean"),
    ), group="dicepool"),
    TriggerDef("on_give_in", "On Give In", (
        Variable("contest_entity_opponent", "entity"),
        Variable("gave_in", "string"),
    ), group="dicepool"),
    TriggerDef("on_push", "On Push", (Variable("pushed", "string"),), group="dicepool"),
    TriggerDef("on_taken_out", "On Taken Out", (
        Variable("contest_entity_opponent", "entity"),
        Variable("taken_out", "string"),
    ), group="dicepool"),
    TriggerDef("on_prevent_taken_out", "On Prevent Taken Out", (
        Variable("effect_die", "die"),
        Variable("prevented", "string"),
    ), group="dicepool"),
    TriggerDef("on_location_change", "On Location Change", (
        Variable("from_location", "location"),
        Variable("to_location", "location"),
        Variable("universe", "universe"),
    )),
    TriggerDef("on_trait_change", "On Trait Change", (
        Variable("trait", "trait"),
        Variable("traitset", "traitset"),
    )),
    TriggerDef("on_trait_learn", "On Trait Learned", (
        Variable("trait", "trait"),
        Variable("trait_setting", "trait_setting"),
        Variable("owner", "entity"),
        Variable("learner", "entity"),
    )),
    TriggerDef("on_trait_offered", "On Trait Offered", (
        Variable("trait", "trait"),
        Variable("trait_setting", "trait_setting"),
        Variable("owner", "entity"),
        Variable("opponent", "entity"),
        Variable("newly_revealed", "string"),
    )),
    TriggerDef("on_relationship_create", "On Relationship Create", (
        Variable("target_entity", "entity"),
        Variable("relationship_type", "string"),
    )),
    TriggerDef("on_character_create", "On Character Created", (Variable("entity_created", "entity"),)),
    TriggerDef("on_projection_create", "On Projection Created", (
        Variable("entity_created", "entity"),
        Variable("projection_created", "projection"),
        Variable("universe", "universe"),
    )),
    TriggerDef("on_set", "On Set", (
        Variable("effect_die", "die"),
        Variable("total", "number"),
    ), group="dicepool"),
    TriggerDef("on_beat", "On Beat Advance", group="auto"),
    TriggerDef("on_scene", "On Scene Advance", group="auto"),
) + tuple(
    TriggerDef(value, _MENU_TRIGGER_LABELS[value], tuple(MENU_CONTEXT_VARIABLES[value]), group="menu")
    for value in MENU_CONTEXT_IDS
)


def menu_context_variables(menu_context: str) -> list[Variable]:
    """Deprecated alias — menu contexts are triggers now."""
    return trigger_variables(menu_context)


def trigger_variables(trigger: str) -> list[Variable]:
    """Return the typed variables exposed by a trigger or menu context (empty when unknown)."""
    for t in TRIGGERS:
        if t.value == trigger:
            return list(t.variables)
    return []


def is_menu_trigger(trigger: str) -> bool:
    """True if ``trigger`` names a post-roll consequence menu."""
    return trigger in MENU_TRIGGERS
