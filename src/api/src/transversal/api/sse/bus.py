"""SSE event bus — in-process publish/subscribe for real-time state push.

Events are scoped to a **campaign and a session**. Services publish events; SSE
streams subscribe and push to connected clients.

The campaign is not decoration ([[B305]]). Before it existed, ``list_active()``
returned every campaign's sessions and twenty-odd call sites fanned one campaign's
event out to all of them; because a fork preserves every ``_key``, the receiving
campaign could not even tell an intruder from its own data. Two consequences are
load-bearing here:

- **An event with no campaign is delivered to nobody**, and says so in the log. The
  bug this replaces was spelling "no campaign" as "everyone".
- **The campaign is a default, not an argument every site must remember.** Both
  ``StreamEvent`` and ``SessionManager.list_active()`` resolve it from the scope in
  context (the request's, or one restored by ``use_scope``), which is how the
  twenty-odd ``for s in session_manager.list_active()`` fan-out sites became correct
  without being rewritten — an environment where the safe value is the default one
  cannot be got wrong by omission.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import uuid
from dataclasses import dataclass, field
from typing import AsyncIterator

from transversal.db.redis import REDIS_URL, get_redis_client
from transversal.services.campaign_scope import current_campaign

logger = logging.getLogger("transversal.sse")

CHANNEL_PREFIX = "sse:"


@dataclass
class StreamEvent:
    """An event pushed to SSE clients."""
    event: str  # event type: location_changed, trait_updated, etc.
    data: dict  # JSON-serializable payload
    id: str = ""  # event ID for reconnection
    session_id: str = ""
    #: The campaign this belongs to ([[B305]]). It defaults to **the scope this code
    #: is running in** — set by the request middleware, or by ``use_scope()`` for work
    #: that outlives its request. That is a resolution of an established scope, not a
    #: guess: with no scope it is empty, and :meth:`EventBus.publish` then delivers to
    #: nobody. Stamping it on every construction site by hand would be 24 chances to
    #: forget, so the safe value is the default one.
    campaign: str = field(default_factory=current_campaign)


class EventBus:
    """In-process publish/subscribe bus.

    Each session gets its own queue, within its campaign. Clients subscribe to a
    session and receive events published to that session.
    """

    def __init__(self):
        # (campaign, session_id) → [queues]
        self._queues: dict[tuple[str, str], list[asyncio.Queue]] = {}
        self._worker_id = uuid.uuid4().hex
        self._redis = get_redis_client()  # None when Redis is unavailable (single-worker)

    def publish(self, event: StreamEvent) -> None:
        """Push an event to its campaign's subscribers, and (if Redis is up) other workers.

        An unscoped event reaches **no one**: delivering it to every campaign is the
        defect this scope exists to remove, and a silent delivery to a *guessed*
        campaign would be the same bug wearing a different hat.
        """
        if not event.campaign:
            logger.warning(
                "dropping SSE %r with no campaign — live events must name one "
                "(capture_scope()/use_scope() for work that outlives its request)",
                event.event,
            )
            return

        self._deliver_local(event)
        if self._redis is not None:
            try:
                self._redis.publish(
                    self._channel(event.campaign, event.session_id),
                    json.dumps({
                        "source_worker": self._worker_id,
                        "campaign": event.campaign,
                        "session_id": event.session_id,
                        "event": event.event,
                        "data": event.data,
                    }),
                )
            except Exception:
                pass  # Redis hiccup must not break the local publish

    @staticmethod
    def _channel(campaign: str, session_id: str) -> str:
        return f"{CHANNEL_PREFIX}{campaign}:{session_id}"

    def _deliver_local(self, event: StreamEvent) -> None:
        """Push an event to all subscribers of its session (this process only)."""
        queues = self._queues.get((event.campaign, event.session_id), [])
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
        # Every worker subscribes to every campaign's channel — a worker may hold
        # clients from any of them — and delivery is decided by the keys, not by the
        # subscription.
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
                campaign=payload.get("campaign", ""),
            )
            if loop is not None:
                loop.call_soon_threadsafe(self._deliver_local, event)

    def subscribe(self, session_id: str, campaign: str) -> "Subscription":
        """Create a subscription for a session, inside one campaign."""
        return Subscription(bus=self, session_id=session_id, campaign=campaign)

    def _add_queue(self, campaign: str, session_id: str, queue: asyncio.Queue) -> None:
        self._queues.setdefault((campaign, session_id), []).append(queue)

    def _remove_queue(self, campaign: str, session_id: str, queue: asyncio.Queue) -> None:
        key = (campaign, session_id)
        queues = self._queues.get(key, [])
        if queue in queues:
            queues.remove(queue)
        if not queues:
            self._queues.pop(key, None)


class Subscription:
    """A single client's subscription to a session's event stream."""

    def __init__(self, bus: EventBus, session_id: str, campaign: str):
        self.bus = bus
        self.session_id = session_id
        self.campaign = campaign
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._seq = 0
        bus._add_queue(campaign, session_id, self._queue)

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
            self.bus._remove_queue(self.campaign, self.session_id, self._queue)

    def close(self) -> None:
        self.bus._remove_queue(self.campaign, self.session_id, self._queue)


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
