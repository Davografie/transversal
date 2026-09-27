"""SFX ownership resolution.

Ownership lives on the *owner* side (owners point at SFX ids), not on the
``SFX`` definition. This module resolves the full set of SFX ids an entity can
use right now by unioning every owner surface, universe-gated:

  - ``table`` owner bucket (everyone)
  - direct entity ownership (``Entity.sfx_ids``)
  - active projection ownership (``Projection.sfx_ids``)
  - trait-level grants (``TraitSetting.sfx_ids`` + ``Trait.default_sfx_ids``)
  - trait-set-as-unit grants (``TraitSetSetting.sfx_ids``)

The ``gm`` owner bucket is intentionally excluded — it is resolved in GM
context (e.g. buy-hitch, P3.3), not derived from an entity.
"""

from __future__ import annotations

import logging

log = logging.getLogger("transversal.sfx")

import time

from dataclasses import dataclass, field
from typing import Any

from transversal.domain import SfxOwner

from transversal.services.target_scopes import choice_spec


def _choice(kind: str, scope: str | None = None, mode: str = "choose",
            filter: dict | None = None):
    """The spec a built-in's ``{choose_kind}``/``{random:kind}`` target stands for.

    Built-ins compose the declared scope path rather than the flat spelling, so a
    seeded rule and a migrated one are the same shape.
    """
    return choice_spec(kind, scope, mode, filter=filter)


def ensure_sfx_owners(repo) -> None:
    """Create/refresh the default SFX owner buckets. Idempotent.

    ``table`` = globally available SFX (everyone) — seeded with the give-in
    reward, the contest-complication menu SFX, and the player opportunity SFX;
    ``gm`` = GM-context SFX (not entity-derived; P3.3 buy-hitch). Role is a
    condition (``entity_type``), not a bucket, so there is no ``players`` bucket.
    """
    defaults = {
        "table": [
            "sfx-give-in-get-razmerit",
            "sfx-give-in-targeting-ban",
            "apply-complication",
            "take-complication",
            "prevent-taken-out",
            "sfx-offer-negative-trait",
            "sfx-starter-location",
            "opportunity-step-down-complication",
        ],
        "gm": ["hitch-gain-complication"],
    }
    for owner_id, sfx_ids in defaults.items():
        owner = repo.get_sfx_owner(owner_id)
        if owner is None:
            repo.create_sfx_owner(SfxOwner(id=owner_id, sfx_ids=list(sfx_ids)))
        else:
            merged = list(dict.fromkeys((owner.sfx_ids or []) + sfx_ids))
            if merged != (owner.sfx_ids or []):
                owner.sfx_ids = merged
                repo.update_sfx_owner(owner)

    # Migrate the legacy ``players`` bucket into ``table`` (role moved to the
    # ``entity_type`` condition), then drop it.
    legacy = repo.get_sfx_owner("players")
    if legacy is not None:
        table = repo.get_sfx_owner("table")
        if table is not None and legacy.sfx_ids:
            table.sfx_ids = list(dict.fromkeys((table.sfx_ids or []) + legacy.sfx_ids))
            repo.update_sfx_owner(table)
        repo.delete_sfx_owner("players")


def _challenge_pool_spec(polarity: str):
    """Targeting path selecting challenge-rated traits of ``polarity`` (chosen at fire time)."""
    from transversal.services.target_spec import ChooseStep, FilterStep, NavigateStep, SelectStep, TargetSpec

    return TargetSpec(steps=[
        SelectStep(collection="entities"),
        NavigateStep(edge="traitsettings"),
        FilterStep(field="rating_type", operator="==", value="challenge"),
        FilterStep(field="polarity", operator="==", value=polarity),
        ChooseStep(count=1),
    ])


def ensure_base_move_sfxs(repo) -> None:
    """Seed the post-roll consequence-menu base moves as ``trigger="menu"`` SFX.

    Side (player vs architect) is a ``USER_ROLE`` condition rather than a hard
    code path. The SFX live in the ``table`` bucket (available to every entity);
    the trigger puts them in the menu, which gates them by role. Idempotent.

    The menu used to be a ``placement`` override on a ``manual`` trigger, which
    let the two disagree (see ``menu_contexts.TRIGGERS``); it is the trigger
    now, so the pair cannot be authored into nonsense.
    """
    from transversal.domain import Condition, ConditionType, Effect, EffectTiming, SFX

    base_moves = [
        ("proceed", "Proceed the narrative", "Move the scene forward without applying a consequence.", "player", []),
        ("create_scene_trait", "Create a scene trait", "Introduce a new scene trait at your effect die.", "player", [
            Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait", action="gain_or_step_up",
                   target_spec=_choice("trait"), result="{effect_die}"),
        ]),
        ("decrease_doom", "Decrease the doom pool", "Step down a doom pool die.", "player", [
            Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait", action="step_down",
                   target_spec=_challenge_pool_spec("negative")),
        ]),
        ("work_on_project", "Work on a project", "Advance a progress clock by stepping it up.", "player", [
            Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait", action="gain_or_step_up",
                   result="{effect_die}", target_spec=_challenge_pool_spec("positive")),
        ]),
        ("increase_doom", "Increase the doom pool", "Step up a doom pool die.", "architect", [
            Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait", action="step_up",
                   target_spec=_challenge_pool_spec("negative")),
        ]),
        ("give_asset", "Give a GMC an asset", "Grant a GMC an asset at your effect die.", "architect", [
            Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait", action="gain",
                   target_spec=_choice("trait"), result="{effect_die}"),
        ]),
    ]

    for sfx_id, name, description, role, effects in base_moves:
        if repo.get_sfx(sfx_id) is not None:
            continue
        repo.create_sfx(SFX(
            id=sfx_id, name=name, description=description,
            trigger="menu",
            conditions=[Condition(type=ConditionType.USER_ROLE, target=role)],
            effects=effects,
        ))

    owner = repo.get_sfx_owner("table")
    if owner is not None:
        merged = list(dict.fromkeys((owner.sfx_ids or []) + [m[0] for m in base_moves]))
        if merged != (owner.sfx_ids or []):
            owner.sfx_ids = merged
            repo.update_sfx_owner(owner)


def ensure_starter_location_sfx(repo) -> None:
    """Create/migrate the character-scatter SFX. Idempotent.

    Fires on ``on_character_create`` for unplaced Earth characters and places
    them at a random ``starter_location`` within Earth. Migrates the earlier
    ``travel``/``move`` shape to the dedicated ``location``/``set`` effect.
    """
    from transversal.domain import Condition, ConditionType, Effect, EffectTiming, SFX

    desired = Effect(
        timing=EffectTiming.IMMEDIATE,
        type="location",
        action="set",
        target_spec=_choice("location", "universe:earth", mode="random",
                            filter={"starter_location": True}),
    )

    existing = repo.get_sfx("sfx-starter-location")
    if existing is None:
        repo.create_sfx(SFX(
            id="sfx-starter-location",
            name="Scatter to Starter Location",
            description="A newly created, unplaced Earth character arrives at a random starter location.",
            trigger="on_character_create",
            conditions=[
                Condition(type=ConditionType.UNPLACED),
                Condition(type=ConditionType.IN_UNIVERSE, target="earth"),
            ],
            effects=[desired],
        ))
        return

    # Migrate legacy shapes in place:
    #   - travel/move (with {random_starter_location} + inapposite context)
    #   - location/set with the old {random_starter_location} placeholder
    changed = False
    for i, eff in enumerate(existing.effects):
        if eff.type == "travel" and eff.action == "move":
            existing.effects[i] = desired
            changed = True
        elif eff.type == "location" and eff.action == "set" and eff.target == "{random_starter_location}":
            eff.target = ""
            eff.target_spec = desired.target_spec
            eff.target_filter = {}
            changed = True
    if changed:
        repo.update_sfx(existing)


def ensure_give_in_sfx(repo) -> None:
    """Create the give-in razmerit-reward SFX if missing. Idempotent."""
    from transversal.domain import Effect, EffectTiming, SFX

    if repo.get_sfx("sfx-give-in-get-razmerit") is not None:
        return
    repo.create_sfx(SFX(
        id="sfx-give-in-get-razmerit",
        name="Give In Reward",
        description="Gain 1 razmerit when you give in during a contest",
        trigger="on_give_in",
        effects=[
            Effect(
                timing=EffectTiming.IMMEDIATE,
                type="transfer_razmerit",
                action="earn",
                target="self",
                result="1",
            ),
        ],
    ))


def ensure_support_cast_sfx(repo) -> None:
    """Create/seed the roll-table-as-menu support-cast SFX (B58). Idempotent.

    A manual, sheet-placed SFX carrying a single ``roll_table/menu`` effect that
    opens the Emberline support-cast table. Granted to the ``table`` bucket so
    every entity can self-serve an SC; faction gating lives in the table entries.
    """
    from transversal.domain import Effect, EffectTiming, SFX

    sfx_id = "sfx-roll-support-cast"
    if repo.get_sfx(sfx_id) is None:
        repo.create_sfx(SFX(
            id=sfx_id,
            name="Roll Support Cast",
            description="Open the support-cast roll table to generate a support character — pick an archetype and pay its cost.",
            trigger="manual",
            effects=[
                Effect(
                    timing=EffectTiming.IMMEDIATE,
                    type="roll_table",
                    action="menu",
                    target="rt-emberline-support-cast",
                ),
            ],
        ))

    add_sfx_to_owner(repo, "table", "table", sfx_id)


