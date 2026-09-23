"""Contest reachability — the questions a rule asks about a contest in play.

A contest has no id of its own: it is session state keyed ``(location, entity)``
in the contest tracker, so the element is a **handle** (`pool` and `universe` are
the same shape). These tests pin the three questions the author needs answered, on
the shortest route to each:

- *is this entity in a contest* — ``entity → contest`` resolves, or resolves to
  nothing for a test rolled alone;
- *is this pool's roll a contest* — ``pool → contest``, the route that speaks the
  moment the dice are being assembled;
- *is this place running one, and who is in it* — ``location → contests`` and
  ``contest → entities``.
"""

from types import SimpleNamespace as NS

import pytest

from transversal.services import contest_tracker as ct_module
from transversal.services import scene_state as ss_module
from transversal.services.contest_tracker import ContestTracker
from transversal.services.scene_state import SceneStateStore
from transversal.services.target_resolver import TargetContext, resolve
from transversal.services.target_spec import (
    AggregateStep,
    FilterStep,
    NavigateStep,
    SelectStep,
    TargetSpec,
)


def spec(*steps):
    return TargetSpec(steps=list(steps))


class FakeRepo:
    def __init__(self, entities):
        self.entities = {e.id: e for e in entities}

    def get_entity(self, eid):
        return self.entities.get(eid)

    def get_traitsetting(self, ts_id):
        return None

    def get_trait(self, tid):
        return None

    def get_traitset_by_id(self, tsid):
        return None

    def get_projections_for_entity(self, eid):
        return []

    def get_traitsettings_for_entity(self, eid):
        return []

    def list_entities_by_type(self, entity_type, universe=None):
        # `str(EntityType.LOCATION)` is "EntityType.LOCATION", so compare the value.
        want = getattr(entity_type, "value", entity_type)
        return [e for e in self.entities.values() if e.type == want]


@pytest.fixture
def tracker(monkeypatch):
    fresh = ContestTracker()
    monkeypatch.setattr(ct_module, "_contest_tracker", fresh)
    monkeypatch.setattr(ss_module, "_store", SceneStateStore())
    return fresh


def _world():
    kael = NS(id="kael", type="character", name="Kael", current_location="loc-1",
              current_universe="earth")
    guard = NS(id="guard", type="gmc", name="Guard", current_location="loc-1",
               current_universe="earth")
    # Somebody at the same place but in no contest — the "test" case.
    bystander = NS(id="mel", type="character", name="Mel", current_location="loc-1",
                   current_universe="earth")
    loc = NS(id="loc-1", type="location", name="Iron Roots", current_universe="earth")
    return FakeRepo([kael, guard, bystander, loc]), kael, guard, bystander, loc


def _challenge(tracker, *, high_stakes=False):
    tracker.set_opposition("loc-1", "kael", "guard", "earth")
    if high_stakes:
        tracker.set_stakes("loc-1", "kael", True)


def _pool_handle(owner_id, location_id="loc-1"):
    return {"id": f"pool:{owner_id}", "owner_id": owner_id,
            "location_id": location_id, "kind": "pool"}


# ── entity → contest ─────────────────────────────────────────

def test_an_entity_in_a_contest_reaches_it(tracker):
    repo, *_, = _world()
    _challenge(tracker)
    res = resolve(spec(SelectStep(collection="self"), NavigateStep(edge="contest")),
                  TargetContext(subject=repo.get_entity("kael"), repo=repo))
    assert res.errors == []
    assert [c.id for c in res.values] == ["contest:loc-1:kael"]


def test_the_challenged_side_reaches_the_same_contest(tracker):
    """`set_opposition` gives the defendant a state too, so either side reads it."""
    repo, *_, = _world()
    _challenge(tracker)
    res = resolve(spec(SelectStep(collection="self"), NavigateStep(edge="contest")),
                  TargetContext(subject=repo.get_entity("guard"), repo=repo))
    assert [c.id for c in res.values] == ["contest:loc-1:guard"]


