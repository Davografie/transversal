"""B305 — the in-memory live state is campaign-scoped, and empty without a campaign.

The session store and the SSE bus are covered by ``test_campaign_isolation``. This
covers the three process-global registries that stayed behind: presence, the
active-main/current-body maps, and the armed-SFX store. Each one used to be keyed
by player or entity alone, so one campaign's state was readable from another — and
because ``_global_armed`` deliberately means *every entity*, "no campaign" read as
"everyone" was the exact bug being fixed.

All three are plain in-memory dicts, so these tests touch no Redis and no ArangoDB
and need no cleanup beyond clearing the memory they wrote.
"""

import pytest

from transversal.domain import Effect, EffectDuration, EffectTiming, Timer, TimerCombine
from transversal.services import player_manager as pm
from transversal.services import presence, roll_deferral
from transversal.services.campaign_scope import use_campaign

A = "tv2-probe-a"
B = "tv2-probe-b"


@pytest.fixture(autouse=True)
def _clean():
    """The stores are module-level memory; clear them around every test."""
    _clear()
    yield
    _clear()


def _clear():
    roll_deferral.reset()  # a whole-store test reset, every campaign
    presence._online.clear()
    presence._last_seen.clear()
    pm._active_main.clear()
    pm._current_body.clear()


def _effect():
    return Effect(timing=EffectTiming.ON_ROLL, type="modify_trait", action="step_up", target="self")


# ── presence ─────────────────────────────────────────


def test_presence_belongs_to_the_campaign_that_marked_it():
    with use_campaign(A):
        assert presence.mark_online("p1") is True
        assert presence.is_online("p1") is True
        assert presence.list_online_players() == ["p1"]

    with use_campaign(B):
        assert presence.is_online("p1") is False
        assert presence.list_online_players() == []

    # And the entry is still A's, not consumed by B's read.
    with use_campaign(A):
        assert presence.list_online_players() == ["p1"]


def test_presence_with_no_campaign_is_empty_not_everyone():
    with use_campaign(A):
        presence.mark_online("p1")

    assert presence.is_online("p1") is False
    assert presence.list_online_players() == []
    # A write out of scope records nothing to leak into a later read.
    assert presence.mark_online("p2") is False
    with use_campaign(A):
        assert presence.list_online_players() == ["p1"]


# ── active main / current body ───────────────────────


def test_an_active_main_is_invisible_in_another_campaign():
    with use_campaign(A):
        pm._set_active_main("p1", "main-1")
        assert pm.is_main_active("p1", "main-1") is True
        assert pm.list_active_mains() == {"p1": "main-1"}

    with use_campaign(B):
        assert pm.is_main_active("p1", "main-1") is False
        assert pm.list_active_mains() == {}

    assert pm.list_active_mains() == {}  # no scope
    assert pm.is_main_active("p1", "main-1") is False


def test_the_current_body_follows_the_campaign(monkeypatch):
    from transversal.services import state_events

    monkeypatch.setattr(state_events, "fire_state_sfx", lambda *a, **k: None)
    monkeypatch.setattr(state_events, "broadcast_body_changed", lambda *a, **k: None)

    manager = pm.PlayerManager.__new__(pm.PlayerManager)
    manager._repo = None

    with use_campaign(A):
        manager.record_control("p1", "body-a", stamp=False)
        assert pm.list_current_bodies() == {"p1": "body-a"}

    with use_campaign(B):
        assert pm.list_current_bodies() == {}
        manager.record_control("p1", "body-b", stamp=False)
        assert pm.list_current_bodies() == {"p1": "body-b"}

    # Out of scope: neither tracked nor cleared, so B's body survives.
    manager.record_control("p1", "body-unscoped", stamp=False)
    manager.clear_control("p1")
    with use_campaign(B):
        assert pm.list_current_bodies() == {"p1": "body-b"}

    with use_campaign(A):
        manager.clear_control("p1")
        assert pm.list_current_bodies() == {}


