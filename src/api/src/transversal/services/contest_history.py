"""Blue Book history for tests and contests ([[B177]]).

Both stores this reads are ephemeral by design: ``ContestTracker`` is
beat-scoped and lost on restart, the scene store's pools are cleared at
resolution, and a committed result carries only its total/effect die/tier —
never the dice. So a resolved roll leaves nothing behind to draw, and a push
*overwrites* the round before it.

This module is the recording half of the answer: each round is frozen onto the
``ContestState`` as it completes, and at resolution one ``contest`` record is
written to **every participant's** book (a ``test`` record to the roller's),
from that side's own perspective. The renderer ([[blue-book]]'s half) draws it
as two columns — own roll left, who/what they rolled against right — with the
rounds stacked vertically.

The ``data`` payload is the contract between the halves. It is written out in
[[B177]]; change it there first.
"""

from __future__ import annotations

import logging
from typing import Optional

from transversal.domain import ContestOutcome, ContestWinner, HistoricalRecordType

logger = logging.getLogger("transversal.contest_history")

# Injectable for tests (the suite's house pattern: the tracker and scene store
# are swapped the same way). ``None`` means "resolve the real repository", and
# a getter that returns ``None`` means "no repository — records are skipped".
_repo_getter = None


def _resolve_repo(repo):
    if repo is not None:
        return repo
    try:
        if _repo_getter is not None:
            return _repo_getter()
        from transversal.main import _get_repo

        return _get_repo()
    except Exception:  # noqa: BLE001 - recording must never break a roll
        logger.exception("[contest_history] no repository available; record skipped")
        return None


def _name(repo, entity_id: str) -> str:
    if not entity_id or repo is None:
        return ""
    try:
        entity = repo.get_entity(entity_id)
    except Exception:  # noqa: BLE001
        return ""
    return getattr(entity, "name", "") or ""


def _location_name(repo, location_id: str) -> str:
    return _name(repo, location_id)


def _die_row(d: dict) -> dict:
    """One pool die as the renderer needs it — enough to draw, nothing more.

    ``role`` is set server-side by ``POST …/select`` (``"total"``/``"effect"``),
    so the kept dice and the effect die are exact rather than derived from the
    total, which bonuses and step-ups would make unreliable.
    """
    return {
        "die": d.get("die"),
        "label": d.get("label") or d.get("source_id") or "",
        "result": d.get("result"),
        "role": d.get("role"),
        "hitch": bool(d.get("hitch")),
        "resource": bool(d.get("resource")),
    }


def _empty_side() -> dict:
    return {"total": 0, "effect_die": None, "tier": None, "pipeline": "pool", "dice": []}


def _side_fields(row: Optional[dict]) -> dict:
    """The side half of a stored round row (drops the round-level keys)."""
    if not row:
        return _empty_side()
    return {
        "total": row.get("total", 0),
        "effect_die": row.get("effect_die"),
        "tier": row.get("tier"),
        "pipeline": row.get("pipeline", "pool"),
        "dice": list(row.get("dice") or []),
    }


def snapshot_round(
    location_id: str,
    tracker,
    scene_store,
    entity_ids,
    *,
    decision: str = "resolved",
    pending: Optional[str] = None,
) -> None:
    """Freeze the round that just completed onto each side's state.

    Called from the commit endpoints *after* ``compare_if_ready`` — not at
    store time — because the set endpoint fires outcome effects between storing
    and comparing, and those may step the effect die the contest resolves on.

    A side is snapshotted only when it **committed afresh**. After a push only
    the pusher re-rolls; the opponent's earlier result stays on the table as the
    difficulty to beat, so re-snapshotting it would show their roll twice (once
    as the round it was rolled in, once as a round they never rolled in). The
    payload carries it forward as ``standing`` instead. The round guard makes a
    repeated call idempotent, which is what lets the give-in path call this for
    a side that committed before any compare ran.
    """
    for entity_id in entity_ids:
        if not entity_id:
            continue
        state = tracker.get(location_id, entity_id)
        if state is None or state.committed is None:
            continue
        if state.last_snapshotted is state.committed:
            continue
        if any(r.get("round") == state.round_no for r in state.rounds):
            continue
        committed = state.committed
        state.rounds.append(
            {
                "round": state.round_no,
                "total": committed.total,
                "effect_die": committed.effect_die.value if committed.effect_die else None,
                "tier": committed.tier.value if committed.tier else None,
                "pipeline": committed.pipeline,
                "dice": [_die_row(d) for d in scene_store.get_pool(location_id, entity_id)],
                "decision": decision,
                "pending": pending,
            }
        )
        state.last_snapshotted = committed