def test_an_entity_with_no_roll_recorded_resolves_to_nothing(tracker):
    """Nothing recorded at this location for this entity — no roll in play."""
    repo, *_, = _world()
    bystander = repo.get_entity("mel")
    res = resolve(spec(SelectStep(collection="self"), NavigateStep(edge="contest")),
                  TargetContext(subject=bystander, repo=repo))
    assert res.errors == []
    assert res.values == []


# ── pool → contest (the short route) ─────────────────────────

def test_a_pool_reaches_its_contest_in_one_hop(tracker):
    """The route the moment speaks: dice are being assembled *now*."""
    repo, kael, *_ = _world()
    _challenge(tracker)
    res = resolve(spec(SelectStep(collection="self"), NavigateStep(edge="pool"),
                       NavigateStep(edge="contest")),
                  TargetContext(subject=kael, repo=repo))
    assert res.errors == []
    assert [c.id for c in res.values] == ["contest:loc-1:kael"]


def test_a_pool_with_no_contest_resolves_to_nothing(tracker):
    repo, *_, = _world()
    res = resolve(spec(SelectStep(collection="self"), NavigateStep(edge="pool"),
                       NavigateStep(edge="contest")),
                  TargetContext(subject=repo.get_entity("mel"), repo=repo))
    assert res.values == []


def test_a_difficulty_pool_is_not_a_contest(tracker):
    """The GM's difficulty pool belongs to no entity side, so it has no contest."""
    from transversal.services.target_resolver import _pool_handle

    repo, *_, = _world()
    _challenge(tracker)
    pool = _pool_handle("loc-1", "loc-1", "difficulty")
    res = resolve(spec(SelectStep(collection="self"), NavigateStep(edge="pool"),
                       NavigateStep(edge="contest")),
                  TargetContext(subject=repo.get_entity("mel"), repo=repo))
    assert res.values == []


# ── the contest's own facts ──────────────────────────────────

def test_a_contest_carries_its_stakes_and_phase(tracker):
    repo, kael, *_ = _world()
    _challenge(tracker, high_stakes=True)
    res = resolve(spec(SelectStep(collection="self"), NavigateStep(edge="contest"),
                       FilterStep(field="stakes", operator="==", value="high")),
                  TargetContext(subject=kael, repo=repo))
    assert [c.id for c in res.values] == ["contest:loc-1:kael"]

    # Phase reads the scene store: a contest with no pool yet is still assembling.
    res2 = resolve(spec(SelectStep(collection="self"), NavigateStep(edge="contest"),
                        FilterStep(field="phase", operator="==", value="adding")),
                   TargetContext(subject=kael, repo=repo))
    assert [c.id for c in res2.values] == ["contest:loc-1:kael"]


def test_a_contest_names_the_other_side(tracker):
    repo, kael, *_ = _world()
    _challenge(tracker)
    res = resolve(spec(SelectStep(collection="self"), NavigateStep(edge="contest"),
                       FilterStep(field="opposition_id", operator="==", value="guard")),
                  TargetContext(subject=kael, repo=repo))
    assert [c.id for c in res.values] == ["contest:loc-1:kael"]


# ── participants ─────────────────────────────────────────────

def test_a_contest_reaches_both_participants(tracker):
    repo, kael, *_ = _world()
    _challenge(tracker)
    res = resolve(spec(SelectStep(collection="self"), NavigateStep(edge="contest"),
                       NavigateStep(edge="entities")),
                  TargetContext(subject=kael, repo=repo))
    assert res.errors == []
    assert sorted(e.id for e in res.values) == ["guard", "kael"]


def test_the_other_participant_is_one_filter_away(tracker):
    """The shape that replaces asking for a `{contest_entity_opponent}` token."""
    repo, kael, *_ = _world()
    _challenge(tracker)
    res = resolve(spec(SelectStep(collection="self"), NavigateStep(edge="contest"),
                       NavigateStep(edge="entities"),
                       FilterStep(field="id", operator="!=", value="kael")),
                  TargetContext(subject=kael, repo=repo))
    assert [e.id for e in res.values] == ["guard"]


