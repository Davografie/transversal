"""Tests for automated SFX — trigger matching.

Covers:
  - New trigger types: on_location_change, on_trait_change,
    on_contest_loss, on_contest_win, on_success, on_failure
  - SFX push: ContestTracker.push_contest()
"""

import pytest

from transversal.domain import (
    DieRoll,
    DieType,
    Effect,
    EffectTiming,
    OutcomeTier,
    SFX,
    SimplifiedResult,
)
from transversal.services.effects_engine import (
    EffectsEngine,
    GameEvent,
)


# ── New Trigger Types ──────────────────────────────────

class TestNewTriggers:
    """Verify the new trigger types in _trigger_matches()."""

    def test_on_location_change_matches(self):
        engine = EffectsEngine()
        sfx = SFX(id="sfx-anchor", name="Dimensional Anchor",
                  trigger="on_location_change")
        event = GameEvent(type="location_changed", entity_id="e1", universe="earth")
        assert engine._trigger_matches(sfx, event)

    def test_on_location_change_no_match_on_other_event(self):
        engine = EffectsEngine()
        sfx = SFX(id="sfx-anchor", name="Dimensional Anchor",
                  trigger="on_location_change")
        event = GameEvent(type="on_roll", entity_id="e1", universe="earth")
        assert not engine._trigger_matches(sfx, event)

    def test_on_trait_change_matches(self):
        engine = EffectsEngine()
        sfx = SFX(id="sfx-trait", name="Trait Watcher",
                  trigger="on_trait_change")
        event = GameEvent(type="trait_updated", entity_id="e1", universe="earth")
        assert engine._trigger_matches(sfx, event)

    def test_on_trait_change_no_match_on_other(self):
        engine = EffectsEngine()
        sfx = SFX(id="sfx-trait", name="Trait Watcher",
                  trigger="on_trait_change")
        event = GameEvent(type="on_roll", entity_id="e1", universe="earth")
        assert not engine._trigger_matches(sfx, event)

    def test_on_character_create_matches(self):
        engine = EffectsEngine()
        sfx = SFX(id="sfx-spawn", name="Scatter",
                  trigger="on_character_create")
        event = GameEvent(type="character_created", entity_id="e1", universe="earth")
        assert engine._trigger_matches(sfx, event)

    def test_on_character_create_no_match_on_other(self):
        engine = EffectsEngine()
        sfx = SFX(id="sfx-spawn", name="Scatter",
                  trigger="on_character_create")
        event = GameEvent(type="location_changed", entity_id="e1", universe="earth")
        assert not engine._trigger_matches(sfx, event)

    def test_on_projection_create_matches(self):
        engine = EffectsEngine()
        sfx = SFX(id="sfx-proj", name="Projection Starter",
                  trigger="on_projection_create")
        event = GameEvent(type="projection_created", entity_id="e1", universe="three_realms")
        assert engine._trigger_matches(sfx, event)

    def test_on_projection_create_no_match_on_other(self):
        engine = EffectsEngine()
        sfx = SFX(id="sfx-proj", name="Projection Starter",
                  trigger="on_projection_create")
        event = GameEvent(type="character_created", entity_id="e1", universe="earth")
        assert not engine._trigger_matches(sfx, event)

    def test_on_contest_loss_matches_when_opponent_wins(self):
        engine = EffectsEngine()
        sfx = SFX(id="sfx-loss", name="Sore Loser",
                  trigger="on_contest_loss")
        event = GameEvent(type="on_roll", entity_id="e1", universe="earth",
                          context={"contest_winner": "opponent"})
        assert engine._trigger_matches(sfx, event)

    def test_on_contest_loss_no_match_when_player_wins(self):
        engine = EffectsEngine()
        sfx = SFX(id="sfx-loss", name="Sore Loser",
                  trigger="on_contest_loss")
        event = GameEvent(type="on_roll", entity_id="e1", universe="earth",
                          context={"contest_winner": "player"})
        assert not engine._trigger_matches(sfx, event)

    def test_on_contest_win_matches(self):
        engine = EffectsEngine()
        sfx = SFX(id="sfx-win", name="Victory Lap",
                  trigger="on_contest_win")
        event = GameEvent(type="on_roll", entity_id="e1", universe="earth",
                          context={"contest_winner": "player"})
        assert engine._trigger_matches(sfx, event)

    def test_on_success_matches(self):
        engine = EffectsEngine()
        sfx = SFX(id="sfx-success", name="Thrive on Success",
                  trigger="on_success")
        event = GameEvent(
            type="on_roll", entity_id="e1", universe="earth",
            roll_result=SimplifiedResult(
                rolls=[DieRoll(die=DieType.D8, result=7, label="test")],
                highest=7, tier=OutcomeTier.SUCCESS,
                effect_die=DieType.D6, hitches=[], botch=False,
                hitches_count=0,
            ),
        )
        assert engine._trigger_matches(sfx, event)

    def test_on_failure_matches(self):
        engine = EffectsEngine()
        sfx = SFX(id="sfx-fail", name="Learn from Failure",
                  trigger="on_failure")
        event = GameEvent(
            type="on_roll", entity_id="e1", universe="earth",
            roll_result=SimplifiedResult(
                rolls=[DieRoll(die=DieType.D8, result=2, label="test")],
                highest=2, tier=OutcomeTier.FAIL,
                effect_die=None, hitches=[], botch=False,
                hitches_count=0,
            ),
        )
        assert engine._trigger_matches(sfx, event)

    def test_on_failure_no_match_on_success(self):
        engine = EffectsEngine()
        sfx = SFX(id="sfx-fail", name="Learn from Failure",
                  trigger="on_failure")
        event = GameEvent(
            type="on_roll", entity_id="e1", universe="earth",
            roll_result=SimplifiedResult(
                rolls=[DieRoll(die=DieType.D8, result=8, label="test")],
                highest=8, tier=OutcomeTier.SUCCESS,
                effect_die=DieType.D6, hitches=[], botch=False,
                hitches_count=0,
            ),
        )
        assert not engine._trigger_matches(sfx, event)