def ensure_targeting_ban_sfx(repo) -> None:
    """Create/migrate the give-in targeting-ban SFX. Idempotent.

    The ban is applied immediately and its inverse (``remove_targeting_ban``) is
    scheduled to fire after one scene via the unified duration model.  Migrates
    the legacy seed (``result="1"``) to the ``duration`` shape in place.
    """
    from transversal.domain import Effect, EffectDuration, EffectTiming, SFX, Timer

    desired = Effect(
        timing=EffectTiming.IMMEDIATE,
        type="entity",
        action="targeting_ban",
        target="",
        duration=EffectDuration(timers=[Timer(event="scene", remaining=1)]),
    )

    existing = repo.get_sfx("sfx-give-in-targeting-ban")
    if existing is None:
        repo.create_sfx(SFX(
            id="sfx-give-in-targeting-ban",
            name="Give In — Keep Your Distance",
            description="When you give in, you can't target that opponent for the rest of the scene",
            trigger="on_give_in",
            effects=[desired],
        ))
        return

    changed = False
    for i, eff in enumerate(existing.effects):
        if eff.type == "entity" and eff.action == "targeting_ban" and eff.duration is None:
            existing.effects[i] = desired
            changed = True
    if changed:
        repo.update_sfx(existing)


def ensure_contest_complication_sfx(repo) -> None:
    """Create + migrate the winner (apply) / conceder (take) complication SFX.

    Both carry the same ``cortex_gain`` effect with negative polarity so winning
    applies a complication at the effect die via Cortex create-or-step-up rules.
    Idempotent: also rewrites stale ``gain_complication`` effects in place.
    """
    from transversal.domain import Condition, ConditionType, Effect, EffectTiming, SFX

    def _complication_effect() -> Effect:
        return Effect(
            timing=EffectTiming.IMMEDIATE,
            type="modify_trait",
            action="cortex_gain",
            target_spec=_choice("trait", "traitset:ts-complications-a190"),
            result="{effect_die}",
            negative=True,
        )

    def _ensure(sfx_id: str, name: str, description: str, outcome: str) -> None:
        existing = repo.get_sfx(sfx_id)
        outcome_cond = Condition(type=ConditionType.CONTEST_OUTCOME, target=outcome)
        if existing is None:
            repo.create_sfx(SFX(
                id=sfx_id,
                name=name,
                description=description,
                trigger="menu",
                conditions=[outcome_cond],
                effects=[_complication_effect()],
            ))
            return
        desired = _complication_effect()
        changed = False
        for i, eff in enumerate(existing.effects):
            if eff.type == "modify_trait" and eff.action in (
                "gain_complication", "gain_or_step_up_complication", "cortex_gain",
            ):
                if eff.action != desired.action or not eff.negative:
                    existing.effects[i] = desired
                    changed = True
        if existing.trigger != "menu" or existing.placement is not None:
            existing.trigger = "menu"
            existing.placement = None
            changed = True
        conditions = [c for c in (existing.conditions or []) if c.type != ConditionType.CONTEST_OUTCOME]
        conditions.append(outcome_cond)
        if [c.type for c in conditions] != [c.type for c in (existing.conditions or [])] or \
           [c.target for c in conditions] != [c.target for c in (existing.conditions or [])]:
            existing.conditions = conditions
            changed = True
        if changed:
            repo.update_sfx(existing)

    _ensure("apply-complication", "Apply a complication",
            "When you win a contest, give your opponent a complication at your effect die",
            "player")
    _ensure("take-complication", "Take a complication",
            "When you give in, take a complication at the winner's effect die",
            "give_in")


# ── Worked example: a rule owned by a place ──────────────────
#
# Location scope (see [[Place-Owned Rules]]) means an SFX attached to a location
# reaches the entities inside it — and inside its sub-locations. That is content,
# not mechanism, so this example is seeded **by hand** rather than from startup:
# `main.py` never calls it, which is what makes deleting the example stick.
#
# To (re)create it:
#     from transversal.services.sfx_owner import ensure_place_rule_example
#     ensure_place_rule_example(repo)

PLACE_RULE_EXAMPLE_ID = "sfx-azure-dawn-initiation"
_PLACE_RULE_EXAMPLE_LOCATION = "Azure Dawn"
_PLACE_RULE_EXAMPLE_LIFE_PATH = "Azure Dawn"


def ensure_place_rule_example(repo) -> None:
    """Seed the place-owned worked example. Idempotent; a no-op without its data.

    Azure Dawn's initiation: whoever arrives on the sect's grounds discovers its
    life path. Attached to the *location*, so it reaches everyone inside.

    Note what is deliberately **not** authored: there is no "at location"
    condition. The scope already says who the rule reaches, and an `AT_LOCATION`
    condition would be *wrong* for a character standing in the sect's cellar —
    the rule reaches them, the condition would refuse them.

    What each setting does here:
      * owner = the Azure Dawn location   → who it reaches (everyone inside)
      * trigger = On Location Change      → when it fires (arriving)
      * condition = Entity type: character→ who it applies to (not the GMCs)
      * effect = Discover Life Path      → what happens, landing on the arriver
    """
    from transversal.domain import (
        Condition, ConditionType, Effect, EffectTiming, EntityType, SFX,
    )

    location = next(
        (e for e in repo.list_all_entities()
         if e.type == EntityType.LOCATION and e.name == _PLACE_RULE_EXAMPLE_LOCATION),
        None,
    )
    life_path = next(
        (p for p in repo.list_all_lifepaths() if p.name == _PLACE_RULE_EXAMPLE_LIFE_PATH),
        None,
    )
    if location is None or life_path is None:
        return  # nothing to attach it to (or a renamed world)

    desired = SFX(
        id=PLACE_RULE_EXAMPLE_ID,
        name="Sect Initiation",
        description="Whoever arrives on Azure Dawn's grounds discovers its life path.",
        trigger="on_location_change",
        source_kind="location",
        conditions=[Condition(type=ConditionType.ENTITY_TYPE, target="character")],
        effects=[Effect(timing=EffectTiming.IMMEDIATE, type="life_path",
                        action="discover", target=life_path.id)],
    )

    # Create-only: this is content, and once the author edits it (a condition
    # added, a trigger changed) re-running the seeder must not clobber them.
    if repo.get_sfx(PLACE_RULE_EXAMPLE_ID) is None:
        repo.create_sfx(desired)

    # The owner side: attach it as a *location*, which is what its declared
    # source kind requires — `add_sfx_to_owner` refuses a mismatch, so a
    # place-owned rule can't quietly sit on a character.
    add_sfx_to_owner(repo, "location", location.id, PLACE_RULE_EXAMPLE_ID)


def ensure_prevent_taken_out_sfx(repo) -> None:
    """Create the prevent-taken-out SFX (spend 1 razmerit). Idempotent.

    The complication itself is applied by the winner via the consequence menu,
    so this SFX only handles the razmerit spend.
    """
    from transversal.domain import Effect, EffectTiming, SFX

    if repo.get_sfx("prevent-taken-out") is not None:
        return
    repo.create_sfx(SFX(
        id="prevent-taken-out",
        name="Prevent Being Taken Out",
        description="Spend 1 razmerit to avoid being taken out of the scene",
        trigger="on_prevent_taken_out",
        effects=[
            Effect(
                timing=EffectTiming.IMMEDIATE,
                type="transfer_razmerit",
                action="spend",
                target="self",
                result="1",
            ),
        ],
    ))


def ensure_hitch_gain_complication_sfx(repo) -> None:
    """Create the GM hitch-menu SFX that turns bought hitches into a complication.

    P3.3: the GM selects a player's hitches and picks this SFX from the ``hitch``
    menu. The roller (``{hitch_entity}``) gains (or steps up) a complication at
    d4 + ``{number_of_hitches}`` steps, then earns 1 razmerit.
    """
    from transversal.domain import Condition, ConditionType, Effect, EffectTiming, SFX

    hitch_cond = Condition(type=ConditionType.HITCH)
    effects = [
        Effect(
            timing=EffectTiming.IMMEDIATE,
            type="modify_trait",
            action="gain_or_step_up",
            target_spec=_choice("trait", "traitset:ts-complications-a190"),
            entity="{hitch_entity}",
            result="d4",
            negative=True,
            context={"steps": "{number_of_hitches}"},
        ),
        Effect(
            timing=EffectTiming.IMMEDIATE,
            type="transfer_razmerit",
            action="earn",
            target="self",
            entity="{hitch_entity}",
            result="1",
        ),
    ]

    existing = repo.get_sfx("hitch-gain-complication")
    if existing is None:
        repo.create_sfx(SFX(
            id="hitch-gain-complication",
            name="Gain a complication",
            description="Roller takes a complication stepped up by the bought hitches, then earns 1 razmerit",
            trigger="menu",
            conditions=[hitch_cond],
            effects=effects,
        ))
        return
    changed = False
    if existing.trigger != "menu" or existing.placement is not None:
        existing.trigger = "menu"
        existing.placement = None
        changed = True
    if not any(c.type == ConditionType.HITCH for c in (existing.conditions or [])):
        existing.conditions = [*(existing.conditions or []), hitch_cond]
        changed = True
    if changed:
        repo.update_sfx(existing)


def ensure_opportunity_sfx(repo) -> None:
    """Create the player opportunity SFX (buy a hitch to step down a complication).

    The player spends 1 razmerit and steps down one of their own complications.
    ``{buying_entity}`` is the player doing the buying; ``{hitch_entity}`` is
    the roller whose 1 was bought.
    """
    from transversal.domain import Condition, ConditionType, Effect, EffectTiming, SFX

    hitch_cond = Condition(type=ConditionType.HITCH)
    entity_cond = Condition(type=ConditionType.ENTITY_TYPE, subject="{buying_entity}", target="character")
    effects = [
        Effect(
            timing=EffectTiming.IMMEDIATE,
            type="transfer_razmerit",
            action="spend",
            target="self",
            entity="{buying_entity}",
            result="1",
        ),
        Effect(
            timing=EffectTiming.IMMEDIATE,
            type="modify_trait",
            action="step_down",
            target_spec=_choice("trait", "traitset:ts-complications-a190"),
            entity="{buying_entity}",
        ),
    ]

    existing = repo.get_sfx("opportunity-step-down-complication")
    if existing is not None:
        changed = False
        if existing.trigger != "menu" or existing.placement is not None:
            existing.trigger = "menu"
            existing.placement = None
            changed = True
        conditions = list(existing.conditions or [])
        if not any(c.type == ConditionType.HITCH for c in conditions):
            conditions.append(hitch_cond)
            changed = True
        if not any(c.type == ConditionType.ENTITY_TYPE for c in conditions):
            conditions.append(entity_cond)
            changed = True
        if changed:
            existing.conditions = conditions
            repo.update_sfx(existing)
        return
    repo.create_sfx(SFX(
        id="opportunity-step-down-complication",
        name="Step down a complication",
        description="Spend 1 razmerit to step down one of your complications",
        trigger="menu",
        conditions=[hitch_cond, entity_cond],
        effects=effects,
    ))


