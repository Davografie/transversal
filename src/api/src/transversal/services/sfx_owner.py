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

from transversal.domain import SfxOwner


def ensure_sfx_owners(repo) -> None:
    """Create/refresh the default SFX owner buckets. Idempotent.

    ``table`` = globally available SFX (everyone) — seeded with the give-in
    reward and the contest-complication menu SFX; ``gm`` = GM-context SFX (not
    entity-derived; P3.3 buy-hitch); ``players`` = player-facing SFX bucket
    (reserved, currently empty).
    """
    defaults = {
        "table": [
            "sfx-give-in-get-razmerit",
            "sfx-give-in-targeting-ban",
            "apply-complication",
            "take-complication",
            "prevent-taken-out",
        ],
        "gm": [],
        "players": [],
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
    """Create the give-in targeting-ban SFX if missing. Idempotent."""
    from transversal.domain import Effect, EffectTiming, SFX

    if repo.get_sfx("sfx-give-in-targeting-ban") is not None:
        return
    repo.create_sfx(SFX(
        id="sfx-give-in-targeting-ban",
        name="Give In — Keep Your Distance",
        description="When you give in, you can't target that opponent for the rest of the scene",
        trigger="on_give_in",
        effects=[
            Effect(
                timing=EffectTiming.IMMEDIATE,
                type="entity",
                action="targeting_ban",
                target="",
                result="1",
            ),
        ],
    ))


def ensure_contest_complication_sfx(repo) -> None:
    """Create the winner (apply) + conceder (take) complication SFX. Idempotent.

    Both carry the same ``gain_complication`` effect; they differ only in label
    so the frontend can surface the right one at each end of a contest. They
    are ``on_consequence`` SFX owned by ``table`` (available to players + GM).
    """
    from transversal.domain import Effect, EffectTiming, SFX

    def _complication_effect() -> list:
        return [
            Effect(
                timing=EffectTiming.IMMEDIATE,
                type="modify_trait",
                action="gain_complication",
                target="{choose_trait}",
                target_scope="traitset:ts-complications",
                result="{effect_die}",
            ),
        ]

    if repo.get_sfx("apply-complication") is None:
        repo.create_sfx(SFX(
            id="apply-complication",
            name="Apply a complication",
            description="When you win a contest, give your opponent a complication at your effect die",
            trigger="on_consequence",
            effects=_complication_effect(),
        ))
    if repo.get_sfx("take-complication") is None:
        repo.create_sfx(SFX(
            id="take-complication",
            name="Take a complication",
            description="When you give in, take a complication at the winner's effect die",
            trigger="on_consequence",
            effects=_complication_effect(),
        ))


def ensure_prevent_taken_out_sfx(repo) -> None:
    """Create the prevent-taken-out SFX (spend 1 razmerit). Idempotent."""
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

    # Direct entity + active projection ownership.
    entity = repo.get_entity(entity_id)
    if entity is not None:
        ids.update(entity.sfx_ids or [])
        if entity.current_projection:
            proj = repo.get_projection(entity.current_projection)
            if proj is not None:
                ids.update(proj.sfx_ids or [])

    # Table-wide ownership (everyone).
    table = repo.get_sfx_owner("table")
    if table is not None:
        ids.update(table.sfx_ids or [])

    # Trait-level grants, universe-gated via effective trait settings.
    for ts in repo.get_effective_traitsettings(entity_id, [universe]):
        ids.update(ts.sfx_ids or [])
        trait = repo.get_trait(ts.trait_id)
        if trait is not None:
            ids.update(trait.default_sfx_ids or [])

    # Trait-set-as-unit grants, universe-gated via effective set settings.
    for tss in repo.get_effective_traitsetsettings(entity_id, [universe]):
        ids.update(tss.sfx_ids or [])

    return sorted(ids)
