"""Tests for automatic SFX firing after roll/contest resolution."""

from types import SimpleNamespace

import transversal.services.roll_orchestrator as roll_orchestrator

from transversal.domain import (
    Condition,
    ConditionType,
    ContestResult,
    ContestWinner,
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
from transversal.services.roll_orchestrator import fire_contest_sfx_auto, fire_roll_sfx


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


def _simplified(tier=OutcomeTier.SUCCESS, hitches=None, botch=False):
    return SimplifiedResult(
        rolls=[DieRoll(die=DieType.D8, result=7, label="a")],
        highest=7,
        tier=tier,
        effect_die=DieType.D6,
        hitches=hitches or [],
        botch=botch,
        razmerit_earned=0,
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


def test_fire_contest_sfx_auto_fires_per_side():
    repo = Repo({
        "challenger": SimpleNamespace(razmerit=10, sfx_ids=["sfx-win"], current_projection=None),
        "defendant": SimpleNamespace(razmerit=5, sfx_ids=["sfx-loss"], current_projection=None),
    })
    engine = EffectsEngine()
    engine.register(SFX(
        id="sfx-win", name="Victory", trigger="on_contest_win",
        effects=[Effect(timing=EffectTiming.IMMEDIATE, type="modify_roll",
                        action="step_up_die", target="next")],
    ))
    engine.register(SFX(
        id="sfx-loss", name="Sore", trigger="on_contest_loss",
        effects=[Effect(timing=EffectTiming.IMMEDIATE, type="modify_roll",
                        action="step_down_die", target="self")],
    ))

    result = ContestResult(
        pipeline="simplified",
        winner=ContestWinner.PLAYER,
        player_result=_simplified(),
        opponent_result=_simplified(tier=OutcomeTier.MARGINAL),
    )

    applied = fire_contest_sfx_auto(engine, repo, result, "challenger", "defendant", "earth")
    assert sorted(a.action for a in applied) == ["step_down_die", "step_up_die"]


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
