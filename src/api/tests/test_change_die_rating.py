"""Changing a die of a trait instance's *rating* — the persistent locus.

The other home for a die. A rating is a list (``TraitSetting.dice``): a static
trait holds one die, a resource trait its unspent remainder. Each die is named by
its position (``rating:<index>:<ts_id>``), and the two boundary rules are the
author's: a d4 stepped down leaves the rating, and an empty rating stepped up
restores a d4.

Where a pool change lasts the roll, a rating change is a fact about the
character — so its undo restores the **whole** prior list rather than trying to
reverse the change. Counts and the d4 floor are why: "step down 2" from a d6
ends with the die *gone*, and no single inverse step puts it back.
"""

from types import SimpleNamespace as NS

from transversal.domain import DieType, Effect, EffectTiming
from transversal.services.effects_applier import handlers_change_die as hcd
from transversal.services.effects_applier.handlers_change_die import (
    _apply_change_double,
    _apply_change_remove,
    _apply_restore_die,
    _apply_change_set,
    _apply_change_split,
    _apply_change_step_down,
    _apply_change_step_up,
    _parse_rating_ref,
)


class Result:
    def __init__(self):
        self.applied = []
        self.new_trait_settings = []
        self.updated_trait_settings = []
        self.removed_trait_settings = []


class Repo:
    def __init__(self, ts):
        self._ts = ts

    def get_traitsetting(self, ts_id):
        return self._ts if self._ts is not None and self._ts.id == ts_id else None


def _ts(dice, ts_id="kael:spiritual-power"):
    return NS(id=ts_id, dice=[DieType(d) for d in dice])


def _effect(target, count=None, size=None):
    context = {"count": str(count)} if count is not None else {}
    return Effect(timing=EffectTiming.IMMEDIATE, type="modify_roll",
                  action="step_up_die", target=target, result=size, context=context)


def _apply(handler, ts, target, *, count=None, size=None):
    result = Result()
    handler(NS(id="kael"), _effect(target, count=count, size=size), Repo(ts), result)
    return result


REF = "rating:0:kael:spiritual-power"


# ── The reference ──────────────────────────────────────

def test_a_rating_reference_parses_despite_colons_in_the_trait_id():
    """A traitsetting id contains colons, which is why the index comes first."""
    assert _parse_rating_ref(REF) == (0, "kael:spiritual-power")
    assert _parse_rating_ref("rating:3:gmc-1:trait-qi") == (3, "gmc-1:trait-qi")
    assert _parse_rating_ref("rating:x:kael:qi") is None
    assert _parse_rating_ref("die:loc-1:kael:0") is None
    assert _parse_rating_ref("kael:spiritual-power") is None


# ── The verbs, on a rating ─────────────────────────────

def test_step_up_changes_the_named_die():
    ts = _ts(["d6"])
    _apply(_apply_change_step_up, ts, REF)
    assert [d.value for d in ts.dice] == ["d8"]


def test_step_up_takes_a_count():
    ts = _ts(["d6"])
    _apply(_apply_change_step_up, ts, REF, count=2)
    assert [d.value for d in ts.dice] == ["d10"]


def test_a_named_die_is_the_one_changed_when_the_rating_holds_several():
    ts = _ts(["d6", "d10"])
    _apply(_apply_change_step_down, ts, "rating:1:kael:spiritual-power")
    assert [d.value for d in ts.dice] == ["d6", "d8"]


def test_step_down_a_d4_removes_that_die_and_keeps_the_others():
    """The author's rule: a d4 stepped down is *gone* — but the trait persists."""
    ts = _ts(["d4", "d10"])
    result = _apply(_apply_change_step_down, ts, REF)
    assert [d.value for d in ts.dice] == ["d10"]
    assert "stepped down off the ladder" in result.applied[0].summary


def test_step_up_an_empty_rating_restores_a_d4():
    """The other half of the rule: a trait with no dice is still a trait, and
    stepping it up gives it one."""
    ts = _ts([])
    _apply(_apply_change_step_up, ts, REF)
    assert [d.value for d in ts.dice] == ["d4"]


def test_set_restores_an_empty_rating_at_the_authored_size():
    ts = _ts([])
    _apply(_apply_change_set, ts, REF, size="d8")
    assert [d.value for d in ts.dice] == ["d8"]


def test_set_gives_the_named_die_a_size():
    ts = _ts(["d6", "d6"])
    _apply(_apply_change_set, ts, "rating:1:kael:spiritual-power", size="d12")
    assert [d.value for d in ts.dice] == ["d6", "d12"]


