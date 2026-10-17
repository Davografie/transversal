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


# ── The references an action declares for its retired fields ([[B261]]) ──
# These were *derived* from the positional fields while those existed, so that an
# action could not add a fallback field and forget its reference. The fields are
# going away, so the references are declared here instead — one table, keyed by
# action, listing exactly what the derivation produced (name, label, elements).
# `role` says which question each reference answers, for the accessors.
# Generated from the derived refs at the moment they were made explicit.
# (action_id, [(ref name, label, elements, role, anchor), ...])
_DECLARED_REFS: dict[str, list[tuple[str, str, tuple[str, ...], str | None, bool]]] = {
    "add_dice": [("pool", "Pool", ('pool',), 'target', False)],
    "add_rating_die": [("trait", "Target Trait", ('traitsetting',), 'target', False)],
    "attune": [("applies_to", "Who It Applies To", ('entity',), 'target', False)],
    "change_trait": [("instance", "Target Trait", ('traitsetting',), 'target', False)],
    "consolidate_dice": [("die", "Target", ('die', 'rating_die'), 'target', False)],
    "copy_trait": [("recipient", "Give To", ('entity',), 'entity', False)],
    "cortex_gain_trait": [("trait", "Trait", ('trait',), 'target', False), ("recipient", "Entity", ('entity',), 'entity', False), ("owner", "Anchored to", ('entity', 'projection', 'relationship', 'traitsetting'), 'owner', True)],
    "create_projection": [("recipient", "Entity", ('entity',), 'entity', False)],
    # A spawn: the template is the operand, and the place it lands is an *anchor*
    # (settled once) named `owner` — the name `resolve_effect_owner` reads.
    "duplicate_entity": [("template", "Template", ('entity',), 'target', False),
                         ("owner", "Spawn At", ('location',), 'owner', True)],
    "create_relationship": [("contact", "Target Entity", ('entity',), 'target', False)],
    "delete_trait": [("trait", "Target Trait", ('traitsetting',), 'target', False)],
    "disable_trait": [("trait", "Target Trait", ('traitsetting',), 'target', False)],
    "discover_life_path": [("life_path", "Life Path", ('life_path',), 'target', False)],
    "enter_life_path": [("life_path", "Life Path", ('life_path',), 'target', False)],
    "double_die": [("die", "Target", ('die', 'rating_die'), 'target', False)],
    "draft_life_path": [("life_path", "Life Path", ('life_path',), 'target', False)],
    "earn_razmerit": [("recipient", "Entity", ('entity',), 'entity', False)],
    "enable_trait": [("trait", "Target Trait", ('traitsetting',), 'target', False)],
    "end_active_effect": [("recipient", "Entity", ('entity',), 'entity', False), ("effect", "Active Effect", ('scheduled_event',), 'target', False)],
    "entity_targeting_ban": [("entity", "Target Entity", ('entity',), 'target', False)],
    # Two retired verbs. Retiring is about *authoring*: the registry keeps the
    # effect's dispatch, and the seeded base moves still construct these -- so
    # they need the reference their target field defers to like any other. The
    # element is the one their own `target_kind` declares.
    # The inverse verbs, declared so they have a reference surface at all.
    "restore_die": [("die", "Target", ('die', 'rating_die'), 'target', False)],
    "remove_added_dice": [("pool", "Pool", ('pool',), 'target', False)],
    "delete_entity": [("entity", "Entity", ('entity',), 'target', False)],
    "disable_attunement": [("entity", "Body", ('entity',), 'target', False)],
    "unsuppress_attunement": [("entity", "Body", ('entity',), 'target', False)],
    "remove_targeting_ban": [("entity", "Entity", ('entity',), 'target', False)],
    "step_up_trait": [("trait", "Target Trait", ('trait',), 'target', False),
                      ("recipient", "Entity", ('entity',), 'entity', False)],
    "step_down_trait": [("trait", "Target Trait", ('trait',), 'target', False),
                        ("recipient", "Entity", ('entity',), 'entity', False)],
    "remove_rating_die": [("trait", "Target Trait", ('trait',), 'target', False),
                          ("recipient", "Entity", ('entity',), 'entity', False)],
    "gain_relationship_trait": [("trait", "Trait", ('trait',), 'target', False),
                                ("recipient", "Entity", ('entity',), 'entity', False)],
    "gain_or_step_up_trait": [("trait", "Trait", ('trait',), 'target', False), ("recipient", "Entity", ('entity',), 'entity', False), ("owner", "Anchored to", ('entity', 'projection', 'relationship', 'traitsetting'), 'owner', True)],
    "gain_subtrait": [("trait", "Trait", ('trait',), 'target', False), ("owner", "Anchored to", ('traitsetting',), 'owner', True)],
    "gain_trait": [("trait", "Trait", ('trait',), 'target', False), ("recipient", "Entity", ('entity',), 'entity', False), ("owner", "Anchored to", ('entity', 'projection', 'relationship', 'traitsetting'), 'owner', True)],
    "grant_sfx": [("recipient", "Entity", ('entity',), 'entity', False)],
    "increase_by_effect_die": [("die", "Target", ('die', 'rating_die'), 'target', False)],
    "invert_polarity": [("trait", "Target", ('traitsetting',), 'target', False)],
    "learn_entities": [("entity", "Which Entity", ('entity',), 'target', False)],
    "move_trait": [("recipient", "Give To", ('entity',), 'entity', False)],
    "next_step": [("table", "Next Table", ('roll_table',), 'target', False)],
    "open_roll_table": [("table", "Roll Table", ('roll_table',), 'target', False)],
    "open_sheet": [("recipient", "On Whose Screen", ('entity',), 'entity', False), ("owner", "Owner", ('entity',), 'target', False)],
    "reduce_by_effect_die": [("die", "Target", ('die', 'rating_die'), 'target', False)],
    "remove_die": [("die", "Target", ('die', 'rating_die'), 'target', False)],
    "reroll_die": [("die", "Target", ('die',), 'target', False)],
    "reveal_trait": [("trait", "Trait", ('traitsetting',), 'target', False)],
    "set_destination": [("recipient", "Entity", ('entity',), 'entity', False), ("location", "Destination Location", ('location',), 'target', False)],
    "set_die": [("die", "Target", ('die', 'rating_die'), 'target', False)],
    "set_hitch_threshold": [("recipient", "Entity", ('entity',), 'entity', False)],
    "set_location": [("recipient", "Entity", ('entity',), 'entity', False), ("location", "Destination Location", ('location',), 'target', False)],
    # The departure board ([[B323]]). The **portal** is what the effect acts on,
    # so it is the ordinary reference; the **destination** is an *anchor* —
    # settled once, like every owner path — because a board is one place, and a
    # destination path that matched three cities must not set it three times.
    #
    # The anchor's ref name is `owner` because that is the name
    # `resolve_effect_owner` reads (it is also what `duplicate_entity`'s "Spawn
    # At" is called). The *label* is what an author sees, and it reads
    # "Destination"; there is no cleaner role — `role` names the positional field
    # a reference supersedes, and `owner` is the only anchored one.
    "set_portal_destination": [("portal", "Portal", ('relationship',), 'target', False),
                               ("owner", "Destination", ('location',), 'owner', True)],
    "set_polarity": [("trait", "Target", ('traitsetting',), 'target', False)],
    "set_trait": [("trait", "Target Trait", ('traitsetting',), 'target', False)],
    "set_trait_rating_type": [("trait", "Target Trait", ('traitsetting',), 'target', False)],
    "set_trait_statement": [("trait", "Trait", ('trait',), 'target', False), ("owner", "Anchored to", ('entity', 'projection', 'relationship', 'traitsetting'), 'owner', True)],
    "set_traitset_limit": [("recipient", "Entity", ('entity',), 'entity', False), ("traitset", "Trait Set", ('traitset',), 'target', False)],
    "show_toast": [("recipient", "On Whose Screen", ('entity',), 'entity', False), ("tap_target", "Tap Target", ('entity',), 'target', False)],
    # No `recipient` ref: the subject *is* the screen here (the character the rule
    # fired for), so declaring one made the editor inject a `select self` and the
    # card read "show the Life on Earth on you life path". An author who really
    # means somebody else's screen uses the `entity` field, which stays as the
    # positional form.
    "show_life_path": [("life_path", "Life Path", ('life_path',), 'target', False)],
    "spend_razmerit": [("recipient", "Entity", ('entity',), 'entity', False)],
    "split_die": [("die", "Target", ('die', 'rating_die'), 'target', False)],
    "start_contest": [("opponent", "Opponent", ('entity',), 'target', False)],
    "step_down_die": [("die", "Target", ('die', 'rating_die'), 'target', False)],
    "step_up_die": [("die", "Target", ('die', 'rating_die'), 'target', False)],
    "suppress": [("applies_to", "Who It Applies To", ('entity',), 'target', False)],
    "toggle_trait": [("trait", "Target Trait", ('traitsetting',), 'target', False)],
    "transfer_razmerit": [("entity", "Target Entity", ('entity',), 'target', False)],
    "travel": [("recipient", "Entity", ('entity',), 'entity', False), ("location", "Destination Location", ('location',), 'target', False)],
}

