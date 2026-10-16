"""Accounts and forks — the registry's documents (B255).

Kept out of ``domain/players.py`` deliberately: an **account** is not a player and
must not be mistaken for one. A player lives inside one campaign database and is
taken after admission; an account exists *before* any campaign is chosen, outlives
any one of them, and is the only identity that holds recovery credentials
([[Identity Programme]] §3).
"""

from typing import Optional

from pydantic import BaseModel


class Account(BaseModel):
    """A person who owns forks.

    Stored in the registry's ``accounts`` collection. ``email`` is the recovery
    identifier *and* the only credential v1 has, which is why ``verified_at`` must
    be set before sign-in is allowed: an unverified address is a way in for whoever
    owns the typo ([[Identity Programme]] §5.3).

    ``epoch`` is the session-revocation counter, the account-tier twin of
    ``Player.epoch`` — bumping it kills every account session issued under it,
    because a signed cookie cannot be recalled.
    """

    id: str
    email: str
    verified_at: Optional[str] = None
    created_at: str = ""
    epoch: int = 0
    #: May this account edit the global multiverse directly? v1 is whole-world or
    #: nothing ([[Global Multiverse and Forks]] §5.2), so the right is a flag on the
    #: account rather than scoped to a subtree.
    global_editor: bool = False


class Fork(BaseModel):
    """A tenant: one account's copy of the global multiverse.

    Called a *fork* rather than a campaign because under the current direction that
    is what it is — a verbatim copy, not a composition of packages. It is still the
    campaign the admission model operates inside.

    ``database`` is the ArangoDB database name this fork routes to; it is the reason
    this row exists at all. ``kind`` leaves room for the playroom/global distinction
    without a second collection. ``slug`` is the DNS label it answers on
    (``<slug>.<base-domain>``) — the way a request names its campaign.
    """

    id: str
    name: str
    database: str
    owner_account: str
    kind: str = "fork"  # "fork" | "global"
    created_at: str = ""
    slug: str = ""
