"""Join tokens — split out of src/api/src/transversal/db/repository.py."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from transversal.db.arango import JOIN_TOKENS


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RepositoryJoinTokens:
    """Mixin contributing join-token liveness to the repository.

    The store holds *liveness only*. The token a client presents is signed and
    self-describing (``api/access_tokens.py``), so proving one is ours needs no
    lookup; what needs storage is being able to **close one early**, and to see
    which are open. Under campaign-per-database these live in the campaign's own
    database, so this is per-campaign for free.
    """

    def create_join_token(self, created_by: str = "", expires_at: str = "") -> str:
        token_id = f"join-{uuid.uuid4().hex[:12]}"
        self._join_tokens.insert(
            {
                "_key": token_id,
                "created_by": created_by,
                "created_at": _now_iso(),
                "expires_at": expires_at,
                "closed_at": None,
                "closed_by": "",
            }
        )
        return token_id

    def get_join_token(self, token_id: str) -> dict | None:
        return self._join_tokens.get(token_id)

    def close_join_token(self, token_id: str, closed_by: str = "") -> bool:
        """Close a token early. False when it does not exist or is already closed."""
        doc = self._join_tokens.get(token_id)
        if not doc or doc.get("closed_at"):
            return False
        doc["closed_at"] = _now_iso()
        doc["closed_by"] = closed_by
        self._join_tokens.update(doc)
        return True

    def list_join_tokens(self, open_only: bool = True) -> list[dict]:
        docs = [doc for doc in self._join_tokens.all()]
        if open_only:
            docs = [doc for doc in docs if not doc.get("closed_at")]
        docs.sort(key=lambda d: d.get("created_at") or "", reverse=True)
        return docs

    def close_all_join_tokens(self, closed_by: str = "") -> int:
        """Close every open token. Returns how many were closed."""
        closed = 0
        for doc in self.list_join_tokens(open_only=True):
            if self.close_join_token(doc["_key"], closed_by=closed_by):
                closed += 1
        return closed
