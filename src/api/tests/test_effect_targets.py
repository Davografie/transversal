"""Tests for target-candidate resolution (choose/random shared resolver)."""

from types import SimpleNamespace

from transversal.domain import DieType, Entity, EntityType
from transversal.services.effect_targets import (
    TargetCandidate,
    parse_scope,
    register_scope,
    resolve_candidates,
)


def _e(id, name="", universe=""):
    return SimpleNamespace(id=id, name=name or id, current_universe=universe)


def _t(id, name="", universes=None):
    return SimpleNamespace(id=id, name=name or id, universes=universes or [])


def _n(id, name="", universe=""):
    return SimpleNamespace(id=id, name=name or id, universe=universe)


class TargetRepo:
    """Configurable fake covering every listing method the resolver touches."""

    def __init__(self):
        self.locations = []           # _e objects
        self.all_entities = []        # _e objects
        self.occupants = {}           # loc_id -> [_e]
        self.traits_universe = {}     # universe -> [_t]
        self.traits_traitset = {}     # traitset_id -> [_t]
        self.lifepaths = {}           # universe -> [_n]
        self.roll_tables = []         # [_n]
        self.descendants = {}         # loc_id -> [desc ids]
        self.by_id = {}               # id -> _e
        self.faction_members = {}     # faction_id -> [_e]

    # ── repo surface ─────────────────────────────────
    def list_entities_by_type(self, entity_type, universe=None):
        if entity_type == EntityType.LOCATION:
            return [e for e in self.locations if not universe or e.current_universe == universe]
        return []

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

    def list_lifepaths_by_universe(self, universe):
        return self.lifepaths.get(universe, [])

    def list_roll_tables(self):
        return self.roll_tables

    def list_location_descendants(self, location_id):
        return self.descendants.get(location_id, [])

    def get_entities_by_ids(self, ids):
        return [self.by_id[i] for i in ids if i in self.by_id]

    def list_faction_members(self, faction_id):
        return self.faction_members.get(faction_id, [])


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
    repo.locations = [_e("l1", universe="earth"), _e("l2", universe="three_realms")]
    out = resolve_candidates("location", None, _entity(), repo)
    assert _ids(out) == ["l1"]


def test_default_occupant_uses_current_location_and_excludes_self():
    repo = TargetRepo()
    repo.occupants = {"railyard": [_e("dmitry"), _e("char-1")]}
    out = resolve_candidates("occupant", None, _entity(current_location="railyard"), repo)
    assert _ids(out) == ["dmitry"]


def test_rating_die_is_scope_independent():
    out = resolve_candidates("rating_die", None, _entity(), TargetRepo())
    assert _ids(out) == [d.value for d in DieType]


# ── explicit scopes ──────────────────────────────────

def test_universe_scope_overrides_current():
    repo = TargetRepo()
    repo.locations = [_e("l1", universe="earth"), _e("l2", universe="three_realms")]
    out = resolve_candidates("location", "universe:three_realms", _entity(), repo)
    assert _ids(out) == ["l2"]


def test_location_scope_lists_occupants():
    repo = TargetRepo()
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
    repo.descendants = {"root": ["a"]}
    repo.occupants = {"root": [_e("dmitry")], "a": [_e("ivan"), _e("char-1")]}
    out = resolve_candidates("occupant", "subtree:root", _entity(), repo)
    assert _ids(out) == ["dmitry", "ivan"]


def test_faction_scope_lists_members():
    repo = TargetRepo()
    repo.faction_members = {"mafia": [_e("dmitry"), _e("ivan")]}
    out = resolve_candidates("entity", "faction:mafia", _entity(), repo)
    assert _ids(out) == ["dmitry", "ivan"]


def test_traitset_scope_lists_traits():
    repo = TargetRepo()
    repo.traits_traitset = {"ts-skills": [_t("medicine", universes=["earth"])]}
    out = resolve_candidates("trait", "traitset:ts-skills", _entity(), repo)
    assert _ids(out) == ["medicine"]
    assert out[0].name == "medicine"


# ── extensibility ────────────────────────────────────

def test_register_scope_adds_a_new_prefix():
    def _always(instance_kind, value, entity, repo):
        return [TargetCandidate(id="x", name="X")]

    register_scope("__test_custom__", _always)
    out = resolve_candidates("entity", "__test_custom__:anything", _entity(), TargetRepo())
    assert _ids(out) == ["x"]
