"""Regression — ``Player.main_entity`` must not raise on a stale spotlight stamp.

``spotlightRecency`` (B55) resolves each player's ``mainEntity``. A player whose
``last_main_entity_id`` points at a since-deleted entity must not fail the whole
query: the resolver treats the remembered main as absent, falls back to the
designated main (B63), and only then returns null.
"""

from transversal.api.graphql.types import Player as GqlPlayer
from transversal.domain import Entity, EntityType


class _Repo:
    def __init__(self, entities=None, designated=None):
        self._entities = {e.id: e for e in (entities or [])}
        self._designated = designated

    def get_entity(self, entity_id):
        return self._entities.get(entity_id)

    def get_designated_main(self, player_id):
        return self._designated


class _EntityManager:
    def __init__(self, repo):
        self.repo = repo


class _Info:
    def __init__(self, repo):
        self.context = {"entity_manager": _EntityManager(repo)}


def _player(**kw):
    return GqlPlayer(id="player-1", name="Test", **kw)


def _char(eid):
    return Entity(id=eid, type=EntityType.GMC, name=eid, current_universe="earth")


def test_stale_remembered_main_falls_back_to_designated_main():
    repo = _Repo(entities=[_char("main-live")], designated="main-live")
    p = _player(last_main_entity_id="character-deleted")
    assert p.main_entity(_Info(repo)).id == "main-live"


def test_stale_remembered_main_without_designation_is_null():
    repo = _Repo(entities=[], designated=None)
    p = _player(last_main_entity_id="character-deleted")
    assert p.main_entity(_Info(repo)) is None


def test_no_stamp_uses_designated_main():
    repo = _Repo(entities=[_char("main-live")], designated="main-live")
    p = _player()
    assert p.main_entity(_Info(repo)).id == "main-live"


def test_designated_main_that_was_deleted_is_null():
    repo = _Repo(entities=[], designated="main-deleted")
    p = _player()
    assert p.main_entity(_Info(repo)) is None


def test_live_remembered_main_wins_over_designation():
    repo = _Repo(entities=[_char("main-a"), _char("main-b")], designated="main-a")
    p = _player(last_main_entity_id="main-b")
    assert p.main_entity(_Info(repo)).id == "main-b"
