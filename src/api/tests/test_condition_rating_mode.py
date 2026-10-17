"""A rating gate can read a pool's **shape**, not just its dice ([[B242]]).

`TRAIT_RATING` compared per-die — `any(_compare(d.max_value, op, threshold))` — so
`== d8` meant *"is some die a d8"* and **1d8 and 2d8 were indistinguishable**. That
is what blocked gating two rungs of the cultivation ladder apart, and it also made
`<`/`<=` mean different things per pool shape. `mode` adds `all` and `count` while
leaving the historical test as the default, so no existing gate changes meaning.
"""

from types import SimpleNamespace

from transversal.domain import Condition, ConditionType, DieType, TraitSetting
from transversal.services.conditions import evaluate_condition


class FakeRepo:
    def __init__(self, dice):
        self._ts = TraitSetting(id="char-1:trait-x", entity_id="char-1",
                                trait_id="trait-x", dice=list(dice))

    def get_traitsettings_for_entity(self, entity_id):
        return [self._ts]


def _gate(dice, **kw):
    entity = SimpleNamespace(id="char-1")
    condition = Condition(type=ConditionType.TRAIT_RATING, target="trait-x",
                          value="d8", **kw)
    return evaluate_condition(entity, condition, FakeRepo(dice))


def test_the_default_test_is_unchanged_and_cannot_see_the_shape():
    """`any` is what every gate authored before modes means — and why they could not
    tell one d8 from two."""
    assert _gate([DieType.D8], operator="==") is True
    assert _gate([DieType.D8, DieType.D8], operator="==") is True


def test_count_an_exact_pool_shape():
    """`== 2d8` is the case that motivated the change."""
    assert _gate([DieType.D8], operator="==", mode="count", count=2) is False
    assert _gate([DieType.D8, DieType.D8], operator="==", mode="count", count=2) is True
    assert _gate([DieType.D8, DieType.D8, DieType.D8],
                 operator="==", mode="count", count=2) is False
    # …and the operator composes with the count, not just equality.
    assert _gate([DieType.D8, DieType.D8], operator=">=", mode="count", count=2) is True
    assert _gate([DieType.D8], operator=">=", mode="count", count=2) is False


def test_count_counts_only_the_dice_at_the_threshold():
    assert _gate([DieType.D8, DieType.D10, DieType.D8],
                 operator="==", mode="count", count=2) is True
    assert _gate([DieType.D8, DieType.D10],
                 operator="==", mode="count", count=2) is False


def test_all_requires_every_die_to_clear_the_threshold():
    assert _gate([DieType.D8, DieType.D6], operator=">=", mode="all") is False
    assert _gate([DieType.D8, DieType.D10], operator=">=", mode="all") is True
