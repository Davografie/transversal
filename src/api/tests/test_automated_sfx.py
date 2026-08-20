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
