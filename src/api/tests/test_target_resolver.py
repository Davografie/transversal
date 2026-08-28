"""Tests for the target spec resolver."""

from types import SimpleNamespace as NS

from transversal.services.target_resolver import (
    TargetContext,
    register_edge,
    resolve,
)
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
    def __init__(self, entities=None, traitsettings=None, traits=None, traitsets=None, projections=None):
        self.entities = entities or {}
        self.traitsettings = traitsettings or {}
        self.traits = traits or {}
        self.traitsets = traitsets or {}
        self.projections = projections or {}

    def get_entity(self, eid):
        return self.entities.get(eid)

    def get_traitsetting(self, ts_id):
        return self.traitsettings.get(ts_id)

    def get_trait(self, tid):
        return self.traits.get(tid)

    def get_traitset_by_id(self, tsid):
        return self.traitsets.get(tsid)

    def get_projection(self, pid):
        return self.projections.get(pid)

    def get_projections_for_entity(self, eid):
        return [p for p in self.projections.values() if p.entity_id == eid]

    def get_traitsettings_for_entity(self, eid):
        return [ts for ts in self.traitsettings.values() if ts.entity_id == eid]

    def get_traits_by_traitset(self, tsid):
        return [t for t in self.traits.values() if t.traitset_id == tsid]

    def list_entities_by_location(self, lid):
        return [e for e in self.entities.values() if e.current_location == lid]


def _one_trick_world():
    kael = NS(id="kael", type="character", current_location="loc-1", current_universe="earth",
              current_projection=None, razmerit=0)
    gmc = NS(id="gmc-1", type="gmc", current_location="loc-1", current_universe="earth",
             current_projection=None, razmerit=0)
    ts_martial = NS(id="kael:trait-martial", trait_id="trait-martial", traitset_id="ts-combat",
                    entity_id="kael", projection_id=None, rating="d8")
    ts_qi = NS(id="kael:trait-qi", trait_id="trait-qi", traitset_id="ts-qi",
               entity_id="kael", projection_id=None, rating="d6")
    ts_gmc = NS(id="gmc-1:trait-martial", trait_id="trait-martial", traitset_id="ts-combat",
                entity_id="gmc-1", projection_id=None, rating="d8")
    repo = FakeRepo(
        entities={"kael": kael, "gmc-1": gmc},
        traitsettings={"kael:trait-martial": ts_martial, "kael:trait-qi": ts_qi, "gmc-1:trait-martial": ts_gmc},
        traits={"trait-martial": NS(id="trait-martial", traitset_id="ts-combat", universes=["earth"]),
                "trait-qi": NS(id="trait-qi", traitset_id="ts-qi", universes=["earth"])},
        traitsets={"ts-combat": NS(id="ts-combat", name="Combat"), "ts-qi": NS(id="ts-qi", name="Qi")},
    )
    return kael, repo


def test_one_trick_resolves_to_traitsettings():
    kael, repo = _one_trick_world()
    ctx = TargetContext(subject=kael, repo=repo, collections={
        "rolled_dice": [
            {"ts_id": "kael:trait-martial", "source_kind": "trait", "result": 7},
            {"ts_id": "kael:trait-qi", "source_kind": "trait", "result": 3},
        ],
    })
    s = spec(
        SelectStep(collection="rolled_dice"),
        FilterStep(field="source_kind", value="trait"),
        NavigateStep(edge="traitsetting", dedup=True),
    )
    res = resolve(s, ctx)
    assert res.errors == []
    assert [v.id for v in res.values] == ["kael:trait-martial", "kael:trait-qi"]


def test_example_resolves_gmcs_that_used_set_traits():
    kael, repo = _one_trick_world()
    ctx = TargetContext(subject=kael, repo=repo, collections={
        "rolled_dice": [
            {"ts_id": "kael:trait-martial", "source_kind": "trait", "owner_id": "kael", "result": 7},
            {"ts_id": "gmc-1:trait-martial", "source_kind": "trait", "owner_id": "gmc-1", "result": 5},
        ],
    })
    # dice → traitsetting → filter traitset_id == ts-combat → owning entity → dedup
    s = spec(
        SelectStep(collection="rolled_dice"),
        FilterStep(field="source_kind", value="trait"),
        NavigateStep(edge="traitsetting"),
        FilterStep(field="traitset_id", value="ts-combat"),
        NavigateStep(edge="entity", dedup=True),
    )
    res = resolve(s, ctx)
    assert res.errors == []
    assert [v.id for v in res.values] == ["kael", "gmc-1"]