# ── Contest-to-Event Pipeline ──────────────────────────

# ── SFX Push via ContestTracker ────────────────────────

class TestPushContest:
    """Push mechanic: spend 1 razmerit to reassemble and reroll."""

    @staticmethod
    def _die(die, source):
        return {"die": die, "source_kind": "manual", "source_id": source, "label": source, "ts_id": None}

    def test_push_returns_new_result(self):
        from transversal.services.contest_tracker import ContestTracker
        from transversal.services.scene_state import SceneStateStore

        ct = ContestTracker()
        scene = SceneStateStore()
        scene.save_pool("loc-1", "kael", [
            self._die("d10", "int"), self._die("d8", "skill"), self._die("d8", "dist"),
        ])
        ct.set_opposition("loc-1", "kael", "guard", "earth")
        scene.save_pool("loc-1", "guard", [
            self._die("d8", "agi"), self._die("d6", "ale"), self._die("d6", "tra"),
        ])

        # Push with new dice
        result = ct.push_contest("loc-1", "kael", scene, [
            self._die("d10", "int"), self._die("d10", "skill"), self._die("d8", "dist"),
        ])
        assert result is not None
        assert result.pushed is True
        assert len(scene.get_pool("loc-1", "kael")) == 3

    def test_push_blocked_when_already_pushed(self):
        from transversal.services.contest_tracker import ContestTracker
        from transversal.services.scene_state import SceneStateStore

        ct = ContestTracker()
        scene = SceneStateStore()
        scene.save_pool("loc-1", "kael", [
            self._die("d10", "int"), self._die("d8", "skill"),
        ])
        ct.set_opposition("loc-1", "kael", "guard", "earth")
        scene.save_pool("loc-1", "guard", [self._die("d8", "agi")])

        # Set push flag
        ct.set_pushed("loc-1", "kael")

        # Try to push again — should be blocked
        result = ct.push_contest("loc-1", "kael", scene, [
            self._die("d10", "int"), self._die("d10", "skill"),
        ])
        assert result is None

    def test_push_returns_none_without_opponent(self):
        from transversal.services.contest_tracker import ContestTracker
        from transversal.services.scene_state import SceneStateStore

        ct = ContestTracker()
        scene = SceneStateStore()
        scene.save_pool("loc-1", "kael", [self._die("d10", "int")])
        result = ct.push_contest("loc-1", "kael", scene, [
            self._die("d10", "int"),
        ])
        assert result is None


# ── Source binding ────────────────────────────────────

def test_manual_source_binding_resolves_source_variable(monkeypatch):
    from transversal.domain import Effect, EffectTiming, SFX
    from transversal.services import effects_applier

    engine = EffectsEngine()
    sfx = SFX(
        id="sfx-muscle-memory", name="Muscle Memory", trigger="manual",
        source_kind="trait_setting",
        effects=[Effect(
            timing=EffectTiming.IMMEDIATE, type="modify_trait", action="step_up",
            target="{trait_setting}",
        )],
    )
    engine.register(sfx)

    applied = []
    class FakeRegistry:
        def apply(self, effect, entity_id, universe, context):
            applied.append(effect)
    monkeypatch.setattr(effects_applier, "effect_registry", FakeRegistry())

    event = GameEvent(type="manual", entity_id="char-1", universe="earth",
                      context={"source_id": "char-1:martial"})
    engine.process_event_outcome(event, ["sfx-muscle-memory"], 0)

    assert [e.target for e in applied] == ["char-1:martial"]


def test_manual_source_binding_without_source_id_is_noop(monkeypatch):
    from transversal.domain import Effect, EffectTiming, SFX
    from transversal.services import effects_applier

    engine = EffectsEngine()
    sfx = SFX(
        id="sfx-x", name="X", trigger="manual", source_kind="trait_setting",
        effects=[Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait",
                        action="step_up", target="{trait_setting}")],
    )
    engine.register(sfx)

    applied = []
    class FakeRegistry:
        def apply(self, effect, entity_id, universe, context):
            applied.append(effect)
    monkeypatch.setattr(effects_applier, "effect_registry", FakeRegistry())

    # No source_id in context → the {trait_setting} placeholder survives untouched.
    engine.process_event_outcome(GameEvent(type="manual", entity_id="char-1", universe="earth"), ["sfx-x"], 0)
    assert [e.target for e in applied] == ["{trait_setting}"]
