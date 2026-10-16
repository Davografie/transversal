"""Move pre-scoping sessions into their campaign — and prune the empty leftovers (B305).

Sessions written before the campaign scoping have keys that name no campaign
(``session:<id>``, tracked in one ``sessions:active`` set). The store reads them for the
**default campaign only**, as one release of compatibility, which is what keeps the live
game working across the change ([[Campaign-Scoped Transient State Plan]] §6). This
script finishes the move so that fallback can be deleted.

Two things it does, and one it refuses:

- **Renames** each record to ``session:<campaign>:<id>`` and moves it between the active
  sets, attributing it to the **default campaign** — the playroom, the only surface that
  existed before host routing. Nothing else is guessed.
- **Prunes empty leftovers** with ``--prune-empty``: a session with no entities that is
  not mid-session is one nobody is at, and those are what made the session list 463 long
  (the client picks a table from that list, so the leftovers were being chosen from).
- It **refuses to touch a session with entities or ``in_session=true``** beyond the
  rename. A table that is mid-game is not this script's business.

Dry run by default; ``--apply`` writes.
"""

from __future__ import annotations

import argparse
import json
import logging

from transversal.db.redis import get_redis_client
from transversal.services.campaign_scope import campaign_for_database, default_database

logger = logging.getLogger("transversal.migrate_sessions")

_KEY = "session:{}"
_SCOPED_KEY = "session:{}:{}"
_LEGACY_ACTIVE = "sessions:active"
_SCOPED_ACTIVE = "sessions:active:{}"


def _legacy_ids(redis) -> list[str]:
    """Session ids whose key names no campaign. A scoped key has three segments."""
    return sorted(
        key.split(":", 1)[1]
        for key in redis.scan_iter("session:*")
        if len(key.split(":")) == 2
    )


def migrate(redis, *, campaign: str, prune_empty: bool, apply: bool) -> dict:
    """Returns a report: what was renamed, pruned, and deliberately left alone."""
    report = {"campaign": campaign, "renamed": 0, "pruned": 0, "held": 0, "broken": 0}

    for session_id in _legacy_ids(redis):
        raw = redis.get(_KEY.format(session_id))
        if not raw:
            continue
        try:
            record = json.loads(raw)
        except Exception:
            report["broken"] += 1
            continue

        empty = not record.get("entity_ids")
        if empty and not record.get("in_session"):
            if prune_empty:
                report["pruned"] += 1
                logger.info("prune %s (no entities)", session_id)
                if apply:
                    redis.delete(_KEY.format(session_id))
                    redis.srem(_LEGACY_ACTIVE, session_id)
                continue
            report["held"] += 1

        # Renamed either way: a session with entities, one mid-session, or an empty one
        # we are deliberately keeping.
        record["campaign"] = campaign
        report["renamed"] += 1
        if apply:
            pipe = redis.pipeline()
            pipe.set(_SCOPED_KEY.format(campaign, session_id), json.dumps(record))
            pipe.sadd(_SCOPED_ACTIVE.format(campaign), session_id)
            pipe.delete(_KEY.format(session_id))
            pipe.srem(_LEGACY_ACTIVE, session_id)
            pipe.execute()

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m transversal.migrate_session_campaigns")
    parser.add_argument("--apply", action="store_true", help="write (default: dry run)")
    parser.add_argument(
        "--prune-empty",
        action="store_true",
        help="also drop sessions with no entities that are not mid-session",
    )
    args = parser.parse_args(argv)

    redis = get_redis_client()
    if redis is None:
        print("no Redis: nothing to migrate (the in-memory store empties on restart)")
        return 1

    database = default_database()
    campaign = campaign_for_database(database)
    report = migrate(
        redis, campaign=campaign, prune_empty=args.prune_empty, apply=args.apply
    )

    verb = "moved" if args.apply else "would move"
    print(f"default database {database} → campaign {campaign}")
    print(f"  {verb}: {report['renamed']}")
    print(f"  {'pruned' if args.apply else 'would prune'}: {report['pruned']}")
    print(f"  held (has entities or in session): {report['held']}")
    print(f"  unreadable records: {report['broken']}")
    print(f"  legacy keys left: {len(_legacy_ids(redis))}")
    if not args.apply:
        print("dry run — pass --apply to write")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
