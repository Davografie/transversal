"""Migrate trait settings from the old ``negative``/challenge ``polarity`` split
to the unified, non-null ``polarity`` field.

Usage:
    docker compose exec api python -m transversal.migrate_polarity

Rule (baked, non-null):
    polarity = "negative" when (negative is True or polarity == "negative"),
    otherwise "positive".  The legacy ``negative`` field is removed.
"""

from __future__ import annotations

import sys

from transversal.db.arango import get_db, TRAITSETTINGS


def migrate() -> int:
    db = get_db()
    col = db.collection(TRAITSETTINGS)

    updated = 0
    removed_negative = 0
    for doc in col.all():
        new_doc = dict(doc)
        negative = bool(new_doc.get("negative"))
        old_polarity = new_doc.get("polarity")
        if negative or old_polarity == "negative":
            new_doc["polarity"] = "negative"
        else:
            new_doc["polarity"] = "positive"
        if "negative" in new_doc:
            del new_doc["negative"]
            removed_negative += 1
        if new_doc != dict(doc):
            col.update(new_doc)
            updated += 1

    print(f"Updated {updated} trait settings; removed legacy negative from {removed_negative}.")
    return 0


if __name__ == "__main__":
    sys.exit(migrate())