def ensure_offer_negative_sfx(repo) -> None:
    """Create the table SFX that rewards offering a negative trait mid-contest.

    Fires on the server event ``trait_offered`` (the player routed one of their
    negative traits to the opponent's pool).  The endpoint only fires that event
    when the opponent hadn't learned the trait yet, so the +1 razmerit here is
    the atomic "reveal-and-reward" payout.
    """
    from transversal.domain import Effect, EffectTiming, SFX

    if repo.get_sfx("sfx-offer-negative-trait") is not None:
        return
    repo.create_sfx(SFX(
        id="sfx-offer-negative-trait",
        name="Offer Negative Trait",
        description="Gain 1 razmerit when you offer one of your negative traits to an opponent who hasn't learned it yet",
        trigger="on_trait_offered",
        effects=[
            Effect(
                timing=EffectTiming.IMMEDIATE,
                type="transfer_razmerit",
                action="earn",
                target="self",
                result="1",
            ),
        ],
    ))


def remove_legacy_buy_hitch_sfx(repo) -> None:
    """Delete the retired ``buy-hitch`` SFX (superseded by the hitch menu)."""
    legacy_id = "buy-hitch"
    if repo.get_sfx(legacy_id) is not None:
        repo.delete_sfx(legacy_id)
    owner = repo.get_sfx_owner("gm")
    if owner is not None and legacy_id in (owner.sfx_ids or []):
        owner.sfx_ids = [sid for sid in owner.sfx_ids if sid != legacy_id]
        repo.update_sfx_owner(owner)


def remove_legacy_contest_complication_sfx(repo) -> None:
    """Delete the retired auto-fired contest-loss complication SFX. Idempotent.

    P2.10d moved contest-loss complications into the manual consequence menu.
    This removes a previously-seeded ``sfx-contest-loss-complication`` row and
    its reference in the ``table`` owner bucket so a stale DB doesn't keep
    re-registering it on ``on_contest_loss``.
    """
    legacy_id = "sfx-contest-loss-complication"
    if repo.get_sfx(legacy_id) is not None:
        repo.delete_sfx(legacy_id)
    owner = repo.get_sfx_owner("table")
    if owner is not None and legacy_id in (owner.sfx_ids or []):
        owner.sfx_ids = [sid for sid in owner.sfx_ids if sid != legacy_id]
        repo.update_sfx_owner(owner)


# ── Rules on a *sub*-trait ───────────────────────────
#
# An instance can hang under another instance rather than under the entity:
# an agenda's portents under their container, an elemental root under Spiritual
# Power. **A rule can live there, and it must still work.** Both availability and
# ownership used to read `get_effective_traitsettings` alone, which returns only
# `from_type == 'entity'` rows — so a rule on a sub-trait was authored, attached
# and *silently dead*: the engine never considered it, and `select source` could
# never resolve to the instance granting it.
#
# Effectiveness is inherited: a sub-trait grants its rules when its **ancestor
# chain reaches an instance that is itself in play**. A disabled ancestor
# therefore takes its whole subtree dark, which is the same rule that makes a
# landed portent grant nothing.


def _walk_nested(repo, parent_ids: list[str]) -> list:
    """Every sub-trait reachable downward from ``parent_ids`` (one read per level).

    The walk is what makes the ancestor rule true by construction rather than by
    a depth limit: it recurses until a level yields nothing new, so nesting a root
    under a root works without anyone remembering to raise a constant.
    """
    out: list = []
    seen: set[str] = set()
    parents = list(parent_ids)
    while parents:
        children = repo.get_sub_traitsettings_for_parents(parents)
        nxt: list[str] = []
        for kids in children.values():
            for k in kids:
                if k.id in seen:
                    continue
                seen.add(k.id)
                out.append(k)
                nxt.append(k.id)
        parents = nxt
    return out


def _relationship_traitsettings_for(repo, entity_id: str, prefetch=None) -> list:
    """The trait instances the entity holds *on its relationship edges*.

    Outgoing only, matching the sheet's own reading of "what I hold about others":
    the tie's traits are on the edge, so the entity that owns the edge owns the
    rules. Two edges to the same contact of different kinds are distinct, which is
    why the *edge* — not the contact — carries them.
    """
    if prefetch is not None and entity_id in prefetch.relationship_traitsettings:
        return [row.get("setting") if isinstance(row, dict) else row
                for row in prefetch.relationship_traitsettings[entity_id]]
    read = getattr(repo, "get_relationship_traitsettings_for_entity", None)
    if read is None:
        # A repo that cannot answer is missing the edge scope, not reporting "no
        # rules" — say so rather than returning a confident empty. Every repository
        # has the read; a test double that does not is under-specified.
        log.warning("[get_available_sfx_ids] repo has no relationship-trait read — "
                    "rules on a tie's traits are invisible (entity=%s)", entity_id)
        return []
    rows = read(entity_id) or []
    return [row.get("setting") if isinstance(row, dict) else row for row in rows]


def _nested_traitsettings_for(repo, entity_id: str, universe: str) -> list:
    """The entity's sub-trait instances that are in play (see the note above)."""
    effective = repo.get_effective_traitsettings(entity_id, [universe])
    # An instance with no id has no children to walk to, so it is skipped rather
    # than crashing the whole availability call for the entity.
    return _walk_nested(repo, [ts.id for ts in effective if getattr(ts, "id", None)])


def _walk_nested_bulk(repo, effective_by_entity: dict[str, list]) -> dict[str, list]:
    """The bulk sibling of :func:`_walk_nested`, for the availability prefetch."""
    out: dict[str, list] = {}
    owner: dict[str, str] = {}
    for eid, tss in effective_by_entity.items():
        for ts in tss:
            if getattr(ts, "id", None):
                owner[ts.id] = eid
    parents = list(owner)
    while parents:
        nxt: list[str] = []
        for pid, kids in repo.get_sub_traitsettings_for_parents(parents).items():
            eid = owner.get(pid)
            if eid is None:
                continue
            for k in kids:
                if k.id in owner:  # already walked — also stops a cycle dead
                    continue
                owner[k.id] = eid
                out.setdefault(eid, []).append(k)
                nxt.append(k.id)
        parents = nxt
    return out


@dataclass
class SfxAvailabilityPrefetch:
    """Bulk-loaded per-entity data for :func:`get_available_sfx_ids`.

    A global boundary fan-out (``on_beat`` / ``on_scene`` / ``on_session_end``)
    visits every entity; resolving availability the per-entity way costs 4-6 DB
    round-trips each, and one of them (the ``table`` bucket, and the SFX docs)
    is the same record re-read every time. This holds those in bulk so the walk
    costs a handful of queries regardless of entity count.
    """

    entities: dict[str, Any] = field(default_factory=dict)           # entity_id → Entity
    projections: dict[str, Any] = field(default_factory=dict)        # projection_id → Projection
    table_bucket: Any = None                                         # shared "table" SfxOwner
    traitsettings: dict[str, list] = field(default_factory=dict)     # entity_id → [TraitSetting]
    traitsetsettings: dict[str, list] = field(default_factory=dict)  # entity_id → [TraitSetSetting]
    location_rules: dict[str, list] = field(default_factory=dict)    # location_id → [sfx_id] in scope
    faction_rules: dict[str, list] = field(default_factory=dict)     # entity_id → [sfx_id] from its factions
    relationship_traitsettings: dict[str, list] = field(default_factory=dict)  # entity_id → [edge traits]
    sfx_by_id: dict[str, Any] = field(default_factory=dict)          # sfx_id → SFX


# ── SFX record cache ─────────────────────────────────
#
# Availability runs on every state event, every roll, and every "what can I do"
# query, and it needs each candidate's *record* (to read its trigger and static
# conditions). Reading one document per candidate made the cost linear in the
# whole catalogue — fine for 30 SFX, ruinous for a thousand. SFX content changes
# rarely, so the records are cached.
#
# Staleness is bounded twice over: the SFX mutations call
# :func:`invalidate_sfx_cache` eagerly (same process, so the editor sees its own
# edit immediately), and ``_SFX_CACHE_TTL`` caps how long a write from another
# process (the MCP server, a script) can go unnoticed here.
_SFX_CACHE_TTL = 30.0
_SFX_CACHE: dict[str, Any] = {}
_SFX_CACHE_FILLED_AT = 0.0


# The other half of the same read: which rules a trait's instances get *without*
# learning them ([[B131]]). Availability walks an entity's trait instances, and
# reading each instance's registry trait to find its `possible_sfx_ids` would add
# a query per instance to the hottest path in the system. Traits change as rarely
# as rules do, so the declaration is cached by trait id — including the empty
# answer, which is the common one, so a trait that declares nothing is asked once.
_POSSIBLE_SFX_CACHE: dict[str, tuple[str, ...]] = {}


def invalidate_sfx_cache() -> None:
    """Drop the cached SFX records and trait declarations (any rule/trait write).

    Every rule write goes through here, which is why the SFX mutations call it
    whether or not an effects engine happens to be attached.
    """
    global _SFX_CACHE_FILLED_AT, _GRANTED_BY_OWNER_CACHE, _REACH_CACHE_FILLED_AT
    _SFX_CACHE.clear()
    _POSSIBLE_SFX_CACHE.clear()
    _REACH_INDEX_CACHE.clear()
    _GRANTED_BY_OWNER_CACHE = None
    _REACH_CACHE_FILLED_AT = 0.0
    _SFX_CACHE_FILLED_AT = 0.0


