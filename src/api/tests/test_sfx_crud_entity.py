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


# ── B298 — duplicating a rule ──────────────────────────────────────────────

SFX_SELECTION = """
  id name description trigger sourceKind placement armingScope
  listenerSpec reach boundVariables { name spec }
  conditions { type subject target targets value operator narrative spec }
  effects { timing type action target entity result dieFilter negative context
            targetSpec entitySpec resultSpec ownerSpec refs output
            conditions { type subject target targets value operator narrative spec } }
  duration { timers { event remaining } combine }
"""

CREATE_QUERY = "mutation($input: SfxInput!) { createSfx(input: $input) {" + SFX_SELECTION + "} }"
DUPLICATE_QUERY = "mutation($id: ID!, $name: String) { duplicateSfx(id: $id, name: $name) {" + SFX_SELECTION + "} }"

# One input carrying every field a hand-written client mapping could forget:
# the targeting specs, the named references, the die filter, a multi-valued
# condition, reach, listener scope, bound variables and a duration.
RICH_INPUT = {
    "id": "sfx-source", "name": "Hard Push", "description": "A shove.",
    "trigger": "on_roll", "sourceKind": "trait_setting",
    "placement": "character", "armingScope": "listener_spec",
    "listenerSpec": {"steps": [{"kind": "select", "collection": "self"}]},
    "reach": [{"spec": {"steps": [{"kind": "select", "collection": "traits"}]},
               "flavour": "granted"}],
    "boundVariables": [{"name": "stage_tier", "spec": STAGE_TIER_SPEC}],
    "conditions": [{
        "type": "PHASE", "target": "picking", "targets": ["picking"],
        "value": "d8", "operator": ">=",
        "spec": {"steps": [{"kind": "select", "collection": "self"},
                           {"kind": "evaluate", "field": "count", "operator": "exists"}]},
    }],
    "effects": [{
        "timing": "IMMEDIATE", "type": "modify_trait", "action": "gain",
        "result": "d6",
        "dieFilter": {"role": None, "ts_id": "{trait_setting}"},
        "context": {"projection": "{last_projection}"},
        "targetSpec": {"steps": [{"kind": "select", "collection": "traits"}]},
        "refs": {"recipient": {"value": "{hitch_entity}"}},
        "output": "beast",
    }],
    "duration": {"timers": [{"event": "scene", "remaining": 2}], "combine": "FIRST_TO_FIRE"},
}


def test_a_duplicate_carries_the_whole_rule_and_is_its_own_copy():
    """Fidelity is the point of copying on the server: the copy is made from the
    **stored** document, so no field can be lost to an editor's field mapping —
    and it is a *deep* copy, so editing the variant cannot reach back into the
    original ([[B298]])."""
    repo = SfxRepo()
    _run(repo, CREATE_QUERY, {"input": RICH_INPUT})

    data = _run(repo, DUPLICATE_QUERY, {"id": "sfx-source", "name": "Hard Push (variant)"})
    dup = data["duplicateSfx"]
    assert dup["name"] == "Hard Push (variant)"
    assert dup["id"] == "sfx-hard-push-variant"

    source, copy = repo.sfxs["sfx-source"], repo.sfxs[dup["id"]]
    assert copy.model_dump(exclude={"id", "name"}) == source.model_dump(exclude={"id", "name"})
    # …through the wire too, so the editor that opens on it sees the same rule.
    assert dup["effects"][0]["refs"]["recipient"]["value"] == "{hitch_entity}"
    assert dup["conditions"][0]["targets"] == ["picking"]

    copy.effects[0].refs["recipient"].value = "someone-else"
    copy.conditions[0].targets.append("giving_in")
    copy.effects[0].context["projection"] = "changed"
    assert source.effects[0].refs["recipient"].value == "{hitch_entity}"
    assert source.conditions[0].targets == ["picking"]
    assert source.effects[0].context["projection"] == "{last_projection}"