def test_double_adds_copies_of_the_named_die():
    ts = _ts(["d8"])
    _apply(_apply_change_double, ts, REF, count=2)
    assert [d.value for d in ts.dice] == ["d8", "d8", "d8"]


def test_split_makes_smaller_copies():
    ts = _ts(["d8"])
    _apply(_apply_change_split, ts, REF, count=2)
    assert [d.value for d in ts.dice] == ["d6", "d6", "d6"]


def test_remove_takes_the_die_out():
    ts = _ts(["d8", "d6"])
    _apply(_apply_change_remove, ts, "rating:1:kael:spiritual-power")
    assert [d.value for d in ts.dice] == ["d8"]


def test_removing_the_last_die_leaves_a_valid_empty_rating():
    ts = _ts(["d4"])
    _apply(_apply_change_remove, ts, REF)
    assert ts.dice == []


def test_a_stale_index_reports_rather_than_touching_another_die():
    ts = _ts(["d8"])
    result = _apply(_apply_change_step_down, ts, "rating:7:kael:spiritual-power")
    assert [d.value for d in ts.dice] == ["d8"]
    assert "no die 7" in result.applied[0].summary


def test_an_unknown_trait_instance_is_reported():
    result = Result()
    _apply_change_step_up(NS(id="kael"), _effect("rating:0:kael:nope"), Repo(None), result)
    assert "no trait instance" in result.applied[0].summary


def test_the_change_marks_the_trait_setting_for_persistence():
    """A rating change is a real mutation — the caller has to save it."""
    ts = _ts(["d6"])
    result = _apply(_apply_change_step_up, ts, REF)
    assert result.updated_trait_settings == [ts]


# ── The undo ───────────────────────────────────────────

def test_the_forward_change_records_the_whole_prior_list(monkeypatch):
    """Not a single value: a change can resize, add or remove several dice, and
    the inverse of a *counted* change is not the change reversed."""
    recorded = {}
    monkeypatch.setattr(hcd, "_queue_trait_revert",
                        lambda repo, ts, effect, **kw: recorded.update(kw))
    ts = _ts(["d8"])
    _apply(_apply_change_split, ts, REF, count=2)
    assert recorded["context_extra"]["prior_dice"] == ["d8"]


def test_the_undo_restores_the_recorded_list():
    ts = _ts(["d6", "d6", "d6"])
    effect = Effect(timing=EffectTiming.IMMEDIATE, type="modify_roll", action="restore_die",
                    target=REF, context={"prior_dice": ["d8"]})
    result = Result()
    _apply_restore_die(NS(id="kael"), effect, Repo(ts), result)
    assert [d.value for d in ts.dice] == ["d8"]
    assert result.updated_trait_settings == [ts]


def test_the_undo_can_restore_an_empty_rating():
    """An empty list is a legal value to restore to — that is how a temporary
    'step down the last die' comes back."""
    ts = _ts(["d6"])
    effect = Effect(timing=EffectTiming.IMMEDIATE, type="modify_roll", action="restore_die",
                    target=REF, context={"prior_dice": []})
    _apply_restore_die(NS(id="kael"), effect, Repo(ts), Result())
    assert ts.dice == []


# ── The whole chain ────────────────────────────────────

def test_a_path_resolves_a_rating_die_and_the_handler_changes_it():
    """Resolve → reference → handler, for real. This is the junction that can
    drift: the path hands out a dict, `resolved_id` turns it into a reference, and
    the handler parses that reference back into (index, trait instance). A test of
    either half alone would not notice them disagreeing."""
    from transversal.services.target_resolver import TargetContext, resolve, resolved_id
    from transversal.services.target_spec import (
        AggregateStep, NavigateStep, SelectStep, TargetSpec,
    )

    ts = _ts(["d6", "d10"])
    spec = TargetSpec(steps=[
        SelectStep(collection="self_traitsettings"),
        NavigateStep(edge="rating_dice"),
        AggregateStep(fn="top", field="rating"),      # the highest die of the rating
    ])
    res = resolve(spec, TargetContext(subject=NS(id="kael"), repo=Repo(ts),
                                      collections={"self_traitsettings": [ts]}))
    assert res.errors == []
    assert len(res.values) == 1

    ref = resolved_id(res.values[0])
    assert ref == "rating:1:kael:spiritual-power"

    _apply(_apply_change_step_up, ts, ref)
    assert [d.value for d in ts.dice] == ["d6", "d12"]
