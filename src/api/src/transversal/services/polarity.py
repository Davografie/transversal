"""Trait polarity — baked defaults plus propagation on higher-level changes.

A ``TraitSetting`` stores a concrete, non-null ``polarity`` (see the domain
model).  When a trait or trait set changes its polarity default, that default is
propagated down to the settings that were inheriting it.  Because polarity is
baked (not resolved at read time), propagation uses the simple rule: flip every
setting whose current value equals the old default.  This may also flip an
explicit override that happened to equal the old default — an accepted trade-off
for keeping reads join-free.
"""

from __future__ import annotations

from typing import Optional

from transversal.domain import Polarity, Trait, TraitSet, TraitSetting


def default_polarity(
    trait: Optional[Trait], traitset: Optional[TraitSet]
) -> Polarity:
    """Resolve the baked default: trait → traitset → global positive."""
    trait_polarity = getattr(trait, "polarity", None)
    if trait_polarity is not None:
        return trait_polarity
    traitset_polarity = getattr(traitset, "polarity", None)
    if traitset_polarity is not None:
        return traitset_polarity
    return Polarity.POSITIVE


def _flip(repo, settings: list[TraitSetting], old: Polarity, new: Polarity) -> int:
    """Flip every setting currently equal to ``old`` to ``new``; persist changes."""
    changed = 0
    for ts in settings:
        if ts.polarity == old:
            ts.polarity = new
            repo.update_traitsetting(ts)
            changed += 1
    return changed


def propagate_trait_polarity(
    repo,
    trait_id: str,
    old_trait_polarity: Optional[Polarity],
    new_trait_polarity: Optional[Polarity],
    traitset_polarity: Optional[Polarity],
) -> int:
    """Propagate a trait-level polarity change to that trait's settings."""
    base = traitset_polarity if traitset_polarity is not None else Polarity.POSITIVE
    old_default = old_trait_polarity if old_trait_polarity is not None else base
    new_default = new_trait_polarity if new_trait_polarity is not None else base
    if old_default == new_default:
        return 0
    return _flip(repo, repo.get_traitsettings_by_trait(trait_id), old_default, new_default)


def propagate_traitset_polarity(
    repo,
    traitset_id: str,
    old_traitset_polarity: Optional[Polarity],
    new_traitset_polarity: Optional[Polarity],
) -> int:
    """Propagate a trait-set polarity change to its traits' settings.

    Traits that carry their own polarity override the set and are left alone.
    """
    old_default = (
        old_traitset_polarity if old_traitset_polarity is not None else Polarity.POSITIVE
    )
    new_default = (
        new_traitset_polarity if new_traitset_polarity is not None else Polarity.POSITIVE
    )
    if old_default == new_default:
        return 0

    changed = 0
    for trait in repo.get_traits_by_traitset(traitset_id):
        if trait.polarity is not None:
            continue  # trait overrides the set default
        changed += _flip(
            repo, repo.get_traitsettings_by_trait(trait.id), old_default, new_default
        )
    return changed
