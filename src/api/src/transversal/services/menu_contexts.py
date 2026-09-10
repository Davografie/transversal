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

# The set of consequence-menu outcome signals (the ``menu_context`` argument to
# consequence-menu assembly), mapped to outcome conditions by
# ``consequence_menu._outcome_context``. Not SFX trigger values anymore.

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
    group: str = "auto"  # "manual" | "dicepool" | "auto"


# Card-facing trigger phrases ([[SFX Natural Language Plan]]): how the trigger
# reads in derived rules text ("Whenever a roll happens, …"). Kept beside
# [[TRIGGERS]] deliberately — the editor label and the card phrase answer
# different questions. An unlisted trigger falls back to its editor label, so a
# new trigger never renders as nothing.
TRIGGER_CARDS: dict[str, str] = {
    "manual": "Activated",
    "on_roll": "Whenever a roll happens",
    "on_result": "When a roll is resolved",
    "on_complication": "When a complication is rolled",
    "on_botch": "When you botch",
    "on_success": "When a roll succeeds",
    "on_failure": "When a roll fails",
    "on_contest_win": "When you win a contest",
    "on_contest_loss": "When you lose a contest",
    "on_give_in": "When you give in",
    "on_push": "When you push",
    "on_taken_out": "When you are taken out",
    "on_prevent_taken_out": "When you would be taken out",
    "on_location_change": "When a location changes",
    "on_trait_change": "When a trait changes",
    "on_trait_learn": "When a trait is learned",
    "on_trait_offered": "When a trait is offered",
    "on_relationship_create": "When a relationship is created",
    "on_character_create": "When a character is created",
    "on_projection_create": "When a projection is created",
    "on_set": "When a die is set",
    "on_beat": "At the end of each beat",
    "on_scene": "At the end of each scene",
    "on_session_start": "At the start of each session",
    "on_session_end": "At the end of each session",
    "on_challenge_completed": "When a challenge is completed",
}


def trigger_card(trigger: str) -> str:
    """The card-facing phrase for a trigger (explicit, else the editor label)."""
    if trigger in TRIGGER_CARDS:
        return TRIGGER_CARDS[trigger]
    for t in TRIGGERS:
        if t.value == trigger:
            return t.label
    return trigger or "Activated"


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
    TriggerDef("on_session_start", "On Session Start", group="auto"),
    TriggerDef("on_session_end", "On Session End", group="auto"),
    TriggerDef("on_challenge_completed", "On Challenge Completed", (
        Variable("entity_id", "entity"),
        Variable("trait_setting_id", "trait_setting"),
        Variable("trait_id", "trait"),
        Variable("capacity", "string"),
    ), group="auto"),
)


def menu_context_variables(menu_context: str) -> list[Variable]:
    """The typed ``{variables}`` in scope for a consequence-menu outcome signal."""
    return list(MENU_CONTEXT_VARIABLES.get(menu_context, []))


def trigger_variables(trigger: str) -> list[Variable]:
    """Return the typed variables exposed by an activation trigger (empty when unknown)."""
    for t in TRIGGERS:
        if t.value == trigger:
            return list(t.variables)
    return []