def possible_sfx_ids(repo, trait_id: str) -> tuple[str, ...]:
    """The rules a registry trait declares as *possible*, cached by trait id.

    Empty when the trait declares none — the common case, and cached so the walk
    does not ask twice.
    """
    if not trait_id:
        return ()
    cached = _POSSIBLE_SFX_CACHE.get(trait_id)
    if cached is not None:
        return cached
    trait = repo.get_trait(trait_id) if hasattr(repo, "get_trait") else None
    ids = tuple(getattr(trait, "possible_sfx_ids", None) or ()) if trait is not None else ()
    _POSSIBLE_SFX_CACHE[trait_id] = ids
    return ids


#: ``flavour -> {rule id: the owner ids its reach declarations select}``. Resolved
#: once and cached beside the SFX records (same invalidation), because a reach
#: declaration is a **set-producing** query where the old offer was a lookup — the
#: read must not become "walk every owner and run a path" ([[Dynamic SFX Reach]]).
_REACH_INDEX_CACHE: dict[str, dict[str, frozenset[str]]] = {}

#: When the reach-derived caches were last built, on the same clock the SFX records
#: use (``_SFX_CACHE_TTL``). A reach declaration is a **live query over the world** —
#: its answer changes when a trait moves, a place fills up, a tag changes — so it
#: cannot be kept honest by enumerating every write that might affect it; it refreshes
#: on a clock instead. This used to be missing, which meant the index only aged out
#: when some *other* code path happened to load an SFX record: a trait that changed
#: hands kept offering the rule to its old owner and the new owner saw nothing, until
#: somebody edited a rule.
_REACH_CACHE_FILLED_AT = 0.0


def _age_out_reach_caches() -> None:
    """Drop the reach-derived caches once they are older than the record TTL."""
    global _REACH_CACHE_FILLED_AT, _GRANTED_BY_OWNER_CACHE
    if _REACH_CACHE_FILLED_AT and (time.monotonic() - _REACH_CACHE_FILLED_AT) > _SFX_CACHE_TTL:
        _REACH_INDEX_CACHE.clear()
        _GRANTED_BY_OWNER_CACHE = None
        _REACH_CACHE_FILLED_AT = 0.0


def reach_owner_ids(repo, sfx, flavour: str) -> tuple[str, ...]:
    """The owner ids one rule's reach declarations of ``flavour`` select.

    Each declaration's path **yields** the owners, so this resolves it against the
    live world — read-only, with nothing written onto anyone. Declarations of one
    flavour combine with **OR** (the union *is* the reach). A path that errors or
    resolves to nothing contributes nothing rather than raising: a broken
    declaration is an authoring problem `validateSfx` reports, not a reason to fail
    a sheet read.
    """
    out: list[str] = []
    seen: set[str] = set()
    for declaration in (getattr(sfx, "reach", None) or []):
        declared = getattr(declaration, "flavour", None)
        if getattr(declared, "value", declared) != flavour:
            continue
        result = _resolve_reach_spec(repo, getattr(declaration, "spec", None))
        for value in result:
            owner_id = getattr(value, "id", None) or str(value)
            if owner_id not in seen:
                seen.add(owner_id)
                out.append(owner_id)
    return tuple(out)


def _resolve_reach_spec(repo, spec) -> list:
    """Resolve one reach path against the live world, failing closed."""
    if spec is None or not getattr(spec, "steps", None):
        return []
    from transversal.services.target_resolver import TargetContext, resolve

    try:
        # No subject on purpose: a reach declaration *yields* the owners, so it must
        # not depend on which owner is asking — that was the retired gate's reading.
        result = resolve(spec, TargetContext(subject=None, repo=repo))
    except Exception:
        return []
    return [] if result.errors else list(result.values)


def reach_index(repo, flavour: str) -> dict[str, frozenset[str]]:
    """Every rule declaring reach of ``flavour``, mapped to the owners it selects.

    One pass over the registry, cached until a rule write **or** the record TTL —
    so a fan-out over many entities resolves each declaration **once** rather than
    per entity (the cost note in [[Dynamic SFX Reach]]), while a world that changed
    underneath it (a trait that moved, a place that filled up) is picked up within
    the TTL rather than never. Empty while no rule declares reach.
    """
    global _REACH_CACHE_FILLED_AT
    _age_out_reach_caches()
    cached = _REACH_INDEX_CACHE.get(flavour)
    if cached is not None:
        return cached
    index: dict[str, frozenset[str]] = {}
    getter = getattr(repo, "get_all_sfxs", None)
    for sfx in (getter() if callable(getter) else []):
        owners = reach_owner_ids(repo, sfx, flavour)
        if owners:
            index[sfx.id] = frozenset(owners)
    _REACH_INDEX_CACHE[flavour] = index
    _REACH_CACHE_FILLED_AT = time.monotonic()
    return index


#: ``owner id -> the rules that simply have it``: the inverse of the *granted* half of
#: the reach index. Built once per cache fill, so a per-row read — the sheet asking each
#: trait instance what it has — is a dict lookup rather than a scan of every rule.
_GRANTED_BY_OWNER_CACHE: dict[str, tuple[str, ...]] | None = None


def granted_sfx_by_owner(repo) -> dict[str, tuple[str, ...]]:
    """Which rules each owner id simply *has*, from **granted** reach declarations.

    Read-time only, and deliberately **not** folded into ``TraitSetting.sfx_ids``: that
    list is what is *attached*, and the trait editor writes it back wholesale, so
    merging the two would materialise a reach rule onto the instance the first time
    anything saved a trait — quietly turning a live read into a one-time grant. The
    aggregate is built from the same index availability reads, so the two cannot
    disagree about who has what ([[Dynamic SFX Reach]]).
    """
    global _GRANTED_BY_OWNER_CACHE
    _age_out_reach_caches()
    if _GRANTED_BY_OWNER_CACHE is not None:
        return _GRANTED_BY_OWNER_CACHE
    by_owner: dict[str, list[str]] = {}
    for sfx_id, owners in reach_index(repo, "granted").items():
        for owner_id in owners:
            by_owner.setdefault(owner_id, []).append(sfx_id)
    _GRANTED_BY_OWNER_CACHE = {k: tuple(sorted(v)) for k, v in by_owner.items()}
    return _GRANTED_BY_OWNER_CACHE


def _load_sfx(repo, sfx_id: str):
    """An SFX record, cache-first (see the cache notes above).

    Only *hits* are cached. A miss stays a miss on every call, because a missing
    record usually means "not created yet" — caching that would hide a brand-new
    SFX for the whole TTL, which is a functional bug, not a staleness one.
    """
    global _SFX_CACHE_FILLED_AT
    now = time.monotonic()
    if _SFX_CACHE_FILLED_AT and (now - _SFX_CACHE_FILLED_AT) > _SFX_CACHE_TTL:
        invalidate_sfx_cache()
    if not _SFX_CACHE_FILLED_AT:
        _SFX_CACHE_FILLED_AT = now
    if sfx_id in _SFX_CACHE:
        return _SFX_CACHE[sfx_id]
    sfx = repo.get_sfx(sfx_id)
    if sfx is not None:
        _SFX_CACHE[sfx_id] = sfx
    return sfx


def build_sfx_availability_prefetch(
    repo,
    entities: list,
    universes: list[str] | None = None,
    sfx_docs: list | None = None,
) -> SfxAvailabilityPrefetch:
    """Bulk-fetch everything :func:`get_available_sfx_ids` reads, for many entities.

    ``entities`` are already-loaded ``Entity`` objects (callers generally have
    them from ``list_all_entities``), so no entity is re-fetched. Trait grants
    are universe-gated, so they're fetched once per distinct entity universe.
    ``sfx_docs`` reuses an already-fetched SFX list (e.g. from the caller's
    trigger short-circuit) instead of re-reading the collection.
    """
    entity_ids = [e.id for e in entities]

    projections: dict[str, Any] = {}
    for projs in repo.get_projections_for_entities(entity_ids).values():
        for p in projs:
            projections[p.id] = p

    traitsettings: dict[str, list] = {}
    traitsetsettings: dict[str, list] = {}
    by_universe: dict[str, list[str]] = {}
    for e in entities:
        by_universe.setdefault(e.current_universe or "", []).append(e.id)
    for uni, eids in by_universe.items():
        scoped = universes or [uni]
        traitsettings.update(repo.get_effective_traitsettings_bulk(eids, scoped))
        traitsetsettings.update(repo.get_effective_traitsetsettings_bulk(eids, scoped))

    # Sub-trait grants, in the same bulk shape: the effective reads above return
    # only `from_type == 'entity'` rows, so an entity's nested instances are
    # walked in here rather than costing a per-entity query during the fan-out.
    for eid, nested in _walk_nested_bulk(repo, traitsettings).items():
        traitsettings.setdefault(eid, [])
        traitsettings[eid] = traitsettings[eid] + nested

    # …and the edge-anchored instances, in one batch for the whole fan-out.
    read_edge_traits = getattr(repo, "get_relationship_traitsettings_for_entities", None)
    relationship_traitsettings = read_edge_traits(eids) if read_edge_traits is not None else {}

    # Location scope, resolved once per *distinct* location rather than per
    # entity: the fan-out visits every entity, and most of them share a room.
    location_rules: dict[str, list] = {}
    for loc_id in {e.current_location for e in entities if getattr(e, "current_location", None)}:
        rule_ids: list[str] = []
        for place in repo.list_ancestor_locations_with_sfx(loc_id):
            for sid in (place.sfx_ids or []):
                if sid not in rule_ids:
                    rule_ids.append(sid)
        location_rules[loc_id] = rule_ids

    return SfxAvailabilityPrefetch(
        entities={e.id: e for e in entities},
        faction_rules=repo.list_member_factions_with_sfx_bulk(entity_ids),
        projections=projections,
        table_bucket=repo.get_sfx_owner("table"),
        traitsettings=traitsettings,
        traitsetsettings=traitsetsettings,
        location_rules=location_rules,
        relationship_traitsettings=relationship_traitsettings,
        sfx_by_id={s.id: s for s in (sfx_docs if sfx_docs is not None else repo.get_all_sfxs())},
    )


