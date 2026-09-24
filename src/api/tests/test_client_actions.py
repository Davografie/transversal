"""Client-directed effects ([[B132]]): open a sheet, show a toast.

These are the only effects that change nothing in the world — they tell a *device*
to do something. So what matters is the wire contract: who is told, what about, and
that a rule and a client cannot drift on the event's name or payload.
"""

from types import SimpleNamespace as NS

import pytest

from transversal.domain import Effect, EffectTiming
from transversal.services.client_actions import (
    CLIENT_ACTION_EVENT,
    client_action_payload,
    publish_client_action,
)
from transversal.services.effects_applier import apply_effects
from transversal.services.effects_registry import EFFECT_ACTION_REGISTRY


def _effect(action, **kw):
    return Effect(timing=EffectTiming.IMMEDIATE, type="client", action=action, **kw)


def _entity(**over):
    kw = dict(id="char-1", name="Kael", type="character", current_universe="earth")
    kw.update(over)
    return NS(**kw)


class Repo:
    def get_entity(self, eid):
        return _entity(id=eid, name=eid)


# ── The declaration ────────────────────────────

def test_the_client_family_declares_both_actions():
    metas = {m.action_id: m for m in EFFECT_ACTION_REGISTRY if m.effect_type == "client"}
    assert set(metas) == {"open_sheet", "show_toast"}
    for m in metas.values():
        # Nothing in the world changes, so there is nothing to revert.
        assert m.supports_duration is False
        assert m.inverse is None
        assert m.category == "either"
    assert metas["show_toast"].group == "Client"


def test_both_client_actions_are_on_the_engine_registry():
    """A rule fires through ``effect_registry`` — a handler only in
    ``_MUTATION_HANDLERS`` would never run on a real trigger."""
    from types import SimpleNamespace
    import transversal.services.effects_applier as applier
    from transversal.services.effects_applier import EffectRegistry

    original = applier.effect_registry
    applier.effect_registry = EffectRegistry()
    try:
        raz = SimpleNamespace(spend=lambda *a, **k: None, earn=lambda *a, **k: None,
                              transfer=lambda *a, **k: None)
        em = SimpleNamespace(repo=None, create=lambda *a, **k: None)
        applier._register_core_handlers(em, raz)
        handlers = applier.effect_registry._handlers
        assert ("client", "open_sheet") in handlers
        assert ("client", "toast") in handlers
    finally:
        applier.effect_registry = original


# ── The wire contract ──────────────────────────

def test_an_absent_value_is_omitted_rather_than_null():
    """A client reading `message` only for a toast should not have to tell "no
    message" from "an empty one"."""
    assert client_action_payload("open_sheet", "char-1") == {
        "action": "open_sheet", "recipient_id": "char-1"}
    full = client_action_payload("toast", "char-1", target_id="char-2",
                                 message="hi", sticky=True, tap="open_sheet",
                                 sfx_id="sfx-x")
    assert full == {"action": "toast", "recipient_id": "char-1", "target_id": "char-2",
                    "message": "hi", "sticky": True, "tap": "open_sheet", "sfx_id": "sfx-x"}


def test_publishing_reaches_every_active_session(monkeypatch):
    from transversal.api.sse import bus as bus_mod

    published = []
    monkeypatch.setattr(bus_mod.event_bus, "publish",
                        lambda evt: published.append(evt))
    monkeypatch.setattr(bus_mod, "event_bus", bus_mod.event_bus)

    from transversal.services import session_manager as sm
    monkeypatch.setattr(sm.session_manager, "list_active",
                        lambda: [NS(id="s1"), NS(id="s2")])

    payload = client_action_payload("toast", "char-1", message="hi", sticky=True)
    publish_client_action(payload)

    assert [e.session_id for e in published] == ["s1", "s2"]
    assert all(e.event == CLIENT_ACTION_EVENT for e in published)
    assert all(e.data == payload for e in published)


# ── The handlers ───────────────────────────────

def test_open_sheet_tells_the_recipient_which_sheet(monkeypatch):
    seen = []
    import transversal.services.client_actions as ca
    monkeypatch.setattr(ca, "publish_client_action", lambda payload: seen.append(payload))

    result = apply_effects(_entity(), [_effect("open_sheet", entity="char-2", target="char-7")], Repo())
    assert seen == [{"action": "open_sheet", "recipient_id": "char-2", "target_id": "char-7"}]
    assert "char-7" in result.applied[0].summary


def test_open_sheet_with_no_target_opens_the_recipients_own(monkeypatch):
    seen = []
    import transversal.services.client_actions as ca
    monkeypatch.setattr(ca, "publish_client_action", lambda payload: seen.append(payload))
    apply_effects(_entity(), [_effect("open_sheet", entity="char-2")], Repo())
    assert seen[0]["recipient_id"] == "char-2"
    assert seen[0]["target_id"] == "char-2"


def test_a_toast_carries_its_text_and_stays_until_dismissed(monkeypatch):
    seen = []
    import transversal.services.client_actions as ca
    monkeypatch.setattr(ca, "publish_client_action", lambda payload: seen.append(payload))
    effect = _effect("toast", entity="char-2", result="The court convenes")
    apply_effects(_entity(), [effect], Repo())
    assert seen[0]["action"] == "toast" and seen[0]["recipient_id"] == "char-2"
    # Sticky is the action's nature, so it defaults on.
    assert seen[0]["message"] == "The court convenes" and seen[0]["sticky"] is True
    assert "tap" not in seen[0]


def test_a_toast_with_no_message_says_so_instead_of_showing_a_blank(monkeypatch):
    seen = []
    import transversal.services.client_actions as ca
    monkeypatch.setattr(ca, "publish_client_action", lambda payload: seen.append(payload))
    result = apply_effects(_entity(), [_effect("toast", entity="char-2", result="  ")], Repo())
    assert seen == []
    assert "no message to show" in result.applied[0].summary


def test_a_toast_only_carries_a_tap_target_when_tapping_opens_something(monkeypatch):
    seen = []
    import transversal.services.client_actions as ca
    monkeypatch.setattr(ca, "publish_client_action", lambda payload: seen.append(payload))
    plain = _effect("toast", entity="char-2", result="hi", target="char-7",
                    context={"tap": "none"})
    apply_effects(_entity(), [plain], Repo())
    assert "target_id" not in seen[0]

    tappable = _effect("toast", entity="char-2", result="hi", target="char-7",
                       context={"tap": "open_sheet", "sticky": False})
    apply_effects(_entity(), [tappable], Repo())
    assert seen[1]["tap"] == "open_sheet"
    assert seen[1]["target_id"] == "char-7"
    # An author who turned sticky off gets the plain toast the app already has.
    assert "sticky" not in seen[1]
