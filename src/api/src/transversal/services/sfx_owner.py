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

import time

from dataclasses import dataclass, field
from typing import Any

from transversal.domain import SfxOwner


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
    """Seed the post-roll consequence-menu base moves as ``placement="menu"`` SFX.

    Side (player vs architect) is a ``USER_ROLE`` condition rather than a hard
    code path. The SFX live in the ``table`` bucket (available to every entity);
    menu assembly gates them by role. Idempotent.
    """
    from transversal.domain import Condition, ConditionType, Effect, EffectTiming, SFX

    base_moves = [
        ("proceed", "Proceed the narrative", "Move the scene forward without applying a consequence.", "player", []),
        ("create_scene_trait", "Create a scene trait", "Introduce a new scene trait at your effect die.", "player", [
            Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait", action="gain_or_step_up",
                   target="{choose_trait}", result="{effect_die}"),
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
                   target="{choose_trait}", result="{effect_die}"),
        ]),
    ]

    for sfx_id, name, description, role, effects in base_moves:
        if repo.get_sfx(sfx_id) is not None:
            continue
        repo.create_sfx(SFX(
            id=sfx_id, name=name, description=description,
            trigger="manual", placement="menu",
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
        target="{random:location}",
        target_scope="universe:earth",
        target_filter={"starter_location": True},
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
            eff.target = desired.target
            eff.target_filter = desired.target_filter
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
            target="{choose_trait}",
            target_scope="traitset:ts-complications-a190",
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
                trigger="manual", placement="menu",
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
        if existing.trigger != "manual" or existing.placement != "menu":
            existing.trigger = "manual"
            existing.placement = "menu"
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
            target="{choose_trait}",
            entity="{hitch_entity}",
            target_scope="traitset:ts-complications-a190",
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
            trigger="manual", placement="menu",
            conditions=[hitch_cond],
            effects=effects,
        ))
        return
    changed = False
    if existing.trigger != "manual" or existing.placement != "menu":
        existing.trigger = "manual"
        existing.placement = "menu"
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
            target="{choose_trait}",
            entity="{buying_entity}",
            target_scope="traitset:ts-complications-a190",
        ),
    ]

    existing = repo.get_sfx("opportunity-step-down-complication")
    if existing is not None:
        changed = False
        if existing.trigger != "manual" or existing.placement != "menu":
            existing.trigger = "manual"
            existing.placement = "menu"
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
        trigger="manual", placement="menu",
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


def invalidate_sfx_cache() -> None:
    """Drop the cached SFX records (call after any SFX write)."""
    global _SFX_CACHE_FILLED_AT
    _SFX_CACHE.clear()
    _SFX_CACHE_FILLED_AT = 0.0


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
        projections=projections,
        table_bucket=repo.get_sfx_owner("table"),
        traitsettings=traitsettings,
        traitsetsettings=traitsetsettings,
        location_rules=location_rules,
        sfx_by_id={s.id: s for s in (sfx_docs if sfx_docs is not None else repo.get_all_sfxs())},
    )


def get_available_sfx_ids(
    entity_id: str,
    universe: str,
    repo,
    prefetch: SfxAvailabilityPrefetch | None = None,
    triggers: frozenset[str] | None = None,
) -> list[str]:
    """Return the sorted SFX ids available to ``entity_id`` in ``universe``.

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
        traitset_settings = repo.get_effective_traitsetsettings(entity_id, [universe])

    for ts in trait_settings:
        for sid in (ts.sfx_ids or []):
            ids.add(sid)
            sfx_sources.setdefault(sid, ts)

    # Trait-set-as-unit grants, universe-gated via effective set settings.
    for tss in traitset_settings:
        ids.update(tss.sfx_ids or [])

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

    return sorted(ids)


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

# Every owner surface an SFX can be attached to (mirrors SfxOwnerKind).
# Every owner surface an SFX can be attached to (mirrors SfxOwnerKind).
# ``location`` is a distinct surface even though a location *is* an entity: a
# place-owned rule resolves its source to the place, and a `location`-sourced SFX
# attached to a character has to be catchable.
_OWNER_SURFACES = ("table", "gm", "entity", "location", "projection", "trait", "trait_instance", "trait_set")


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
    """Return flattened owner refs of one type for the ownership panel.

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
            "sfx_ids": list(e.sfx_ids or []),
        } for e in repo.list_all_entities() if e.type != EntityType.LOCATION]

    if owner_type == "location":
        from transversal.domain import EntityType
        return [{
            "owner_type": "location",
            "owner_id": e.id,
            "label": e.name or e.id,
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
    a source kind are unrestricted.
    """
    sfx = repo.get_sfx(sfx_id) if hasattr(repo, "get_sfx") else None
    if sfx is not None and sfx.source_kind:
        from transversal.services.target_catalog import source_kind
        sk = source_kind(sfx.source_kind)
        if sk is not None and owner_type != sk.owner_surface:
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
            description="Baseline opposition for GMCs with no authored traits.",
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
