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
    """Create the default SFX owner buckets if missing. Idempotent.

    ``table`` = globally available SFX (everyone); ``gm`` = GM-context SFX
    (not entity-derived; P3.3 buy-hitch lands here).
    """
    defaults = {"table": [], "gm": []}
    for owner_id, sfx_ids in defaults.items():
        if repo.get_sfx_owner(owner_id) is None:
            repo.create_sfx_owner(SfxOwner(id=owner_id, sfx_ids=list(sfx_ids)))


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
