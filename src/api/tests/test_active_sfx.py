"""The Active rail's read: *what* is running, *where it came from*, and *what it bound*.

``inFlightSfxIds`` is narrowed to the manual take-back window (its caller is the
chip that offers to end the rule). ``activeSfx`` is the *display* union, so an
**automatic** rule whose duration timer is still running appears here even though
it is not "in flight" — that gap is why the rail stayed empty while the sheet
showed a bare "1 rolls" and nothing said where it came from.

A running rule must also say where it came from and which names its targeting
paths bound: a countdown with no origin is a mystery, and ``{beast}`` is only
useful next to what it points at.
"""

from types import SimpleNamespace

import pytest

from transversal.api.graphql.resolvers.queries_sfx import QueriesSfx
from transversal.domain import Effect, EffectTiming, ScheduledEvent, Timer
from transversal.services import roll_deferral
from transversal.services.scheduled_events import in_flight_sfx_ids
from transversal.services.target_resolver import Binding


class _Repo:
    """Only what the active read touches: rows, one trait instance, one trait."""

    def __init__(self, events=(), traitsettings=None, traits=None):
        self.events = list(events)
        self._traitsettings = traitsettings or {}
        self._traits = traits or {}

    def list_all_scheduled_events(self):
        return list(self.events)

    def get_entity(self, entity_id):
        return None

    def get_traitsetting(self, ts_id):
        return self._traitsettings.get(ts_id)

    def get_trait(self, trait_id):
        return self._traits.get(trait_id)


class _Engine:
    """The registry of record: id → name (absent = the rule is gone)."""

    def __init__(self, names=None):
        self._names = dict(names or {})

    def get(self, sfx_id):
        name = self._names.get(sfx_id)
        return SimpleNamespace(id=sfx_id, name=name) if name else None


def _info(repo):
    return SimpleNamespace(context={"entity_manager": SimpleNamespace(repo=repo)})


def _duration_row(sfx_id, entity_id="pc-rail", source=None):
    context = {"activation_source": source} if source else {}
    return ScheduledEvent(
        id=f"se-{sfx_id}", target_type="entity", target_id=entity_id,
        source_sfx_id=sfx_id, kind="revert",
        timers=[Timer(event="rolls", remaining=1)],
        effect=Effect(
            timing=EffectTiming.IMMEDIATE, type="modify_trait", action="step_up",
            context=context,
        ),
    )


@pytest.fixture(autouse=True)
def _clean_armed():
    roll_deferral.reset()
    yield
    roll_deferral.reset()


def test_a_running_duration_shows_as_active_with_its_source(monkeypatch):
    """The author's case: an automatic `rolls: 1` effect, and the instance it is on."""
    from transversal import main

    monkeypatch.setattr(main, "_get_engine", lambda: _Engine({"sfx-qi": "Cultivation Stage"}))
    repo = _Repo(
        [_duration_row("sfx-qi", source="pc-rail:spirit")],
        traitsettings={"pc-rail:spirit": SimpleNamespace(statement="", trait_id="trait-spirit")},
        traits={"trait-spirit": SimpleNamespace(name="Spiritual Power")},
    )

    entries = QueriesSfx().active_sfx(_info(repo), "pc-rail")

    assert [(e.sfx_id, e.name, e.source_name, e.bindings) for e in entries] == [
        ("sfx-qi", "Cultivation Stage", "Spiritual Power", []),
    ]


def test_an_armed_rule_shows_its_source_and_bound_names(monkeypatch):
    """The live half: the activation's own source and the names it bound.

    Bindings are not persisted on the rows, so an armed entry is the only place
    they exist — which is exactly why the rail reads this query rather than the
    timer rows alone.
    """
    from transversal import main

    monkeypatch.setattr(main, "_get_engine", lambda: _Engine({"sfx-beast": "Summon Beast"}))
    repo = _Repo(
        traitsettings={
            "pc-rail:martial": SimpleNamespace(statement="Crimson Scar", trait_id="trait-martial"),
            "pc-rail:beast": SimpleNamespace(statement="", trait_id="trait-beast"),
        },
        traits={"trait-beast": SimpleNamespace(name="Summoned Beast")},
    )
    roll_deferral.arm_sfx(
        "pc-rail",
        [Effect(timing=EffectTiming.ON_ROLL, type="modify_trait", action="step_up")],
        source_sfx_id="sfx-beast",
        source_kind="trait_setting",
        source_id="pc-rail:martial",
        bindings={
            "beast": Binding(value="pc-rail:beast", element="traitsetting", cardinality="one"),
            "rolled_dice": Binding(values=["die:1", "die:2"], element="die", cardinality="many"),
        },
    )

    entry = QueriesSfx().active_sfx(_info(repo), "pc-rail")[0]

    assert entry.source_kind == "trait_setting"
    assert entry.source_name == "Crimson Scar"  # a statement names the instance
    assert [(b.name, b.summary) for b in entry.bindings] == [
        ("beast", "Summoned Beast"),   # no statement → its registry trait
        ("rolled_dice", "2 dice"),     # many/dice reads as a count, not a wall of ids
    ]


def test_a_globally_armed_passive_shows_as_active(monkeypatch):
    """A session passive covers every entity, so it belongs on every rail — even
    though no entity armed it, it has no instance source, and it is nobody's
    take-back to cancel (One Trick)."""
    from transversal import main

    monkeypatch.setattr(main, "_get_engine", lambda: _Engine({"sfx-passive": "One Trick"}))
    roll_deferral.arm_passive(
        [Effect(timing=EffectTiming.ON_ROLL, type="modify_trait", action="step_down")],
        source_sfx_id="sfx-passive",
    )

    entries = QueriesSfx().active_sfx(_info(_Repo()), "pc-rail")

    assert [(e.sfx_id, e.source_name, e.bindings) for e in entries] == [
        ("sfx-passive", None, []),
    ]
    # ...but it is not in the manual take-back window.
    assert in_flight_sfx_ids(_Repo(), "pc-rail") == []


def test_a_row_from_a_deleted_rule_is_dropped(monkeypatch):
    """The engine is the registry of record: no card for a source that is gone."""
    from transversal import main

    monkeypatch.setattr(main, "_get_engine", lambda: _Engine())
    repo = _Repo([_duration_row("sfx-gone")])

    assert QueriesSfx().active_sfx(_info(repo), "pc-rail") == []


def test_a_timer_row_names_the_rule_that_booked_it():
    """`sourceSfxName` is what lets the trait detail say *One Trick*, not just *1 beat*."""
    from transversal.api.graphql.resolvers.converters import _scheduled_event_to_gql

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
