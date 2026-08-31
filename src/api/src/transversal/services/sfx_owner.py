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
    from transversal.domain import Effect, EffectTiming, SFX

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

    def _ensure(sfx_id: str, name: str, description: str, menu_context: str) -> None:
        existing = repo.get_sfx(sfx_id)
        if existing is None:
            repo.create_sfx(SFX(
                id=sfx_id,
                name=name,
                description=description,
                trigger=menu_context,
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
        if existing.trigger != menu_context:
            existing.trigger = menu_context
            changed = True
        if changed:
            repo.update_sfx(existing)

    _ensure("apply-complication", "Apply a complication",
            "When you win a contest, give your opponent a complication at your effect die",
            "contest_win")
    _ensure("take-complication", "Take a complication",
            "When you give in, take a complication at the winner's effect die",
            "contest_give_in")


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
    from transversal.domain import Effect, EffectTiming, SFX

    if repo.get_sfx("hitch-gain-complication") is not None:
        return
    repo.create_sfx(SFX(
        id="hitch-gain-complication",
        name="Gain a complication",
        description="Roller takes a complication stepped up by the bought hitches, then earns 1 razmerit",
        trigger="hitch",
        effects=[
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
        ],
    ))


def ensure_opportunity_sfx(repo) -> None:
    """Create the player opportunity SFX (buy a hitch to step down a complication).

    The player spends 1 razmerit and steps down one of their own complications.
    ``{buying_entity}`` is the player doing the buying; ``{hitch_entity}`` is
    the roller whose 1 was bought.
    """
    from transversal.domain import Condition, ConditionType, Effect, EffectTiming, SFX

    existing = repo.get_sfx("opportunity-step-down-complication")
    if existing is not None:
        # Migration: role moved from the ``players`` bucket to an entity_type gate.
        if not any(c.type == ConditionType.ENTITY_TYPE for c in (existing.conditions or [])):
            existing.conditions = [
                *(existing.conditions or []),
                Condition(type=ConditionType.ENTITY_TYPE, subject="{buying_entity}", target="character"),
            ]
            repo.update_sfx(existing)
        return
    repo.create_sfx(SFX(
        id="opportunity-step-down-complication",
        name="Step down a complication",
        description="Spend 1 razmerit to step down one of your complications",
        trigger="hitch",
        conditions=[
            Condition(type=ConditionType.ENTITY_TYPE, subject="{buying_entity}", target="character"),
        ],
        effects=[
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
        ],
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


def get_available_sfx_ids(entity_id: str, universe: str, repo) -> list[str]:
    """Return the sorted SFX ids available to ``entity_id`` in ``universe``."""
    ids: set[str] = set()
    # Map each trait-granted SFX id to its source trait-setting, so source-aware
    # conditions (SOURCE_RATING) can resolve "the trait this SFX is on".
    sfx_sources: dict[str, Any] = {}

    # Direct entity + active projection ownership.
    entity = repo.get_entity(entity_id)
    if entity is not None:
        ids.update(entity.sfx_ids or [])
        if entity.current_projection:
            proj = repo.get_projection(entity.current_projection)
            if proj is not None:
                ids.update(proj.sfx_ids or [])

    # Table-wide ownership (available to every entity).
    bucket = repo.get_sfx_owner("table")
    if bucket is not None:
        ids.update(bucket.sfx_ids or [])

    # Trait-level grants, universe-gated via effective trait settings. Defaults
    # are already materialized onto the instance's ``sfx_ids`` at grant time
    # (see ``EntityRepository.create_traitsetting``), so this reads the instance
    # list directly rather than re-unioning ``Trait.default_sfx_ids``.
    for ts in repo.get_effective_traitsettings(entity_id, [universe]):
        for sid in (ts.sfx_ids or []):
            ids.add(sid)
            sfx_sources.setdefault(sid, ts)

    # Trait-set-as-unit grants, universe-gated via effective set settings.
    for tss in repo.get_effective_traitsetsettings(entity_id, [universe]):
        ids.update(tss.sfx_ids or [])

    # Filter by context-free conditions so listing matches fireability
    # (e.g. entity_type, in_universe, source_rating). Variable/context-gated
    # conditions stay fire-time.
    if entity is not None:
        from transversal.services.conditions import evaluate_conditions, static_conditions
        for sfx_id in list(ids):
            sfx = repo.get_sfx(sfx_id)
            if sfx is None:
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
        return [{
            "owner_type": "entity",
            "owner_id": e.id,
            "label": e.name or e.id,
            "sfx_ids": list(e.sfx_ids or []),
        } for e in repo.list_all_entities()]

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
    if owner_type == "entity":
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
    if owner_type == "entity":
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