def test_die_owner_edge_falls_back_to_subject():
    kael, repo = _one_trick_world()
    ctx = TargetContext(subject=kael, repo=repo, collections={
        "rolled_dice": [{"ts_id": "kael:trait-martial", "source_kind": "trait", "result": 7}],
    })
    s = spec(SelectStep(collection="rolled_dice"), NavigateStep(edge="owner"))
    res = resolve(s, ctx)
    assert res.errors == []
    assert [v.id for v in res.values] == ["kael"]


def test_die_owner_edge_uses_owner_id_when_present():
    kael, repo = _one_trick_world()
    ctx = TargetContext(subject=kael, repo=repo, collections={
        "rolled_dice": [{"ts_id": "gmc-1:trait-martial", "source_kind": "trait", "owner_id": "gmc-1", "result": 5}],
    })
    s = spec(SelectStep(collection="rolled_dice"), NavigateStep(edge="owner"))
    res = resolve(s, ctx)
    assert res.errors == []
    assert [v.id for v in res.values] == ["gmc-1"]


def test_dedup_collapses_duplicate_traitsettings():
    kael, repo = _one_trick_world()
    ctx = TargetContext(subject=kael, repo=repo, collections={
        "rolled_dice": [
            {"ts_id": "kael:trait-martial", "source_kind": "trait", "result": 7},
            {"ts_id": "kael:trait-martial", "source_kind": "trait", "result": 5},  # 2d8 → same instance
        ],
    })
    s = spec(SelectStep(collection="rolled_dice"), NavigateStep(edge="traitsetting", dedup=True))
    res = resolve(s, ctx)
    assert res.errors == []
    assert [v.id for v in res.values] == ["kael:trait-martial"]


def test_aggregate_count_and_min():
    kael, repo = _one_trick_world()
    ctx = TargetContext(subject=kael, repo=repo, collections={
        "rolled_dice": [
            {"ts_id": "kael:trait-martial", "source_kind": "trait", "result": 7},
            {"ts_id": "kael:trait-qi", "source_kind": "trait", "result": 3},
        ],
    })
    assert resolve(spec(SelectStep(collection="rolled_dice"), AggregateStep(fn="count")), ctx).values == [2]
    assert resolve(spec(SelectStep(collection="rolled_dice"), AggregateStep(fn="min", field="result")), ctx).values == [3]
    assert resolve(spec(SelectStep(collection="rolled_dice"), AggregateStep(fn="mean", field="result")), ctx).values == [5.0]


def test_select_self_seeds_subject():
    kael, repo = _one_trick_world()
    ctx = TargetContext(subject=kael, repo=repo)
    res = resolve(spec(SelectStep(collection="self")), ctx)
    assert res.errors == []
    assert [v.id for v in res.values] == ["kael"]


def test_missing_collection_is_an_error():
    res = resolve(spec(SelectStep(collection="rolled_dice")), TargetContext())
    assert res.errors and "not provided" in res.errors[0].message


def test_unknown_edge_is_an_error():
    kael, repo = _one_trick_world()
    ctx = TargetContext(subject=kael, repo=repo, collections={"rolled_dice": [{"ts_id": "x", "source_kind": "trait"}]})
    res = resolve(spec(SelectStep(collection="rolled_dice"), NavigateStep(edge="nope")), ctx)
    assert res.errors and "no edge/resolver" in res.errors[0].message


def test_custom_edge_registration_overrides_default():
    from transversal.services import target_resolver
    key = ("die", "traitsetting")
    original = target_resolver._EDGE_RESOLVERS.get(key)
    try:
        register_edge("die", "traitsetting", lambda d, ctx: [NS(id="custom")])
        ctx = TargetContext(repo=None, collections={"rolled_dice": [{"ts_id": "x"}]})
        res = resolve(spec(SelectStep(collection="rolled_dice"), NavigateStep(edge="traitsetting")), ctx)
        assert res.errors == []
        assert [v.id for v in res.values] == ["custom"]
    finally:
        if original is not None:
            target_resolver._EDGE_RESOLVERS[key] = original
        else:
            target_resolver._EDGE_RESOLVERS.pop(key, None)


