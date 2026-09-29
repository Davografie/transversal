"""Players — split out of src/api/src/transversal/domain/__init__.py."""

from pydantic import BaseModel
from pydantic import Field
from typing import Optional


class Player(BaseModel):
    """A human player's identity for session persistence.

    Stored in the `players` collection. Ownership of entities is expressed as
    `agency` edges (``relationships``, type ``agency``) — *not* stored here;
    it is resolved from the graph at read time.

    Spotlight recency is player-level table-management state: ``last_spotlight_at``
    (when this player last took control of a main) and ``last_main_entity_id``
    (which main that was). These are distinct from ``Projection.last_used_at``,
    which is *mechanical* body-reuse state for transversal — do not conflate them.
    """
    id: str
    name: str = ""
    role: str = "player"  # "player" | "architect"
    # Session-revocation counter (SEC-3 groundwork; not yet enforced anywhere). A
    # session cookie will carry the epoch it was issued under, and validating it
    # compares against this. Bumping the value therefore kills every session that
    # names this player — the *only* way "eject this person" can work, because a
    # signed cookie cannot be recalled. Absent on older documents: reads default to
    # 0, which is correct because nothing has been revoked yet.
    epoch: int = 0
    last_spotlight_at: Optional[str] = None  # ISO timestamp; sort key for the recency list
    last_main_entity_id: Optional[str] = None  # the main last taken control of
    entity_ids: list[str] = Field(
        default_factory=list, exclude=True
    )  # transient (never persisted) — resolved from `agency` edges at read time
