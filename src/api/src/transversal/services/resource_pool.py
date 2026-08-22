"""Resource dice operations — spend / recover dice from a TraitSetting.

No separate ResourcePool model: ``dice`` is the currently-available pool and
``spent_dice`` is the spent-but-recoverable ledger.  Spending moves one die
``dice → spent_dice``; recovery moves it back.  Because recovery only moves
dice that are actually in ``spent_dice``, it can never exceed what was spent
and the pool's capacity (``dice + spent_dice``) is always preserved.
"""

from __future__ import annotations

from transversal.domain import DieType, TraitSetting
from transversal.services.change_log import change_log
from transversal.services.entity_manager import EntityManager


class ResourcePoolError(Exception):
    pass


def spend_die(ts: TraitSetting, die: DieType, em: EntityManager, session_id: str = "") -> TraitSetting:
    """Move one die of *die* type from ``ts.dice`` to ``ts.spent_dice`` and persist.

    Returns the updated TraitSetting.
    """
    try:
        idx = ts.dice.index(die)
    except ValueError:
        raise ResourcePoolError(
            f"No {die.value} die available in trait '{ts.id}'"
        )

    old_rating = _rating(ts)
    ts.dice.pop(idx)
    ts.spent_dice.append(die)
    result = em.update_traitsetting(ts)

    change_log.record(
        ts.entity_id,
        f"traitsetting.{ts.id}.dice.spend",
        f"{old_rating}:{die.value}",
        _rating(ts),
        session_id,
    )
    return result


def recover_die(ts: TraitSetting, die: DieType, em: EntityManager, session_id: str = "") -> TraitSetting:
    """Move one die of *die* type from ``ts.spent_dice`` back to ``ts.dice`` and persist.

    Raises ``ResourcePoolError`` if no such die is in the spent ledger, so
    recovery can never push the pool past its capacity.

    Returns the updated TraitSetting.
    """
    try:
        idx = ts.spent_dice.index(die)
    except ValueError:
        raise ResourcePoolError(
            f"No spent {die.value} die to recover in trait '{ts.id}'"
        )

    old_rating = _rating(ts)
    ts.spent_dice.pop(idx)
    ts.dice.append(die)
    result = em.update_traitsetting(ts)

    change_log.record(
        ts.entity_id,
        f"traitsetting.{ts.id}.dice.recover",
        old_rating,
        _rating(ts),
        session_id,
    )
    return result


def step_up(ts: TraitSetting, die: DieType, em: EntityManager, session_id: str = "") -> TraitSetting:
    """Permanently upgrade one die in the array (advancement)."""
    try:
        idx = ts.dice.index(die)
    except ValueError:
        raise ResourcePoolError(
            f"No {die.value} die available in trait '{ts.id}' to step up"
        )

    old_rating = _rating(ts)
    stepped = die.step_up()
    ts.dice[idx] = stepped
    result = em.update_traitsetting(ts)

    change_log.record(
        ts.entity_id,
        f"traitsetting.{ts.id}.dice.step_up",
        f"{old_rating}:{die.value}→{stepped.value}",
        _rating(ts),
        session_id,
    )
    return result


def _rating(ts: TraitSetting) -> str:
    from transversal.domain import dice_list_to_rating
    return dice_list_to_rating(ts.dice)
