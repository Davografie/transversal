"""Changing a die in an assembled pool (the Change a Die family, pool locus).

These actions were declared, seeded and *inert*: the applier passed
``modify_roll`` through to "the resolver context" and nothing consumed it there,
so a rule could name a die and nothing happened. They are real now — and the
target is a **targeting path**, which is how an author says *which* die (the one
from the fire technique, say) rather than a strategy keyword.

A die has no id of its own: two dice from the same trait are different dice. So a
die resolved through ``pool → dice`` carries its provenance
(``die:<location>:<owner>:<index>``), and that is what the applier acts on.
"""

from transversal.domain import DieType, Effect, EffectTiming
from transversal.domain.dice import step_die
from transversal.services import scene_state as ss_module
from transversal.services.effects_applier.handlers_change_die import (
    _apply_change_double,
    _apply_change_remove,
    _apply_change_set,
    _apply_change_split,
    _apply_change_step_down,
    _apply_change_step_up,
    _highest_trait_die,
)
from transversal.services.effects_applier.handlers_pools import _parse_die_ref
from transversal.services.scene_state import SceneStateStore


class Result:
    """Just enough of the applier's result for a handler that only reports."""

    def __init__(self):
        self.applied = []
        self.updated_trait_settings = []


class Entity:
    def __init__(self, id="kael", current_location="loc-1"):
        self.id = id
        self.current_location = current_location


def _effect(target, count=None, size=None):
    """One effect to hand a verb wrapper; the verb comes from the wrapper."""
    context = {"count": str(count)} if count is not None else {}
    return Effect(timing=EffectTiming.IMMEDIATE, type="modify_roll",
                  action="step_down_die", target=target, result=size, context=context)


def _with_pool(dice):
    """Install a fresh scene store holding ``kael``'s pool at ``loc-1``."""
    store = SceneStateStore()
    store.save_pool("loc-1", "kael", dice)
    ss_module._store = store
    return store


def teardown_function(_fn):
    ss_module._store = SceneStateStore()


# ── The pieces ────────────────────────────────────────

def test_a_die_reference_parses_and_a_keyword_does_not():
    assert _parse_die_ref("die:loc-1:kael:2") == ("loc-1", "kael", 2)
    assert _parse_die_ref("die:loc-1:kael:notanumber") is None
    assert _parse_die_ref("die:loc-1:kael") is None
    assert _parse_die_ref("highest_trait_die") is None
    assert _parse_die_ref("") is None


def test_the_ladder_clamps_at_the_top_and_removes_at_the_bottom():
    """One rule for both homes: there is no d14, and a d4 stepped down is *gone*
    rather than clinging on. Stepping up from nothing restores a d4 — an empty
    rating sits below the ladder."""
    assert step_die(DieType.D4, 1) == DieType.D6
    assert step_die(DieType.D8, -1) == DieType.D6
    assert step_die(DieType.D12, 1) == DieType.D12      # there is no d14
    assert step_die(DieType.D4, -1) is None             # a d4 steps down to nothing
    assert step_die(DieType.D8, 2) == DieType.D12       # counts
    assert step_die(DieType.D8, -2) == DieType.D4
    assert step_die(None, 1) == DieType.D4              # an empty rating restores at d4
    assert step_die(None, 2) == DieType.D6
    assert step_die(None, -1) is None


def test_the_keyword_picks_the_highest_die_that_came_from_a_trait():
    pool = [
        {"die": "d6", "ts_id": None, "source_kind": "manual"},
        {"die": "d8", "ts_id": "kael:fire", "source_kind": "trait"},
        {"die": "d10", "ts_id": "kael:metal", "source_kind": "trait"},
    ]
    assert _highest_trait_die(pool) == 2
    # No trait dice at all → nothing to choose, not "the first die".
    assert _highest_trait_die([{"die": "d6", "ts_id": None}]) is None


# ── The verbs ─────────────────────────────────────────

