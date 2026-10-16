"""Registry repository — accounts, forks and email-link liveness (B255).

Deliberately separate from :class:`transversal.db.repository.EntityRepository`:
that class opens the *campaign* database through ``get_db()`` and binds 20
collections on construction. This one binds the registry's three
(:mod:`transversal.db.registry`) and nothing else.

Accounts and forks come back as the domain models rather than raw documents, the
same way ``player_manager`` returns a ``Player`` — the row's shape is the model's
job, not every caller's.

The lookups here all go through ``Collection.find`` with a literal filter rather
than interpolated AQL, so there is no query surface for an email address to reach
(SEC-1's lesson).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from transversal.db.registry import (
    ACCOUNT_TOKENS,
    ACCOUNTS,
    CAMPAIGNS,
    get_registry_db,
)
from transversal.domain.accounts import Account, Fork

if TYPE_CHECKING:
    from arango.database import StandardDatabase

#: What an email link is for. One mechanism, two entry points (recovery is sign-in).
PURPOSE_VERIFY = "verify"
PURPOSE_SIGN_IN = "sign_in"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_email(email: str) -> str:
    """The address as stored and compared: trimmed, case-folded.

    The unique index is on this value, so ``Dave@Example.com`` and
    ``dave@example.com`` cannot become two accounts.
    """
    return (email or "").strip().lower()


def _to_account(doc: dict | None) -> Account | None:
    if not doc:
        return None
    return Account(
        id=doc["_key"],
        email=doc.get("email", ""),
        verified_at=doc.get("verified_at"),
        created_at=doc.get("created_at", ""),
        epoch=int(doc.get("epoch") or 0),
        global_editor=bool(doc.get("global_editor")),
    )


def _to_fork(doc: dict | None) -> Fork | None:
    if not doc:
        return None
    return Fork(
        id=doc["_key"],
        name=doc.get("name", ""),
        database=doc.get("database", ""),
        owner_account=doc.get("owner_account", ""),
        kind=doc.get("kind", "fork"),
        created_at=doc.get("created_at", ""),
        slug=doc.get("slug", ""),
    )


class RegistryRepository:
    """Accounts, forks and single-use email links, against the registry DB."""

    def __init__(self, db: "StandardDatabase | None" = None):
        self.db = db or get_registry_db()
        self._accounts = self.db.collection(ACCOUNTS)
        self._campaigns = self.db.collection(CAMPAIGNS)
        self._tokens = self.db.collection(ACCOUNT_TOKENS)

    # ── Accounts ──────────────────────────────────────────────────────

    def create_account(
        self, email: str, *, global_editor: bool = False
    ) -> Account:
        """Insert a new, unverified account. The caller must have checked for a
        duplicate — the unique index is the backstop, not the flow."""
        account_id = f"acct-{uuid.uuid4().hex[:12]}"
        self._accounts.insert(
            {
                "_key": account_id,
                "email": normalize_email(email),
                "verified_at": None,
                "created_at": _now_iso(),
                "epoch": 0,
                "global_editor": bool(global_editor),
            }
        )
        return self.get_account(account_id)

    def get_account(self, account_id: str) -> Account | None:
        return _to_account(self._accounts.get(account_id))

    def find_account_by_email(self, email: str) -> Account | None:
        found = list(self._accounts.find({"email": normalize_email(email)}, limit=1))
        return _to_account(found[0]) if found else None

    def mark_email_verified(self, account_id: str) -> Account | None:
        """Set ``verified_at`` once. Returns the updated account, or None if unknown."""
        doc = self._accounts.get(account_id)
        if not doc:
            return None
        if not doc.get("verified_at"):
            doc["verified_at"] = _now_iso()
            self._accounts.update(doc)
        return _to_account(doc)

    def bump_account_epoch(self, account_id: str) -> int:
        """Revoke every account session: the epoch a cookie carries is now stale."""
        doc = self._accounts.get(account_id)
        if not doc:
            return 0
        doc["epoch"] = int(doc.get("epoch") or 0) + 1
        self._accounts.update(doc)
        return doc["epoch"]

    # ── Forks (the routing table) ─────────────────────────────────────

    def create_fork(
        self,
        name: str,
        database: str,
        owner_account: str,
        *,
        kind: str = "fork",
        slug: str = "",
    ) -> Fork:
        fork_id = f"fork-{uuid.uuid4().hex[:12]}"
        self._campaigns.insert(
            {
                "_key": fork_id,
                "name": name,
                "database": database,
                "owner_account": owner_account,
                "kind": kind,
                "created_at": _now_iso(),
                "slug": slug,
            }
        )
        return self.get_fork(fork_id)

    def get_fork(self, fork_id: str) -> Fork | None:
        return _to_fork(self._campaigns.get(fork_id))

    def find_fork_by_database(self, database: str) -> Fork | None:
        found = list(self._campaigns.find({"database": database}, limit=1))
        return _to_fork(found[0]) if found else None

    def find_fork_by_slug(self, slug: str) -> Fork | None:
        """The routing lookup: which fork answers on this DNS label."""
        found = list(self._campaigns.find({"slug": (slug or "").strip().lower()}, limit=1))
        return _to_fork(found[0]) if found else None

    def list_forks_for(self, account_id: str) -> list[Fork]:
        rows = list(self._campaigns.find({"owner_account": account_id}))
        rows.sort(key=lambda row: row.get("created_at") or "", reverse=True)
        return [fork for fork in (_to_fork(row) for row in rows) if fork]

    # ── Email links ───────────────────────────────────────────────────

    def create_account_token(
        self, account_id: str, purpose: str, expires_at: str
    ) -> str:
        """Record a link's liveness. The link itself is signed (access_tokens)."""
        token_id = f"link-{uuid.uuid4().hex[:12]}"
        self._tokens.insert(
            {
                "_key": token_id,
                "account_id": account_id,
                "purpose": purpose,
                "created_at": _now_iso(),
                "expires_at": expires_at,
                "consumed_at": None,
            }
        )
        return token_id

    def get_account_token(self, token_id: str) -> dict | None:
        return self._tokens.get(token_id)

    def consume_account_token(self, token_id: str) -> bool:
        """Spend a link. False when it is unknown or already spent — single use is
        the whole reason the record exists, because the signature cannot be recalled."""
        record = self._tokens.get(token_id)
        if not record or record.get("consumed_at"):
            return False
        record["consumed_at"] = _now_iso()
        self._tokens.update(record)
        return True
