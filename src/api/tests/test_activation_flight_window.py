"""The activation flight window.

A manual activation books an undo for every effect it applies that the registry
can invert. Effects with a duration book a timed **revert** (as ever). Effects
without one book a **hold**: a row that never fires on its own, is *applied* when
the activation is ended early, and is *dissolved* when the activation commits —
a delayed part of it fires, or the dice are rolled. Until then, pressing the rule
again takes it back.
"""

import pytest

from transversal.domain import (
    Effect,
    EffectDuration,
    EffectTiming,
    Entity,
    EntityType,
    SFX,
    ScheduledEvent,
    Timer,
)
from transversal.services import roll_deferral
from transversal.services.scheduled_events import (
    activation_booking,
    advance_scheduled_events,
    commit_holds,
    end_activation,
    schedule_revert,
)


def _entity(entity_id="kael", current_location=None):
    return Entity(
        id=entity_id,
        type=EntityType.CHARACTER,
        name=entity_id,
        current_universe="earth",
        current_location=current_location,
    )


class FakeRepo:
    """In-memory stand-in for the scheduled-events store (see test_scheduled_events)."""

    def __init__(self, entities=(), traitsettings=()):
        self.events = []
        self.entities = {e.id: e for e in entities}
        self.traitsettings = {ts.id: ts for ts in traitsettings}

    def create_scheduled_event(self, event):
        self.events.append(event)
        return event

    def list_all_scheduled_events(self):
        return list(self.events)

    def update_scheduled_event(self, event):
        for i, e in enumerate(self.events):
            if e.id == event.id:
                self.events[i] = event
        return event

    def delete_scheduled_event(self, event_id):
        self.events = [e for e in self.events if e.id != event_id]
        return True

    def get_entity(self, entity_id):
        return self.entities.get(entity_id)

    def get_traitsetting(self, ts_id):
        return self.traitsettings.get(ts_id)

    def get_trait(self, trait_id):
        return None


def _invertible_effect(duration=None):
    """``modify_dice_limit/increase`` — the registry declares its inverse (decrease)."""
    return Effect(
        timing=EffectTiming.IMMEDIATE,
        type="modify_dice_limit",
        action="increase",
        target="",
        result="1",
        duration=duration,
    )


def _spy_applier(monkeypatch, fired):
    monkeypatch.setattr(
        "transversal.services.effects_applier.effect_registry.apply",
        lambda eff, eid, u, ctx: fired.append((eff.type, eff.action, eff.target, eid)),
    )


def _route_applier(monkeypatch, repo, entity):
    """Route dispatched effects through ``apply_effects`` against the test repo.

    The production registry's handlers reach for the singleton EntityManager's
    repo; a unit test's FakeRepo is only reached by going through apply_effects.
    """
    from transversal.services.effects_applier import apply_effects

    monkeypatch.setattr(
        "transversal.services.effects_applier.effect_registry.apply",
        lambda eff, eid, u, ctx: apply_effects(entity, [eff], repo),
    )


@pytest.fixture(autouse=True)
def _clean_armed():
    roll_deferral.reset()
    yield
    roll_deferral.reset()


# ── Booking ──────────────────────────────────────────

def test_a_manual_activation_holds_an_untimed_undo():
    repo = FakeRepo(entities=[_entity()])

    with activation_booking("sfx-x", cancelable=True):
        event = schedule_revert(repo, "entity", "kael", _invertible_effect())

    assert event is not None
    assert event.kind == "hold"
    assert event.timers == []
    assert event.source_sfx_id == "sfx-x"
    assert (event.effect.type, event.effect.action) == ("modify_dice_limit", "decrease")
    assert repo.events == [event]


def test_outside_a_cancelable_activation_nothing_is_held():
    repo = FakeRepo(entities=[_entity()])

    assert schedule_revert(repo, "entity", "kael", _invertible_effect()) is None
    with activation_booking("sfx-x", cancelable=False):
        assert schedule_revert(repo, "entity", "kael", _invertible_effect()) is None

    assert repo.events == []


def test_a_timed_effect_books_a_revert_and_borrows_the_activating_sfx():
    repo = FakeRepo(entities=[_entity()])
    effect = _invertible_effect(
        duration=EffectDuration(timers=[Timer(event="rolls", remaining=1)])
    )

    with activation_booking("sfx-x", cancelable=True):
        event = schedule_revert(repo, "entity", "kael", effect)

    assert event.kind == "revert"
    assert [t.event for t in event.timers] == ["rolls"]
    assert event.source_sfx_id == "sfx-x"


# ── The hold never fires on its own ──────────────────

