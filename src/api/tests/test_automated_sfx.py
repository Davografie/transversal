"""Tests for automated SFX — trigger matching and contest-to-event pipeline.

Covers:
  - New trigger types: on_location_change, on_trait_change,
    on_contest_loss, on_contest_win, on_success, on_failure
  - contest_to_events(): ContestResult → GameEvents for both sides
  - SFX push: ContestTracker.push_contest()
"""

import pytest

from transversal.domain import (
    ContestResult,
    ContestWinner,
    DieRoll,
    DieType,
    Effect,
    EffectTiming,
    OutcomeTier,
    PoolResult,
    SFX,
    SimplifiedResult,
)
from transversal.services.effects_engine import (
    EffectsEngine,
    GameEvent,
    contest_to_events,
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
                razmerit_earned=0,
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
                razmerit_earned=0,
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
                razmerit_earned=0,
            ),
        )
        assert not engine._trigger_matches(sfx, event)


# ── Contest-to-Event Pipeline ──────────────────────────

class TestContestToEvents:
    """contest_to_events() turns a ContestResult into GameEvents for both sides."""

    def test_produces_two_events(self):
        contest = ContestResult(
            pipeline="pool",
            winner=ContestWinner.PLAYER,
            player_result=PoolResult(
                rolls=[DieRoll(die=DieType.D10, result=9, label="a"),
                       DieRoll(die=DieType.D8, result=6, label="b"),
                       DieRoll(die=DieType.D8, result=5, label="c")],
                kept=[DieRoll(die=DieType.D10, result=9, label="a"),
                      DieRoll(die=DieType.D8, result=6, label="b")],
                total=15, effect_die=DieType.D8, effect_die_value=5,
                unused=[DieRoll(die=DieType.D8, result=5, label="c")],
                hitches=[], botch=False, razmerit_earned=0,
            ),
            opponent_result=PoolResult(
                rolls=[DieRoll(die=DieType.D8, result=5, label="x"),
                       DieRoll(die=DieType.D6, result=4, label="y"),
                       DieRoll(die=DieType.D6, result=3, label="z")],
                kept=[DieRoll(die=DieType.D8, result=5, label="x"),
                      DieRoll(die=DieType.D6, result=4, label="y")],
                total=9, effect_die=DieType.D6, effect_die_value=3,
                unused=[DieRoll(die=DieType.D6, result=3, label="z")],
                hitches=[], botch=False, razmerit_earned=0,
            ),
        )
        events = contest_to_events(contest, "kael", "guard", "earth")
        assert len(events) == 2
        assert events[0].entity_id == "kael"
        assert events[1].entity_id == "guard"

    def test_player_win_context(self):
        """When player wins, player gets 'player' context, opponent gets 'opponent'."""
        contest = ContestResult(
            pipeline="pool",
            winner=ContestWinner.PLAYER,
            player_result=PoolResult(
                rolls=[DieRoll(die=DieType.D10, result=9, label="a"),
                       DieRoll(die=DieType.D8, result=6, label="b"),
                       DieRoll(die=DieType.D6, result=3, label="c")],
                kept=[DieRoll(die=DieType.D10, result=9, label="a"),
                      DieRoll(die=DieType.D8, result=6, label="b")],
                total=15, effect_die=DieType.D6, effect_die_value=3,
                unused=[DieRoll(die=DieType.D6, result=3, label="c")],
                hitches=[], botch=False, razmerit_earned=0,
            ),
            opponent_result=PoolResult(
                rolls=[DieRoll(die=DieType.D8, result=5, label="x"),
                       DieRoll(die=DieType.D6, result=4, label="y"),
                       DieRoll(die=DieType.D6, result=3, label="z")],
                kept=[DieRoll(die=DieType.D8, result=5, label="x"),
                      DieRoll(die=DieType.D6, result=4, label="y")],
                total=9, effect_die=DieType.D6, effect_die_value=3,
                unused=[DieRoll(die=DieType.D6, result=3, label="z")],
                hitches=[], botch=False, razmerit_earned=0,
            ),
        )
        events = contest_to_events(contest, "kael", "guard", "earth")
        assert events[0].context["contest_winner"] == "player"
        assert events[1].context["contest_winner"] == "opponent"

    def test_opponent_win_context(self):
        contest = ContestResult(
            pipeline="pool",
            winner=ContestWinner.OPPONENT,
            player_result=PoolResult(
                rolls=[DieRoll(die=DieType.D10, result=6, label="a"),
                       DieRoll(die=DieType.D8, result=4, label="b"),
                       DieRoll(die=DieType.D6, result=3, label="c")],
                kept=[DieRoll(die=DieType.D10, result=6, label="a"),
                      DieRoll(die=DieType.D8, result=4, label="b")],
                total=10, effect_die=DieType.D6, effect_die_value=3,
                unused=[DieRoll(die=DieType.D6, result=3, label="c")],
                hitches=[], botch=False, razmerit_earned=0,
            ),
            opponent_result=PoolResult(
                rolls=[DieRoll(die=DieType.D10, result=9, label="x"),
                       DieRoll(die=DieType.D8, result=5, label="y"),
                       DieRoll(die=DieType.D6, result=2, label="z")],
                kept=[DieRoll(die=DieType.D10, result=9, label="x"),
                      DieRoll(die=DieType.D8, result=5, label="y")],
                total=14, effect_die=DieType.D6, effect_die_value=2,
                unused=[DieRoll(die=DieType.D6, result=2, label="z")],
                hitches=[], botch=False, razmerit_earned=0,
            ),
        )
        events = contest_to_events(contest, "kael", "guard", "earth")
        assert events[0].context["contest_winner"] == "opponent"  # kael lost
        assert events[1].context["contest_winner"] == "player"   # guard won

    def test_tie_favors_challenger_context(self):
        """Tie → challenger (initiator) wins."""
        contest = ContestResult(
            pipeline="pool",
            winner=ContestWinner.PLAYER,
            player_result=PoolResult(
                rolls=[DieRoll(die=DieType.D10, result=8, label="a"),
                       DieRoll(die=DieType.D8, result=5, label="b"),
                       DieRoll(die=DieType.D6, result=4, label="c")],
                kept=[DieRoll(die=DieType.D10, result=8, label="a"),
                      DieRoll(die=DieType.D8, result=5, label="b")],
                total=13, effect_die=DieType.D6, effect_die_value=4,
                unused=[DieRoll(die=DieType.D6, result=4, label="c")],
                hitches=[], botch=False, razmerit_earned=0,
            ),
            opponent_result=PoolResult(
                rolls=[DieRoll(die=DieType.D10, result=8, label="x"),
                       DieRoll(die=DieType.D6, result=5, label="y"),
                       DieRoll(die=DieType.D6, result=3, label="z")],
                kept=[DieRoll(die=DieType.D10, result=8, label="x"),
                      DieRoll(die=DieType.D6, result=5, label="y")],
                total=13, effect_die=DieType.D6, effect_die_value=3,
                unused=[DieRoll(die=DieType.D6, result=3, label="z")],
                hitches=[], botch=False, razmerit_earned=0,
            ),
        )
        events = contest_to_events(contest, "kael", "guard", "earth")
        assert events[0].context["contest_winner"] == "player"    # challenger won tie
        assert events[1].context["contest_winner"] == "opponent"  # defendant lost tie

    def test_events_carry_roll_results(self):
        contest = ContestResult(
            pipeline="simplified",
            winner=ContestWinner.PLAYER,
            player_result=SimplifiedResult(
                rolls=[DieRoll(die=DieType.D8, result=7, label="shooting")],
                highest=7, tier=OutcomeTier.SUCCESS,
                effect_die=DieType.D6, hitches=[], botch=False,
                razmerit_earned=0,
            ),
            opponent_result=SimplifiedResult(
                rolls=[DieRoll(die=DieType.D6, result=4, label="agility")],
                highest=4, tier=OutcomeTier.MARGINAL,
                effect_die=DieType.D4, hitches=[], botch=False,
                razmerit_earned=0,
            ),
        )
        events = contest_to_events(contest, "kael", "guard", "earth")
        assert events[0].roll_result is not None
        assert events[1].roll_result is not None
        assert events[0].roll_result.highest == 7
        assert events[1].roll_result.highest == 4


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
