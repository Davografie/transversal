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
    reward; ``gm`` = GM-context SFX (not entity-derived; P3.3 buy-hitch);
    ``players`` = player-facing SFX bucket (reserved, currently empty).
    """
    defaults = {"table": ["sfx-give-in-get-razmerit"], "gm": [], "players": []}
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
