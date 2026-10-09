"""Regression: SFX CRUD must round-trip Effect.entity / entity_scope."""

from graphql import graphql_sync

from transversal.api.graphql.schema import schema


class FakeEM:
    def __init__(self, repo):
        self.repo = repo


class SfxRepo:
    def __init__(self):
        self.sfxs = {}
        # A rule write consults the owner buckets: a `table`/`gm` rule may live in
        # its bucket and nowhere else, so the write keeps that membership true
        # (`sync_bucket_membership`). Empty = no bucket provisioned, which is the
        # state this double describes.
        self.owners = {}

    def get_sfx_owner(self, owner_id):
        return self.owners.get(owner_id)

    def update_sfx_owner(self, owner):
        self.owners[owner.id] = owner

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
    id effects { type action target entity result negative }
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
            "result": "d4", "negative": True,
            "context": {"steps": "{number_of_hitches}"},
        }],
    }})
    eff = data["createSfx"]["effects"][0]
    assert eff["entity"] == "{hitch_entity}"


BOUND_VARIABLE_QUERY = """
mutation($input: SfxInput!) {
  createSfx(input: $input) { id boundVariables { name spec } }
}
"""

UPDATE_BOUND_VARIABLE_QUERY = """
mutation($input: SfxUpdateInput!) {
  updateSfx(input: $input) { id boundVariables { name spec } }
}
"""

STAGE_TIER_SPEC = {
    "steps": [
        {"kind": "select", "collection": "source"},
        {"kind": "aggregate", "fn": "tier", "field": "rating"},
    ],
}


def test_create_sfx_round_trips_bound_variables():
    """The section is a *stored* declaration, so the wire has to carry it both
    ways. A selection that omitted it, or a mutation that never assigned it,
    would leave the editor authoring a list the server quietly drops."""
    repo = SfxRepo()
    data = _run(repo, BOUND_VARIABLE_QUERY, {"input": {
        "id": "sfx-qi", "name": "Cultivation Stage", "trigger": "on_roll",
        "sourceKind": "trait_setting",
        "boundVariables": [{"name": "stage_tier", "spec": STAGE_TIER_SPEC}],
    }})

    stored = repo.sfxs["sfx-qi"].bound_variables
    assert [bv.name for bv in stored] == ["stage_tier"]
    assert stored[0].spec.steps[1].fn == "tier"
    assert data["createSfx"]["boundVariables"][0]["name"] == "stage_tier"


def test_an_update_can_remove_every_bound_variable():
    """`None` means *unchanged* and `[]` means *none left* — the distinction the
    ticket's "a save that doesn't know a field erases it" lesson cuts both ways
    on: without it, a deleted variable would come back on the next save."""
    repo = SfxRepo()
    _run(repo, BOUND_VARIABLE_QUERY, {"input": {
        "id": "sfx-qi", "name": "Cultivation Stage", "trigger": "on_roll",
        "sourceKind": "trait_setting",
        "boundVariables": [{"name": "stage_tier", "spec": STAGE_TIER_SPEC}],
    }})

    _run(repo, UPDATE_BOUND_VARIABLE_QUERY, {"input": {"id": "sfx-qi"}})
    assert len(repo.sfxs["sfx-qi"].bound_variables) == 1, "an absent field must not clear"

    _run(repo, UPDATE_BOUND_VARIABLE_QUERY, {"input": {"id": "sfx-qi", "boundVariables": []}})
    assert repo.sfxs["sfx-qi"].bound_variables == []