def _row_at(rows: list[dict], number: int) -> Optional[dict]:
    return next((r for r in rows if r.get("round") == number), None)


def _latest_row(rows: list[dict], number: int) -> Optional[dict]:
    """The side's most recent roll at or before ``number``."""
    candidates = [r for r in rows if r.get("round", 0) <= number]
    if not candidates:
        return None
    return max(candidates, key=lambda r: r.get("round", 0))


def _merged_rounds(own_state, opp_state, own_id: str, opp_id: str) -> list[dict]:
    """Interleave both sides' snapshots into the payload's round list.

    A side that did not roll in this round carries its previous roll forward,
    flagged ``standing`` so the renderer can say "still the number to beat"
    rather than implying a fresh roll.
    """
    numbers = sorted(
        {r.get("round", 0) for r in own_state.rounds} | {r.get("round", 0) for r in opp_state.rounds}
    )
    rounds = []
    for number in numbers:
        own_here = _row_at(own_state.rounds, number)
        opp_here = _row_at(opp_state.rounds, number)
        own_row = own_here or _latest_row(own_state.rounds, number)
        opp_row = opp_here or _latest_row(opp_state.rounds, number)
        source = own_here or opp_here or own_row or opp_row or {}
        pending = source.get("pending")
        rounds.append(
            {
                "round": number,
                "own": {**_side_fields(own_row), "standing": own_here is None},
                "opposition": {**_side_fields(opp_row), "standing": opp_here is None},
                "decision": source.get("decision"),
                "pending": (
                    "own" if pending == own_id else "opposition" if pending == opp_id else None
                ),
            }
        )
    return rounds


def _write(repo, entity_id: str, record_type: HistoricalRecordType, data: dict, universe: str) -> None:
    if repo is None or not entity_id:
        return
    repo.add_historical_record(entity_id, record_type, data, universe=universe or "")


def pending_contest_effects(entity_id: str, universe: str = "", *, repo=None) -> dict:
    """The effects that would fire on give-in / prevent-take-out, by name ([[B14]]).

    Those two controls used to be bare buttons — "Prevent take out (1 razmerit)" —
    with the cost and the consequence living only in authored SFX, invisible until
    they fired. Which rules apply is a question for the SFX owner, not the contest:
    the same trigger filter the engine uses (``triggers=``) answers it, so an
    authored rule appears here without the contest having to know it exists.
    """
    empty = {"give_in": [], "prevent_taken_out": []}
    repo = _resolve_repo(repo)
    if repo is None or not entity_id:
        return empty
    from transversal.services.sfx_owner import get_available_sfx_ids

    if not universe:
        try:
            entity = repo.get_entity(entity_id)
            universe = getattr(entity, "current_universe", "") or ""
        except Exception:  # noqa: BLE001
            universe = ""

    out: dict[str, list[dict]] = {}
    for key, trigger in (("give_in", "on_give_in"), ("prevent_taken_out", "on_prevent_taken_out")):
        rows: list[dict] = []
        try:
            ids = get_available_sfx_ids(entity_id, universe, repo, triggers=frozenset({trigger}))
        except Exception:  # noqa: BLE001 - a forecast must never break the panel
            logger.exception("[contest_history] pending-effects lookup failed for %s", trigger)
            ids = []
        for sfx_id in ids:
            sfx = None
            try:
                sfx = repo.get_sfx(sfx_id)
            except Exception:  # noqa: BLE001
                sfx = None
            rows.append({
                "id": sfx_id,
                "name": getattr(sfx, "name", "") or sfx_id,
                "description": getattr(sfx, "description", "") or "",
            })
        out[key] = rows
    return out


