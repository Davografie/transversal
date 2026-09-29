"""Tests for target-candidate resolution (choose/random shared resolver)."""

from types import SimpleNamespace

import pytest

from transversal.domain import (
    DieType,
    Effect,
    Entity,
    EntityType,
    ScheduledEvent,
    Timer,
    TimerCombine,
    TraitSetting,
)
from transversal.services.target_scopes import (
    UnknownScope,
    UnsupportedScopeKind,
    parse_scope,
    resolve_candidates,
)


def _e(id, name="", universe=""):
    return SimpleNamespace(id=id, name=name or id, current_universe=universe)


def _t(id, name="", universes=None, traitset_id=""):
    # `traitset_id` belongs on the **definition**: a setting has not recorded which
    # set it is in since B209, and a fixture that put it on the instance is what
    # let a dead `traitsetting.traitset_id` reader go unnoticed ([[B253]]).
    return SimpleNamespace(id=id, name=name or id, universes=universes or [],
                           traitset_id=traitset_id)


def _n(id, name="", universe=""):
    return SimpleNamespace(id=id, name=name or id, universe=universe)


def _rt(id, name="", universe="", life_path=None):
    return SimpleNamespace(id=id, name=name or id, universe=universe, life_path=life_path)


def _proj(id, name="", universe="", entity_id="char-1"):
    return SimpleNamespace(id=id, name=name, universe=universe, entity_id=entity_id)


class TargetRepo:
    """Configurable fake covering every listing method the resolver touches."""

    def __init__(self):
        self.locations = []           # _e objects
        self.all_entities = []        # _e objects
        self.universes = []           # _e objects
        self.projections = []         # _proj objects (entity_id, id, name, universe)
        self.occupants = {}           # loc_id -> [_e]
        self.traits_universe = {}     # universe -> [_t]
        self.traits_traitset = {}     # traitset_id -> [_t]
        self.lifepaths = {}           # universe -> [_n]
        self.roll_tables = []         # [_n]
        self.descendants = {}         # loc_id -> [desc ids]
        self.by_id = {}               # id -> _e
        self.faction_members = {}     # faction_id -> [_e]
        self.scheduled_events = []    # [ScheduledEvent]
        self.traitsettings_by_id = {} # ts_id -> TraitSetting
        self.traitsettings_by_entity = {}  # entity_id -> [TraitSetting]
        self.traitsets = []               # TraitSet-ish objects
        self.entity_factions = {}         # entity_id -> [faction ids]
        self.relationships = {}           # entity_id -> [edge dicts]

    # ── repo surface ─────────────────────────────────
    def list_relationships_for_entity(self, entity_id):
        """Outgoing edges the entity holds about others — the same orientation the
        real read has, which is what lets a path name an edge by its contact."""
        return list(self.relationships.get(entity_id, []))

    def list_entities_by_type(self, entity_type, universe=None):
        if entity_type == EntityType.LOCATION:
            return [e for e in self.locations if not universe or e.current_universe == universe]
        if entity_type == EntityType.UNIVERSE:
            return [e for e in self.universes if not universe or e.current_universe == universe]
        return []

    def get_projections_for_entity(self, entity_id):
        return [p for p in self.projections if p.entity_id == entity_id]

    def list_entities_by_location(self, location_id):
        return self.occupants.get(location_id, [])

    def list_entities_by_locations(self, location_ids):
        out = []
        for lid in location_ids:
            out.extend(self.occupants.get(lid, []))
        return out

    def list_all_entities(self, universe=None):
        return [e for e in self.all_entities if not universe or e.current_universe == universe]

    def get_traits_by_universe(self, universe):
        return self.traits_universe.get(universe, [])

    def get_traits_by_traitset(self, traitset_id):
        return self.traits_traitset.get(traitset_id, [])

    def get_trait(self, trait_id):
        for traits in self.traits_traitset.values():
            for t in traits:
                if t.id == trait_id:
                    return t
        for traits in self.traits_universe.values():
            for t in traits:
                if t.id == trait_id:
                    return t
        return None

    def get_all_traits(self):
        out = []
        for traits in self.traits_universe.values():
            out.extend(traits)
        return out

    def get_traitsettings_by_traitset(self, entity_id, traitset_id):
        return getattr(self, "trait_settings_by_traitset", {}).get((entity_id, traitset_id), [])

    def get_traitsettings_for_entity(self, entity_id):
        return list(getattr(self, "traitsettings_by_entity", {}).get(entity_id, []))

    def get_traitset_by_id(self, traitset_id):
        for ts in self.traitsets:
            if ts.id == traitset_id:
                return ts
        if traitset_id in self.traits_traitset:
            return SimpleNamespace(id=traitset_id, name=traitset_id, universes=[])
        return None

    def get_all_traitsets(self):
        return list(self.traitsets)

    def list_all_lifepaths(self):
        out = []
        for paths in self.lifepaths.values():
            out.extend(paths)
        return out

    def get_lifepath(self, lifepath_id):
        for path in self.list_all_lifepaths():
            if path.id == lifepath_id:
                return path
        known = {"lp-1", "lp-2"}
        return SimpleNamespace(id=lifepath_id, name=lifepath_id, universe="") if lifepath_id in known else None

    def get_roll_table(self, table_id):
        return next((t for t in self.roll_tables if t.id == table_id), None)

    def get_entity_factions(self, entity_id):
        return list(self.entity_factions.get(entity_id, []))

    def get_scheduled_event(self, event_id):
        return next((e for e in self.scheduled_events if e.id == event_id), None)

    def list_lifepaths_by_universe(self, universe):
        return self.lifepaths.get(universe, [])

    def list_roll_tables(self):
        return self.roll_tables

    def list_location_descendants(self, location_id):
        return self.descendants.get(location_id, [])

    def get_entities_by_ids(self, ids):
        return [e for e in (self.get_entity(i) for i in ids) if e is not None]

    def list_all_projections(self):
        return list(self.projections)

    def list_faction_members(self, faction_id):
        return self.faction_members.get(faction_id, [])

    def get_entity(self, entity_id):
        if entity_id in self.by_id:
            return self.by_id[entity_id]
        for e in [*self.locations, *self.universes, *self.all_entities]:
            if getattr(e, "id", None) == entity_id:
                return e
        return None

    def list_scheduled_events(self, target_type=None, target_id=None, target_ids=None):
        events = list(self.scheduled_events)
        if target_type is not None:
            events = [e for e in events if e.target_type == target_type]
        if target_id is not None:
            events = [e for e in events if e.target_id == target_id]
        if target_ids is not None:
            ids = set(target_ids)
            events = [e for e in events if e.target_id in ids]
        return events

    def get_traitsetting(self, ts_id):
        return self.traitsettings_by_id.get(ts_id)


