"""The effect action registry — assembled from the per-section action modules.

Order is significant: it is the order the editor lists actions in, so the
sections are concatenated in the order they appeared in the original
single-file registry.
"""

from __future__ import annotations

from transversal.services.effects_registry import (
    actions_lifepath,
    actions_razmerit,
    actions_relationships,
    actions_roll,
    actions_sfx,
    actions_trait,
    actions_trait_gain,
    actions_world,
)
from transversal.services.effects_registry.action_types import EffectActionMeta


EFFECT_ACTION_REGISTRY: list[EffectActionMeta] = [
    *actions_roll.ACTIONS,
    *actions_trait.ACTIONS,
    *actions_razmerit.ACTIONS,
    *actions_world.ACTIONS,
    *actions_trait_gain.ACTIONS,
    *actions_lifepath.ACTIONS,
    *actions_relationships.ACTIONS,
    *actions_sfx.ACTIONS,
]


# ── Functional grouping (editor optgroups) ─────────────
# Assigned after construction so each action's group lives beside the section
# it belongs to, without repeating the label in every constructor call.
_ACTION_GROUPS: dict[str, str] = {
    "play_as_rating": "Dice Pool", "step_up_die": "Dice Pool",
    "step_down_die": "Dice Pool", "double_die": "Dice Pool",
    "reroll_die": "Dice Pool", "add_dice": "Dice Pool",
    "add_trait_rating_dice": "Dice Pool", "roll_pool": "Dice Pool", "resolve_pool": "Dice Pool",
    "remove_die": "Dice Pool", "split_die": "Dice Pool",
    "step_up_effect": "Outcome", "step_up_outcome": "Outcome",
    "increase_dice_limit": "Outcome", "decrease_dice_limit": "Outcome",
    "negate_complication": "Outcome", "convert_complication": "Outcome",
    "reroll_highest": "Outcome",
    "step_up_trait": "Trait", "step_down_trait": "Trait", "set_trait": "Trait",
    "reduce_by_effect_die": "Trait", "increase_by_effect_die": "Trait",
    "add_rating_die": "Trait", "remove_rating_die": "Trait",
    "disable_trait": "Trait", "toggle_trait": "Trait", "set_traitset_limit": "Trait",
    "gain_trait": "Trait", "gain_or_step_up_trait": "Trait",
    "cortex_gain_trait": "Trait", "reveal_trait": "Trait",
    "earn_razmerit": "Razmerit", "spend_razmerit": "Razmerit",
    "transfer_razmerit": "Razmerit",
    "create_asset": "Entity", "end_active_effect": "Entity", "create_projection": "Entity", "attune": "Attunement",
    "travel": "Travel", "set_location": "Travel",
    "discover_life_path": "Life Path", "next_step": "Life Path",
    "open_roll_table": "Roll Table",
    "draft_life_path": "Life Path", "force_muster": "Life Path",
    "muster": "Life Path", "enroll_life_path": "Life Path",
    "create_relationship": "Relationship", "entity_targeting_ban": "Relationship",
    "grant_sfx": "Rules",
}

for _m in EFFECT_ACTION_REGISTRY:
    _m.group = _ACTION_GROUPS.get(_m.action_id, "Other")
