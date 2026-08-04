"""SSE event bus — in-process publish/subscribe for real-time state push.

Events are scoped to sessions. Services publish events;
SSE streams subscribe and push to connected clients.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import AsyncIterator


@dataclass
class StreamEvent:
    """An event pushed to SSE clients."""
    event: str  # event type: location_changed, trait_updated, etc.
    data: dict  # JSON-serializable payload
    id: str = ""  # event ID for reconnection
    session_id: str = ""


class EventBus:
    """In-process publish/subscribe bus.

    Each session gets its own queue. Clients subscribe to a session
    and receive events published to that session.
    """

    def __init__(self):
        self._queues: dict[str, list[asyncio.Queue]] = {}  # session_id → [queues]

    def publish(self, event: StreamEvent) -> None:
        """Push an event to all subscribers of its session."""
        queues = self._queues.get(event.session_id, [])
        dead = []
        for q in queues:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            queues.remove(q)

    def subscribe(self, session_id: str) -> "Subscription":
        """Create a subscription for a session."""
        return Subscription(bus=self, session_id=session_id)

    def _add_queue(self, session_id: str, queue: asyncio.Queue) -> None:
        if session_id not in self._queues:
            self._queues[session_id] = []
        self._queues[session_id].append(queue)

    def _remove_queue(self, session_id: str, queue: asyncio.Queue) -> None:
        queues = self._queues.get(session_id, [])
        if queue in queues:
            queues.remove(queue)
        if not queues:
            self._queues.pop(session_id, None)


class Subscription:
    """A single client's subscription to a session's event stream."""

    def __init__(self, bus: EventBus, session_id: str):
        self.bus = bus
        self.session_id = session_id
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._seq = 0
        bus._add_queue(session_id, self._queue)

    async def stream(self) -> AsyncIterator[dict]:
        """Async generator yielding SSE-compatible dicts."""
        try:
            while True:
                event: StreamEvent = await self._queue.get()
                self._seq += 1
                yield {
                    "event": event.event,
                    "data": json.dumps(event.data),
                    "id": str(self._seq),
                }
        except asyncio.CancelledError:
            pass
        finally:
            self.bus._remove_queue(self.session_id, self._queue)

    def close(self) -> None:
        self.bus._remove_queue(self.session_id, self._queue)


def _format_sse(event: StreamEvent, seq: int) -> str:
    """Format a StreamEvent as an SSE message string."""
    lines = []
    if event.id:
        lines.append(f"id: {event.id}")
    else:
        lines.append(f"id: {seq}")
    lines.append(f"event: {event.event}")
    lines.append(f"data: {json.dumps(event.data)}")
    lines.append("")  # blank line terminates the message
    return "\n".join(lines) + "\n"


# Global singleton
event_bus = EventBus()