def _entity(**overrides):
    kwargs = dict(id="char-1", type=EntityType.CHARACTER, name="Kael", current_universe="earth")
    kwargs.update(overrides)
    return Entity(**kwargs)


def _ids(candidates):
    return [c.id for c in candidates]


# ── parse_scope ──────────────────────────────────────

def test_parse_scope_bare_and_empty():
    assert parse_scope(None) == (None, "")
    assert parse_scope("") == (None, "")
    assert parse_scope("earth") == (None, "earth")


def test_parse_scope_prefixed():
    assert parse_scope("faction:ru-maffia") == ("faction", "ru-maffia")
    assert parse_scope("subtree:krasnoyarsk") == ("subtree", "krasnoyarsk")


# ── default scope ────────────────────────────────────

def test_default_location_uses_current_universe():
    repo = TargetRepo()
    repo.universes = [_e("earth", universe="earth")]
    repo.locations = [_e("l1", universe="earth"), _e("l2", universe="three_realms")]
    out = resolve_candidates("location", None, _entity(), repo)
    assert _ids(out) == ["l1"]


def test_default_occupant_uses_current_location_and_excludes_self():
    repo = TargetRepo()
    repo.locations = [_e("railyard", "Railyard")]
    repo.occupants = {"railyard": [_e("dmitry"), _e("char-1")]}
    out = resolve_candidates("occupant", None, _entity(current_location="railyard"), repo)
    assert _ids(out) == ["dmitry"]


def test_rating_die_is_scope_independent():
    out = resolve_candidates("rating_die", None, _entity(), TargetRepo())
    assert _ids(out) == [d.value for d in DieType]


# ── explicit scopes ──────────────────────────────────

def test_universe_scope_overrides_current():
    repo = TargetRepo()
    repo.universes = [_e("three_realms", universe="three_realms")]
    repo.locations = [_e("l1", universe="earth"), _e("l2", universe="three_realms")]
    out = resolve_candidates("location", "universe:three_realms", _entity(), repo)
    assert _ids(out) == ["l2"]


