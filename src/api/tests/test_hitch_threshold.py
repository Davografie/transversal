"""A rule can widen which die faces count as hitches ([[B231]]).

The base rule is "a 1 hitches". The written SFX ship a second form — *"both 1s
and 2s on your dice count as hitches"* (MHR *Growing Dread*, ToX *Dread*,
TorchLite *Sunlight Sensitivity*, Cortex Lite *Violent Escalation*, Xine One
*Finite Energies*) — and before this the resolver and the roller both hardcoded
the face, so no rule could say it.

These tests are deliberately written against **both** directions: that a widened
range excludes a hatched 2, and that the base rule is bit-for-bit unchanged. The
second half matters as much as the first, because the exclusion is implemented by
reordering the kept dice and that reorder has to be a no-op at threshold 1.
"""

from types import SimpleNamespace

from transversal.domain import (
    DicePoolRequest,
    DieRoll,
    DieSpec,
    DieType,
    RollKind,
)
from transversal.services import dice_resolver
from transversal.services.dice_resolver import detect_hitches, is_botch, pick_effect_die


def _roll(die: DieType, result: int) -> DieRoll:
    return DieRoll(die=die, result=result, source_kind="manual", label=die.value)


class TestDetectHitches:
    def test_base_rule_is_ones_only(self):
        rolls = [_roll(DieType.D6, 1), _roll(DieType.D6, 2), _roll(DieType.D6, 5)]
        assert [r.result for r in detect_hitches(rolls)] == [1]

    def test_widened_range_takes_twos_too(self):
        rolls = [_roll(DieType.D6, 1), _roll(DieType.D6, 2), _roll(DieType.D6, 5)]
        assert [r.result for r in detect_hitches(rolls, 2)] == [1, 2]

    def test_threshold_is_floored_at_the_base_rule(self):
        """A stored 0 must not make a pool hitch-free; 1 is the floor."""
        rolls = [_roll(DieType.D6, 1), _roll(DieType.D6, 2)]
        assert [r.result for r in detect_hitches(rolls, 0)] == [1]
        assert [r.result for r in detect_hitches(rolls, -3)] == [1]


class TestBotchIsUnchangedByAWidenedRange:
    """A widened range makes 2s *buyable*, not botching.

    This is the one place the two readings could silently diverge: "every die is a
    hitch" is not "every die shows 1".
    """

    def test_all_twos_is_not_a_botch(self):
        rolls = [_roll(DieType.D6, 2), _roll(DieType.D6, 2)]
        assert is_botch(rolls) is False

    def test_all_ones_is_still_a_botch(self):
        rolls = [_roll(DieType.D6, 1), _roll(DieType.D6, 1)]
        assert is_botch(rolls) is True


class TestPickEffectDie:
    def test_a_two_is_eligible_at_the_base_rule_and_not_once_the_range_widens(self):
        """The provable change: a 2 that hitches can no longer be the effect die.

        One non-hitch (the 2) and one hitch (the 1), so at the base rule the 2 is
        the only candidate and once the range widens there is nothing left.
        """
        rolls = [_roll(DieType.D8, 2), _roll(DieType.D4, 1)]
        assert pick_effect_die(rolls, [], True, 1).result == 2
        assert pick_effect_die(rolls, [], True, 2) is None

    def test_the_base_rule_still_offers_the_same_die(self):
        """Threshold 1 and "no threshold argument" agree, so nothing regressed."""
        rolls = [_roll(DieType.D8, 3), _roll(DieType.D10, 4)]
        assert (
            pick_effect_die(rolls, [], True).result
            == pick_effect_die(rolls, [], True, 1).result
        )


def _request(dice, threshold, **kw) -> DicePoolRequest:
    return DicePoolRequest(
        entity_id="e1", universe="earth",
        dice=[DieSpec(die=d, label=d.value) for d in dice],
        kind=RollKind.TEST, hitch_threshold=threshold, **kw,
    )