def test_an_unnamed_duplicate_falls_back_to_name_copy():
    repo = SfxRepo()
    _run(repo, CREATE_QUERY, {"input": RICH_INPUT})
    dup = _run(repo, DUPLICATE_QUERY, {"id": "sfx-source"})["duplicateSfx"]
    assert dup["name"] == "Hard Push (copy)"
    assert dup["id"] == "sfx-hard-push-copy"


def test_a_second_copy_of_one_name_gets_a_free_id():
    """The id is derived from the name, so two variants of one rule must not
    collide on it — ids are the Arango `_key` ([[B298]])."""
    repo = SfxRepo()
    _run(repo, CREATE_QUERY, {"input": RICH_INPUT})
    first = _run(repo, DUPLICATE_QUERY, {"id": "sfx-source", "name": "Hard Push (variant)"})
    second = _run(repo, DUPLICATE_QUERY, {"id": "sfx-source", "name": "Hard Push (variant)"})
    assert first["duplicateSfx"]["id"] == "sfx-hard-push-variant"
    assert second["duplicateSfx"]["id"] == "sfx-hard-push-variant-2"
    assert second["duplicateSfx"]["name"] == "Hard Push (variant)"
    assert set(repo.sfxs) == {"sfx-source", "sfx-hard-push-variant", "sfx-hard-push-variant-2"}


def test_a_duplicate_lands_on_nobody():
    """The author's decision: a copy is *always* unattached. One that silently
    arrived on the same trait as its original would double the rule ([[B298]])."""
    from transversal.domain import SfxOwner

    repo = SfxRepo()
    _run(repo, CREATE_QUERY, {"input": RICH_INPUT})
    # The source is held by a trait instance and, being a plain rule, may also sit
    # in a bucket; neither may be inherited.
    repo.owners["character-1:ts-3"] = SfxOwner(id="character-1:ts-3", sfx_ids=["sfx-source"])
    repo.owners["table"] = SfxOwner(id="table", sfx_ids=["sfx-source"])

    dup = _run(repo, DUPLICATE_QUERY, {"id": "sfx-source", "name": "Hard Push (variant)"})["duplicateSfx"]
    assert repo.owners["character-1:ts-3"].sfx_ids == ["sfx-source"]
    assert repo.owners["table"].sfx_ids == ["sfx-source"]
    assert all(dup["id"] not in (o.sfx_ids or []) for o in repo.owners.values())


def test_a_table_sourced_copy_joins_its_bucket():
    """A `table`/`gm` rule may live *nowhere else*, so the bucket is derived from
    the declaration rather than attached — the copy inherits that, which is not an
    attachment ([[B298]])."""
    from transversal.domain import SfxOwner

    repo = SfxRepo()
    repo.owners["table"] = SfxOwner(id="table", sfx_ids=[])
    # No `reach`: a rule that declares who it reaches is refused by every owner
    # outside that set, and a bucket is not in it — a declaration the bucket
    # cannot satisfy, which is `reach_refusal`'s job rather than this test's.
    _run(repo, CREATE_QUERY, {"input": {**RICH_INPUT, "sourceKind": "table", "reach": []}})
    assert "sfx-source" in repo.owners["table"].sfx_ids, "the source's own membership"

    dup = _run(repo, DUPLICATE_QUERY, {"id": "sfx-source", "name": "Hard Push (variant)"})["duplicateSfx"]
    assert dup["id"] in repo.owners["table"].sfx_ids


def test_duplicating_something_that_is_not_there_raises():
    from transversal.services.effects_engine import EffectsEngine

    repo = SfxRepo()
    result = graphql_sync(
        schema._schema, DUPLICATE_QUERY,
        context_value={"entity_manager": FakeEM(repo), "razmerit_service": None,
                       "effects_engine": EffectsEngine()},
        variable_values={"id": "sfx-nope", "name": "Whatever"},
    )
    assert result.errors, "a missing source must not silently produce an empty rule"
    assert "not found" in str(result.errors[0])
