"""Change log — append-only mutation log with undo support.

Every state-changing operation records an entry. Undo walks the log backward and
reverses mutations for a given entity within a session.

**A mutation belongs to a campaign** ([[B305]]). The log is in-process and was keyed by
entity id — which a fork **shares with its ancestor**, every copied document keeping its
``_key`` — so ``undo_entity(entity_id)`` with no session id could reach into another world
and reverse a mutation made there. It is not a read leak: it is a wrong write.

Three consequences, all deliberate:

- entries carry the campaign, and every query is confined to one;
- the "no session id means any session" wildcard survives, but only *within* a campaign,
  because that is what callers mean by it;
- a mutation recorded with **no campaign in scope is not stored**. An unundoable change is
  a smaller failure than an undo that lands in the wrong world.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from transversal.services.campaign_scope import current_campaign

logger = logging.getLogger("transversal.change_log")


@dataclass
class Mutation:
    """A single state change."""
    entity_id: str
    field: str           # e.g. "razmerit", "trait.hacking.die_type", "location"
    old_value: Any
    new_value: Any
    timestamp: float = field(default_factory=time.time)
    session_id: str = ""
    #: Which campaign's change this is ([[B305]]). Empty never occurs: an unrecordable
    #: mutation is dropped rather than filed under a guess.
    campaign: str = ""
    sequence: int = 0    # global sequence number


class ChangeLog:
    """Append-only log of all mutations.

    Supports undo by walking backward through mutations for a given
    entity and session, within one campaign.
    """

    def __init__(self):
        self._mutations: list[Mutation] = []
        self._seq: int = 0

    @staticmethod
    def _scope(campaign: str | None) -> str:
        """The campaign to act under: the argument, else this context's scope."""
        return campaign or current_campaign()

    def record(
        self,
        entity_id: str,
        field: str,
        old_value: Any,
        new_value: Any,
        session_id: str = "",
        campaign: str | None = None,
    ) -> Optional[Mutation]:
        """Record a mutation. Returns the entry for potential undo, or None if dropped."""
        scope = self._scope(campaign)
        if not scope:
            logger.debug(
                "not recording %s.%s — this context names no campaign", entity_id, field
            )
            return None

        self._seq += 1
        mutation = Mutation(
            entity_id=entity_id,
            field=field,
            old_value=old_value,
            new_value=new_value,
            session_id=session_id,
            campaign=scope,
            sequence=self._seq,
        )
        self._mutations.append(mutation)
        return mutation

    def _entries(
        self, entity_id: str, session_id: str, campaign: str
    ) -> list[Mutation]:
        """This campaign's mutations for an entity — optionally one session's."""
        return [
            m
            for m in self._mutations
            if m.entity_id == entity_id
            and m.campaign == campaign
            and (not session_id or m.session_id == session_id)
        ]

    def undo_entity(
        self, entity_id: str, session_id: str = "", campaign: str | None = None
    ) -> list[Mutation]:
        """Undo all mutations for an entity in a session, **in this campaign**.

        Returns the reversed mutations (for the caller to apply to state).
        Walks backward so mutations are undone in reverse order.
        """
        to_undo = list(
            reversed(self._entries(entity_id, session_id, self._scope(campaign)))
        )
        # Remove undone mutations from the log
        for m in to_undo:
            self._mutations.remove(m)
        return to_undo

    def undo_last(
        self, entity_id: str, session_id: str = "", campaign: str | None = None
    ) -> Optional[Mutation]:
        """Undo the most recent mutation for an entity in a session."""
        scope = self._scope(campaign)
        for i in range(len(self._mutations) - 1, -1, -1):
            m = self._mutations[i]
            if (
                m.entity_id == entity_id
                and m.campaign == scope
                and (not session_id or m.session_id == session_id)
            ):
                self._mutations.pop(i)
                return m
        return None

    def mutations_for(
        self, entity_id: str, session_id: str = "", campaign: str | None = None
    ) -> list[Mutation]:
        """Get all mutations for an entity, in this campaign."""
        return self._entries(entity_id, session_id, self._scope(campaign))

    def count(self) -> int:
        return len(self._mutations)

    def clear(self) -> None:
        self._mutations.clear()
        self._seq = 0


# Global singleton
change_log = ChangeLog()