def test_a_contests_pools_are_each_sides_own_pool(tracker):
    """The handle must name the *owner*, not the location — a reversed argument
    would still read fine through the handle's fields and only break whoever
    parses the id (`pool:<entity>`)."""
    repo, kael, *_ = _world()
    _challenge(tracker)
    res = resolve(spec(SelectStep(collection="self"), NavigateStep(edge="contest"),
                       NavigateStep(edge="pools")),
                  TargetContext(subject=kael, repo=repo))
    assert res.errors == []
    assert sorted(p["id"] for p in res.values) == ["pool:guard", "pool:kael"]
    assert sorted(p["owner_id"] for p in res.values) == ["guard", "kael"]
    assert all(p["location_id"] == "loc-1" for p in res.values)


def test_the_element_covers_a_recorded_roll_of_either_kind(tracker):
    """`entity -> contest` means *a roll is in play at this location*, and `kind`
    says which it was — so one element answers both questions and a filter picks.

    Deliberately not "declared a challenge": a test and a contest both reach the
    same `on_set`/`on_result` effects (`/resolve` says so in its own docstring),
    so a rule that gates on the roll needs to see both. Gate on a *challenge* with
    `filter kind == contest`.
    """
    repo, kael, *_ = _world()
    _challenge(tracker)
    # Both a test elsewhere and a contest here read back, distinguishable by kind.
    assert [c.kind for c in resolve(
        spec(SelectStep(collection="self"), NavigateStep(edge="contest")),
        TargetContext(subject=kael, repo=repo)).values] == ["contest"]


def test_a_roll_resolved_as_a_test_says_so(tracker):
    """A test is recorded as a test at its commit path (`/resolve`), not inferred:
    a pool opposed *later* was still rolled as a test."""
    from transversal.domain import RollKind

    repo, kael, *_ = _world()
    tracker.mark_kind("loc-1", "kael", RollKind.TEST)
    res = resolve(spec(SelectStep(collection="self"), NavigateStep(edge="contest"),
                       FilterStep(field="kind", operator="==", value="test")),
                  TargetContext(subject=kael, repo=repo))
    assert [c.id for c in res.values] == ["contest:loc-1:kael"]


def test_a_committed_contest_says_contest(tracker):
    """Committing through the contest endpoint is what makes it a contest."""
    from transversal.domain import CommittedResult, DieType, RollKind

    repo, kael, *_ = _world()
    _challenge(tracker)
    tracker.store_committed("loc-1", "kael",
                            CommittedResult(total=10, effect_die=DieType.D6, pipeline="pool"))
    states = tracker.get_contests_at("loc-1")
    assert states["kael"].kind == RollKind.CONTEST


# ── location → contests ──────────────────────────────────────

def test_a_location_lists_the_contests_running_there(tracker):
    repo, kael, guard, *_ = _world()
    _challenge(tracker)
    res = resolve(spec(SelectStep(collection="locations"),
                       FilterStep(field="id", operator="==", value="loc-1"),
                       NavigateStep(edge="contests")),
                  TargetContext(subject=kael, repo=repo))
    assert res.errors == []
    # One contest, not one per side.
    assert [c.id for c in res.values] == ["contest:loc-1:kael"]


def test_a_quiet_location_lists_nothing(tracker):
    repo, kael, *_ = _world()
    res = resolve(spec(SelectStep(collection="locations"),
                       FilterStep(field="id", operator="==", value="loc-1"),
                       NavigateStep(edge="contests")),
                  TargetContext(subject=kael, repo=repo))
    assert res.values == []


def test_a_location_can_count_its_contests(tracker):
    repo, kael, *_ = _world()
    _challenge(tracker)
    res = resolve(spec(SelectStep(collection="locations"),
                       FilterStep(field="id", operator="==", value="loc-1"),
                       NavigateStep(edge="contests"),
                       AggregateStep(fn="count")),
                  TargetContext(subject=kael, repo=repo))
    assert res.values == [1]