def record_contest_outcome(
    location_id: str,
    challenger,
    defendant,
    outcome: ContestOutcome,
    *,
    repo=None,
) -> None:
    """Write one ``contest`` record to each participant's book.

    Each side gets its **own** perspective: own roll left, the other side right,
    and the result as that side lived it. A participant whose side never
    committed (the pre-compare give-in) still gets an entry — with an empty own
    half — because the contest happened to them either way.
    """
    repo = _resolve_repo(repo)
    if repo is None:
        return
    try:
        universe = challenger.universe or defendant.universe or ""
        loc_name = _location_name(repo, location_id)
        # A contest resolves once. A repeated `/set` on a settled contest would
        # otherwise append the same entry again.
        if challenger.settled and defendant.settled:
            return
        winner_id = (
            challenger.entity_id if outcome.winner == ContestWinner.PLAYER else defendant.entity_id
        )
        gave_in_side = (
            None
            if outcome.gave_in is None
            else (challenger.entity_id if outcome.gave_in == ContestWinner.PLAYER else defendant.entity_id)
        )
        for own_state, opp_state in ((challenger, defendant), (defendant, challenger)):
            own_id, opp_id = own_state.entity_id, opp_state.entity_id
            if own_id == gave_in_side:
                result = "gave_in"
            elif own_id == winner_id:
                result = "win"
            else:
                result = "taken_out" if outcome.taken_out else "loss"
            _write(
                repo,
                own_id,
                HistoricalRecordType.CONTEST,
                {
                    "kind": "contest",
                    "own_entity_id": own_id,
                    "own_name": _name(repo, own_id),
                    "opposition_entity_id": opp_id,
                    "opposition_name": _name(repo, opp_id),
                    "location_id": location_id,
                    "location_name": loc_name,
                    "universe": universe,
                    "high_stakes": bool(outcome.high_stakes),
                    "result": result,
                    "effect_die": outcome.effect_die.value if outcome.effect_die else None,
                    "rounds": _merged_rounds(own_state, opp_state, own_id, opp_id),
                },
                universe,
            )
        challenger.settled = True
        defendant.settled = True
    except Exception:  # noqa: BLE001 - a book entry must never break a roll
        logger.exception("[contest_history] contest record failed loc=%s", location_id)


def record_test(
    location_id: str,
    entity_id: str,
    dice: list[dict],
    *,
    total: int,
    effect_die: Optional[str],
    difficulty: Optional[int],
    universe: str = "",
    high_stakes: bool = False,
    repo=None,
) -> None:
    """Write one ``test`` record to the roller's book.

    The opposition half is the difficulty — a place, not a person — so
    ``opposition_entity_id`` stays empty and ``difficulty`` carries the number
    to beat. The record type is what makes tests filterable: ``BlueBook.vue``
    already sets a record entry's threads to ``[recordType]``, so ``#test``
    appears as a thread chip with no new mechanism.
    """
    repo = _resolve_repo(repo)
    if repo is None or not entity_id:
        return
    try:
        if difficulty is None:
            result = "unopposed"
        else:
            result = "win" if total > difficulty else "loss"
        _write(
            repo,
            entity_id,
            HistoricalRecordType.TEST,
            {
                "kind": "test",
                "own_entity_id": entity_id,
                "own_name": _name(repo, entity_id),
                "opposition_entity_id": "",
                "opposition_name": _location_name(repo, location_id),
                "location_id": location_id,
                "location_name": _location_name(repo, location_id),
                "universe": universe,
                "high_stakes": bool(high_stakes),
                "result": result,
                "effect_die": effect_die,
                "rounds": [
                    {
                        "round": 1,
                        "own": {
                            "total": total,
                            "effect_die": effect_die,
                            "tier": None,
                            "pipeline": "pool",
                            "dice": [_die_row(d) for d in dice],
                        },
                        "opposition": {
                            **_empty_side(),
                            "total": difficulty or 0,
                            "difficulty": difficulty,
                        },
                        "decision": "resolved",
                        "pending": None,
                    }
                ],
            },
            universe,
        )
    except Exception:  # noqa: BLE001 - a book entry must never break a roll
        logger.exception("[contest_history] test record failed loc=%s entity=%s", location_id, entity_id)
