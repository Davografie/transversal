"""Tests for automatic SFX firing after roll/contest resolution."""

from types import SimpleNamespace

import transversal.services.roll_orchestrator as roll_orchestrator

from transversal.domain import (
    Condition,
    ConditionType,
    DieRoll,
    DieType,
    Effect,
    EffectTiming,
    OutcomeTier,
    SFX,
    SimplifiedResult,
)
from transversal.services.effects_applier import choose_kind, is_choose_target
from transversal.services.effects_engine import EffectsEngine, GameEvent
from transversal.services.roll_orchestrator import fire_roll_sfx


class Repo:
    """In-memory double covering the surfaces the resolver + orchestrator read."""

    def __init__(self, entities=None):
        self.entities = entities or {}

    def get_entity(self, entity_id):
        return self.entities.get(entity_id)

    def get_projection(self, projection_id):
        return None

    def get_sfx_owner(self, owner_id):
        return None

    def get_effective_traitsettings(self, entity_id, universes):
        return []

    def get_trait(self, trait_id):
        return None

    def get_effective_traitsetsettings(self, entity_id, universes):
        return []

    def get_sfx(self, sfx_id):
        return None


def _simplified(tier=OutcomeTier.SUCCESS, hitches=None, botch=False):
    return SimplifiedResult(
        rolls=[DieRoll(die=DieType.D8, result=7, label="a")],
        highest=7,
        tier=tier,
        effect_die=DieType.D6,
        hitches=hitches or [],
        botch=botch,
        hitches_count=0,
    )


def test_fire_roll_sfx_fires_matching_trigger():
    repo = Repo({"e1": SimpleNamespace(razmerit=10, sfx_ids=["sfx-success"], current_projection=None)})
    engine = EffectsEngine()
    engine.register(SFX(
        id="sfx-success", name="Thrive", trigger="on_success",
        effects=[Effect(timing=EffectTiming.IMMEDIATE, type="modify_roll",
                        action="step_up_die", target="next")],
    ))

    applied = fire_roll_sfx(engine, repo, "e1", "earth", _simplified())
    assert [a.action for a in applied] == ["step_up_die"]


def test_fire_roll_sfx_missing_entity_is_noop():
    repo = Repo()
    engine = EffectsEngine()
    engine.register(SFX(
        id="sfx-success", name="Thrive", trigger="on_success",
        effects=[Effect(timing=EffectTiming.IMMEDIATE, type="modify_roll",
                        action="step_up_die", target="next")],
    ))

    assert fire_roll_sfx(engine, repo, "ghost", "earth", _simplified()) == []


def test_process_event_outcome_returns_pending_for_choose_target():
    engine = EffectsEngine()
    engine.register(SFX(
        id="sfx-choose", name="Choose", trigger="on_success",
        effects=[Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait",
                        action="gain", target="{choose_trait}")],
    ))
    event = GameEvent(type="on_roll", entity_id="e1", universe="earth", roll_result=_simplified())

    outcome = engine.process_event_outcome(event, ["sfx-choose"], 10)
    assert outcome.applied == []
    assert [p.effect.target for p in outcome.pending] == ["{choose_trait}"]


def test_fire_roll_sfx_emits_choose_target_instead_of_applying(monkeypatch):
    repo = Repo({"e1": SimpleNamespace(razmerit=10, sfx_ids=["sfx-choose"], current_projection=None)})
    engine = EffectsEngine()
    engine.register(SFX(
        id="sfx-choose", name="Choose", trigger="on_success",
        effects=[Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait",
                        action="gain", target="{choose_trait}")],
    ))
    emitted = []
    monkeypatch.setattr(
        roll_orchestrator, "_emit_pending_choices",
        lambda entity_id, universe, effects: emitted.extend(effects),
    )

    applied = fire_roll_sfx(engine, repo, "e1", "earth", _simplified())
    assert applied == []
    assert [p.effect.target for p in emitted] == ["{choose_trait}"]


def test_emit_pending_choices_includes_target_filter(monkeypatch):
    from transversal.services.effects_engine import PendingSfxEffect

    eff = Effect(
        timing=EffectTiming.IMMEDIATE, type="location", action="set",
        target="{choose_location}", target_scope="universe:earth",
        target_filter={"starter_location": True},
    )
    pending = [PendingSfxEffect(effect=eff, sfx_name="Starter", sfx_description="")]

    published = []
    monkeypatch.setattr(
        "transversal.services.session_manager.session_manager.list_active",
        lambda: [SimpleNamespace(id="s1")],
    )
    monkeypatch.setattr(
        "transversal.api.sse.bus.event_bus.publish",
        lambda evt: published.append(evt),
    )

    roll_orchestrator._emit_pending_choices("e1", "earth", pending)

    assert len(published) == 1
    choice = published[0].data["choices"][0]
    assert choice["filter"] == {"starter_location": True}
    assert choice["effect"]["target_filter"] == {"starter_location": True}


def test_is_choose_target_and_choose_kind():
    assert is_choose_target("{choose_trait}") is True
    assert is_choose_target("{random:location}") is False
    assert is_choose_target("self") is False
    assert choose_kind("{choose_trait}") == "trait"
    assert choose_kind("self") is None


def test_fire_roll_sfx_gated_by_condition():
    repo = Repo({"e1": SimpleNamespace(razmerit=10, sfx_ids=["sfx-cond"], current_projection=None, current_location="loc-a")})
    engine = EffectsEngine()
    engine.register(SFX(
        id="sfx-cond", name="Cond", trigger="on_success",
        conditions=[Condition(type=ConditionType.AT_LOCATION, target="loc-a")],
        effects=[Effect(timing=EffectTiming.IMMEDIATE, type="modify_roll",
                        action="step_up_die", target="next")],
    ))

    assert len(fire_roll_sfx(engine, repo, "e1", "earth", _simplified())) == 1

    # Wrong location -> condition gates it out.
    repo.entities["e1"].current_location = "loc-b"
    assert fire_roll_sfx(engine, repo, "e1", "earth", _simplified()) == []