def test_a_die_reference_steps_that_die_in_the_pool():
    store = _with_pool([
        {"die": "d8", "ts_id": "kael:fire", "source_kind": "trait", "label": "Fire Palm"},
        {"die": "d6", "ts_id": None, "source_kind": "manual", "label": "wary"},
    ])
    result = Result()

    _apply_change_step_down(Entity(), _effect("die:loc-1:kael:0"), None, result)

    assert [d["die"] for d in store.get_pool("loc-1", "kael")] == ["d6", "d6"]
    assert "d8 → d6 in kael's pool" in result.applied[0].summary
    # Nothing else about the die is disturbed.
    assert store.get_pool("loc-1", "kael")[0]["ts_id"] == "kael:fire"


def test_the_same_action_steps_up():
    store = _with_pool([{"die": "d6", "ts_id": None, "source_kind": "manual"}])
    result = Result()

    _apply_change_step_up(Entity(), _effect("die:loc-1:kael:0"), None, result)

    assert store.get_pool("loc-1", "kael")[0]["die"] == "d8"


def test_a_count_moves_several_steps():
    store = _with_pool([{"die": "d8", "ts_id": None, "source_kind": "manual"}])
    result = Result()

    _apply_change_step_up(Entity(), _effect("die:loc-1:kael:0", count=2), None, result)

    assert store.get_pool("loc-1", "kael")[0]["die"] == "d12"


def test_a_d4_stepped_down_leaves_the_pool():
    """The author's rule: stepping down a d4 *removes* the die."""
    store = _with_pool([
        {"die": "d4", "ts_id": None, "source_kind": "manual"},
        {"die": "d8", "ts_id": None, "source_kind": "manual"},
    ])
    result = Result()

    _apply_change_step_down(Entity(), _effect("die:loc-1:kael:0"), None, result)

    assert [d["die"] for d in store.get_pool("loc-1", "kael")] == ["d8"]


def test_double_adds_copies_at_the_same_size():
    store = _with_pool([
        {"die": "d8", "ts_id": "kael:fire", "source_kind": "trait"},
        {"die": "d6", "ts_id": None, "source_kind": "manual"},
    ])
    result = Result()

    _apply_change_double(Entity(), _effect("die:loc-1:kael:0", count=2), None, result)

    pool = store.get_pool("loc-1", "kael")
    assert [d["die"] for d in pool] == ["d8", "d8", "d8", "d6"]
    # The copies keep the provenance of the die they came from.
    assert all(d["ts_id"] == "kael:fire" for d in pool[:3])


def test_split_makes_smaller_copies():
    store = _with_pool([{"die": "d8", "ts_id": None, "source_kind": "manual"}])
    result = Result()

    _apply_change_split(Entity(), _effect("die:loc-1:kael:0", count=2), None, result)

    assert [d["die"] for d in store.get_pool("loc-1", "kael")] == ["d6", "d6", "d6"]


def test_a_d4_cannot_be_split():
    """There is no smaller die, so a split is refused rather than invented."""
    store = _with_pool([{"die": "d4", "ts_id": None, "source_kind": "manual"}])
    result = Result()

    _apply_change_split(Entity(), _effect("die:loc-1:kael:0"), None, result)

    assert store.get_pool("loc-1", "kael")[0]["die"] == "d4"
    assert "already the smallest die" in result.applied[0].summary


def test_set_gives_a_die_a_size():
    store = _with_pool([{"die": "d8", "ts_id": None, "source_kind": "manual"}])
    result = Result()

    _apply_change_set(Entity(), _effect("die:loc-1:kael:0", size="d12"), None, result)

    assert store.get_pool("loc-1", "kael")[0]["die"] == "d12"


def test_remove_takes_the_die_out():
    store = _with_pool([
        {"die": "d8", "ts_id": None, "source_kind": "manual"},
        {"die": "d6", "ts_id": None, "source_kind": "manual"},
    ])
    result = Result()

    _apply_change_remove(Entity(), _effect("die:loc-1:kael:1"), None, result)

    assert [d["die"] for d in store.get_pool("loc-1", "kael")] == ["d8"]


