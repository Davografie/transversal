"""Scheduled events — split out of src/api/src/transversal/db/repository.py."""

from __future__ import annotations

from transversal.db.arango import SCHEDULED_EVENTS
from transversal.domain import ScheduledEvent
from typing import Optional


class RepositoryScheduledEvents:
    """Mixin contributing 7 member(s) to the repository."""

    def create_scheduled_event(self, event: ScheduledEvent) -> ScheduledEvent:
        doc = event.model_dump()
        doc["_key"] = event.id
        self._scheduled_events.insert(doc)
        return event

    def get_scheduled_event(self, event_id: str) -> Optional[ScheduledEvent]:
        doc = self._scheduled_events.get(event_id)
        return ScheduledEvent.model_validate({**doc, "id": doc["_key"]}) if doc else None

    def update_scheduled_event(self, event: ScheduledEvent) -> ScheduledEvent:
        doc = event.model_dump()
        doc["_key"] = event.id
        self._scheduled_events.replace(doc)
        return event

    def delete_scheduled_event(self, event_id: str) -> bool:
        try:
            self._scheduled_events.delete(event_id)
            return True
        except Exception:
            return False

    def delete_scheduled_events(
        self,
        *,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        target_ids: Optional[list[str]] = None,
    ) -> int:
        """Delete scheduled events scoped to target owners; return count removed.

        At least one scope must be given (a bare call would wipe the store).
        ``target_id`` scopes to a single owner; ``target_ids`` to a set of owners.
        """
        if target_type is None and target_id is None and target_ids is None:
            raise ValueError("delete_scheduled_events requires a scope")
        filters = []
        bind_vars = {}
        if target_type is not None:
            filters.append("e.target_type == @target_type")
            bind_vars["target_type"] = target_type
        if target_id is not None:
            filters.append("e.target_id == @target_id")
            bind_vars["target_id"] = target_id
        if target_ids is not None:
            filters.append("e.target_id IN @target_ids")
            bind_vars["target_ids"] = target_ids
        query = (
            f"FOR e IN {SCHEDULED_EVENTS} "
            f"FILTER {' AND '.join(filters)} "
            f"REMOVE e IN {SCHEDULED_EVENTS} RETURN OLD._key"
        )
        return len(list(self.db.aql.execute(query, bind_vars=bind_vars)))

    def list_all_scheduled_events(self) -> list[ScheduledEvent]:
        query = f"FOR e IN {SCHEDULED_EVENTS} RETURN e"
        return [
            ScheduledEvent.model_validate({**doc, "id": doc["_key"]})
            for doc in self.db.aql.execute(query)
        ]

    def list_scheduled_events(
        self,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        target_ids: Optional[list[str]] = None,
    ) -> list[ScheduledEvent]:
        """List scheduled events, optionally scoped to target owners.

        ``target_type`` is ``"entity"`` or ``"trait_setting"``. ``target_id``
        scopes to a single owner (entity id or trait-setting id); ``target_ids``
        scopes to a set of owners. When every filter is omitted this is the full
        store; otherwise the query is filtered on the owner columns.
        """
        if target_type is None and target_id is None and target_ids is None:
            return self.list_all_scheduled_events()
        filters = []
        bind_vars = {}
        if target_type is not None:
            filters.append("e.target_type == @target_type")
            bind_vars["target_type"] = target_type
        if target_id is not None:
            filters.append("e.target_id == @target_id")
            bind_vars["target_id"] = target_id
        if target_ids is not None:
            filters.append("e.target_id IN @target_ids")
            bind_vars["target_ids"] = target_ids
        query = f"FOR e IN {SCHEDULED_EVENTS} FILTER {' AND '.join(filters)} RETURN e"
        return [
            ScheduledEvent.model_validate({**doc, "id": doc["_key"]})
            for doc in self.db.aql.execute(query, bind_vars=bind_vars)
        ]
