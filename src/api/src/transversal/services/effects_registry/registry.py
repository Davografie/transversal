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


# ── References derived from the positional fields they replace ([[B261]]) ──
# An action opts in by marking the *field* it is retiring with
# `hidden_when_ref="<ref name>"`: that field is the fallback form, and the
# reference is declared from it here, labelled in the field's own words. One
# source of truth — a new action cannot add the fallback field and forget the
# reference, and the two labels cannot drift.
#
# The elements come from where the action already declares them: a recipient is
# an entity, and a target accepts exactly what the action's path already accepted
# — `path_element` where the action has a path, else the flat `target_kind` it was
# authored against (the two share the catalog's vocabulary; only `occupant` is a
# scope word rather than an element). `path_element` is a *set* for the change-die
# family, where a die lives in a pool or in a rating. A field with no declared
# elements is left alone rather than given a ref nothing could type-check against.
#
# Appended after whatever the action declares itself, which is what keeps the
# trait before the recipient for copy/move (and so keeps the panel's order, and
# the engine's, reading subject → destination).
_ELEMENTS_FOR_FIELD = {
    "entity": lambda m: ("entity",),
    "target": lambda m: tuple(m.path_element or ()) or (
        (m.target_kind,) if m.target_kind else ()
    ),
}
for _m in EFFECT_ACTION_REGISTRY:
    for _f in _m.fields:
        _ref_name = _f.hidden_when_ref
        if not _ref_name or any(r.name == _ref_name for r in _m.refs):
            continue
        _source = _ELEMENTS_FOR_FIELD.get(_f.name)
        if _source is None:
            continue
        _elements = _source(_m)
        if not _elements:
            continue
        _m.refs = [*_m.refs, RefDef(name=_ref_name, label=_f.label,
                                    elements=_elements, legacy_field=_f.name)]


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
