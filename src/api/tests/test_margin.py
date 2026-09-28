"""Margin beside tier ([[B234]]).

The tier is **absolute** — a face on the dice, mapped through the outcome ladder.
The margin is **relative** — how far this roll beat whatever it was rolled
against. The written SFX lean on both: "on a heroic success" is the books' *"beat
the difficulty by 5"* (relative), while "step up the effect die" hangs off the
tier (absolute). So the margin sits *beside* the tier rather than replacing it.

Signed from the roller's own point of view throughout, so a rule can say
``{margin} >= 5`` on either side of a contest and mean "I am ahead by five".
"""

from types import SimpleNamespace

from transversal.domain import (
    DicePoolRequest,
    DieRoll,
    DieSpec,
    DieType,
    Opposition,
    RollKind,
)
from transversal.services import dice_resolver
from transversal.services.conditions import evaluate_condition
from transversal.domain import Condition, ConditionType


def _fixed(monkeypatch, faces):
    """Pin every face, in the order the resolver rolls them.

    Patches ``_roll_die`` rather than ``roll_dice``: the *opposition's* dice go
    through ``_roll_die`` directly, so patching only the pool's roller would leave
    the thing the margin is measured against random.
    """
    queue = list(faces)

    def fake(spec):
        return DieRoll(die=spec.die, result=queue.pop(0),
                       source_kind=spec.source_kind, label=spec.label)

    monkeypatch.setattr(dice_resolver, "_roll_die", fake)


def _request(dice, opposition=None, **kw):
    return DicePoolRequest(
        entity_id="e1", universe="earth",
        dice=[DieSpec(die=d, label=d.value) for d in dice],
        opposition=opposition, kind=RollKind.TEST, **kw,
    )


def _difficulty(value):
    return Opposition(type="static_difficulty", static_difficulty=value)


class TestPoolMargin:
    def test_positive_when_the_total_beats_the_difficulty(self, monkeypatch):
        _fixed(monkeypatch, [8, 6, 3])
        result = dice_resolver.resolve(
            _request([DieType.D8, DieType.D6, DieType.D6], _difficulty(9)))
        assert result.total == 14
        assert result.margin == 5

    def test_negative_when_it_does_not(self, monkeypatch):
        _fixed(monkeypatch, [3, 2, 6])
        result = dice_resolver.resolve(
            _request([DieType.D8, DieType.D6, DieType.D6], _difficulty(20)))
        assert result.total == 9
        assert result.margin == -11

    def test_none_without_an_opposition(self, monkeypatch):
        """Nothing to beat is not a margin of zero — the gate must not pass."""
        _fixed(monkeypatch, [8, 6, 3])
        result = dice_resolver.resolve(
            _request([DieType.D8, DieType.D6, DieType.D6]))
        assert result.margin is None

    def test_a_gmc_opposition_uses_its_two_highest(self, monkeypatch):
        """The same rule as ``opposition_total``: the margin is against *that*."""
        _fixed(monkeypatch, [8, 6, 5, 9, 4])
        result = dice_resolver.resolve(_request(
            [DieType.D8, DieType.D6, DieType.D6],
            Opposition(type="gmc", dice=[DieSpec(die=DieType.D8),
                                         DieSpec(die=DieType.D6)]),
        ))
        assert result.opposition_total == 13  # 9 + 4
        assert result.margin == 14 - 13


class TestSimplifiedMargin:
    def test_static_difficulty(self, monkeypatch):
        _fixed(monkeypatch, [7, 4])
        result = dice_resolver.resolve(
            _request([DieType.D8, DieType.D6], _difficulty(5)))
        assert result.margin == 2  # the highest, 7, against 5

    def test_challenge_die(self, monkeypatch):
        """The challenge path already computed this diff to pick the tier."""
        _fixed(monkeypatch, [7, 4, 2])
        result = dice_resolver.resolve(_request(
            [DieType.D8, DieType.D6],
            Opposition(type="challenge", challenge_die=DieType.D4),
        ))
        assert result.opposition_roll.result == 2
        assert result.margin == 5

    def test_a_simplified_gmc_is_compared_by_its_highest(self, monkeypatch):
        """`CommittedResult.total` holds a simplified side's highest, so this is
        the number the contest layer compares — even though `opposition_total`
        stays unset on this path, as it always has."""
        _fixed(monkeypatch, [7, 3, 4])
        result = dice_resolver.resolve(_request(
            [DieType.D8, DieType.D6],
            Opposition(type="gmc", dice=[DieSpec(die=DieType.D6)]),
        ))
        assert result.opposition_total is None
        assert result.margin == 3  # 7 - 4


class TestTheMarginCondition:
    @staticmethod
    def _gate(operator, value, margin):
        cond = Condition(type=ConditionType.MARGIN, operator=operator, value=value)
        # `repo` is unused by a context-only condition, so None is the honest stub
        # (the margin is on the roll, not on any entity).
        return evaluate_condition(None, cond, None, context={"margin": margin})

    def test_heroic_success_is_beat_it_by_five(self):
        assert self._gate(">=", "5", 5) is True
        assert self._gate(">=", "5", 4) is False

    def test_the_operators_are_numeric(self):
        assert self._gate("<", "0", -3) is True
        assert self._gate("==", "0", 0) is True
        assert self._gate("!=", "0", 0) is False

    def test_no_margin_does_not_pass(self):
        """Absent is not zero: a roll with nothing to beat must not satisfy ">= 0"."""
        assert self._gate(">=", "0", None) is False

    def test_a_junk_threshold_does_not_pass(self):
        assert self._gate(">=", "lots", 9) is False

    def test_it_declares_the_context_key_it_reads(self):
        from transversal.services.conditions import CONDITION_TYPES

        meta = next(d for d in CONDITION_TYPES if d.value == ConditionType.MARGIN.name)
        assert meta.requires_context_any_of == ("margin",)
        assert set(meta.operators) >= {">=", "<=", "==", "!="}
