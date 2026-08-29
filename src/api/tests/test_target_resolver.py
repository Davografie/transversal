"""Tests for the target spec resolver."""

from types import SimpleNamespace as NS

from transversal.services.target_resolver import (
    TargetContext,
    register_edge,
    resolve,
    serialize_candidates,
)
from transversal.services.target_spec import (
    AggregateStep,
    ChooseStep,
    FilterStep,
    NavigateStep,
    RandomStep,
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


def test_location_to_difficulty_pool_edge():
    loc = NS(id="loc-1", type="location", current_location=None, current_universe="earth")
    repo = FakeRepo(entities={"loc-1": loc})
    ctx = TargetContext(repo=repo, collections={"locations": [loc]})
    res = resolve(spec(SelectStep(collection="locations"), NavigateStep(edge="difficulty_pool")), ctx)
    assert res.errors == []
    assert res.values == [{"id": "difficulty:loc-1", "owner_id": "loc-1", "location_id": "loc-1", "kind": "difficulty"}]


def test_entity_to_pool_edge():
    kael, repo = _one_trick_world()
    ctx = TargetContext(subject=kael, repo=repo, collections={"occupants": [kael]})
    res = resolve(spec(SelectStep(collection="occupants"), NavigateStep(edge="pool")), ctx)
    assert res.errors == []
    assert res.values == [{"id": "pool:kael", "owner_id": "kael", "location_id": "loc-1", "kind": "pool"}]


def test_missing_collection_is_an_error():
    res = resolve(spec(SelectStep(collection="rolled_dice")), TargetContext())
    assert res.errors and "not provided" in res.errors[0].message


def test_select_occupants_is_seeded_from_subject_location():
    kael, repo = _one_trick_world()
    ctx = TargetContext(subject=kael, repo=repo)  # no collections provided
    res = resolve(spec(SelectStep(collection="occupants")), ctx)
    assert res.errors == []
    assert [v.id for v in res.values] == ["kael", "gmc-1"]


def test_select_self_traitsettings_is_seeded_from_subject():
    kael, repo = _one_trick_world()
    ctx = TargetContext(subject=kael, repo=repo)  # no collections provided
    res = resolve(spec(SelectStep(collection="self_traitsettings")), ctx)
    assert res.errors == []
    assert [v.id for v in res.values] == ["kael:trait-martial", "kael:trait-qi"]


def test_select_variable_seeds_typed_binding():
    from transversal.services.target_resolver import Binding
    kael, repo = _one_trick_world()
    ctx = TargetContext(subject=kael, repo=repo, bindings={"complication": Binding(value="gmc-1:trait-martial", element="traitsetting")})
    res = resolve(spec(SelectStep(collection="variable", variable="complication")), ctx)
    assert res.errors == []
    assert [v.id for v in res.values] == ["gmc-1:trait-martial"]


def test_select_variable_requires_typed_binding():
    from transversal.services.target_resolver import Binding
    kael, repo = _one_trick_world()
    ctx = TargetContext(subject=kael, repo=repo, bindings={"x": Binding(value="abc", element="")})
    res = resolve(spec(SelectStep(collection="variable", variable="x")), ctx)
    assert res.errors and "not bound or untyped" in res.errors[0].message


def test_step_output_is_bound_into_context():
    kael, repo = _one_trick_world()
    ctx = TargetContext(subject=kael, repo=repo)
    res = resolve(spec(SelectStep(collection="self", output="who")), ctx)
    assert res.errors == []
    assert ctx.bindings["who"].value == "kael"
    assert ctx.bindings["who"].element == "entity"


def test_step_output_binds_full_list_when_many():
    kael, repo = _one_trick_world()
    ctx = TargetContext(subject=kael, repo=repo, collections={"rolled_dice": [
        {"ts_id": "die-a", "rating": "d6"}, {"ts_id": "die-b", "rating": "d8"},
    ]})
    res = resolve(spec(SelectStep(collection="rolled_dice", output="friends")), ctx)
    assert res.errors == []
    b = ctx.bindings["friends"]
    assert b.cardinality == "many"
    assert b.values == ["die-a", "die-b"]
    assert b.value == "die-a"
    assert b.element == "die"


def test_select_variable_seeds_many_binding():
    from transversal.services.target_resolver import Binding
    kael, repo = _one_trick_world()
    ctx = TargetContext(subject=kael, repo=repo, bindings={
        "friends": Binding(
            value="kael:trait-martial",
            values=["kael:trait-martial", "kael:trait-qi"],
            element="traitsetting", cardinality="many",
        ),
    })
    res = resolve(spec(SelectStep(collection="variable", variable="friends")), ctx)
    assert res.errors == []
    assert [v.id for v in res.values] == ["kael:trait-martial", "kael:trait-qi"]


def test_select_variable_one_binding_stays_single():
    from transversal.services.target_resolver import Binding
    kael, repo = _one_trick_world()
    ctx = TargetContext(subject=kael, repo=repo, bindings={
        "complication": Binding(value="gmc-1:trait-martial", values=["gmc-1:trait-martial"], element="traitsetting", cardinality="one"),
    })
    res = resolve(spec(SelectStep(collection="variable", variable="complication")), ctx)
    assert res.errors == []
    assert [v.id for v in res.values] == ["gmc-1:trait-martial"]


def _heal_like_spec():
    return spec(
        SelectStep(collection="occupants"),
        ChooseStep(count=1),
        NavigateStep(edge="traitsettings"),
        FilterStep(field="traitset_id", operator="==", value="ts-combat"),
        ChooseStep(count=1),
    )


def test_midpath_choose_emits_pending_then_resumes():
    kael, repo = _one_trick_world()
    ctx = TargetContext(subject=kael, repo=repo)

    # No answers yet → the first choose (index 1) surfaces a pending choice.
    first = resolve(_heal_like_spec(), ctx)
    assert first.errors == []
    assert first.values == []
    assert len(first.pending_choices) == 1
    assert first.pending_choices[0].step_index == 1
    assert [c.id for c in first.pending_choices[0].candidates] == ["kael", "gmc-1"]

    # Answer the first choose → the second choose (index 4) surfaces next.
    second = resolve(_heal_like_spec(), ctx, answers={1: ["kael"]})
    assert second.errors == []
    assert second.values == []
    assert len(second.pending_choices) == 1
    assert second.pending_choices[0].step_index == 4
    assert [c.id for c in second.pending_choices[0].candidates] == ["kael:trait-martial"]

    # Answer both → fully resolved to the chosen complication.
    third = resolve(_heal_like_spec(), ctx, answers={1: ["kael"], 4: ["kael:trait-martial"]})
    assert third.errors == []
    assert third.pending_choices == []
    assert [v.id for v in third.values] == ["kael:trait-martial"]


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


def test_random_picks_single_member_of_set():
    kael, repo = _one_trick_world()
    dice = [
        {"ts_id": "a", "result": 7},
        {"ts_id": "b", "result": 3},
        {"ts_id": "c", "result": 5},
    ]
    ctx = TargetContext(subject=kael, repo=repo, collections={"rolled_dice": dice})
    s = spec(SelectStep(collection="rolled_dice"), RandomStep())
    res = resolve(s, ctx)
    assert res.errors == []
    assert len(res.values) == 1
    assert res.values[0]["ts_id"] in {"a", "b", "c"}


def test_random_picks_subset_without_replacement():
    kael, repo = _one_trick_world()
    dice = [{"ts_id": "a"}, {"ts_id": "b"}, {"ts_id": "c"}, {"ts_id": "d"}]
    ctx = TargetContext(subject=kael, repo=repo, collections={"rolled_dice": dice})
    s = spec(SelectStep(collection="rolled_dice"), RandomStep(count=2))
    res = resolve(s, ctx)
    assert res.errors == []
    assert len(res.values) == 2
    ids = {v["ts_id"] for v in res.values}
    assert len(ids) == 2  # distinct (sampled without replacement)
    assert ids <= {"a", "b", "c", "d"}


def test_random_degrades_gracefully_when_count_exceeds_set():
    kael, repo = _one_trick_world()
    dice = [{"ts_id": "a"}, {"ts_id": "b"}]
    ctx = TargetContext(subject=kael, repo=repo, collections={"rolled_dice": dice})
    s = spec(SelectStep(collection="rolled_dice"), RandomStep(count=5))
    res = resolve(s, ctx)
    assert res.errors == []
    assert [v["ts_id"] for v in res.values] == ["a", "b"]  # whole set returned


def test_choose_emits_pending_choice_and_stops():
    kael, repo = _one_trick_world()
    dice = [{"ts_id": "a", "rating": "d6"}, {"ts_id": "b", "rating": "d8"}]
    ctx = TargetContext(subject=kael, repo=repo, collections={"rolled_dice": dice})
    s = spec(SelectStep(collection="rolled_dice"), ChooseStep())
    res = resolve(s, ctx)
    assert res.errors == []
    assert res.values == []
    assert len(res.pending_choices) == 1
    choice = res.pending_choices[0]
    assert choice.element == "die"
    assert choice.count == 1
    assert [c["ts_id"] for c in choice.candidates] == ["a", "b"]


def test_choose_count_keeps_candidate_set_and_count():
    kael, repo = _one_trick_world()
    dice = [{"ts_id": "a"}, {"ts_id": "b"}, {"ts_id": "c"}]
    ctx = TargetContext(subject=kael, repo=repo, collections={"rolled_dice": dice})
    s = spec(SelectStep(collection="rolled_dice"), ChooseStep(count=2))
    res = resolve(s, ctx)
    assert res.errors == []
    assert len(res.pending_choices) == 1
    assert res.pending_choices[0].count == 2
    assert len(res.pending_choices[0].candidates) == 3


def test_choose_requires_many_collection():
    kael, repo = _one_trick_world()
    ctx = TargetContext(subject=kael, repo=repo)
    s = spec(SelectStep(collection="self"), ChooseStep())
    res = resolve(s, ctx)
    assert any("many-cardinality" in e.message for e in res.errors)
    assert res.pending_choices == []


def test_serialize_candidates_is_data_driven():
    dice = [
        {"ts_id": "a", "rating": "d6", "role": "trait"},
        {"ts_id": "b", "rating": "d8", "role": "difficulty"},
    ]
    out = serialize_candidates("die", dice)
    assert [(c.id, c.name, c.subtitle) for c in out] == [
        ("a", "d6", "trait"),
        ("b", "d8", "difficulty"),
    ]


def test_serialize_pool_candidates_render_friendly_labels():
    out = serialize_candidates("pool", [
        {"id": "difficulty:loc-1", "kind": "difficulty"},
        {"id": "pool:kael", "kind": "pool"},
    ])
    assert [(c.id, c.name) for c in out] == [
        ("difficulty:loc-1", "Difficulty pool"),
        ("pool:kael", "Dice pool"),
    ]