def get_available_sfx_ids(
    entity_id: str,
    universe: str,
    repo,
    prefetch: SfxAvailabilityPrefetch | None = None,
    triggers: frozenset[str] | None = None,
    out_sources: dict | None = None,
) -> list[str]:
    """Return the sorted SFX ids available to ``entity_id`` in ``universe``.

    ``out_sources`` (optional) receives the walk's own map from a granted SFX id to
    the trait instance that grants it. It is handed out rather than re-derived so a
    second reader cannot disagree with this one about "the trait this rule sits on"
    — which is what ``unavailable_sfx_reasons`` needs to say *why* a rule is out.

    ``prefetch`` (optional) supplies bulk-loaded per-entity data so a fan-out
    over many entities avoids the per-entity round-trips; see
    :func:`build_sfx_availability_prefetch`.

    ``triggers`` (optional) narrows to SFX whose trigger is one of these — the
    caller knows which triggers an event could match
    (``effects_engine.triggers.triggers_for_event``), so a candidate that cannot
    fire is dropped before it is read or evaluated. ``None`` = no narrowing, and
    callers that list SFX for a *person* to activate (the sheet) must leave it
    unset: a manual activation has no event type.
    """
    ids: set[str] = set()
    # The active projection's id, if any — one more surface this entity "owns", for
    # the reach membership test below.
    owned_projection_id = ""
    # Map each trait-granted SFX id to its source trait-setting, so source-aware
    # conditions (SOURCE_RATING) can resolve "the trait this SFX is on".
    sfx_sources: dict[str, Any] = {}

    # Direct entity + active projection ownership.
    if prefetch is not None:
        entity = prefetch.entities.get(entity_id)
    else:
        entity = repo.get_entity(entity_id)
    if entity is not None:
        ids.update(entity.sfx_ids or [])
        if entity.current_projection:
            if prefetch is not None:
                proj = prefetch.projections.get(entity.current_projection)
            else:
                proj = repo.get_projection(entity.current_projection)
            if proj is not None:
                ids.update(proj.sfx_ids or [])
                owned_projection_id = proj.id

    # Table-wide ownership (available to every entity).
    bucket = prefetch.table_bucket if prefetch is not None else repo.get_sfx_owner("table")
    if bucket is not None:
        ids.update(bucket.sfx_ids or [])

    # Trait-level grants, universe-gated via effective trait settings. Defaults
    # are already materialized onto the instance's ``sfx_ids`` at grant time
    # (see ``EntityRepository.create_traitsetting``), so this reads the instance
    # list directly rather than re-unioning ``Trait.default_sfx_ids``.
    if prefetch is not None:
        trait_settings = prefetch.traitsettings.get(entity_id, [])
        traitset_settings = prefetch.traitsetsettings.get(entity_id, [])
    else:
        trait_settings = repo.get_effective_traitsettings(entity_id, [universe])
        # A *sub*-trait's rules count too (a portent, an elemental root); the
        # effective read excludes them, so they are walked in.
        trait_settings = trait_settings + _nested_traitsettings_for(
            repo, entity_id, universe)
        # …and the instances it holds on its **relationship edges** ([[B153]]): a
        # tie carries its own sheet (a rank, a tenure, a statement), and the rules
        # that sheet offers belong to the entity holding the tie. The effective read
        # is entity-anchored rows only, so before this the rules a tie carried were
        # never offered — `sfx-challenge-statement` sat greyed on the sheet with no
        # condition to blame (its trait declares no conditions at all).
        trait_settings = trait_settings + _relationship_traitsettings_for(
            repo, entity_id, prefetch)
        traitset_settings = repo.get_effective_traitsetsettings(entity_id, [universe])

    for ts in trait_settings:
        # A **disabled** instance grants nothing. "Landed" is a state — a spent
        # agenda step, a suppressed technique — and the rules it carries must stop
        # being offered with it, or the button that fired it is offered again.
        # This is implicit for every rule whose owner is disabled, rather than
        # something each rule authors: it is a fact about the owner, not the rule.
        # (The nearest condition, HAS_EFFECTIVE_TRAIT, cannot stand in: it matches
        # by *registry trait* and returns the first match's `enabled`, so several
        # instances of one generic trait — an agenda's steps — answer arbitrarily.)
        if not getattr(ts, "enabled", True):
            continue
        for sid in (ts.sfx_ids or []):
            ids.add(sid)
            sfx_sources.setdefault(sid, ts)
        # …and the rules the trait says every instance simply *has*. A trait lists
        # a rule in `possible_sfx_ids` to say "this trait offers it"; a declaration
        # on its own is the learn-chip's business, not availability's, so it is
        # deliberately not added here. The exception used to be a rule-level
        # `implicit` flag ([[B131]]), now retired in favour of a **granted reach
        # declaration** on the rule itself — the dynamic form of the same
        # relationship, which availability reads wherever the rule reaches
        # ([[Dynamic SFX Reach]]).

    # Trait-set-as-unit grants, universe-gated via effective set settings.
    for tss in traitset_settings:
        ids.update(tss.sfx_ids or [])

    # Reach declarations on the rules themselves ([[Dynamic SFX Reach]]): a
    # **granted** declaration means every owner its path yields simply *has* the
    # rule. Resolved once per rule and cached (`reach_index`), then membership-tested
    # against what this entity owns — so this does not become "walk every owner, for
    # every rule, on every event". An **offered** declaration is the learn-chip's
    # business (`acquirableSfxIds`), not availability's: it needs taking first.
    granted = reach_index(repo, "granted")
    if granted:
        owned_ids: set[str] = set()
        if entity is not None:
            owned_ids.add(entity.id)
        if owned_projection_id:
            owned_ids.add(owned_projection_id)
        owned_ids.update(ts.id for ts in trait_settings)
        owned_ids.update(tss.id for tss in traitset_settings)
        if owned_ids:
            for sfx_id, owners in granted.items():
                if sfx_id in ids or not (owners & owned_ids):
                    continue
                ids.add(sfx_id)
                # A rule granted through a trait instance sits on that instance, so
                # a source-aware condition reads the right trait.
                for ts in trait_settings:
                    if ts.id in owners:
                        sfx_sources.setdefault(sfx_id, ts)
                        break

    # Membership scope: a rule owned by a *faction* reaches its members
    # ([[B109]]). Read-time only, exactly like the place scope below — nothing is
    # written on the member, so leaving the roster ends the rule by itself, and a
    # **rank** gate is a condition the author writes rather than a second
    # mechanism here. `list_member_factions_with_sfx` returns only the factions the
    # entity is on the roster of that actually carry rules, so an entity in no
    # faction costs a handful of id reads.
    if entity is not None:
        if prefetch is not None:
            ids.update(prefetch.faction_rules.get(entity_id, []))
        else:
            for faction in repo.list_member_factions_with_sfx(entity_id):
                ids.update(faction.sfx_ids or [])

    # Location scope: a rule owned by a *place* reaches the entities under it.
    # Read-time only — nothing is written to the occupant, so walking out ends
    # the rule by itself. `list_ancestor_locations_with_sfx` returns just the
    # places above the entity that actually carry rules (itself included), so a
    # world with no place-owned rules costs one empty read.
    #
    # This is also what keeps the cost bounded: candidates come from the room
    # you are in, not from every rule in the game.
    if entity is not None:
        location_id = getattr(entity, "current_location", None)
        if location_id:
            if prefetch is not None:
                ids.update(prefetch.location_rules.get(location_id, []))
            else:
                for place in repo.list_ancestor_locations_with_sfx(location_id):
                    ids.update(place.sfx_ids or [])

    # Filter by context-free conditions so listing matches fireability
    # (e.g. entity_type, in_universe, source_rating). Variable/context-gated
    # conditions stay fire-time.
    if entity is not None:
        from transversal.services.conditions import evaluate_conditions, static_conditions
        for sfx_id in list(ids):
            if prefetch is not None:
                sfx = prefetch.sfx_by_id.get(sfx_id)
            else:
                sfx = _load_sfx(repo, sfx_id)
            if sfx is None:
                # Unresolvable id: keep it (as before) rather than silently
                # dropping a reference the data may still be catching up to.
                continue
            if triggers is not None and sfx.trigger not in triggers:
                # Cannot match this event: no read of the conditions, no
                # evaluation — that is the point of the narrowing.
                ids.discard(sfx_id)
                continue
            static = static_conditions(sfx.conditions or [])
            source = sfx_sources.get(sfx_id)
            source_element = None
            if source is not None and getattr(sfx, "source_kind", None):
                from transversal.services import target_catalog as tc
                source_element = tc.source_element(sfx.source_kind)
            if static and not evaluate_conditions(entity, static, repo, source=source, source_element=source_element):
                ids.discard(sfx_id)

    if out_sources is not None:
        out_sources.update(sfx_sources)
    return sorted(ids)


def get_place_sfx_rules(entity_id: str, universe: str, repo) -> list[dict]:
    """The rules an entity may press *because of where it stands*, by place.

    Availability already folds a place's rules into the entity's own list; this
    is that same contribution, kept apart and attributed to the place it comes
    from, so a sheet can show them under a heading instead of silently mixing
    them with the entity's own. Nothing is written on the occupant — the group
    disappears the moment they walk out, which is the point of reading scope at
    read time rather than attaching.

    Filtered *through* :func:`get_available_sfx_ids` rather than re-deriving
    from the place's list, so the strip can never offer something the activation
    path would refuse. One rule, two views.

    A rule that fires *as you arrive* is left out (see
    :func:`menu_contexts.trigger_fires_on_arrival`): it has already done its
    work by the time you are standing there — an instant, not a permanent — so
    there is nothing to keep track of. The rule still *happens*; it just isn't
    held up as something the place lends you.

    Each rule is attributed to the nearest place that carries it (the entity's
    own room wins over an ancestor), and places with nothing left to show are
    dropped.
    """
    entity = repo.get_entity(entity_id)
    if entity is None:
        return []
    location_id = getattr(entity, "current_location", None)
    if not location_id:
        return []
    available = set(get_available_sfx_ids(entity_id, universe, repo))
    if not available:
        return []
    groups: list[dict] = []
    claimed: set[str] = set()
    for place in repo.list_ancestor_locations_with_sfx(location_id):
        owned = sorted({sid for sid in (place.sfx_ids or [])
                        if sid in available and sid not in claimed
                        and not _spent_on_arrival(repo, sid)})
        if not owned:
            continue
        claimed.update(owned)
        groups.append({
            "location_id": place.id,
            "location_name": getattr(place, "name", None) or place.id,
            "sfx_ids": owned,
        })
    return groups


