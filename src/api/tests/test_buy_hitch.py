"""Buy-hitch extra-hitch rule: die stepping + razmerit/botch handling."""

from graphql import graphql_sync

from transversal.api.graphql.schema import schema
from transversal.domain import Entity, EntityType


class FakeEM:
    def __init__(self, repo):
        self.repo = repo


class BuyHitchRepo:
    """Minimal repo backing the buy_hitch mutation (pending-choice path)."""

    def __init__(self):
        self.entities: dict[str, Entity] = {}

    def get_entity(self, eid):
        return self.entities.get(eid)

    def update_entity(self, e):
        self.entities[e.id] = e
        return e

    def get_traitsettings_for_entity(self, eid):
        return []

    def get_relationship_traitsettings(self, edge_key):
        return []

    def get_relationship(self, a, b, t):
        return None

    def get_trait(self, tid):
        return None


def _run(repo, query, variables=None):
    from transversal.services.effects_engine import EffectsEngine

    result = graphql_sync(
        schema._schema,
        query,
        context_value={
            "entity_manager": FakeEM(repo),
            "razmerit_service": None,
            "effects_engine": EffectsEngine(),
        },
        variable_values=variables or {},
    )
    assert result.errors is None, result.errors
    return result.data


def _repo():
    repo = BuyHitchRepo()
    repo.entities["char-1"] = Entity(
        id="char-1", type=EntityType.CHARACTER, name="Kael", current_universe="earth",
    )
    return repo


QUERY = """
mutation($eid: ID!, $n: Int!, $botch: Boolean!) {
  buyHitch(entityId: $eid, hitchesCount: $n, botch: $botch) {
    applied pendingChoices { kind scope effect { type action target result targetScope negative } }
  }
}
"""


def test_buy_hitch_single_hitch_d6_and_earns():
    repo = _repo()
    data = _run(repo, QUERY, {"eid": "char-1", "n": 1, "botch": False})
    assert "earned 1 razmerit" in data["buyHitch"]["applied"]
    assert repo.entities["char-1"].razmerit == 1
    choice = data["buyHitch"]["pendingChoices"][0]
    assert choice["kind"] == "trait"
    assert choice["scope"] == "traitset:ts-complications-a190"
    assert choice["effect"]["type"] == "modify_trait"
    assert choice["effect"]["action"] == "cortex_gain"
    assert choice["effect"]["result"] == "d6"
    assert choice["effect"]["negative"] is True


def test_buy_hitch_extra_hitches_step_up():
    repo = _repo()
    data = _run(repo, QUERY, {"eid": "char-1", "n": 3, "botch": False})
    assert data["buyHitch"]["pendingChoices"][0]["effect"]["result"] == "d10"


def test_buy_hitch_botch_is_free():
    repo = _repo()
    data = _run(repo, QUERY, {"eid": "char-1", "n": 2, "botch": True})
    assert repo.entities["char-1"].razmerit == 0
    assert data["buyHitch"]["applied"] == []
    assert data["buyHitch"]["pendingChoices"][0]["effect"]["result"] == "d8"


def test_buy_hitch_caps_at_d12():
    repo = _repo()
    data = _run(repo, QUERY, {"eid": "char-1", "n": 10, "botch": False})
    assert data["buyHitch"]["pendingChoices"][0]["effect"]["result"] == "d12"
