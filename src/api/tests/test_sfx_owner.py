"""Tests for SFX ownership resolution (`services/sfx_owner.py`).

Uses an in-memory repository double so the resolver is exercised standalone
without a live ArangoDB.
"""

from types import SimpleNamespace

from transversal.services.sfx_owner import get_available_sfx_ids


class Repo:
    """Minimal in-memory double covering every owner surface the resolver reads."""

    def __init__(self):
        self.entity = None
        self.projection = None
        self.owners = {}                # owner_id -> SimpleNamespace(sfx_ids=[...])
        self.trait_settings = []        # SimpleNamespace(sfx_ids=[...], trait_id=...)
        self.traits = {}                # trait_id -> SimpleNamespace(default_sfx_ids=[...])
        self.traitset_settings = []     # SimpleNamespace(sfx_ids=[...])

    def get_entity(self, entity_id):
        return self.entity

    def get_projection(self, projection_id):
        return self.projection

    def get_sfx_owner(self, owner_id):
        return self.owners.get(owner_id)

    def get_effective_traitsettings(self, entity_id, universes):
        return self.trait_settings

    def get_trait(self, trait_id):
        return self.traits.get(trait_id)

    def get_effective_traitsetsettings(self, entity_id, universes):
        return self.traitset_settings


def _entity(sfx_ids=None, current_projection=None):
    return SimpleNamespace(sfx_ids=sfx_ids or [], current_projection=current_projection)


def test_empty_repo_returns_empty():
    repo = Repo()
    repo.entity = _entity()
    assert get_available_sfx_ids("e1", "earth", repo) == []


def test_direct_entity_ownership():
    repo = Repo()
    repo.entity = _entity(sfx_ids=["sfx-a", "sfx-b"])
    assert get_available_sfx_ids("e1", "earth", repo) == ["sfx-a", "sfx-b"]


def test_active_projection_ownership():
    repo = Repo()
    repo.entity = _entity(current_projection="proj-1")
    repo.projection = SimpleNamespace(sfx_ids=["sfx-proj"])
    assert get_available_sfx_ids("e1", "earth", repo) == ["sfx-proj"]


def test_table_owner_included():
    repo = Repo()
    repo.entity = _entity()
    repo.owners = {"table": SimpleNamespace(sfx_ids=["sfx-table"])}
    assert get_available_sfx_ids("e1", "earth", repo) == ["sfx-table"]


def test_gm_owner_is_excluded():
    repo = Repo()
    repo.entity = _entity()
    repo.owners = {"gm": SimpleNamespace(sfx_ids=["sfx-buy-hitch"])}
    assert get_available_sfx_ids("e1", "earth", repo) == []


def test_trait_level_grants():
    repo = Repo()
    repo.entity = _entity()
    repo.trait_settings = [SimpleNamespace(sfx_ids=["sfx-flashback"], trait_id="origin")]
    repo.traits = {"origin": SimpleNamespace(default_sfx_ids=["sfx-default"])}
    assert get_available_sfx_ids("e1", "earth", repo) == ["sfx-default", "sfx-flashback"]


def test_traitset_as_unit_grants():
    repo = Repo()
    repo.entity = _entity()
    repo.traitset_settings = [SimpleNamespace(sfx_ids=["sfx-set"])]
    assert get_available_sfx_ids("e1", "earth", repo) == ["sfx-set"]


def test_union_is_sorted_and_deduplicated():
    repo = Repo()
    repo.entity = _entity(sfx_ids=["sfx-a"])
    repo.owners = {"table": SimpleNamespace(sfx_ids=["sfx-a", "sfx-b"])}
    repo.trait_settings = [SimpleNamespace(sfx_ids=["sfx-c"], trait_id="t1")]
    repo.traits = {"t1": SimpleNamespace(default_sfx_ids=[])}
    repo.traitset_settings = [SimpleNamespace(sfx_ids=["sfx-b"])]
    assert get_available_sfx_ids("e1", "earth", repo) == ["sfx-a", "sfx-b", "sfx-c"]


def test_missing_entity_still_collects_other_surfaces():
    repo = Repo()
    repo.entity = None
    repo.owners = {"table": SimpleNamespace(sfx_ids=["sfx-table"])}
    repo.trait_settings = [SimpleNamespace(sfx_ids=["sfx-trait"], trait_id="t1")]
    repo.traits = {"t1": SimpleNamespace(default_sfx_ids=[])}
    assert get_available_sfx_ids("ghost", "earth", repo) == ["sfx-table", "sfx-trait"]
