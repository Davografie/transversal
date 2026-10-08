"""The effect action registry — assembled from the per-section action modules.

Order is significant: it is the order the editor lists actions in, so the
sections are concatenated in the order they appeared in the original
single-file registry.
"""

from __future__ import annotations

from transversal.services.effects_registry import (
    actions_client,
    actions_lifepath,
    actions_razmerit,
    actions_relationships,
    actions_roll,
    actions_sfx,
    actions_trait,
    actions_trait_gain,
    actions_world,
)
from transversal.services.effects_registry.action_types import EffectActionMeta, RefDef


EFFECT_ACTION_REGISTRY: list[EffectActionMeta] = [
    *actions_roll.ACTIONS,
    *actions_trait.ACTIONS,
    *actions_razmerit.ACTIONS,
    *actions_world.ACTIONS,
    *actions_trait_gain.ACTIONS,
    *actions_lifepath.ACTIONS,
    *actions_relationships.ACTIONS,
    *actions_sfx.ACTIONS,
    *actions_client.ACTIONS,
]


# ── The recipient reference ([[B261]]) ─────────────────
# *Who an effect lands on* is a declared reference, not a positional field. An
# action opts in by marking its `entity` field `hidden_when_ref="recipient"` —
# that field is the fallback form — and the reference is declared from it here,
# labelled in the field's own words. One source of truth: a new action cannot add
# the fallback field and forget the reference, and the two labels cannot drift.
#
# Appended after whatever the action declares itself, which is what keeps the
# trait before the recipient for copy/move (and so keeps the panel's order, and
# the engine's, reading subject → destination).
for _m in EFFECT_ACTION_REGISTRY:
    _fallback = next((f for f in _m.fields if f.hidden_when_ref == "recipient"), None)
    if _fallback is None or any(r.name == "recipient" for r in _m.refs):
        continue
    _m.refs = [*_m.refs, RefDef(name="recipient", label=_fallback.label,
                                elements="entity", legacy_field="entity")]


# ── Functional grouping (editor optgroups) ─────────────
# Assigned after construction so each action's group lives beside the section
# it belongs to, without repeating the label in every constructor call.
_ACTION_GROUPS: dict[str, str] = {
    # One family, because they are one question: which die, and what happens to
    # it. The path picks the die (in a pool, or in a trait's rating) and where it
    # lands decides whether the change is transient or persists.
    "set_die": "Change a Die", "step_up_die": "Change a Die",
    "step_down_die": "Change a Die", "double_die": "Change a Die",
    "split_die": "Change a Die", "remove_die": "Change a Die",
    "consolidate_dice": "Change a Die",
    "reroll_die": "Change a Die",
    # The two comparison verbs change a die too — the effect die is their
    # reference instead of a number — so they sit with the family rather than
    # under Trait, which is where they lived when a die had only one home.
    "reduce_by_effect_die": "Change a Die", "increase_by_effect_die": "Change a Die",
    "play_as_rating": "Dice Pool", "add_dice": "Dice Pool",
    "add_trait_rating_dice": "Dice Pool", "roll_pool": "Dice Pool", "resolve_pool": "Dice Pool",
    "step_up_effect": "Outcome", "step_up_outcome": "Outcome",
    "increase_dice_limit": "Outcome", "decrease_dice_limit": "Outcome",
    "set_hitch_threshold": "Outcome",
    "negate_complication": "Outcome", "convert_complication": "Outcome",
    "reroll_highest": "Outcome",
    "step_up_trait": "Trait", "step_down_trait": "Trait", "set_trait": "Trait",
    "add_rating_die": "Trait", "remove_rating_die": "Trait",
    "disable_trait": "Trait", "toggle_trait": "Trait", "set_traitset_limit": "Trait",
    "gain_trait": "Trait", "gain_or_step_up_trait": "Trait",
    "cortex_gain_trait": "Trait", "reveal_trait": "Trait",
    # The rest of the trait family: the actions that move, copy, re-point or
    # switch an instance off were falling into "Other" — the junkyard group the
    # picker sorts last — which is where B105 sends an author looking for the
    # transfer verbs.
    "copy_trait": "Trait", "move_trait": "Trait", "change_trait": "Trait",
    "delete_trait": "Trait", "enable_trait": "Trait",
    "invert_polarity": "Trait", "set_polarity": "Trait",
    "set_trait_rating_type": "Trait",
    "gain_relationship_trait": "Trait", "gain_subtrait": "Trait",
    "earn_razmerit": "Razmerit", "spend_razmerit": "Razmerit",
    "transfer_razmerit": "Razmerit",
    "create_asset": "Entity", "end_active_effect": "Entity", "create_projection": "Entity",
    "learn_entities": "Entity",
    # `suppress` is the removal half of `attune` (see actions_world), and
    # `set_destination` is how a rule grants travel directions.
    "attune": "Attunement", "suppress": "Attunement",
    "travel": "Travel", "set_location": "Travel", "set_destination": "Travel",
    "discover_life_path": "Life Path", "next_step": "Life Path",
    "open_roll_table": "Roll Table",
    "draft_life_path": "Life Path", "force_muster": "Life Path",
    "muster": "Life Path", "enroll_life_path": "Life Path",
    "create_relationship": "Relationship", "entity_targeting_ban": "Relationship",
    "start_contest": "Contest",
    "grant_sfx": "Rules",
    # Client-directed: they change nothing in the world, only what a screen shows.
    "open_sheet": "Client", "show_toast": "Client",
}

for _m in EFFECT_ACTION_REGISTRY:
    _m.group = _ACTION_GROUPS.get(_m.action_id, "Other")