class TestPoolResolution:
    """The full pool path, on a fixed roll (``roll_dice`` is monkeypatched)."""

    @staticmethod
    def _fixed(monkeypatch, faces):
        calls = {"i": 0}

        def fake(specs):
            out = []
            for spec in specs:
                out.append(DieRoll(
                    die=spec.die, result=faces[calls["i"]],
                    source_kind=spec.source_kind, label=spec.label,
                ))
                calls["i"] += 1
            return out

        monkeypatch.setattr(dice_resolver, "roll_dice", fake)

    def test_a_hatched_two_falls_below_every_ordinary_die(self, monkeypatch):
        """`d6=2, d6=6, d8=7, d8=8` — the two highest (8, 7) make the total.

        The 2 is *reported* as a hitch and is ineligible as an effect die, but the
        kept-dice selection is untouched: a face that hitches is always lower than
        every face that does not, so it sorts last of its own accord. This pins
        that the widened range did not disturb the total.
        """
        self._fixed(monkeypatch, [2, 6, 7, 8])
        result = dice_resolver.resolve(_request(
            [DieType.D6, DieType.D6, DieType.D8, DieType.D8], threshold=2,
        ))
        assert [r.result for r in result.hitches] == [2]
        assert result.total == 15  # 8 + 7

    def test_the_same_pool_reports_nothing_at_the_base_rule(self, monkeypatch):
        """Threshold 1: the 2 is an ordinary die, and it is not a hitch."""
        self._fixed(monkeypatch, [2, 6, 7, 8])
        result = dice_resolver.resolve(_request(
            [DieType.D6, DieType.D6, DieType.D8, DieType.D8], threshold=1,
        ))
        assert result.hitches == []
        assert result.total == 15

    def test_the_roll_still_reports_the_widened_hitch(self, monkeypatch):
        self._fixed(monkeypatch, [1, 2, 6])
        result = dice_resolver.resolve(_request(
            [DieType.D6, DieType.D6, DieType.D8], threshold=2,
        ))
        assert sorted(r.result for r in result.hitches) == [1, 2]
        assert result.botch is False

    def test_hitches_apply_false_ignores_the_range(self, monkeypatch):
        """A difficulty determination has no hitches however wide the range."""
        self._fixed(monkeypatch, [1, 2, 6])
        result = dice_resolver.resolve(_request(
            [DieType.D6, DieType.D6, DieType.D8], threshold=2, hitches_apply=False,
        ))
        assert result.hitches == []


class TestTheCardSaysWhichFace:
    """A card reading only "widen hitches" hides the one decision the effect makes."""

    @staticmethod
    def _text(face):
        from transversal.domain import Effect, EffectTiming
        from transversal.services.sfx_text import effect_text

        return effect_text(Effect(
            timing=EffectTiming.IMMEDIATE,
            type="modify_hitch_threshold", action="set", result=face,
        ))

    def test_two_reads_as_the_widened_range(self):
        assert self._text("2") == "hitches on 1s and 2s"

    def test_one_reads_as_the_base_rule(self):
        """Not "hitch on 1s and 1s" — 1 is the base rule, and it has to say so."""
        assert self._text("1") == "hitches on 1s only"

    def test_the_action_is_registered_and_has_a_card_template(self):
        from transversal.services import effects_registry as reg
        from transversal.services.effects_registry.cards import EFFECT_ACTION_CARDS

        metas = [m for m in reg.EFFECT_ACTION_REGISTRY if m.action_id == "set_hitch_threshold"]
        assert len(metas) == 1, "the action is not registered exactly once"
        assert not metas[0].retired
        assert metas[0].inverse == ("modify_hitch_threshold", "set")
        assert metas[0].inverse_captures_prior, "the prior face must ride the revert"
        assert ("modify_hitch_threshold", "set") in EFFECT_ACTION_CARDS


class TestServerReadsTheThresholdFromTheEntity:
    """The roller is a view of the rules, not their author ([[B231]])."""

    @staticmethod
    def _repo(entity):
        return SimpleNamespace(get_entity=lambda eid: entity if eid == "e1" else None)

    def test_reads_the_entity(self, monkeypatch):
        from transversal.api.rest.roll import _hitch_threshold
        monkeypatch.setattr(
            "transversal.main._get_repo",
            lambda: self._repo(SimpleNamespace(hitch_threshold=2)),
        )
        assert _hitch_threshold("e1") == 2

    def test_missing_entity_falls_back_to_the_base_rule(self, monkeypatch):
        from transversal.api.rest.roll import _hitch_threshold
        monkeypatch.setattr(
            "transversal.main._get_repo",
            lambda: self._repo(SimpleNamespace(hitch_threshold=2)),
        )
        assert _hitch_threshold("nobody") == 1

    def test_zero_is_floored(self, monkeypatch):
        from transversal.api.rest.roll import _hitch_threshold
        monkeypatch.setattr(
            "transversal.main._get_repo",
            lambda: self._repo(SimpleNamespace(hitch_threshold=0)),
        )
        assert _hitch_threshold("e1") == 1