def get_arrival_sfx_rules(location_id: str, repo) -> list[dict]:
    """The rules that fire as an audience **arrives** at a place, by place.

    The deliberate counterpart of :func:`get_place_sfx_rules`, which leaves exactly
    these out: the strip a sheet shows is what the place *lends you while you stand
    there*, and an arrival rule has already done its work by then — an instant, not
    a permanent. So no surface ever listed one, and "what happens when someone
    walks in here?" was invisible from the place itself ([[B8]]).

    The GM inspecting a place needs the opposite question, so this keeps only the
    arrival rules and drops the rest. No availability filter, because the audience
    is not known: this is a fact about the place, not about what one occupant may
    use. The same ancestors-with-rules walk as the standing read, deduped
    nearest-first, so a rule on a parent room shows only against the nearer place
    that carries it.
    """
    if not location_id:
        return []
    groups: list[dict] = []
    claimed: set[str] = set()
    for place in repo.list_ancestor_locations_with_sfx(location_id):
        owned = sorted({sid for sid in (place.sfx_ids or [])
                        if sid not in claimed and _spent_on_arrival(repo, sid)})
        if not owned:
            continue
        claimed.update(owned)
        groups.append({
            "location_id": place.id,
            "location_name": getattr(place, "name", None) or place.id,
            "sfx_ids": owned,
        })
    return groups


def _spent_on_arrival(repo, sfx_id: str) -> bool:
    """Whether this rule fires as its audience arrives (so it isn't held).

    An unresolvable record answers ``False``: the strip keeps what it cannot
    judge rather than hiding a rule the data may still be catching up to — the
    same posture the availability read takes.
    """
    sfx = _load_sfx(repo, sfx_id)
    if sfx is None:
        return False
    from transversal.services.menu_contexts import trigger_fires_on_arrival
    return trigger_fires_on_arrival(getattr(sfx, "trigger", "") or "")


def resolve_sfx_source(repo, entity_id: str, universe: str, sfx_id: str, source_kind: str):
    """Resolve an SFX's activation source from ownership when the event carries
    no explicit ``source_id`` (automatic triggers like ``on_roll``).

    Returns ``(source_object, catalog_element)`` or None. For trait/trait-set
    sources the object is the instance that grants this SFX; for entity/projection
    sources it is the entity/active projection itself.
    """
    from transversal.services import target_catalog as tc

    element = tc.source_element(source_kind) if source_kind else None
    if element is None or repo is None:
        return None
    if source_kind == "faction":
        # Which of the entity's factions owns this rule ([[B109]]). Branches on the
        # *kind*, not the element: a faction resolves to the ``entity`` element, so
        # the element alone cannot tell it from an entity-owned rule — and a
        # faction-owned rule's source is the faction, never the member.
        for faction in repo.list_member_factions_with_sfx(entity_id):
            if sfx_id in (faction.sfx_ids or []):
                return (faction, "faction")
        return None
    if element == "entity":
        entity = repo.get_entity(entity_id)
        return (entity, "entity") if entity is not None else None
    if element == "location":
        # A place-owned rule's source is the *place*, not the entity standing in
        # it — that is the whole point of the kind. Find which place in the
        # entity's scope owns this SFX (the location itself or an ancestor).
        entity = repo.get_entity(entity_id)
        location_id = getattr(entity, "current_location", None) if entity is not None else None
        if not location_id:
            return None
        for place in repo.list_ancestor_locations_with_sfx(location_id):
            if sfx_id in (place.sfx_ids or []):
                return (place, "location")
        return None
    if element == "projection":
        entity = repo.get_entity(entity_id)
        proj = repo.get_projection(entity.current_projection) if (entity is not None and entity.current_projection) else None
        return (proj, "projection") if proj is not None else None
    if element == "traitsetting":
        for ts in repo.get_effective_traitsettings(entity_id, [universe]):
            if sfx_id in (ts.sfx_ids or []):
                return (ts, "traitsetting")
        # A rule may live on a *sub*-trait (an agenda's portent, an elemental
        # root). The effective read returns only `from_type == 'entity'` rows, so
        # without this the rule was attached and silently dead — and `select
        # source`, which is how such a rule reaches its container, could never
        # resolve to the instance granting it.
        for ts in _nested_traitsettings_for(repo, entity_id, universe):
            if sfx_id in (ts.sfx_ids or []):
                return (ts, "traitsetting")
        return None
    if element == "traitsetsetting":
        for tss in repo.get_effective_traitsetsettings(entity_id, [universe]):
            if sfx_id in (tss.sfx_ids or []):
                return (tss, "traitsetsetting")
        return None
    return None


# ── Owner index + batch management ────────────────────
#
# The GM ownership panel reads a flattened view of every owner surface (the
# two ``sfx_owners`` buckets plus entity/projection/trait/trait-instance/
# trait-set ``sfx_ids`` fields) and writes add/remove operations back through
# a dispatcher so the frontend doesn't need to know which collection each
# owner type lives in.

_BUCKET_TYPES = ("table", "gm")
_BUCKET_LABELS = {"table": "Table", "gm": "GM"}

# Owner surfaces in author-facing words — used when telling someone why a rule
# can't go where they tried to put it.
_SURFACE_LABELS = {
    "table": "the Table (everyone)",
    "gm": "the GM bucket",
    "entity": "an entity",
    "location": "a location",
    "projection": "a projection",
    "trait": "a trait definition",
    "trait_instance": "a trait instance",
    "trait_set": "a trait set instance",
}

# Every owner surface an SFX can be attached to (mirrors SfxOwnerKind).
# Every owner surface an SFX can be attached to (mirrors SfxOwnerKind).
# ``location`` is a distinct surface even though a location *is* an entity: a
# place-owned rule resolves its source to the place, and a `location`-sourced SFX
# attached to a character has to be catchable.
_OWNER_SURFACES = ("table", "gm", "entity", "location", "projection", "trait", "trait_instance", "trait_set")


def owner_surfaces_for(sfx) -> frozenset[str]:
    """Every owner surface this SFX may be attached to.

    The declared ``source_kind`` names the surface it belongs on (see
    ``target_catalog.SOURCE_KINDS``); an SFX without one is unrestricted. This is
    the **one rule** behind three things that used to disagree: the attach guard,
    the picker's filter, and authoring validation — so a mismatch is refused for
    the same reason it isn't offered.
    """
    from transversal.services import target_catalog as tc

    kind = tc.source_kind(getattr(sfx, "source_kind", None) or "")
    if kind is None or not kind.owner_surfaces:
        return frozenset(_OWNER_SURFACES)
    return frozenset(kind.owner_surfaces)


def can_attach(sfx, owner_type: str) -> bool:
    """Whether ``sfx`` may be attached to an owner of ``owner_type``."""
    return owner_type in owner_surfaces_for(sfx)


def reach_refusal(sfx, owner_id: str, repo) -> str | None:
    """Why this rule may not attach to that owner — or ``None`` when it may.

    A rule that declares reach says **who it reaches**, so attaching it outside that
    set contradicts the declaration. This is the acquire gate's *enforcement*, moved
    onto the selector: the gate asked "does the path hold for *this* candidate?", the
    selector answers "here is the whole set", and membership is the same refusal
    without a per-candidate read. A rule with no reach declaration is unrestricted —
    the common case, where its hand-picked lists are what offer it.
    """
    if repo is None or not owner_id or not (getattr(sfx, "reach", None) or []):
        return None
    reached = set(reach_owner_ids(repo, sfx, "granted"))
    reached |= set(reach_owner_ids(repo, sfx, "offered"))
    return None if owner_id in reached else "outside this rule's reach"


def attach_refusal(sfx, owner_type: str, owner_id: str = "", repo=None) -> str | None:
    """Why this SFX can't attach there — or ``None`` when it can.

    Two questions, in order: *may it live on this kind of thing* (its declared
    source), and *does this rule reach that owner* (its reach declarations, when it
    has any). Author-facing: the picker filters on the first and the chip list on the
    second, and both show this text for what they leave out.
    """
    if not can_attach(sfx, owner_type):
        wanted = sorted(owner_surfaces_for(sfx))
        named = " or ".join(_SURFACE_LABELS.get(s, s) for s in wanted)
        return f"belongs on {named}"
    refusal = reach_refusal(sfx, owner_id, repo)
    if refusal:
        return refusal
    # Directions have to be *followable* from the place that grants them. Only a
    # place owner is measured: an entity moves, so what it could tell you depends
    # on where it stands when the rule fires. [[Guided Route]]
    if repo is not None and owner_id and owner_type == "location":
        from transversal.services.guided_route import (
            find_unreachable_directions,
            refusal_reason,
        )

        findings = find_unreachable_directions(sfx, repo, [owner_id])
        if findings:
            return refusal_reason(findings[0], repo)
    return None


def _owner_object(repo, owner_type: str, owner_id: str):
    """The object an owner id refers to, for seeding an acquire path."""
    try:
        if owner_type == "trait_instance":
            return repo.get_traitsetting(owner_id)
        if owner_type == "trait_set":
            return repo.get_traitsetsetting(owner_id)
        return repo.get_entity(owner_id)
    except Exception:
        return None


def owned_surfaces(repo, sfx_id: str) -> set[str]:
    """The owner-surface names that actively carry ``sfx_id`` (empty = unowned).

    Used by authoring validation to catch a declared ``source_kind`` that does
    not match where the SFX is actually attached (a silent no-op at fire time).
    """
    surfaces: set[str] = set()
    for owner_type in _OWNER_SURFACES:
        for ref in list_owner_refs(repo, owner_type):
            if sfx_id in (ref.get("sfx_ids") or []):
                surfaces.add(owner_type)
                break  # one matching ref is enough per surface type
    return surfaces


