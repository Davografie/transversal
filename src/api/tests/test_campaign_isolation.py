"""B305 — one campaign's live state is not observable from another.

Measured live before this work: a single Redis namespace held **every** campaign's
sessions (``session:*`` plus one ``sessions:active``), 24 call sites fanned an event out
to all of them, and — because a fork preserves every ``_key`` — the receiving campaign
could not tell an intruder from its own data (31 sessions resolved in both databases at
once).

This drives the **real** session store and the **real** bus. The two leaks this thread
has already had were both missed by fakes and found live, so a fake-based test here
would be repeating the mistake. Probe campaigns are namespaced and cleaned up; the live
campaigns are never touched.
"""

import json

import pytest

from transversal.api.sse.bus import StreamEvent, event_bus
from transversal.services import session_manager as sm_mod
from transversal.services.campaign_scope import (
    capture_scope,
    current_campaign,
    use_campaign,
)
from transversal.services.session_manager import SessionManager

A = "tv2-probe-a"
B = "tv2-probe-b"


@pytest.fixture
def mgr(monkeypatch):
    """The real manager, pointed at a **scratch Redis database**.

    The suite shares the dev Redis with the running app, and an earlier version of this
    fixture deleted the live ``sessions:active`` set on teardown — 463 real session
    records lost their index (rebuilt from the records themselves). Index 1 is used by
    nothing, so these tests can be ruthless there while the live instance stays
    untouched: the teardown is a ``flushdb`` of the scratch database.
    """
    import os

    import redis as redis_sync

    url = os.environ.get("REDIS_URL", "")
    scratch = None
    if url:
        try:
            scratch = redis_sync.Redis.from_url(f"{url}/1", decode_responses=True)
            scratch.ping()
            scratch.flushdb()
        except Exception:
            scratch = None
    if scratch is not None:
        monkeypatch.setattr(sm_mod, "get_redis_client", lambda: scratch)

    yield SessionManager()

    if scratch is not None:
        scratch.flushdb()
        scratch.close()


@pytest.fixture(autouse=True)
def _never_publish_to_the_live_broker(monkeypatch):
    """The bus would publish to the app's Redis. Local delivery is what is asserted,
    and a probe campaign has no business on the live broker at all."""
    monkeypatch.setattr(event_bus, "_redis", None)


def _drain(sub) -> list[StreamEvent]:
    out = []
    while True:
        try:
            out.append(sub._queue.get_nowait())
        except Exception:
            return out


def test_a_session_belongs_to_the_campaign_that_made_it(mgr):
    with use_campaign(A):
        a = mgr.create("Table A")
    with use_campaign(B):
        b = mgr.create("Table B")

    assert a.campaign == A and b.campaign == B
    assert [s.id for s in mgr.list_active(A)] == [a.id]
    assert [s.id for s in mgr.list_active(B)] == [b.id]


def test_the_same_session_id_in_two_campaigns_is_two_sessions(mgr):
    """The sharp one: ids are shared between a campaign and its ancestor by design, so
    the *key* has to carry the campaign or one campaign's table is the other's."""
    shared = "session-shared-id"
    with use_campaign(A):
        mgr._put(sm_mod.Session(id=shared, name="A's table", campaign=A))
    with use_campaign(B):
        mgr._put(sm_mod.Session(id=shared, name="B's table", campaign=B))

    assert [s.name for s in mgr.list_active(A)] == ["A's table"]
    assert [s.name for s in mgr.list_active(B)] == ["B's table"]


def test_an_event_reaches_its_own_campaign_and_no_other(mgr):
    with use_campaign(A):
        a = mgr.create("Table A")
    with use_campaign(B):
        b = mgr.create("Table B")

    sub_a = event_bus.subscribe(a.id, A)
    sub_b = event_bus.subscribe(b.id, B)
    try:
        event_bus.publish(
            StreamEvent(event="entity_moved", session_id=a.id, campaign=A, data={"x": 1})
        )

        # Both halves, deliberately: silence alone would also hold if the bus were dead.
        assert [e.event for e in _drain(sub_a)] == ["entity_moved"]
        assert _drain(sub_b) == []

        event_bus.publish(
            StreamEvent(event="entity_moved", session_id=b.id, campaign=B, data={"x": 2})
        )
        assert [e.event for e in _drain(sub_b)] == ["entity_moved"]
        assert _drain(sub_a) == []
    finally:
        sub_a.close()
        sub_b.close()


def test_an_unscoped_event_reaches_nobody(mgr, caplog):
    """Fail-closed: "no campaign" is not "everyone" — that spelling was the bug."""
    with use_campaign(A):
        a = mgr.create("Table A")
    sub = event_bus.subscribe(a.id, A)
    try:
        with caplog.at_level("WARNING"):
            event_bus.publish(StreamEvent(event="entity_moved", session_id=a.id, data={}))

        assert _drain(sub) == []
        assert any("no campaign" in r.message for r in caplog.records)
    finally:
        sub.close()


