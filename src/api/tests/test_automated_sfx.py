"""Tests for automated SFX — trigger matching and contest-to-event pipeline.

Covers:
  - New trigger types: on_location_change, on_trait_change,
    on_contest_loss, on_contest_win, on_success, on_failure
  - contest_to_events(): ContestResult → GameEvents for both sides
  - fire_contest_sfx(): process both sides through effects engine
  - SFX push: ContestTracker.push_contest()
"""

import pytest

from transversal.domain import (
    ContestResult,
    ContestWinner,
    DieRoll,
    DieType,
    EffectPolarity,
    EffectTiming,
    OutcomeTier,
    PoolResult,
    SFX,
    SfxEffect,
    SimplifiedResult,
)
from transversal.services.effects_engine import (
    EffectsEngine,
    GameEvent,
    contest_to_events,
    fire_contest_sfx,
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

    def test_on_contest_loss_matches_on_tie_defender(self):
        """Tie defender means the entity lost (defender wins ties)."""
        engine = EffectsEngine()
        sfx = SFX(id="sfx-loss", name="Sore Loser",
                  trigger="on_contest_loss")
        event = GameEvent(type="on_roll", entity_id="e1", universe="earth",
                          context={"contest_winner": "tie_defender"})
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
                rolls=[DieRoll(die=DieType.D8, result=7, source="test")],
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
                rolls=[DieRoll(die=DieType.D8, result=2, source="test")],
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
                rolls=[DieRoll(die=DieType.D8, result=8, source="test")],
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
                rolls=[DieRoll(die=DieType.D10, result=9, source="a"),
                       DieRoll(die=DieType.D8, result=6, source="b"),
                       DieRoll(die=DieType.D8, result=5, source="c")],
                kept=[DieRoll(die=DieType.D10, result=9, source="a"),
                      DieRoll(die=DieType.D8, result=6, source="b")],
                total=15, effect_die=DieType.D8, effect_die_value=5,
                unused=[DieRoll(die=DieType.D8, result=5, source="c")],
                hitches=[], botch=False, razmerit_earned=0,
            ),
            opponent_result=PoolResult(
                rolls=[DieRoll(die=DieType.D8, result=5, source="x"),
                       DieRoll(die=DieType.D6, result=4, source="y"),
                       DieRoll(die=DieType.D6, result=3, source="z")],
                kept=[DieRoll(die=DieType.D8, result=5, source="x"),
                      DieRoll(die=DieType.D6, result=4, source="y")],
                total=9, effect_die=DieType.D6, effect_die_value=3,
                unused=[DieRoll(die=DieType.D6, result=3, source="z")],
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
                rolls=[DieRoll(die=DieType.D10, result=9, source="a"),
                       DieRoll(die=DieType.D8, result=6, source="b"),
                       DieRoll(die=DieType.D6, result=3, source="c")],
                kept=[DieRoll(die=DieType.D10, result=9, source="a"),
                      DieRoll(die=DieType.D8, result=6, source="b")],
                total=15, effect_die=DieType.D6, effect_die_value=3,
                unused=[DieRoll(die=DieType.D6, result=3, source="c")],
                hitches=[], botch=False, razmerit_earned=0,
            ),
            opponent_result=PoolResult(
                rolls=[DieRoll(die=DieType.D8, result=5, source="x"),
                       DieRoll(die=DieType.D6, result=4, source="y"),
                       DieRoll(die=DieType.D6, result=3, source="z")],
                kept=[DieRoll(die=DieType.D8, result=5, source="x"),
                      DieRoll(die=DieType.D6, result=4, source="y")],
                total=9, effect_die=DieType.D6, effect_die_value=3,
                unused=[DieRoll(die=DieType.D6, result=3, source="z")],
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
                rolls=[DieRoll(die=DieType.D10, result=6, source="a"),
                       DieRoll(die=DieType.D8, result=4, source="b"),
                       DieRoll(die=DieType.D6, result=3, source="c")],
                kept=[DieRoll(die=DieType.D10, result=6, source="a"),
                      DieRoll(die=DieType.D8, result=4, source="b")],
                total=10, effect_die=DieType.D6, effect_die_value=3,
                unused=[DieRoll(die=DieType.D6, result=3, source="c")],
                hitches=[], botch=False, razmerit_earned=0,
            ),
            opponent_result=PoolResult(
                rolls=[DieRoll(die=DieType.D10, result=9, source="x"),
                       DieRoll(die=DieType.D8, result=5, source="y"),
                       DieRoll(die=DieType.D6, result=2, source="z")],
                kept=[DieRoll(die=DieType.D10, result=9, source="x"),
                      DieRoll(die=DieType.D8, result=5, source="y")],
                total=14, effect_die=DieType.D6, effect_die_value=2,
                unused=[DieRoll(die=DieType.D6, result=2, source="z")],
                hitches=[], botch=False, razmerit_earned=0,
            ),
        )
        events = contest_to_events(contest, "kael", "guard", "earth")
        assert events[0].context["contest_winner"] == "opponent"  # kael lost
        assert events[1].context["contest_winner"] == "player"   # guard won

    def test_tie_defender_context(self):
        """Tie → defender wins, so player lost."""
        contest = ContestResult(
            pipeline="pool",
            winner=ContestWinner.TIE_DEFENDER,
            player_result=PoolResult(
                rolls=[DieRoll(die=DieType.D10, result=8, source="a"),
                       DieRoll(die=DieType.D8, result=5, source="b"),
                       DieRoll(die=DieType.D6, result=4, source="c")],
                kept=[DieRoll(die=DieType.D10, result=8, source="a"),
                      DieRoll(die=DieType.D8, result=5, source="b")],
                total=13, effect_die=DieType.D6, effect_die_value=4,
                unused=[DieRoll(die=DieType.D6, result=4, source="c")],
                hitches=[], botch=False, razmerit_earned=0,
            ),
            opponent_result=PoolResult(
                rolls=[DieRoll(die=DieType.D10, result=8, source="x"),
                       DieRoll(die=DieType.D6, result=5, source="y"),
                       DieRoll(die=DieType.D6, result=3, source="z")],
                kept=[DieRoll(die=DieType.D10, result=8, source="x"),
                      DieRoll(die=DieType.D6, result=5, source="y")],
                total=13, effect_die=DieType.D6, effect_die_value=3,
                unused=[DieRoll(die=DieType.D6, result=3, source="z")],
                hitches=[], botch=False, razmerit_earned=0,
            ),
        )
        events = contest_to_events(contest, "kael", "guard", "earth")
        assert events[0].context["contest_winner"] == "opponent"  # player lost tie
        assert events[1].context["contest_winner"] == "player"   # opponent won tie

    def test_events_carry_roll_results(self):
        contest = ContestResult(
            pipeline="simplified",
            winner=ContestWinner.PLAYER,
            player_result=SimplifiedResult(
                rolls=[DieRoll(die=DieType.D8, result=7, source="shooting")],
                highest=7, tier=OutcomeTier.SUCCESS,
                effect_die=DieType.D6, hitches=[], botch=False,
                razmerit_earned=0,
            ),
            opponent_result=SimplifiedResult(
                rolls=[DieRoll(die=DieType.D6, result=4, source="agility")],
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


# ── fire_contest_sfx ───────────────────────────────────

class TestFireContestSFX:
    """Process a contest result through the effects engine for both sides."""

    def test_processes_both_sides(self):
        engine = EffectsEngine()

        # Register a win SFX for player and a loss SFX for opponent
        engine.register(SFX(
            id="sfx-win", name="Victory Lap", trigger="on_contest_win",
            effects=[SfxEffect(polarity=EffectPolarity.POSITIVE, timing=EffectTiming.IMMEDIATE,
                              type="modify_roll", action="step_up_die", target="next")],
        ))
        engine.register(SFX(
            id="sfx-loss", name="Vengeful", trigger="on_contest_loss",
            effects=[SfxEffect(polarity=EffectPolarity.NEUTRAL, timing=EffectTiming.END_OF_BEAT,
                              type="modify_trait", action="step_up", target="rage")],
        ))

        contest = ContestResult(
            pipeline="pool",
            winner=ContestWinner.PLAYER,
            player_result=PoolResult(
                rolls=[DieRoll(die=DieType.D10, result=9, source="a"),
                       DieRoll(die=DieType.D8, result=6, source="b"),
                       DieRoll(die=DieType.D6, result=3, source="c")],
                kept=[DieRoll(die=DieType.D10, result=9, source="a"),
                      DieRoll(die=DieType.D8, result=6, source="b")],
                total=15, effect_die=DieType.D6, effect_die_value=3,
                unused=[DieRoll(die=DieType.D6, result=3, source="c")],
                hitches=[], botch=False, razmerit_earned=0,
            ),
            opponent_result=PoolResult(
                rolls=[DieRoll(die=DieType.D8, result=5, source="x"),
                       DieRoll(die=DieType.D6, result=4, source="y"),
                       DieRoll(die=DieType.D6, result=3, source="z")],
                kept=[DieRoll(die=DieType.D8, result=5, source="x"),
                      DieRoll(die=DieType.D6, result=4, source="y")],
                total=9, effect_die=DieType.D6, effect_die_value=3,
                unused=[DieRoll(die=DieType.D6, result=3, source="z")],
                hitches=[], botch=False, razmerit_earned=0,
            ),
        )

        applied = fire_contest_sfx(
            engine, contest,
            player_id="kael", opponent_id="guard",
            universe="earth",
            player_sfx_ids=["sfx-win"], opponent_sfx_ids=["sfx-loss"],
            player_razmerit=10, opponent_razmerit=5,
        )

        # Player's win SFX fires immediately
        assert len(applied) >= 1
        win_effects = [a for a in applied if a.action == "step_up_die"]
        assert len(win_effects) >= 1

        # Opponent's loss SFX is deferred (END_OF_BEAT)
        assert engine.scheduled_count == 1

    def test_no_sfx_when_none_available(self):
        engine = EffectsEngine()
        contest = ContestResult(
            pipeline="simplified",
            winner=ContestWinner.PLAYER,
            player_result=SimplifiedResult(
                rolls=[DieRoll(die=DieType.D8, result=7, source="a")],
                highest=7, tier=OutcomeTier.SUCCESS,
                effect_die=DieType.D6, hitches=[], botch=False,
                razmerit_earned=0,
            ),
            opponent_result=SimplifiedResult(
                rolls=[DieRoll(die=DieType.D6, result=4, source="x")],
                highest=4, tier=OutcomeTier.MARGINAL,
                effect_die=DieType.D4, hitches=[], botch=False,
                razmerit_earned=0,
            ),
        )
        applied = fire_contest_sfx(
            engine, contest,
            player_id="kael", opponent_id="guard",
            universe="earth",
            player_sfx_ids=[], opponent_sfx_ids=[],
            player_razmerit=10, opponent_razmerit=5,
        )
        assert len(applied) == 0

    def test_insufficient_razmerit_blocks_sfx(self):
        engine = EffectsEngine()
        engine.register(SFX(
            id="sfx-costly", name="Costly", trigger="on_contest_win",
            effects=[SfxEffect(polarity=EffectPolarity.NEGATIVE, timing=EffectTiming.IMMEDIATE,
                              type="transfer_razmerit", action="spend", target="self", result="3"),
                     SfxEffect(polarity=EffectPolarity.POSITIVE, timing=EffectTiming.IMMEDIATE,
                              type="modify_roll", action="step_up_die", target="next")],
        ))
        contest = ContestResult(
            pipeline="simplified",
            winner=ContestWinner.PLAYER,
            player_result=SimplifiedResult(
                rolls=[DieRoll(die=DieType.D8, result=7, source="a")],
                highest=7, tier=OutcomeTier.SUCCESS,
                effect_die=DieType.D6, hitches=[], botch=False,
                razmerit_earned=0,
            ),
            opponent_result=SimplifiedResult(
                rolls=[DieRoll(die=DieType.D6, result=4, source="x")],
                highest=4, tier=OutcomeTier.MARGINAL,
                effect_die=DieType.D4, hitches=[], botch=False,
                razmerit_earned=0,
            ),
        )
        applied = fire_contest_sfx(
            engine, contest,
            player_id="kael", opponent_id="guard",
            universe="earth",
            player_sfx_ids=["sfx-costly"], opponent_sfx_ids=[],
            player_razmerit=1, opponent_razmerit=5,
        )
        # Cost is 3, only 1 razmerit available — SFX skipped
        assert len(applied) == 0


# ── SFX Push via ContestTracker ────────────────────────

class TestPushContest:
    """Push mechanic: spend 1 razmerit to reassemble and reroll."""

    def test_push_returns_new_result(self):
        from transversal.services.contest_tracker import ContestTracker

        ct = ContestTracker()
        ct.add_die("loc-1", "kael", DieType.D10, "int", "earth")
        ct.add_die("loc-1", "kael", DieType.D8, "skill", "earth")
        ct.add_die("loc-1", "kael", DieType.D8, "dist", "earth")
        ct.set_opposition("loc-1", "kael", "guard", "earth")
        ct.add_die("loc-1", "guard", DieType.D8, "agi", "earth")
        ct.add_die("loc-1", "guard", DieType.D6, "ale", "earth")
        ct.add_die("loc-1", "guard", DieType.D6, "tra", "earth")

        # Push with new dice
        result = ct.push_contest("loc-1", "kael", [
            (DieType.D10, "int"), (DieType.D10, "skill"), (DieType.D8, "dist"),
        ])
        assert result is not None
        assert result.pushed is True
        assert len(ct.get("loc-1", "kael").dice) == 3

    def test_push_blocked_when_already_pushed(self):
        from transversal.services.contest_tracker import ContestTracker

        ct = ContestTracker()
        ct.add_die("loc-1", "kael", DieType.D10, "int", "earth")
        ct.add_die("loc-1", "kael", DieType.D8, "skill", "earth")
        ct.set_opposition("loc-1", "kael", "guard", "earth")
        ct.add_die("loc-1", "guard", DieType.D8, "agi", "earth")

        # Set push flag
        ct.set_pushed("loc-1", "kael")

        # Try to push again — should be blocked
        result = ct.push_contest("loc-1", "kael", [
            (DieType.D10, "int"), (DieType.D10, "skill"),
        ])
        assert result is None

    def test_push_returns_none_without_opponent(self):
        from transversal.services.contest_tracker import ContestTracker

        ct = ContestTracker()
        ct.add_die("loc-1", "kael", DieType.D10, "int", "earth")
        result = ct.push_contest("loc-1", "kael", [
            (DieType.D10, "int"),
        ])
        assert result is None
