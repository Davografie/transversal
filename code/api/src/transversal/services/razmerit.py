"""Razmerit transaction service — atomic earn, spend, and transfer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from transversal.api.sse.bus import StreamEvent, event_bus
from transversal.db.repository import EntityRepository
from transversal.services.change_log import change_log
from transversal.services.session_manager import session_manager


def _publish_to_sessions(event: StreamEvent) -> None:
    for s in session_manager.list_active():
        event_bus.publish(StreamEvent(
            event=event.event, session_id=s.id, data=event.data))


class InsufficientRazmeritError(Exception):
    pass


@dataclass
class RazmeritResult:
    from_id: str
    from_balance: int
    to_id: Optional[str]
    to_balance: Optional[int]
    amount: int
    reason: str


class RazmeritService:
    def __init__(self, repository: EntityRepository | None = None):
        self.repo = repository or EntityRepository()

    def spend(self, entity_id: str, amount: int, reason: str = "sfx_cost",
              session_id: Optional[str] = None) -> RazmeritResult:
        entity = self.repo.get_entity(entity_id)
        if entity is None:
            raise ValueError(f"Entity '{entity_id}' not found")
        if entity.razmerit < amount:
            raise InsufficientRazmeritError(
                f"Entity '{entity.name}' has {entity.razmerit} razmerit, "
                f"needs {amount} for '{reason}'"
            )
        old_balance = entity.razmerit
        entity.razmerit -= amount
        self.repo.update_entity(entity)
        change_log.record(entity_id, "razmerit", old_balance, entity.razmerit, session_id or "")

        _publish_to_sessions(StreamEvent(
            event="razmerit_changed",
            data={"entity_id": entity_id, "old_balance": entity.razmerit + amount,
                  "new_balance": entity.razmerit, "reason": reason},
        ))

        return RazmeritResult(
            from_id=entity_id, from_balance=entity.razmerit,
            to_id=None, to_balance=None, amount=amount, reason=reason,
        )

    def earn(self, entity_id: str, amount: int, reason: str = "complication",
             session_id: Optional[str] = None) -> RazmeritResult:
        entity = self.repo.get_entity(entity_id)
        if entity is None:
            raise ValueError(f"Entity '{entity_id}' not found")
        old_balance = entity.razmerit
        entity.razmerit += amount
        self.repo.update_entity(entity)
        change_log.record(entity_id, "razmerit", old_balance, entity.razmerit, session_id or "")

        _publish_to_sessions(StreamEvent(
            event="razmerit_changed",
            data={"entity_id": entity_id, "old_balance": entity.razmerit - amount,
                  "new_balance": entity.razmerit, "reason": reason},
        ))

        return RazmeritResult(
            from_id="system", from_balance=0,
            to_id=entity_id, to_balance=entity.razmerit,
            amount=amount, reason=reason,
        )

    def transfer(self, from_id: str, to_id: str, amount: int, reason: str = "transfer") -> RazmeritResult:
        from_e = self.repo.get_entity(from_id)
        to_e = self.repo.get_entity(to_id)
        if from_e is None:
            raise ValueError(f"Source '{from_id}' not found")
        if to_e is None:
            raise ValueError(f"Target '{to_id}' not found")
        if from_e.razmerit < amount:
            raise InsufficientRazmeritError(
                f"Entity '{from_e.name}' has {from_e.razmerit} razmerit, needs {amount}"
            )
        from_e.razmerit -= amount
        to_e.razmerit += amount
        self.repo.update_entity(from_e)
        self.repo.update_entity(to_e)
        return RazmeritResult(
            from_id=from_id, from_balance=from_e.razmerit,
            to_id=to_id, to_balance=to_e.razmerit,
            amount=amount, reason=reason,
        )