def test_an_event_defaults_to_the_scope_it_was_built_in(mgr):
    """Why the 24 fan-out sites needed no rewrite: the safe value is the default one."""
    with use_campaign(A):
        a = mgr.create("Table A")
        assert StreamEvent(event="x", session_id=a.id, data={}).campaign == A
        assert current_campaign() == A

    assert StreamEvent(event="x", session_id=a.id, data={}).campaign == ""


def test_the_stored_keys_name_the_campaign(mgr):
    assert mgr._key(A, "session-1") == f"session:{A}:session-1"
    assert mgr._active_key(A) == f"sessions:active:{A}"
    assert mgr._key(A, "session-1") != mgr._key(B, "session-1")


def test_a_campaign_with_no_sessions_sees_an_empty_list(mgr):
    assert mgr.list_active("tv2-probe-nobody") == []


def test_no_campaign_means_no_sessions(mgr, caplog):
    """`list_active()` with no scope returns nothing rather than everything."""
    with caplog.at_level("WARNING"):
        assert mgr.list_active() == []
    assert any("no campaign" in r.message for r in caplog.records)


def test_the_legacy_namespace_is_readable_only_by_the_default_campaign(mgr, monkeypatch):
    """One release of compatibility for records written before the scoping (§6).

    A session created before this change has no campaign in its key. It belongs to the
    *default* campaign — the playroom, the only surface that existed — and no other
    campaign may see it.
    """
    monkeypatch.setattr(sm_mod, "_default_campaign", lambda: A)
    if mgr._redis is None:
        pytest.skip("the legacy namespace is a Redis compatibility read")

    legacy = "session-legacy-probe"
    mgr._redis.set(
        f"session:{legacy}",
        json.dumps({"id": legacy, "name": "Before the scoping", "active": True}),
    )
    mgr._redis.sadd(mgr._LEGACY_ACTIVE, legacy)

    assert [s.id for s in mgr.list_active(A)] == [legacy]
    assert mgr.list_active(B) == []

    # A record re-saved under the new key is not reported twice.
    with use_campaign(A):
        session = mgr.get(legacy)
        session.name = "Migrated"
        mgr._put(session)
    assert [s.id for s in mgr.list_active(A)] == [legacy]
    assert [s.name for s in mgr.list_active(A)] == ["Migrated"]


# ── The imagen job tracker, and background work ───────────────────────


def test_a_background_task_runs_in_the_campaign_that_queued_it():
    """A generation outlives its request, so its scope travels with it ([[B305]]).

    This is the media lesson made explicit: the orchestrator has no request context,
    and resolving the wrong campaign there writes records and files into the wrong world.
    """
    from transversal.api.rest.imagen import background_scoped

    seen = {}

    @background_scoped
    def _task(*, _scope=None):
        seen["campaign"] = current_campaign()

    with use_campaign(A):
        scope = capture_scope()
    assert current_campaign() == ""

    _task(_scope=scope)
    assert seen["campaign"] == A

    # Without a captured scope it still runs — but names no campaign rather than a
    # guessed one, and the tracker then declines to record it.
    _task()
    assert seen["campaign"] == ""


def test_imagen_jobs_are_per_campaign():
    from transversal.api.rest import imagen

    imagen.active_jobs.clear()
    imagen._job_order.clear()
    try:
        with use_campaign(A):
            imagen._queue_job("entity-1", "imagen")
            assert list(imagen.active_jobs) == [(A, "entity-1")]
            assert imagen._job_entry("entity-1")["status"] == "queued"

        # Another campaign has no job for the same entity id — the ids are shared
        # between a campaign and its ancestor, so the tracker key has to carry it.
        with use_campaign(B):
            assert imagen._job_entry("entity-1") is None
            imagen._queue_job("entity-1", "animate")
            assert imagen._job_entry("entity-1")["type"] == "animate"
            assert imagen._job_with_queue(
                "entity-1", imagen._job_entry("entity-1")
            )["queue_position"] == 1

        with use_campaign(A):
            assert imagen._job_entry("entity-1")["type"] == "imagen"
            imagen._update_job("entity-1", "imagen", "complete")
            assert imagen._job_entry("entity-1") is None

        with use_campaign(B):
            assert imagen._job_entry("entity-1") is not None  # A's finish did not touch it
    finally:
        imagen.active_jobs.clear()
        imagen._job_order.clear()


def test_imagen_jobs_are_not_tracked_without_a_campaign():
    from transversal.api.rest import imagen

    imagen.active_jobs.clear()
    imagen._job_order.clear()
    try:
        imagen._queue_job("entity-1", "imagen")
        assert imagen.active_jobs == {}
        assert imagen._job_entry("entity-1") is None
    finally:
        imagen.active_jobs.clear()
        imagen._job_order.clear()
