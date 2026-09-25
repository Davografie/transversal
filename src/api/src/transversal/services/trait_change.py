"""Changing a trait instance's *definition*.

A trait instance stores its registry definition as an Arango edge: ``_from`` is
the owner (entity, relationship, projection or parent instance) and ``_to`` is
the registry trait.  Repointing an instance at a different definition moves
``_to``; the repository derives it from ``trait_id`` on every write
(``trait_settings.update_traitsetting``), so committing the updated instance
rewrites the pointer itself.

The instance keeps everything that is *its own* — its owner, dice, rating type,
polarity, statement, notes, tags, grants and children — and changes what it
**is**.  "Your blade" becomes "a blade of fire".  Its set follows the new
definition, because the set is what says where the instance renders and how a
``HAS_TRAIT_IN_TRAITSET`` condition reads it; an instance that kept the old set
would point at a trait that is not in it.

This is the single operation behind both callers: the sheet's trait editor and
the ``change_trait`` effect action (which is also its own inverse — a timed
change is a timed revert).  Keeping it in one place is what stops the two from
drifting apart, in the same way :mod:`transversal.services.trait_reveal` does for
fog-of-war reveals.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from transversal.domain import CONTAINER_TAG
from transversal.domain import Trait
from transversal.domain import TraitSetting


class TraitChangeError(ValueError):
    """The requested definition change is invalid, or cannot be allowed."""


class TraitChangeRefused(TraitChangeError):
    """The change is well-formed but the rules refuse it.

    Separate from a malformed request: "a container may only become another
    container" is a rule about the *model*, not a mistake in the caller.
    """


@dataclass
class TraitChange:
    """What one call to :func:`repoint_trait_setting` did, or why it did nothing.

    ``changed`` is the only thing callers must branch on.  The reason codes exist
    so the two callers can phrase it for their own audience — the effect handler
    reports into an ``AppliedEffect`` summary, the editor raises a validation
    error — without either of them re-deriving the case.
    """

    #: The instance that was repointed (mutated in place when ``changed``).
    setting: Optional[TraitSetting] = None
    #: The definition the instance pointed at before.
    was_trait_id: str = ""
    #: The definition it points at now (the one asked for, when ``changed``).
    is_trait_id: str = ""
    #: The set before / after, so a caller can say whether it moved.
    was_traitset_id: str = ""
    is_traitset_id: str = ""

    #: False when the call was a no-op.
    changed: bool = False
    #: Why nothing changed: "missing" | "already" | None.
    reason: Optional[str] = None
    #: The definition id the caller asked for, for reporting when it is unknown.
    requested_trait_id: str = ""

    @property
    def traitset_moved(self) -> bool:
        """Whether the instance's set followed the new definition."""
        return self.changed and self.was_traitset_id != self.is_traitset_id


def is_container_trait(trait) -> bool:
    """Whether a registry trait is a container — i.e. may hold other traits.

    A container is an ordinary trait carrying the ``container`` tag.  This is the
    registry half of the frontend's predicate (``isContainer`` in
    ``utils/traitTree.js``, which unions the instance's own tags with these); on
    the definition-changing path the destination is always a registry trait, so
    the registry half is the one that decides.
    """
    return CONTAINER_TAG in list(getattr(trait, "tags", None) or [])


def _is_container_setting(ts: TraitSetting, repo) -> bool:
    """Whether an instance is a container — its own tag, or its definition's.

    Mirrors the frontend's union, so the rule the editor shows and the rule the
    write path enforces agree.
    """
    if CONTAINER_TAG in list(getattr(ts, "tags", None) or []):
        return True
    current = _get_trait(repo, ts.trait_id)
    return bool(current is not None and is_container_trait(current))


def _get_trait(repo, trait_id) -> Optional[Trait]:
    getter = getattr(repo, "get_trait", None)
    if getter is None or not trait_id:
        return None
    return getter(str(trait_id))


def repoint_trait_setting(ts: TraitSetting, trait_id: str, repo) -> TraitChange:
    """Point ``ts`` at the registry definition ``trait_id``.

    Mutates ``ts`` in memory only when the change is allowed.  Persisting it (and
    recording it for an undo) is the caller's job, because the two callers record
    it differently.

    Two outcomes are *not* errors, because a revert must be allowed to land on the
    value it is restoring: an unknown definition comes back as
    ``reason="missing"``, and an instance already pointing at the wanted
    definition comes back as ``reason="already"``.

    Raises :class:`TraitChangeError` for a collision, and
    :class:`TraitChangeRefused` when the container rule is broken.
    """
    wanted = _get_trait(repo, trait_id)
    if wanted is None:
        return TraitChange(reason="missing", requested_trait_id=str(trait_id or ""))

    was = str(ts.trait_id)
    if str(wanted.id) == was:
        return TraitChange(setting=ts, was_trait_id=was, is_trait_id=was, reason="already",
                           requested_trait_id=str(wanted.id))

    # The container rule, stated once and enforced for every caller.  Containment
    # is a property of the *definition* (its tag), so an instance that is a
    # container must stay one: repointing it at an ordinary trait would strand its
    # children under a parent that no longer holds anything, and repointing an
    # ordinary trait at a container would give it contents it was never given.
    was_container = _is_container_setting(ts, repo)
    is_container = is_container_trait(wanted)
    if was_container != is_container:
        raise TraitChangeRefused(
            "A container may only change into another container" if was_container
            else "Only a container may change into a container"
        )

    _refuse_collision(ts, wanted, repo)

    # Both sets are read off the *traits* — the old definition and the wanted one.
    # Nothing is copied onto the setting, because it records no set of its own: the
    # set follows the definition by construction ([[B200]]).
    was_traitset = str(getattr(_get_trait(repo, was), "traitset_id", "") or "")
    ts.trait_id = str(wanted.id)
    return TraitChange(
        setting=ts, was_trait_id=was, is_trait_id=str(wanted.id),
        was_traitset_id=was_traitset,
        is_traitset_id=str(getattr(wanted, "traitset_id", "") or ""),
        changed=True, requested_trait_id=str(wanted.id),
    )


def _refuse_collision(ts: TraitSetting, wanted: Trait, repo) -> None:
    """Refuse a repoint that would leave the owner holding the definition twice.

    ``add_trait_setting`` already refuses this on create; without the same check
    here, repointing onto a definition the owner already holds would silently
    produce a twin — two rows claiming the same trait, which the set's one-per-
    trait rule exists to prevent.
    """
    finder = getattr(repo, "find_traitsetting_collision", None)
    if finder is None:
        return
    allow_duplicates = _allow_duplicates(wanted.traitset_id, repo)
    collision = finder(str(ts.entity_id), str(wanted.id),
                       statement=ts.statement or "", allow_duplicates=allow_duplicates)
    if collision is not None and str(collision.id) != str(ts.id):
        raise TraitChangeError(
            f"'{wanted.name or wanted.id}' is already held"
            + (f" with statement '{ts.statement}'" if allow_duplicates and ts.statement else "")
        )


def _allow_duplicates(traitset_id: str, repo) -> bool:
    getter = getattr(repo, "get_traitset_by_id", None)
    traitset = getter(str(traitset_id)) if getter is not None and traitset_id else None
    return bool(getattr(traitset, "allow_duplicates", False))
