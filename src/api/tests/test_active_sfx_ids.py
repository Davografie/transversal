"""The active-timer surfaces: *what* is running, and *what it came from*.

``inFlightSfxIds`` is narrowed to the manual take-back window (its caller is the
chip that offers to end the rule). ``activeSfxIds`` is the *display* union, so an
**automatic** rule whose duration timer is still running appears here even though
it is not "in flight" — that gap is why the rail stayed empty while the sheet
showed a bare "1 rolls" and nothing said where it came from.

A running timer must also name the rule that booked it: the sheet's trait detail
and the Active rail both show a countdown, and a countdown with no origin is a
mystery.
"""

from types import SimpleNamespace

import pytest

from transversal.api.graphql.resolvers.queries_sfx import QueriesSfx
from transversal.domain import Effect, EffectTiming, ScheduledEvent, Timer
from transversal.services import roll_deferral
from transversal.services.scheduled_events import in_flight_sfx_ids


class _Repo:
    """Only what ``in_flight_sfx_ids`` reads for an entity-targeted row."""

    def __init__(self, events=()):
        self.events = list(events)

    def list_all_scheduled_events(self):
        return list(self.events)

    def get_entity(self, entity_id):
        return None

    def get_traitsetting(self, ts_id):
        return None


class _Engine:
    def __init__(self, ids=()):
        self._ids = set(ids)

    def get(self, sfx_id):
        return object() if sfx_id in self._ids else None


def _info(repo):
    return SimpleNamespace(context={"entity_manager": SimpleNamespace(repo=repo)})


def _duration_row(sfx_id, entity_id="pc-rail"):
    return ScheduledEvent(
        id=f"se-{sfx_id}", target_type="entity", target_id=entity_id,
        source_sfx_id=sfx_id, kind="revert",
        timers=[Timer(event="rolls", remaining=1)],
        effect=Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait", action="step_up"),
    )


@pytest.fixture(autouse=True)
def _clean_armed():
    roll_deferral.reset()
    yield
    roll_deferral.reset()


def test_a_running_duration_shows_as_active(monkeypatch):
    """The author's case: an automatic `rolls: 1` effect — the sheet's "1 rolls"."""
    from transversal import main

    monkeypatch.setattr(main, "_get_engine", lambda: _Engine({"sfx-qi"}))
    repo = _Repo([_duration_row("sfx-qi")])

    assert QueriesSfx().active_sfx_ids(_info(repo), "pc-rail") == ["sfx-qi"]


def test_an_armed_rule_shows_as_active(monkeypatch):
    from transversal import main

    monkeypatch.setattr(main, "_get_engine", lambda: _Engine({"sfx-arm"}))
    roll_deferral.arm_sfx(
        "pc-rail",
        [Effect(timing=EffectTiming.ON_SET, type="transfer_razmerit", action="earn", result="1")],
        source_sfx_id="sfx-arm",
    )

    assert QueriesSfx().active_sfx_ids(_info(_Repo()), "pc-rail") == ["sfx-arm"]


def test_a_row_from_a_deleted_rule_is_dropped(monkeypatch):
    """The engine is the registry of record: no card for a source that is gone."""
    from transversal import main

    monkeypatch.setattr(main, "_get_engine", lambda: _Engine())
    repo = _Repo([_duration_row("sfx-gone")])

    assert QueriesSfx().active_sfx_ids(_info(repo), "pc-rail") == []


def test_a_globally_armed_passive_shows_as_active(monkeypatch):
    """A session passive covers every entity, so it belongs on every rail — even
    though no entity armed it and it is nobody's take-back to cancel (One
    Trick)."""
    from transversal import main

    monkeypatch.setattr(main, "_get_engine", lambda: _Engine({"sfx-passive"}))
    roll_deferral.arm_passive(
        [Effect(timing=EffectTiming.ON_ROLL, type="modify_trait", action="step_down")],
        source_sfx_id="sfx-passive",
    )

    assert QueriesSfx().active_sfx_ids(_info(_Repo()), "pc-rail") == ["sfx-passive"]
    # ...but it is not in the manual take-back window.
    assert in_flight_sfx_ids(_Repo(), "pc-rail") == []


def test_a_timer_row_names_the_rule_that_booked_it():
    """`sourceSfxName` is what lets the trait detail say *One Trick*, not just *1 beat*."""
    from transversal.api.graphql.resolvers.converters import _scheduled_event_to_gql
    from transversal.domain import Effect

    class _NamedRepo:
        def get_sfx(self, sfx_id):
            return SimpleNamespace(name="One Trick") if sfx_id == "sfx-one-trick" else None

    event = ScheduledEvent(
        id="se-beat", target_type="trait_setting", target_id="pc-rail:martial",
        effect=Effect(type="modify_trait", action="step_up", target="pc-rail:martial"),
        timers=[Timer(event="beat", remaining=1)], source_sfx_id="sfx-one-trick",
    )

    assert _scheduled_event_to_gql(event, _NamedRepo()).source_sfx_name == "One Trick"
    # A rule that no longer exists (or a repo that cannot resolve names) degrades
    # to no origin rather than an error.
    assert _scheduled_event_to_gql(event, None).source_sfx_name is None