for _m in EFFECT_ACTION_REGISTRY:
    _declared = _DECLARED_REFS.get(_m.action_id, [])
    if not _declared:
        continue
    _existing = {r.name for r in _m.refs}
    _m.refs = [*_m.refs, *[
        RefDef(name=_name, label=_label, elements=_elements,
               role=_legacy, anchor=_anchor)
        for _name, _label, _elements, _legacy, _anchor in _declared
        if _name not in _existing
    ]]


# ── Functional grouping (editor optgroups) ─────────────
# Assigned after construction so each action's group lives beside the section
# it belongs to, without repeating the label in every constructor call.
_ACTION_GROUPS: dict[str, str] = {
    "restore_die": "Change a Die", "remove_added_dice": "Dice Pool",
    "disable_attunement": "Attunement", "unsuppress_attunement": "Attunement",
    "delete_entity": "Entity", "remove_targeting_ban": "Entity",
    "restore_projection": "Attunement", "clear_destination": "Travel",
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
    "duplicate_entity": "Entity",
    "learn_entities": "Entity",
    # `suppress` is the removal half of `attune` (see actions_world), and
    # `set_destination` is how a rule grants travel directions.
    "attune": "Attunement", "suppress": "Attunement",
    "travel": "Travel", "set_location": "Travel", "set_destination": "Travel",
    "set_portal_destination": "Travel",
    "discover_life_path": "Life Path", "next_step": "Life Path",
    "open_roll_table": "Roll Table",
    "draft_life_path": "Life Path", "force_muster": "Life Path",
    "muster": "Life Path", "enroll_life_path": "Life Path", "enter_life_path": "Life Path",
    # Shown with the other life-path verbs (the author, 2026-10-16): an author
    # looking for "give the player a life path" looks *here*, not under Client —
    # which groups by mechanism, and is where you look for a screen you are
    # driving rather than for a path. The action still lives in
    # ``actions_client.py``, because what it *is* is a client-directed effect
    # (nothing in the world changes); the group is the editor's topic shelf.
    "show_life_path": "Life Path",
    "create_relationship": "Relationship", "entity_targeting_ban": "Relationship",
    "start_contest": "Contest",
    "grant_sfx": "Rules",
    # Client-directed: they change nothing in the world, only what a screen shows.
    "open_sheet": "Client", "show_toast": "Client",
}

for _m in EFFECT_ACTION_REGISTRY:
    _m.group = _ACTION_GROUPS.get(_m.action_id, "Other")
