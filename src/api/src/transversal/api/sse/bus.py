"""SSE event bus — in-process publish/subscribe for real-time state push.

Events are scoped to sessions. Services publish events;
SSE streams subscribe and push to connected clients.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import AsyncIterator

from transversal.db.redis import REDIS_URL, get_redis_client

CHANNEL_PREFIX = "sse:"


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
        self._worker_id = uuid.uuid4().hex
        self._redis = get_redis_client()  # None when Redis is unavailable (single-worker)

    def publish(self, event: StreamEvent) -> None:
        """Push an event to local subscribers and (if Redis is up) other workers."""
        self._deliver_local(event)
        if self._redis is not None:
            try:
                self._redis.publish(
                    f"{CHANNEL_PREFIX}{event.session_id}",
                    json.dumps({
                        "source_worker": self._worker_id,
                        "session_id": event.session_id,
                        "event": event.event,
                        "data": event.data,
                    }),
                )
            except Exception:
                pass  # Redis hiccup must not break the local publish

    def _deliver_local(self, event: StreamEvent) -> None:
        """Push an event to all subscribers of its session (this process only)."""
        queues = self._queues.get(event.session_id, [])
        dead = []
        for q in queues:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            queues.remove(q)

    def start_redis_subscriber(self) -> None:
        """Start a daemon thread forwarding other workers' events into the
        local bus, so this worker's SSE clients see cross-worker events.

        A thread + sync pub/sub is used instead of an asyncio task because it
        has no shutdown-cleanup hazards (daemon threads die with the process).
        """
        if self._redis is None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        threading.Thread(
            target=self._run_redis_subscriber_thread,
            args=(loop,),
            daemon=True,
            name="sse-redis-sub",
        ).start()

    def _run_redis_subscriber_thread(self, loop) -> None:
        import redis as redis_sync

        r = redis_sync.Redis.from_url(
            REDIS_URL, decode_responses=True, socket_connect_timeout=1
        )
        pubsub = r.pubsub(ignore_subscribe_messages=True)
        pubsub.psubscribe(f"{CHANNEL_PREFIX}*")
        for message in pubsub.listen():
            if message.get("type") != "pmessage":
                continue
            try:
                payload = json.loads(message["data"])
            except Exception:
                continue
            if payload.get("source_worker") == self._worker_id:
                continue  # echo of our own publish
            event = StreamEvent(
                event=payload.get("event", ""),
                data=payload.get("data", {}),
                session_id=payload.get("session_id", ""),
            )
            if loop is not None:
                loop.call_soon_threadsafe(self._deliver_local, event)

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