def test_universe_current_token_uses_current_universe():
    repo = TargetRepo()
    repo.universes = [_e("earth", universe="earth")]
    repo.locations = [_e("l1", universe="earth"), _e("l2", universe="three_realms")]
    out = resolve_candidates("location", "universe:current", _entity(), repo)
    assert _ids(out) == ["l1"]


def test_location_scope_lists_occupants():
    repo = TargetRepo()
    repo.locations = [_e("railyard", "Railyard")]
    repo.occupants = {"railyard": [_e("dmitry"), _e("char-1")]}
    out = resolve_candidates("occupant", "location:railyard", _entity(), repo)
    assert _ids(out) == ["dmitry"]


def test_subtree_scope_includes_root_and_descendants():
    repo = TargetRepo()
    repo.descendants = {"root": ["a", "b"]}
    repo.by_id = {
        "root": _e("root", "Krasnoyarsk"),
        "a": _e("a", "Railyard"),
        "b": _e("b", "Silo"),
    }
    out = resolve_candidates("location", "subtree:root", _entity(), repo)
    assert _ids(out) == ["root", "a", "b"]


def test_subtree_scope_occupants_across_subtree():
    repo = TargetRepo()
    repo.locations = [_e("root", "Krasnoyarsk"), _e("a", "Railyard")]
    repo.descendants = {"root": ["a"]}
    repo.occupants = {"root": [_e("dmitry")], "a": [_e("ivan"), _e("char-1")]}
    out = resolve_candidates("occupant", "subtree:root", _entity(), repo)
    assert _ids(out) == ["dmitry", "ivan"]


def test_faction_scope_lists_members():
    repo = TargetRepo()
    repo.by_id["mafia"] = _e("mafia", "Mafia")
    repo.faction_members = {"mafia": [_e("dmitry"), _e("ivan")]}
    out = resolve_candidates("entity", "faction:mafia", _entity(), repo)
    assert _ids(out) == ["dmitry", "ivan"]


def test_traitset_scope_lists_traits():
    repo = TargetRepo()
    repo.traits_traitset = {"ts-skills": [_t("medicine", universes=["earth"])]}
    out = resolve_candidates("trait", "traitset:ts-skills", _entity(), repo)
    assert _ids(out) == ["medicine"]
    assert out[0].name == "medicine"


def test_traitset_scope_step_down_filters_to_owned():
    repo = TargetRepo()
    repo.traits_traitset = {"ts-skills": [_t("medicine", traitset_id="ts-skills"),
                                          _t("surgery", traitset_id="ts-skills")]}
    repo.traitsettings_by_entity = {"char-1": [
        SimpleNamespace(id="char-1:medicine", trait_id="medicine"),
    ]}
    out = resolve_candidates("trait", "traitset:ts-skills", _entity(), repo, action="step_down")
    assert _ids(out) == ["medicine"]


def test_traitset_scope_gain_lists_all_traits():
    repo = TargetRepo()
    repo.traits_traitset = {"ts-skills": [_t("medicine", traitset_id="ts-skills"),
                                          _t("surgery", traitset_id="ts-skills")]}
    repo.traitsettings_by_entity = {"char-1": [
        SimpleNamespace(id="char-1:medicine", trait_id="medicine"),
    ]}
    out = resolve_candidates("trait", "traitset:ts-skills", _entity(), repo, action="gain_or_step_up")
    assert _ids(out) == ["medicine", "surgery"]


def test_trait_empty_scope_lists_full_registry():
    repo = TargetRepo()
    repo.traits_universe = {
        "earth": [_t("medicine", universes=["earth"]), _t("surgery", universes=["earth"])],
        "three_realms": [_t("dao", universes=["three_realms"])],
    }
    # Preview context has no concrete universe → the whole registry is shown.
    out = resolve_candidates("trait", None, _entity(current_universe=""), repo)
    assert _ids(out) == ["medicine", "surgery", "dao"]


# ── universe / projection kinds ─────────────────────

def test_universe_kind_lists_universes():
    repo = TargetRepo()
    repo.universes = [_e("earth", universe="earth"), _e("three_realms", universe="three_realms")]
    out = resolve_candidates("universe", None, _entity(), repo)
    assert _ids(out) == ["earth", "three_realms"]


def test_projection_kind_lists_entity_bodies():
    repo = TargetRepo()
    repo.by_id["char-1"] = _entity()
    repo.projections = [
        _proj("char-1:earth", universe="earth"),
        _proj("char-1:three_realms", universe="three_realms"),
        _proj("other:earth", universe="earth", entity_id="other"),
    ]
    out = resolve_candidates("projection", None, _entity(), repo)
    assert _ids(out) == ["char-1:earth", "char-1:three_realms"]
    assert out[0].name == "Kael"  # name falls back to entity name