def test_contains_filters_dice_by_armed_sfx():
    kael, repo = _one_trick_world()
    ctx = TargetContext(subject=kael, repo=repo, collections={
        "rolled_dice": [
            {"ts_id": "kael:trait-martial", "armed_sfx_ids": ["sfx-a", "sfx-b"]},
            {"ts_id": "kael:trait-qi", "armed_sfx_ids": ["sfx-c"]},
        ],
    })
    s = spec(
        SelectStep(collection="rolled_dice"),
        FilterStep(field="armed_sfx_ids", operator="contains", value="sfx-a"),
    )
    res = resolve(s, ctx)
    assert res.errors == []
    assert [v["ts_id"] for v in res.values] == ["kael:trait-martial"]


def test_filter_equality_coerces_int_value():
    kael, repo = _one_trick_world()
    ctx = TargetContext(subject=kael, repo=repo, collections={
        "rolled_dice": [{"ts_id": "a", "result": 7}, {"ts_id": "b", "result": 3}],
    })
    # string-typed spec value still matches the int field
    s = spec(SelectStep(collection="rolled_dice"), FilterStep(field="result", value="7"))
    res = resolve(s, ctx)
    assert res.errors == []
    assert [v["ts_id"] for v in res.values] == ["a"]


def test_filter_ordering_is_numeric_not_lexicographic():
    kael, repo = _one_trick_world()
    ctx = TargetContext(subject=kael, repo=repo, collections={
        "rolled_dice": [{"ts_id": "a", "result": 7}, {"ts_id": "b", "result": 12}],
    })
    s = spec(SelectStep(collection="rolled_dice"), FilterStep(field="result", operator=">", value="9"))
    res = resolve(s, ctx)
    assert res.errors == []
    assert [v["ts_id"] for v in res.values] == ["b"]


def test_literal_step_resolves_via_repo():
    from transversal.services.target_spec import LiteralStep
    kael, repo = _one_trick_world()
    ctx = TargetContext(subject=kael, repo=repo)
    s = spec(LiteralStep(element="trait", value="trait-martial"))
    res = resolve(s, ctx)
    assert res.errors == []
    assert [v.id for v in res.values] == ["trait-martial"]


def test_select_source_resolves_from_context():
    from transversal.services.target_resolver import TargetContext, resolve
    from transversal.services.target_spec import SelectStep, TargetSpec

    class Repo:
        pass

    src = {"id": "char-1:martial", "entity_id": "char-1"}
    ctx = TargetContext(subject=None, repo=Repo(), source=src, source_element="traitsetting")
    res = resolve(TargetSpec(steps=[SelectStep(collection="source")]), ctx)
    assert res.errors == []
    assert [v["id"] for v in res.values] == ["char-1:martial"]


def test_select_source_without_source_is_empty():
    from transversal.services.target_resolver import TargetContext, resolve
    from transversal.services.target_spec import SelectStep, TargetSpec

    res = resolve(TargetSpec(steps=[SelectStep(collection="source")]),
                  TargetContext(subject=None, repo=object(), source=None, source_element="traitsetting"))
    assert res.values == []
    assert res.errors == []


def test_resolve_source_maps_all_kinds():
    from types import SimpleNamespace
    from transversal.services.target_resolver import resolve_source

    repo = SimpleNamespace(
        get_traitsetting=lambda tid: SimpleNamespace(id=tid),
        get_traitsetsetting=lambda tid: SimpleNamespace(id=tid),
        get_entity=lambda eid: SimpleNamespace(id=eid),
        get_projection=lambda pid: SimpleNamespace(id=pid),
    )

    obj, element = resolve_source("trait_setting", "char-1:martial", repo)
    assert element == "traitsetting" and obj.id == "char-1:martial"

    obj, element = resolve_source("traitset_setting", "char-1:ts", repo)
    assert element == "traitsetsetting" and obj.id == "char-1:ts"

    obj, element = resolve_source("entity", "char-1", repo)
    assert element == "entity" and obj.id == "char-1"

    obj, element = resolve_source("projection", "char-1:earth", repo)
    assert element == "projection" and obj.id == "char-1:earth"

    # Unknown kind / empty id / no repo → None.
    assert resolve_source("bogus", "x", repo) is None
    assert resolve_source("trait_setting", "", repo) is None
    assert resolve_source("trait_setting", "x", None) is None