def backfill_source_kinds(repo) -> int:
    """Idempotently backfill ``source_kind`` to match each SFX's owner surface.

    Folds the table/GM owner buckets into the unified source axis (``table`` /
    ``gm``) and fills trait/entity-owned SFX that never declared a source. Runs
    on every startup; a no-op once backfilled. Skips orphaned SFX (owned by
    nothing) and SFX that already declare a source. Returns the number of SFX
    mutated.
    """
    changed = 0

    # Buckets → source kind.
    for bucket_id, kind in (("table", "table"), ("gm", "gm")):
        bucket = repo.get_sfx_owner(bucket_id)
        for sfx_id in (bucket.sfx_ids or []) if bucket else []:
            sfx = repo.get_sfx(sfx_id)
            if sfx is not None and not sfx.source_kind:
                sfx.source_kind = kind
                repo.update_sfx(sfx)
                changed += 1

    # Typed surfaces → source kind. ``trait`` (registry default) and
    # ``trait_instance`` both mean the SFX is carried by a trait setting.
    for sfx in repo.get_all_sfxs():
        if sfx.source_kind:
            continue
        surfaces = owned_surfaces(repo, sfx.id)
        if "trait_instance" in surfaces or "trait" in surfaces:
            sfx.source_kind = "trait_setting"
            repo.update_sfx(sfx)
            changed += 1
        elif "entity" in surfaces:
            sfx.source_kind = "entity"
            repo.update_sfx(sfx)
            changed += 1

    # Explicit passive scope for session-start rules.
    for sfx in repo.get_all_sfxs():
        if sfx.trigger == "on_session_start" and not sfx.arming_scope:
            sfx.arming_scope = "global"
            repo.update_sfx(sfx)
            changed += 1

    return changed


def backfill_play_as_rating_targets(repo) -> int:
    """Idempotently move a **Play as Rating** effect off the dead token onto a path.

    The action used to declare ``implicit_target="{source_trait}"``, and no firing
    path ever bound that token — so every stored ``play_as_rating`` effect passed a
    literal ``"{source_trait}"`` as its target and resolved to no trait instance,
    silently doing nothing (``sfx-hinder`` is the live case). The action now takes a
    targeting path, and the rule's own source is ``select source`` — the trait
    instance itself, since the source kind is ``trait_setting``.

    Runs on every startup; a no-op once migrated. Effects that already carry a spec,
    or whose target is something other than the dead token, are left alone — an
    author's own path is not this pass's business. Returns the number of effects
    rewritten.
    """
    from transversal.services.target_spec import SelectStep, TargetSpec

    changed = 0
    for sfx in repo.get_all_sfxs():
        touched = False
        for effect in (sfx.effects or []):
            if effect.action != "play_as_rating" or effect.target_spec is not None:
                continue
            if (effect.target or "").strip() != "{source_trait}":
                continue
            effect.target_spec = TargetSpec(steps=[SelectStep(collection="source")])
            effect.target = ""
            touched = True
        if touched:
            repo.update_sfx(sfx)
            changed += 1
    return changed


def _entity_name(repo, entity_id: str) -> str:
    entity = repo.get_entity(entity_id)
    return entity.name if entity else ""


def _trait_name(repo, trait_id: str) -> str:
    trait = repo.get_trait(trait_id)
    return trait.name if trait else ""


def _traitset_name(repo, traitset_id: str) -> str:
    ts = repo.get_traitset_by_id(traitset_id)
    return ts.name if ts else ""


def list_owner_refs(repo, owner_type: str) -> list[dict]:
    """Return flattened owner refs of one type, **holders first**, for the panel.

    Ordered by how many rules the owner already holds (descending), and *stable*
    within a count so the underlying order stands: the panel exists to manage what
    is **attached**, and a flat list of hundreds buries the handful that have
    anything at all. Sorting here rather than in the picker keeps one answer for
    every consumer — the same reason the list is built in one place.
    """
    return sorted(_owner_refs_for(repo, owner_type),
                  key=lambda ref: -len(ref.get("sfx_ids") or []))


def _owner_refs_for(repo, owner_type: str) -> list[dict]:
    """The owner refs of one type, in the repository's own order.

    Each ref is ``{owner_type, owner_id, label, sfx_ids}``.  ``sfx_ids`` is the
    *active grant* list for that surface (``Trait.default_sfx_ids`` for the
    trait owner, ``TraitSetting.sfx_ids`` for trait instances, etc.).
    """
    if owner_type in _BUCKET_TYPES:
        owner = repo.get_sfx_owner(owner_type)
        if owner is None:
            return []
        return [{
            "owner_type": owner_type,
            "owner_id": owner.id,
            "label": _BUCKET_LABELS.get(owner_type, owner.id),
            "sfx_ids": list(owner.sfx_ids or []),
        }]

    if owner_type == "entity":
        from transversal.domain import EntityType
        return [{
            "owner_type": "entity",
            "owner_id": e.id,
            "label": e.name or e.id,
            # What kind of entity this is. Without it the picker is a flat list of
            # names — a character, a world and a faction are indistinguishable.
            "entity_type": getattr(e.type, "value", e.type),
            "sfx_ids": list(e.sfx_ids or []),
        } for e in repo.list_all_entities() if e.type != EntityType.LOCATION]

    if owner_type == "location":
        from transversal.domain import EntityType
        return [{
            "owner_type": "location",
            "owner_id": e.id,
            "label": e.name or e.id,
            "entity_type": getattr(e.type, "value", e.type),
            "sfx_ids": list(e.sfx_ids or []),
        } for e in repo.list_all_entities() if e.type == EntityType.LOCATION]

    if owner_type == "projection":
        return [{
            "owner_type": "projection",
            "owner_id": p.id,
            "label": p.name or p.id,
            "sfx_ids": list(p.sfx_ids or []),
        } for p in repo.list_all_projections()]

    if owner_type == "trait":
        return [{
            "owner_type": "trait",
            "owner_id": t.id,
            "label": t.name or t.id,
            "sfx_ids": list(t.default_sfx_ids or []),
        } for t in repo.get_all_traits()]

    if owner_type == "trait_instance":
        refs = []
        entity_names: dict[str, str] = {}
        trait_names: dict[str, str] = {}
        for ts in repo.list_all_traitsettings():
            ename = entity_names.get(ts.entity_id)
            if ename is None:
                ename = _entity_name(repo, ts.entity_id)
                entity_names[ts.entity_id] = ename
            tname = trait_names.get(ts.trait_id)
            if tname is None:
                tname = _trait_name(repo, ts.trait_id)
                trait_names[ts.trait_id] = tname
            label = tname or ts.trait_id
            if ename:
                label = f"{label} @ {ename}"
            refs.append({
                "owner_type": "trait_instance",
                "owner_id": ts.id,
                "label": label,
                "sfx_ids": list(ts.sfx_ids or []),
            })
        return refs

    if owner_type == "trait_set":
        refs = []
        entity_names: dict[str, str] = {}
        traitset_names: dict[str, str] = {}
        for tss in repo.list_all_traitsetsettings():
            ename = entity_names.get(tss.entity_id)
            if ename is None:
                ename = _entity_name(repo, tss.entity_id)
                entity_names[tss.entity_id] = ename
            tsname = traitset_names.get(tss.traitset_id)
            if tsname is None:
                tsname = _traitset_name(repo, tss.traitset_id)
                traitset_names[tss.traitset_id] = tsname
            label = tsname or tss.traitset_id
            if ename:
                label = f"{label} @ {ename}"
            refs.append({
                "owner_type": "trait_set",
                "owner_id": tss.id,
                "label": label,
                "sfx_ids": list(tss.sfx_ids or []),
            })
        return refs

    return []


def _get_owner_sfx_ids(repo, owner_type: str, owner_id: str) -> list[str] | None:
    """Return the current sfx_ids for one owner, or None if it doesn't exist."""
    if owner_type in _BUCKET_TYPES:
        owner = repo.get_sfx_owner(owner_id)
        return list(owner.sfx_ids or []) if owner else None
    if owner_type in ("entity", "location"):
        entity = repo.get_entity(owner_id)
        return list(entity.sfx_ids or []) if entity else None
    if owner_type == "projection":
        proj = repo.get_projection(owner_id)
        return list(proj.sfx_ids or []) if proj else None
    if owner_type == "trait":
        trait = repo.get_trait(owner_id)
        return list(trait.default_sfx_ids or []) if trait else None
    if owner_type == "trait_instance":
        ts = repo.get_traitsetting(owner_id)
        return list(ts.sfx_ids or []) if ts else None
    if owner_type == "trait_set":
        tss = repo.get_traitsetsetting(owner_id)
        return list(tss.sfx_ids or []) if tss else None
    return None


def _set_owner_sfx_ids(repo, owner_type: str, owner_id: str, sfx_ids: list[str]) -> bool:
    """Write the sfx_ids list back onto one owner.  Returns True on success."""
    if owner_type in _BUCKET_TYPES:
        owner = repo.get_sfx_owner(owner_id)
        if owner is None:
            return False
        owner.sfx_ids = list(sfx_ids)
        repo.update_sfx_owner(owner)
        return True
    if owner_type in ("entity", "location"):
        entity = repo.get_entity(owner_id)
        if entity is None:
            return False
        entity.sfx_ids = list(sfx_ids)
        repo.update_entity(entity)
        return True
    if owner_type == "projection":
        proj = repo.get_projection(owner_id)
        if proj is None:
            return False
        proj.sfx_ids = list(sfx_ids)
        repo.update_projection(proj)
        return True
    if owner_type == "trait":
        trait = repo.get_trait(owner_id)
        if trait is None:
            return False
        trait.default_sfx_ids = list(sfx_ids)
        repo.update_trait(trait)
        propagate_trait_default_sfx(repo, owner_id)
        return True
    if owner_type == "trait_instance":
        ts = repo.get_traitsetting(owner_id)
        if ts is None:
            return False
        ts.sfx_ids = list(sfx_ids)
        repo.update_traitsetting(ts)
        return True
    if owner_type == "trait_set":
        tss = repo.get_traitsetsetting(owner_id)
        if tss is None:
            return False
        tss.sfx_ids = list(sfx_ids)
        repo.update_traitsetsetting(tss)
        return True
    return False