def test_projection_kind_filters_by_universe_scope():
    repo = TargetRepo()
    repo.by_id["char-1"] = _entity()
    repo.projections = [
        _proj("char-1:earth", universe="earth"),
        _proj("char-1:three_realms", universe="three_realms"),
    ]
    out = resolve_candidates("projection", "universe:three_realms", _entity(), repo)
    assert _ids(out) == ["char-1:three_realms"]


def test_scheduled_event_kind_lists_entity_timers():
    repo = TargetRepo()
    ev = ScheduledEvent(
        id="se-1", target_type="entity", target_id="char-1",
        effect=Effect(type="modify_trait", action="enable", target="iron-will"),
        timers=[Timer(event="scene", remaining=2)],
        combine=TimerCombine.FIRST_TO_FIRE,
    )
    repo.scheduled_events = [ev]
    out = resolve_candidates("scheduled_event", None, _entity(), repo)
    assert _ids(out) == ["se-1"]
    assert out[0].subtitle == "2 scenes"
    assert "enable" in out[0].name


def test_scheduled_event_kind_includes_owned_trait_setting_timers():
    repo = TargetRepo()
    repo.traitsettings_by_id = {
        "ts-1": TraitSetting(id="ts-1", entity_id="char-1", trait_id="iron-will"),
    }
    owned = ScheduledEvent(
        id="se-2", target_type="trait_setting", target_id="ts-1",
        effect=Effect(type="modify_trait", action="enable", target="iron-will"),
        timers=[Timer(event="beat", remaining=1)],
        combine=TimerCombine.FIRST_TO_FIRE,
    )
    foreign = ScheduledEvent(
        id="se-3", target_type="trait_setting", target_id="other-ts",
        effect=Effect(type="modify_trait", action="enable", target="iron-will"),
        timers=[Timer(event="scene", remaining=1)],
        combine=TimerCombine.FIRST_TO_FIRE,
    )
    repo.scheduled_events = [owned, foreign]
    out = resolve_candidates("scheduled_event", None, _entity(), repo)
    assert _ids(out) == ["se-2"]  # only this entity's trait-setting timer


# ── target filter ──────────────────────────────────

def test_location_kind_filters_by_starter_flag():
    repo = TargetRepo()
    repo.universes = [_e("earth", universe="earth")]
    l1 = _e("l1", universe="earth"); l1.starter_location = True
    l2 = _e("l2", universe="earth"); l2.starter_location = False
    l3 = _e("l3", universe="three_realms"); l3.starter_location = True
    repo.locations = [l1, l2, l3]
    out = resolve_candidates("location", None, _entity(), repo, filter={"starter_location": True})
    assert _ids(out) == ["l1"]


def test_location_kind_filter_respects_universe_scope():
    repo = TargetRepo()
    l1 = _e("l1", universe="earth"); l1.starter_location = True
    l2 = _e("l2", universe="three_realms"); l2.starter_location = True
    repo.locations = [l1, l2]
    out = resolve_candidates("location", "universe:three_realms", _entity(), repo, filter={"starter_location": True})
    assert _ids(out) == ["l2"]


# ── roll_table scopes ───────────────────────────────

def test_roll_table_bare_uses_current_universe():
    repo = TargetRepo()
    repo.universes = [_e("earth", universe="earth")]
    repo.roll_tables = [_rt("t1", universe="earth"), _rt("t2", universe="three_realms")]
    out = resolve_candidates("roll_table", None, _entity(), repo)
    assert _ids(out) == ["t1"]


def test_roll_table_universe_scope_filters():
    repo = TargetRepo()
    repo.roll_tables = [_rt("t1", universe="earth"), _rt("t2", universe="three_realms")]
    out = resolve_candidates("roll_table", "universe:three_realms", _entity(), repo)
    assert _ids(out) == ["t2"]


def test_roll_table_life_path_scope_filters():
    repo = TargetRepo()
    repo.roll_tables = [
        _rt("t1", life_path="lp-1"),
        _rt("t2", life_path="lp-2"),
        _rt("t3", life_path=None),
    ]
    out = resolve_candidates("roll_table", "life_path:lp-1", _entity(), repo)
    assert _ids(out) == ["t1"]


