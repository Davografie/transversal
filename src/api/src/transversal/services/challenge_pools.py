"""Challenge-rating pool operations — spend dice and check completion.

A challenge trait is a pool of dice that drains (negative → doom) or fills
(positive → progress). Unlike a resource pool, there is no ``spent_dice``
recovery ledger: spending removes a die from ``dice`` outright, and the pool
grows back through ``add_die``/``step_up`` (or hitches for doom pools).

Positive progress pools carry a ``capacity`` — the target the ``dice`` ledger
fills toward. When ``dice`` reaches ``capacity`` the project is complete.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Optional

from transversal.domain import DieType, Polarity, RatingType, TraitSetting
from transversal.services.change_log import change_log
from transversal.services.entity_manager import EntityManager


class ChallengePoolError(Exception):
    pass


@dataclass
class ChallengeSpend:
    """Result of spending one die from a challenge pool."""

    ts: TraitSetting
    die: DieType
    resource: bool  # True → the caller should add the die to a pool as a resource die


def spend_challenge_die(
    ts: TraitSetting,
    die: DieType,
    em: EntityManager,
    destination: str = "opposition",
    session_id: str = "",
) -> ChallengeSpend:
    """Remove one *die* from a challenge pool's ``dice`` and route it.

    ``destination`` is either ``"opposition"`` (a doom die the GM spends to
    oppose — returned as a plain die) or ``"pool"`` (a progress die spent for
    partial use — returned flagged ``resource=True`` so it joins the caller's
    pool as a resource die).

    Raises ``ChallengePoolError`` if the trait is not challenge-rated or the
    die is not available.
    """
    if ts.rating_type != RatingType.CHALLENGE:
        raise ChallengePoolError(f"TraitSetting '{ts.id}' is not challenge-rated")
    try:
        idx = ts.dice.index(die)
    except ValueError:
        raise ChallengePoolError(f"No {die.value} die available in challenge pool '{ts.id}'")

    ts.dice.pop(idx)
    result = em.update_traitsetting(ts)

    change_log.record(
        ts.entity_id,
        f"traitsetting.{ts.id}.challenge.spend",
        f"{die.value}",
        "",
        session_id,
    )
    return ChallengeSpend(ts=result, die=die, resource=destination == "pool")


def _multiset(dice: Optional[list[DieType]]) -> Counter:
    return Counter(dice or [])


def check_challenge_completion(ts: TraitSetting) -> bool:
    """True when a positive challenge pool has filled to its ``capacity``."""
    if ts.rating_type != RatingType.CHALLENGE:
        return False
    if ts.polarity != Polarity.POSITIVE:
        return False
    if not ts.capacity:
        return False
    return _multiset(ts.dice) == _multiset(ts.capacity)


def challenge_capacity(ts: TraitSetting) -> list[DieType]:
    """The pool's target/ceiling, or an empty list when unset."""
    return list(ts.capacity or [])


def fire_challenge_completed(ts: TraitSetting, universe: str = "") -> bool:
    """Fire the completion event when a positive challenge reaches capacity.

    Returns ``True`` if the pool completed (and the event fired). The
    ``challenge_completed`` trigger registration is owned by the effects
    session; this is the single runtime fire site.
    """
    if not check_challenge_completion(ts):
        return False
    from transversal.services.state_events import fire_state_sfx

    fire_state_sfx(ts.entity_id, universe, "challenge_completed", {
        "entity_id": ts.entity_id,
        "trait_setting_id": ts.id,
        "trait_id": ts.trait_id,
        "capacity": [d.value for d in (ts.capacity or [])],
    })
    return True