def test_a_hold_does_not_fire_on_any_boundary(monkeypatch):
    repo = FakeRepo(entities=[_entity()])
    with activation_booking("sfx-x", cancelable=True):
        schedule_revert(repo, "entity", "kael", _invertible_effect())
    fired = []
    _spy_applier(monkeypatch, fired)

    for boundary in ("rolls", "beat", "scene", "session"):
        advance_scheduled_events(repo, boundary, entity_id="kael")

    assert fired == []
    assert len(repo.events) == 1


# ── Committing ───────────────────────────────────────

def test_commit_holds_dissolves_them_and_is_idempotent():
    repo = FakeRepo(entities=[_entity()])
    with activation_booking("sfx-x", cancelable=True):
        schedule_revert(repo, "entity", "kael", _invertible_effect())

    assert commit_holds(repo, entity_id="kael") == 1
    assert repo.events == []
    assert commit_holds(repo, entity_id="kael") == 0


def test_a_delayed_fire_commits_the_whole_activation(monkeypatch):
    """A revert firing at its boundary applies itself and dissolves its siblings."""
    repo = FakeRepo(entities=[_entity()])
    fired = []
    _spy_applier(monkeypatch, fired)
    timed = _invertible_effect(
        duration=EffectDuration(timers=[Timer(event="rolls", remaining=1)])
    )
    with activation_booking("sfx-x", cancelable=True):
        schedule_revert(repo, "entity", "kael", timed)          # the timed undo
        schedule_revert(repo, "entity", "kael", _invertible_effect())  # the held one
    assert {e.kind for e in repo.events} == {"revert", "hold"}

    advance_scheduled_events(repo, "rolls", entity_id="kael")

    assert [f[:2] for f in fired] == [("modify_dice_limit", "decrease")]
    assert repo.events == []  # fired: gone. hold: dissolved, never applied.


# ── Ending (the take-back) ───────────────────────────

def test_ending_applies_the_undos_newest_first(monkeypatch):
    repo = FakeRepo(entities=[_entity()])
    fired = []
    _spy_applier(monkeypatch, fired)
    repo.events = [
        ScheduledEvent(
            id="se-1", target_type="entity", target_id="kael",
            effect=_invertible_effect(),
            kind="hold", source_sfx_id="sfx-x",
            created_at="2026-09-12T10:00:00+00:00",
        ),
        ScheduledEvent(
            id="se-2", target_type="entity", target_id="kael",
            effect=Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait",
                          action="step_down", target="trait-fire"),
            kind="hold", source_sfx_id="sfx-x",
            created_at="2026-09-12T10:00:01+00:00",
        ),
    ]

    summary = end_activation(repo, "kael", "sfx-x")

    assert [f[:2] for f in fired] == [
        ("modify_trait", "step_down"),          # applied last → undone first
        ("modify_dice_limit", "increase"),
    ]
    assert summary["reverted"] == 2
    assert summary["records"] == 2
    assert repo.events == []


def test_ending_drops_deferred_parts_it_never_reached(monkeypatch):
    repo = FakeRepo(entities=[_entity()])
    fired = []
    _spy_applier(monkeypatch, fired)
    repo.events = [
        ScheduledEvent(
            id="se-p", target_type="entity", target_id="kael",
            effect=_invertible_effect(), timers=[Timer(event="scene", remaining=1)],
            kind="pending", source_sfx_id="sfx-x",
            created_at="2026-09-12T10:00:00+00:00",
        ),
    ]

    summary = end_activation(repo, "kael", "sfx-x")

    assert fired == []                     # never reached → never applied
    assert summary["dropped_pending"] == 1
    assert summary["reverted"] == 0
    assert repo.events == []


def test_ending_un_arms_what_was_still_waiting():
    roll_deferral.arm_sfx(
        "kael",
        [Effect(timing=EffectTiming.ON_ROLL, type="modify_dice_limit",
                action="increase", result="1")],
        source_sfx_id="sfx-x",
    )
    repo = FakeRepo(entities=[_entity()])

    summary = end_activation(repo, "kael", "sfx-x")

    assert summary["unarmed"] == 1
    assert roll_deferral.list_armed("kael") == []


def test_a_trait_owned_hold_commits_with_its_owner():
    """A trait-setting row belongs to the entity that owns the trait (Sect Cultivation's shape)."""
    from transversal.domain import TraitSetting

    ts = TraitSetting(id="ts-1", entity_id="kael", trait_id="trait-fire", traitset_id="tset")
    repo = FakeRepo(entities=[_entity()], traitsettings=[ts])
    with activation_booking("sfx-x", cancelable=True):
        event = schedule_revert(repo, "trait_setting", "ts-1", _invertible_effect())
    assert event.kind == "hold"

    assert commit_holds(repo, entity_id="kael") == 1
    assert repo.events == []