def test_roll_table_faction_scope_filters_by_suitable_paths():
    repo = TargetRepo()
    repo.by_id["mafia"] = SimpleNamespace(
        id="mafia", name="Mafia", suitable_life_path_ids=["lp-1", "lp-2"]
    )
    repo.roll_tables = [
        _rt("t1", life_path="lp-1"),
        _rt("t2", life_path="lp-2"),
        _rt("t3", life_path="lp-3"),
        _rt("t4", life_path=None),
    ]
    out = resolve_candidates("roll_table", "faction:mafia", _entity(), repo)
    assert _ids(out) == ["t1", "t2"]


# ── unsupported pairs say so ─────────────────────────

def test_an_unknown_scope_prefix_is_an_error():
    """A prefix the vocabulary does not define used to fall back to the default
    scope, so a typo silently answered a different question."""
    with pytest.raises(UnknownScope) as err:
        resolve_candidates("entity", "__test_custom__:anything", _entity(), TargetRepo())
    assert "known scopes" in str(err.value)


def test_an_unsupported_kind_in_a_scope_names_what_it_supports():
    """`[]` is indistinguishable from "nothing matched", which is how a wrong
    pair (occupants on a faction) once read as an empty roster."""
    with pytest.raises(UnsupportedScopeKind) as err:
        resolve_candidates("location", "faction:mafia", _entity(), TargetRepo())
    message = str(err.value)
    assert "cannot be selected" in message
    assert "entity" in message and "roll_table" in message


def test_a_kind_outside_the_vocabulary_is_an_error():
    with pytest.raises(UnsupportedScopeKind):
        resolve_candidates("die", None, _entity(), TargetRepo())


# ── the declaration is readable ──────────────────────

def test_the_declaration_is_readable_over_graphql():
    """The mapping a caller used to have to extract by reading the source."""
    from types import SimpleNamespace
    from transversal.api.graphql.resolvers.queries_targeting import QueriesTargeting

    declared = QueriesTargeting().target_scopes(SimpleNamespace(context={}))
    by_prefix = {s.prefix: s for s in declared}

    assert set(by_prefix) == {"", "location", "subtree", "faction", "actor_faction",
                              "traitset", "life_path"}
    # Every declared kind resolves, and every resolvable pair is declared: the
    # read is the resolver's own table, not a copy.
    for scope in declared:
        for kind in scope.kinds:
            assert resolve_candidates(kind, f"{scope.prefix}:x" if scope.prefix else None,
                                      _entity(), TargetRepo()) is not None
    assert "occupant" in by_prefix[""].kinds
    assert by_prefix["faction"].kinds == ["entity", "roll_table"]
    assert "faction" in by_prefix["faction"].description.lower()


# ── a stored path defers the actor ───────────────────

def test_a_stored_path_defers_the_actor_into_the_path():
    """A stored rule fires for whoever activates it, so its path must not bake in
    the author's universe or id — it binds them (`select self`) and filters on the
    binding. The picker, which *does* know the entity, resolves eagerly."""
    from transversal.services.target_resolver import TargetContext, resolve
    from transversal.services.target_scopes import ACTOR_AT_RUNTIME, selection_spec

    repo = TargetRepo()
    repo.universes = [_e("earth", universe="earth")]
    repo.locations = [_e("l1", universe="earth"), _e("l2", universe="three_realms")]
    subject = _entity()

    stored = selection_spec("location", "", ACTOR_AT_RUNTIME)
    assert "earth" not in [getattr(st, "value", None) for st in stored.steps], \
        "a stored path hard-coded the author's universe"

    eager = [c.id for c in resolve_candidates("location", None, subject, repo)]
    deferred = [v.id for v in resolve(selection_spec(
        "location", "", ACTOR_AT_RUNTIME), TargetContext(subject=subject, repo=repo)).values]
    assert eager == deferred == ["l1"]


def test_a_stored_path_excludes_whichever_actor_activates_it():
    from transversal.services.target_resolver import TargetContext, resolve
    from transversal.services.target_scopes import ACTOR_AT_RUNTIME, selection_spec

    repo = TargetRepo()
    repo.occupants = {"railyard": [_e("dmitry"), _e("char-1"), _e("ivan")]}
    spec = selection_spec("occupant", "", ACTOR_AT_RUNTIME)

    for actor in ("char-1", "dmitry"):
        subject = _entity(id=actor, current_location="railyard")
        resolved = resolve(spec, TargetContext(subject=subject, repo=repo))
        assert actor not in [v.id for v in resolved.values]
