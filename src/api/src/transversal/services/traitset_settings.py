"""Trait-set settings — the (entity, trait set) edge, addressed by a derived id.

A trait-set setting is an **override**, not a relationship. ``limit=None`` means
*use the set's registry default* and ``sfx_ids=[]`` means *this set carries no
rules of its own*, so the pair is meaningful whether or not a document exists and
the document only records that something about the pair was changed. Measured
live when this module landed: **92 rows, 75 of them carrying no information at
all** (their limit matched the registry default), and **0** carrying an SFX.

That is why addressing is derived rather than looked up. Three surfaces need to
name a setting that has never been written:

* the **targeting resolver**, whose paths may land on one
  (``trait instance → its set's setting``, ``entity → its set settings``);
* the **effects applier**, where a set-limit override or a set-level SFX attach
  is routinely the *first* thing to touch the pair;
* **validation**, which must not report an addressable target as missing.

The id is a pure function of the pair, and both writers that have ever minted one
agree on its shape — ``migrate_traitsetsettings`` and
``effects_applier._apply_set_traitset_limit`` each build ``{entity_id}:{traitset_id}``.

**What this deliberately does not decide:** whether a pair is *allowed* (the
``TraitSet.entity_types`` / ``universes`` predicate). Resolution only requires
that both ends exist, because enforcing the pairing predicate belongs where a set
is offered to an entity, not where one is addressed — and every migrated row
would have to be re-checked against a rule that never gated them.
"""

from __future__ import annotations

from transversal.domain import TraitSetSetting
from typing import Optional

#: Sentinel for "leave this field as it is" in :func:`upsert`. ``None`` is already
#: spoken for on ``limit`` — it *means* "clear the override back to the default".
UNSET = object()

_SEP = ":"


def traitsetsetting_id(entity_id: str, traitset_id: str) -> str:
    """The pair's **derived** id — the one key shape both writers use."""
    return f"{entity_id}{_SEP}{traitset_id}"


def parse_traitsetsetting_id(value: str) -> Optional[tuple[str, str]]:
    """Split a derived id into ``(entity_id, traitset_id)``, or ``None``.

    An entity id and a trait-set id each contain no colon (``gmc-138398177``,
    ``ts-25908583``), so the separator is the only colon in the string and the
    split is exact. Note that the *shape* alone cannot tell a set setting from a
    trait instance's id — ``{entity}:{trait}`` looks the same — so a caller that
    must be sure resolves the second half as a trait set.
    """
    if not value or value.count(_SEP) != 1:
        return None
    entity_id, traitset_id = value.split(_SEP)
    if not entity_id or not traitset_id:
        return None
    return entity_id, traitset_id


def resolve(repo, entity_id: str, traitset_id: str) -> TraitSetSetting:
    """The pair's setting: the stored one, else the default it would have.

    The default is not an invention — it is what every reader already computes
    for an absent row (``limit=None`` falls back to the registry default in
    ``TraitsetField.traitset_limit``, and an empty ``sfx_ids`` contributes no
    rules), so returning it as an object changes no answer and makes the pair
    addressable.
    """
    stored = repo.get_traitsetsetting(traitsetsetting_id(entity_id, traitset_id))
    if stored is not None:
        return stored
    return TraitSetSetting(
        id=traitsetsetting_id(entity_id, traitset_id),
        entity_id=entity_id,
        traitset_id=traitset_id,
        from_type="entity",
        sfx_ids=[],
        limit=None,
    )


def resolve_stored_or_default(repo, setting_id: str) -> Optional[TraitSetSetting]:
    """A setting by id — defaulted when the pair is real but nothing is stored.

    Returns ``None`` when the id is not a pair, or when either end does not exist.
    A target invented for a typo is worse than an unresolved one: validation and
    the picker would both report a name for something the world does not have.
    """
    stored = repo.get_traitsetsetting(setting_id)
    if stored is not None:
        return stored
    pair = parse_traitsetsetting_id(setting_id)
    if pair is None:
        return None
    entity_id, traitset_id = pair
    if repo.get_entity(entity_id) is None:
        return None
    if repo.get_traitset_by_id(traitset_id) is None:
        return None
    return resolve(repo, entity_id, traitset_id)


def upsert(repo, entity_id: str, traitset_id: str, *,
           sfx_ids: Optional[list[str]] = None, limit=UNSET) -> TraitSetSetting:
    """Write the pair's setting, **creating the document on first write**.

    Until this existed nothing could create a row except one effect action, which
    is why ``set_sfx_for_owner`` refused every set-level attach for an entity that
    had none — and why no live row carries an SFX. Omitted arguments are left
    alone; ``limit=None`` clears the override rather than ignoring it.
    """
    setting = resolve(repo, entity_id, traitset_id)
    if sfx_ids is not None:
        setting.sfx_ids = [str(s) for s in sfx_ids]
    if limit is not UNSET:
        setting.limit = limit
    if repo.get_traitsetsetting(setting.id) is None:
        repo.create_traitsetsetting(setting)
    else:
        repo.update_traitsetsetting(setting)
    return setting