def test_ending_a_trait_owned_hold_applies_through_the_owner(monkeypatch):
    from transversal.domain import TraitSetting

    ts = TraitSetting(id="ts-1", entity_id="kael", trait_id="trait-fire", traitset_id="tset")
    repo = FakeRepo(entities=[_entity()], traitsettings=[ts])
    fired = []
    _spy_applier(monkeypatch, fired)
    with activation_booking("sfx-x", cancelable=True):
        schedule_revert(repo, "trait_setting", "ts-1", _invertible_effect())

    summary = end_activation(repo, "kael", "sfx-x")

    assert [f[3] for f in fired] == ["kael"]  # applied against the trait's owner
    assert summary["reverted"] == 1
    assert repo.events == []


def test_ending_leaves_other_activations_alone():
    repo = FakeRepo(entities=[_entity(), _entity("mira")])
    with activation_booking("sfx-x", cancelable=True):
        schedule_revert(repo, "entity", "kael", _invertible_effect())
    with activation_booking("sfx-y", cancelable=True):
        schedule_revert(repo, "entity", "kael", _invertible_effect())
    with activation_booking("sfx-x", cancelable=True):
        schedule_revert(repo, "entity", "mira", _invertible_effect())

    end_activation(repo, "kael", "sfx-x")

    assert [(e.source_sfx_id, e.target_id) for e in repo.events] == [
        ("sfx-y", "kael"),
        ("sfx-x", "mira"),
    ]


# ── The inverses the flight window leans on ─────────

def test_the_razmerit_pair_declares_its_inverse():
    from transversal.services.effects_registry import get_inverse

    assert get_inverse("transfer_razmerit", "earn") == (("transfer_razmerit", "spend"), False)
    assert get_inverse("transfer_razmerit", "spend") == (("transfer_razmerit", "earn"), False)


def test_a_revert_lands_on_the_same_subject():
    from transversal.services.scheduled_events import build_revert

    earned = Effect(timing=EffectTiming.IMMEDIATE, type="transfer_razmerit",
                    action="earn", result="1", entity="mira")
    revert = build_revert(earned)
    assert (revert.type, revert.action, revert.entity, revert.result) == (
        "transfer_razmerit", "spend", "mira", "1")

    # An unresolved name is not copied (it would act on nobody) — the row's owner
    # is the right actor then.
    named = Effect(timing=EffectTiming.IMMEDIATE, type="transfer_razmerit",
                   action="earn", result="1", entity="{buyer}")
    assert build_revert(named).entity == ""


def _pool_of(location_id, owner_id):
    from transversal.services.scene_state import get_scene_store

    return get_scene_store().get_pool(location_id, owner_id)


def test_a_pool_add_books_the_exact_dice_it_added():
    from transversal.services.effects_applier import apply_effects
    from transversal.services.scene_state import get_scene_store

    store = get_scene_store()
    store.clear_all()
    repo = FakeRepo(entities=[_entity()])
    entity = _entity()
    effect = Effect(timing=EffectTiming.IMMEDIATE, type="modify_pool", action="add_dice",
                    target="difficulty:loc-1", context={"dice": ["d8", "d8"]})

    with activation_booking("sfx-x", cancelable=True):
        apply_effects(entity, [effect], repo)

    assert [d["die"] for d in _pool_of("loc-1", "loc-1")] == ["d8", "d8"]
    hold = repo.events[0]
    assert hold.kind == "hold"
    assert hold.effect.action == "remove_added_dice"
    assert hold.effect.context["pool_add"]["positions"] == [0, 1]

    # The undo takes exactly those dice back out.
    apply_effects(entity, [hold.effect], repo)
    assert _pool_of("loc-1", "loc-1") == []
    store.clear_all()


def test_a_trait_rating_add_books_a_removable_undo():
    """The Hinder shape: a trait's rating dice go into the pool, and a take-back removes them."""
    from transversal.domain import DieType, TraitSetting
    from transversal.services.effects_applier import apply_effects
    from transversal.services.scene_state import get_scene_store

    store = get_scene_store()
    store.clear_all()
    ts = TraitSetting(id="ts-1", entity_id="kael", trait_id="trait-fire",
                      traitset_id="tset", dice=[DieType.D4])
    repo = FakeRepo(entities=[_entity(current_location="loc-1")], traitsettings=[ts])
    entity = _entity(current_location="loc-1")
    effect = Effect(timing=EffectTiming.IMMEDIATE, type="modify_pool", action="add_trait_rating",
                    target="pool:kael", refs={"trait": {"value": "ts-1"},
                                              "pool": {"value": "pool:kael"}})

    with activation_booking("sfx-x", cancelable=True):
        apply_effects(entity, [effect], repo)

    pool = _pool_of("loc-1", "kael")
    assert [d["die"] for d in pool] == ["d4"]
    hold = repo.events[0]
    assert hold.kind == "hold"
    assert hold.effect.context["pool_add"] == {
        "location": "loc-1", "owner": "kael", "positions": [0], "dice": ["d4"],
    }

    apply_effects(entity, [hold.effect], repo)
    assert _pool_of("loc-1", "kael") == []
    store.clear_all()