def test_the_active_main_helpers_with_no_campaign_answer_nothing():
    with use_campaign(A):
        pm._set_active_main("p1", "main-1")

    pm._set_active_main("p1", "main-2")  # no scope: not recorded
    assert pm.list_active_mains() == {}
    assert pm.is_main_active("p1", "main-2") is False

    with use_campaign(A):
        assert pm.list_active_mains() == {"p1": "main-1"}


# ── armed SFX ────────────────────────────────────────


def test_an_armed_sfx_is_invisible_in_another_campaign():
    with use_campaign(A):
        roll_deferral.arm_sfx("e1", [_effect()], source_sfx_id="sfx-a")
        assert roll_deferral.list_armed_sfx_ids("e1") == ["sfx-a"]
        assert roll_deferral.armed_entry_for("e1", "sfx-a") is not None

    with use_campaign(B):
        assert roll_deferral.list_armed_sfx_ids("e1") == []
        assert roll_deferral.list_armed("e1") == []
        assert roll_deferral.armed_entry_for("e1", "sfx-a") is None
        assert roll_deferral.fire_armed("e1", "on_roll", "earth") == []

    with use_campaign(A):
        assert roll_deferral.list_armed_sfx_ids("e1") == ["sfx-a"]


def test_a_global_passive_covers_every_entity_in_one_campaign_only():
    """The sharp one: ``_global_armed`` means "every entity", which must stop at the
    campaign boundary — an entity that armed nothing still sees it in its own
    campaign, and no entity sees it in another."""
    with use_campaign(A):
        roll_deferral.arm_passive([_effect()], source_sfx_id="sfx-passive")
        assert roll_deferral.list_global_armed_sfx_ids() == ["sfx-passive"]
        assert roll_deferral.armed_entry_for("someone-else", "sfx-passive") is not None

    with use_campaign(B):
        assert roll_deferral.list_global_armed_sfx_ids() == []
        assert roll_deferral.list_global_armed() == []
        assert roll_deferral.armed_entry_for("someone-else", "sfx-passive") is None


def test_no_campaign_means_the_armed_store_is_empty_not_pooled():
    with use_campaign(A):
        roll_deferral.arm_sfx("e1", [_effect()], source_sfx_id="sfx-a")
        roll_deferral.arm_passive([_effect()], source_sfx_id="sfx-global")

    roll_deferral.arm_sfx("e-empty", [_effect()], source_sfx_id="sfx-unscoped")
    assert roll_deferral.list_armed("e-empty") == []
    assert roll_deferral.list_armed_sfx_ids("e1") == []
    assert roll_deferral.list_global_armed() == []
    assert roll_deferral.list_global_armed_sfx_ids() == []
    assert roll_deferral.armed_entry_for("e1", "sfx-a") is None
    assert roll_deferral.fire_armed("e1", "on_roll", "earth") == []
    assert roll_deferral.drop_armed("e1", "sfx-a") == 0

    # The unscoped attempt wrote nothing under a "" campaign.
    with use_campaign(A):
        assert roll_deferral.list_armed_sfx_ids("e-empty") == []


def test_the_unarm_helpers_stay_inside_their_campaign():
    with use_campaign(A):
        roll_deferral.arm_sfx("e1", [_effect()], source_sfx_id="sfx-a")

    with use_campaign(B):
        roll_deferral.clear_armed("e1")
        roll_deferral.expire_armed("e1", "beat")

    with use_campaign(A):
        assert roll_deferral.list_armed_sfx_ids("e1") == ["sfx-a"]
        roll_deferral.clear_armed("e1")
        assert roll_deferral.list_armed_sfx_ids("e1") == []


def test_a_global_boundary_only_touches_its_own_campaign():
    beat = EffectDuration(
        timers=[Timer(event="beat", remaining=1)], combine=TimerCombine.FIRST_TO_FIRE
    )
    with use_campaign(A):
        roll_deferral.arm_passive([_effect()], source_sfx_id="sfx-a", duration=beat)

    with use_campaign(B):
        roll_deferral.expire_global("beat")
        roll_deferral.clear_global_armed()

    with use_campaign(A):
        assert roll_deferral.list_global_armed_sfx_ids() == ["sfx-a"]
