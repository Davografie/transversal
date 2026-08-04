"""Change log — append-only mutation log with undo support.

Every state-changing operation records an entry. Undo walks the log
backward and reverses mutations for a given entity within a session.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Mutation:
    """A single state change."""
    entity_id: str
    field: str           # e.g. "razmerit", "trait.hacking.die_type", "location"
    old_value: Any
    new_value: Any
    timestamp: float = field(default_factory=time.time)
    session_id: str = ""
    sequence: int = 0    # global sequence number


class ChangeLog:
    """Append-only log of all mutations.

    Supports undo by walking backward through mutations for a given
    entity and session, reversing each one.
    """

    def __init__(self):
        self._mutations: list[Mutation] = []
        self._seq: int = 0

    def record(
        self,
        entity_id: str,
        field: str,
        old_value: Any,
        new_value: Any,
        session_id: str = "",
    ) -> Mutation:
        """Record a mutation. Returns the entry for potential undo."""
        self._seq += 1
        mutation = Mutation(
            entity_id=entity_id,
            field=field,
            old_value=old_value,
            new_value=new_value,
            session_id=session_id,
            sequence=self._seq,
        )
        self._mutations.append(mutation)
        return mutation

    def undo_entity(self, entity_id: str, session_id: str = "") -> list[Mutation]:
        """Undo all mutations for an entity in a session.

        Returns the reversed mutations (for the caller to apply to state).
        Walks backward so mutations are undone in reverse order.
        """
        to_undo = [
            m for m in reversed(self._mutations)
            if m.entity_id == entity_id and (not session_id or m.session_id == session_id)
        ]
        # Remove undone mutations from the log
        for m in to_undo:
            self._mutations.remove(m)
        return to_undo

    def undo_last(self, entity_id: str, session_id: str = "") -> Optional[Mutation]:
        """Undo the most recent mutation for an entity in a session."""
        for i in range(len(self._mutations) - 1, -1, -1):
            m = self._mutations[i]
            if m.entity_id == entity_id and (not session_id or m.session_id == session_id):
                self._mutations.pop(i)
                return m
        return None

    def mutations_for(self, entity_id: str, session_id: str = "") -> list[Mutation]:
        """Get all mutations for an entity."""
        return [
            m for m in self._mutations
            if m.entity_id == entity_id and (not session_id or m.session_id == session_id)
        ]

    def count(self) -> int:
        return len(self._mutations)

    def clear(self) -> None:
        self._mutations.clear()
        self._seq = 0


# Global singleton
change_log = ChangeLog()