def test_a_pool_add_with_a_duration_books_a_timed_revert():
    from transversal.services.effects_applier import apply_effects
    from transversal.services.scene_state import get_scene_store

    store = get_scene_store()
    store.clear_all()
    repo = FakeRepo(entities=[_entity()])
    entity = _entity()
    effect = Effect(timing=EffectTiming.IMMEDIATE, type="modify_pool", action="add_dice",
                    target="difficulty:loc-1", context={"dice": ["d6"]},
                    duration=EffectDuration(timers=[Timer(event="scene", remaining=1)]))

    with activation_booking("sfx-x", cancelable=True):
        apply_effects(entity, [effect], repo)

    row = repo.events[0]
    assert row.kind == "revert"
    assert [t.event for t in row.timers] == ["scene"]
    assert row.effect.action == "remove_added_dice"
    store.clear_all()


def test_ending_a_pool_add_takes_the_dice_back_out(monkeypatch):
    """End to end: apply, end the activation, the dice are gone."""
    from transversal.services.effects_applier import apply_effects
    from transversal.services.scene_state import get_scene_store

    store = get_scene_store()
    store.clear_all()
    repo = FakeRepo(entities=[_entity(current_location="loc-1")])
    entity = _entity(current_location="loc-1")
    _route_applier(monkeypatch, repo, entity)
    effect = Effect(timing=EffectTiming.IMMEDIATE, type="modify_pool", action="add_dice",
                    target="pool:kael", context={"dice": ["d4"]})

    with activation_booking("sfx-x", cancelable=True):
        apply_effects(entity, [effect], repo)
    assert [d["die"] for d in _pool_of("loc-1", "kael")] == ["d4"]

    summary = end_activation(repo, "kael", "sfx-x")

    assert summary["reverted"] == 1
    assert _pool_of("loc-1", "kael") == []
    assert repo.events == []
    store.clear_all()


# ── The plumbing that carries the booking ────────────

def test_registry_apply_scopes_bookings_to_the_activation():
    from transversal.services import scheduled_events as se
    from transversal.services.effects_applier import EffectRegistry
    from transversal.services.effects_applier.datatypes import ACTIVATION_CONTEXT_KEY

    seen = []
    registry = EffectRegistry()
    registry.register("modify_dice_limit", "increase",
                      lambda a, eid, u, ctx: seen.append(se._booking()))

    registry.apply(_invertible_effect(), "kael", "earth",
                   {ACTIVATION_CONTEXT_KEY: {"sfx_id": "sfx-x", "cancelable": True}})
    registry.apply(_invertible_effect(), "kael", "earth", {})

    assert seen == [{"sfx_id": "sfx-x", "cancelable": True}, None]


def test_the_engine_marks_a_manual_activation_cancelable(monkeypatch):
    from transversal.services import effects_applier as applier_mod
    from transversal.services.effects_applier.datatypes import ACTIVATION_CONTEXT_KEY
    from transversal.services.effects_engine import EffectsEngine, GameEvent

    captured = []

    class _Reg:
        def apply(self, action, entity_id, universe, context):
            captured.append(context.get(ACTIVATION_CONTEXT_KEY))

    monkeypatch.setattr(applier_mod, "effect_registry", _Reg())
    engine = EffectsEngine()
    engine.register(SFX(id="sfx-x", name="X", trigger="manual",
                        effects=[_invertible_effect()]))
    engine.register(SFX(id="sfx-auto", name="Auto", trigger="on_roll",
                        effects=[_invertible_effect()]))

    engine.process_event_outcome(
        GameEvent(type="manual", entity_id="kael", universe="earth"), ["sfx-x"], 0)
    assert captured == [{"sfx_id": "sfx-x", "cancelable": True}]

    captured.clear()
    engine.process_event_outcome(
        GameEvent(type="on_roll", entity_id="kael", universe="earth"), ["sfx-auto"], 0)
    assert captured == [{"sfx_id": "sfx-auto", "cancelable": False}]