def add_sfx_to_owner(repo, owner_type: str, owner_id: str, sfx_id: str) -> bool:
    """Add an SFX id to one owner.  Idempotent.

    Enforces the SFX's declared ``source_kind``: an SFX that states a source
    kind may only attach to the matching owner surface (the single seam; see
    ``target_catalog.SOURCE_KINDS``). Buckets (``table``/``gm``) and SFX without
    a source kind are unrestricted. A rule that declares **reach** is also held to
    it — enforced here rather than only in the picker, because a list that lives in
    the UI is a suggestion and a direct attach would walk past it.
    """
    sfx = repo.get_sfx(sfx_id) if hasattr(repo, "get_sfx") else None
    if sfx is not None:
        if not can_attach(sfx, owner_type):
            return False
        if reach_refusal(sfx, owner_id, repo):
            return False
    ids = _get_owner_sfx_ids(repo, owner_type, owner_id)
    if ids is None:
        return False
    if sfx_id not in ids:
        ids.append(sfx_id)
        return _set_owner_sfx_ids(repo, owner_type, owner_id, ids)
    return True


def remove_sfx_from_owner(repo, owner_type: str, owner_id: str, sfx_id: str) -> bool:
    """Remove an SFX id from one owner.  Idempotent."""
    ids = _get_owner_sfx_ids(repo, owner_type, owner_id)
    if ids is None:
        return False
    if sfx_id in ids:
        ids.remove(sfx_id)
        return _set_owner_sfx_ids(repo, owner_type, owner_id, ids)
    return True


def propagate_trait_default_sfx(repo, trait_id: str) -> int:
    """Add a trait's current default SFX to every existing instance of it.

    Additive: instances gain any missing default; nothing is removed. This is
    the #49 half — when ``Trait.default_sfx_ids`` changes, existing instances
    are re-provisioned. Also drives the startup backfill. Returns the number of
    instances updated.
    """
    trait = repo.get_trait(trait_id)
    defaults = list(trait.default_sfx_ids or []) if trait is not None else []
    if not defaults:
        return 0
    updated = 0
    for ts in repo.get_traitsettings_by_trait(trait_id):
        existing = list(ts.sfx_ids or [])
        missing = [d for d in defaults if d not in existing]
        if not missing:
            continue
        ts.sfx_ids = existing + missing
        repo.update_traitsetting(ts)
        updated += 1
    return updated


def backfill_trait_default_sfx(repo) -> int:
    """Idempotent startup backfill: materialize every trait's default SFX onto
    its existing instances (for instances created before provisioning landed)."""
    total = 0
    for trait in repo.get_all_traits():
        total += propagate_trait_default_sfx(repo, trait.id)
    return total


def ensure_gmc_base_difficulty(repo) -> None:
    """Seed the GMC-only trait set + its ``base difficulty`` trait. Idempotent.

    A GMC's baseline opposition die (the Cortex "minor GMC = a die" case) lives
    as a registry trait in a trait set filtered to ``EntityType.GMC`` — not as a
    separate entity field — so even a GMC with zero authored traits can oppose a
    roll. See [[Troupe Play]] (Sheet & base difficulty).
    """
    from transversal.domain import DieType, EntityType, RatingType, Trait, TraitSet

    TRAITSET_ID = "ts-gmc-base"
    TRAIT_ID = "trait-base-difficulty"

    if repo.get_traitset_by_id(TRAITSET_ID) is None:
        repo.create_traitset(TraitSet(
            id=TRAITSET_ID,
            name="GMC base",
            explanation="Baseline opposition for GMCs with no authored traits.",
            universes=[],  # universe-agnostic (applies everywhere)
            entity_types=[EntityType.GMC],
            order=0,
            limit=1,
            default_rating_type=RatingType.STATIC,
            default_die_type=DieType.D6,
        ))

    if repo.get_trait(TRAIT_ID) is None:
        repo.create_trait(Trait(
            id=TRAIT_ID,
            name="base difficulty",
            universes=[],
            traitset_id=TRAITSET_ID,
            default_die_type=DieType.D6,
            default_rating_type=RatingType.STATIC,
        ))


# ── The support character's way home (B61) ────────────

#: The rule a support character carries so it can rejoin the main it supports.
TELEPORT_TO_MAIN_SFX_ID = "sfx-teleport-to-main"


def ensure_teleport_to_main_sfx(repo) -> None:
    """Create/seed the teleport-to-main rule ([[B61]]). Idempotent.

    An SC is a *relationship* to a main, not a separate kind of character
    ([[Troupe Play]]), so the rule is provisioned onto whoever holds a `support`
    edge — no new plumbing, and no entity field.

    The route is a **path**, not a lookup: me → the edges I hold → the one typed
    `support` → its far end (`contact`) → where they are. The declared variable
    `world` (`self → universe`) is the **same-universe guard**: the contact is
    kept only when their universe is mine, so in another world the path resolves
    to nobody and the effect does nothing. That matters because `location/set`
    also writes the destination's universe — unguarded, this rule would perform
    the cross-universe jump the design reserves for transversal.
    """
    from transversal.domain import BoundVariable, Effect, EffectTiming, SFX
    from transversal.services.target_spec import (
        FilterStep,
        NavigateStep,
        SelectStep,
        TargetSpec,
    )

    if repo.get_sfx(TELEPORT_TO_MAIN_SFX_ID) is not None:
        return

    repo.create_sfx(SFX(
        id=TELEPORT_TO_MAIN_SFX_ID,
        name="Teleport To Main",
        description=(
            "Rejoin the main you support — step to where they are, if you are in "
            "the same world"
        ),
        limit="",
        trigger="manual",
        source_kind="entity",
        bound_variables=[
            BoundVariable(name="world", spec=TargetSpec(steps=[
                SelectStep(collection="self"),
                NavigateStep(edge="universe"),
            ])),
        ],
        effects=[
            Effect(
                timing=EffectTiming.IMMEDIATE,
                type="location",
                action="set",
                target_spec=TargetSpec(steps=[
                    SelectStep(collection="self"),
                    NavigateStep(edge="relationships"),
                    FilterStep(field="type", value="support"),
                    NavigateStep(edge="contact"),
                    FilterStep(field="current_universe", value="{world}"),
                    NavigateStep(edge="location"),
                ]),
            ),
        ],
    ))


def provision_support_default_sfx(repo, entity_id: str) -> bool:
    """Give one support character the way home. Additive: nothing is removed.

    Called when a support character is created (the roll-table-as-menu flow) and
    by the startup backfill. False when the rule cannot attach — the entity is
    gone, or its surface does not match the rule's declared ``source_kind``.
    """
    return add_sfx_to_owner(repo, "entity", entity_id, TELEPORT_TO_MAIN_SFX_ID)


def backfill_support_default_sfx(repo) -> int:
    """Idempotent startup backfill: every entity holding a `support` edge gets
    the rule (for support characters created before it existed). Returns how many
    were actually changed, so a no-op restart logs zero."""
    updated = 0
    for entity_id in repo.list_entities_with_relationship_type("support"):
        ids = _get_owner_sfx_ids(repo, "entity", entity_id)
        if ids is None or TELEPORT_TO_MAIN_SFX_ID in ids:
            continue
        if provision_support_default_sfx(repo, entity_id):
            updated += 1
    return updated

def unavailable_sfx_reasons(repo, entity, universe: str, sfx_ids, *,
                            prefetch=None) -> dict[str, list[str]]:
    """Why each candidate rule is unavailable: the conditions that stop it.

    Availability can only *discard* a rule when its static conditions fail, so a
    listing knows "not usable" and nothing else — which is how a card ends up greyed
    with no reason. This answers the question the card is asking: for every candidate
    that is not available, the phrase the rule's own conditions render as
    (:func:`sfx_text.condition_text`), one entry per failing condition.

    Only **static** conditions (the ones availability itself reads) can be a reason:
    a context-gated one (``roll_tier``, ``test_outcome``, a ``{variable}``) is not
    false, it is *unknown* until the moment it fires, and reporting it would grey a
    rule that is perfectly usable. An available rule is absent from the result.
    """
    from transversal.services.conditions import (
        evaluate_condition, static_conditions,
    )
    from transversal.services.sfx_text import condition_text, repo_name_resolver

    resolve = repo_name_resolver(repo)
    source_map: dict = {}
    available = set(get_available_sfx_ids(str(getattr(entity, "id", "")), universe, repo,
                                          out_sources=source_map))
    reasons: dict[str, list[str]] = {}
    for sfx_id in sfx_ids:
        sfx = (prefetch.sfx_by_id.get(sfx_id) if prefetch is not None
               else _load_sfx(repo, sfx_id))
        if sfx is None:
            continue
        if str(sfx_id) in available:
            continue
        static = static_conditions(sfx.conditions or [])
        if not static:
            continue
        source = source_map.get(sfx_id)
        source_element = None
        if source is not None and getattr(sfx, "source_kind", None):
            from transversal.services import target_catalog as tc
            source_element = tc.source_element(sfx.source_kind)
        # The phrase is the condition **as written** — `condition_text` renders the
        # positive form ("you are in Three Realms"), which on a *failing* condition
        # reads as its opposite. So each reason is framed explicitly as unmet until
        # the wording pass can negate per type ("you are not in Three Realms"); a
        # reason that states the opposite of the truth is worse than no reason.
        failing: list[str] = []
        for condition in static:
            if evaluate_condition(entity, condition, repo, None, source,
                                  source_element, None):
                continue
            phrase = condition_text(condition, resolve=resolve, source_element=source_element)
            failing.append(f"unmet: {phrase}" if phrase else "unmet: a condition it declares")
        if failing:
            reasons[str(sfx_id)] = failing
    return reasons