def test_the_keyword_steps_the_highest_trait_die():
    store = _with_pool([
        {"die": "d6", "ts_id": None, "source_kind": "manual"},
        {"die": "d8", "ts_id": "kael:fire", "source_kind": "trait"},
        {"die": "d10", "ts_id": "kael:metal", "source_kind": "trait"},
    ])
    result = Result()

    _apply_change_step_down(Entity(), _effect("highest_trait_die"), None, result)

    assert [d["die"] for d in store.get_pool("loc-1", "kael")] == ["d6", "d8", "d8"]
    assert "d10 → d8" in result.applied[0].summary


def test_a_pool_at_the_limit_reports_rather_than_pretending():
    store = _with_pool([{"die": "d12", "ts_id": None, "source_kind": "manual"}])
    result = Result()

    _apply_change_step_up(Entity(), _effect("die:loc-1:kael:0"), None, result)

    assert store.get_pool("loc-1", "kael")[0]["die"] == "d12"
    assert result.applied[0].summary == "d12 is already at the limit in kael's pool"


def test_an_unknown_target_is_reported_not_guessed_at():
    _with_pool([{"die": "d8", "ts_id": None, "source_kind": "manual"}])
    result = Result()

    _apply_change_step_down(Entity(), _effect("the_hitch_die"), None, result)

    assert result.applied[0].summary == "die target not resolved: 'the_hitch_die'"


def test_a_stale_reference_reports_instead_of_touching_another_die():
    store = _with_pool([{"die": "d8", "ts_id": None, "source_kind": "manual"}])
    result = Result()

    _apply_change_step_down(Entity(), _effect("die:loc-1:kael:7"), None, result)

    assert store.get_pool("loc-1", "kael")[0]["die"] == "d8"
    assert "no die at die:loc-1:kael:7" in result.applied[0].summary


def test_an_empty_pool_is_not_an_error():
    _with_pool([])
    result = Result()

    _apply_change_step_down(Entity(), _effect("highest_trait_die"), None, result)

    assert result.applied[0].summary == "no trait die to change"


# ── The two halves agree ──────────────────────────────

def test_a_die_resolved_through_a_pool_becomes_the_reference_the_action_needs():
    """The path hands out provenance; the applier parses it. If these two ever
    drift, a rule would resolve a die and change a different one (or none)."""
    from transversal.services.roll_deferral import _resolved_id

    store = _with_pool([
        {"die": "d8", "ts_id": "kael:fire", "source_kind": "trait"},
        {"die": "d8", "ts_id": "kael:fire", "source_kind": "trait"},
    ])
    assert len(store.get_pool("loc-1", "kael")) == 2

    from transversal.services.target_resolver import TargetContext, _pool_dice

    handle = {"id": "pool:kael", "owner_id": "kael", "location_id": "loc-1", "kind": "pool"}
    dice = _pool_dice(handle, TargetContext())
    refs = [_resolved_id(d) for d in dice]
    assert refs == ["die:loc-1:kael:0", "die:loc-1:kael:1"]

    result = Result()
    _apply_change_step_down(Entity(), _effect(refs[1]), None, result)
    assert [d["die"] for d in store.get_pool("loc-1", "kael")] == ["d8", "d6"]


class Repo:
    """The persistence calls `commit_effects` makes for an effect like this one."""

    def update_entity(self, entity):
        return entity

    def get_entity(self, eid):
        return None


def _real_entity():
    from transversal.domain import Entity as DomainEntity, EntityType

    return DomainEntity(id="kael", name="Kael", type=EntityType.CHARACTER,
                        current_universe="earth", current_location="loc-1")


def test_the_commit_path_reaches_the_handler():
    """The dispatch half. `commit_effects` is what the registry's `_commit` calls,
    and this action used to fall through to the resolver passthrough — a rule
    could name a die and nothing happened. It now lands here."""
    from transversal.services.effects_commit import commit_effects

    store = _with_pool([{"die": "d8", "ts_id": "kael:fire", "source_kind": "trait"}])

    result = commit_effects(_real_entity(), [_effect("die:loc-1:kael:0")], Repo(), {})

    assert store.get_pool("loc-1", "kael")[0]["die"] == "d6"
    assert any("d8 → d6" in a.summary for a in result.applied)
