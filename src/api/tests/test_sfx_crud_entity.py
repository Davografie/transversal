"""Regression: SFX CRUD must round-trip Effect.entity / entity_scope."""

from graphql import graphql_sync

from transversal.api.graphql.schema import schema


class FakeEM:
    def __init__(self, repo):
        self.repo = repo


class SfxRepo:
    def __init__(self):
        self.sfxs = {}

    def create_sfx(self, sfx):
        self.sfxs[sfx.id] = sfx
        return sfx

    def get_sfx(self, sfx_id):
        return self.sfxs.get(sfx_id)

    def update_sfx(self, sfx):
        self.sfxs[sfx.id] = sfx
        return sfx


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


QUERY = """
mutation($input: SfxInput!) {
  createSfx(input: $input) {
    id effects { type action target entity result targetScope entityScope negative }
  }
}
"""


def test_create_sfx_round_trips_entity_fields():
    repo = SfxRepo()
    data = _run(repo, QUERY, {"input": {
        "id": "sfx-x", "name": "X", "trigger": "hitch",
        "effects": [{
            "timing": "IMMEDIATE", "type": "modify_trait", "action": "gain_or_step_up",
            "target": "{choose_trait}", "entity": "{hitch_entity}",
            "result": "d4", "targetScope": "traitset:ts-complications-a190",
            "entityScope": "subtree:loc-x", "negative": True,
            "context": {"steps": "{number_of_hitches}"},
        }],
    }})
    eff = data["createSfx"]["effects"][0]
    assert eff["entity"] == "{hitch_entity}"
    assert eff["entityScope"] == "subtree:loc-x"
