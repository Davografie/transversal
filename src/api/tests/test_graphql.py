"""Integration tests for the GraphQL layer."""

import pytest
from fastapi.testclient import TestClient

from transversal.main import app
from tests.seed_registry import seed_test_trait_registry
from tests.test_entity_manager import InMemoryRepository


@pytest.fixture
def client():
    """Return a TestClient with in-memory data seeded."""
    from transversal import main as api_main

    # Swap in-memory repo before creating the app's singletons
    mem_repo = InMemoryRepository()
    api_main._repo = mem_repo
    api_main._entity_manager = None  # force re-init
    api_main._razmerit_service = None

    # Seed trait registry
    seed_test_trait_registry(mem_repo)

    return TestClient(app)


def _gql(client, query: str, variables: dict | None = None):
    r = client.post("/api/v1/graphql", json={"query": query, "variables": variables or {}})
    assert r.status_code == 200, r.text
    data = r.json()
    assert "errors" not in data, data.get("errors")
    return data["data"]


class TestGraphQLQueries:
    def test_trait_tags_round_trip(self, client):
        """Tags survive create → read (B116: a trait can carry tags)."""
        created = _gql(client, """
            mutation {
              createTrait(input: {id: "trait-tagged-test", name: "Protective Anger",
                                 universes: ["earth"], traitsetId: "ts-earth-skills",
                                 tags: ["violent", "emotion"]}) { id tags }
            }
        """)["createTrait"]
        assert created["tags"] == ["violent", "emotion"]

        # and they come back out of the registry query
        listed = _gql(client, """
            query { traitsByUniverse(universe: "earth") { id tags } }
        """)["traitsByUniverse"]
        row = next(t for t in listed if t["id"] == "trait-tagged-test")
        assert row["tags"] == ["violent", "emotion"]

    def test_traits_by_universe(self, client):
        result = _gql(client, """
            query { traitsByUniverse(universe: "earth") { id name } }
        """)
        names = {t["name"] for t in result["traitsByUniverse"]}
        assert "Hacking" in names
        assert "Agility" in names
        assert "Qi Reserves" not in names  # Three Realms only

    def test_traits_by_universe_three_realms(self, client):
        result = _gql(client, """
            query { traitsByUniverse(universe: "three_realms") { id name } }
        """)
        names = {t["name"] for t in result["traitsByUniverse"]}
        assert "Qi Reserves" in names
        assert "Sword Intent" in names
        assert "Hacking" not in names

    def test_traitsets_by_universe(self, client):
        result = _gql(client, """
            query { traitsetsByUniverse(universe: "earth") { id name } }
        """)
        names = {ts["name"] for ts in result["traitsetsByUniverse"]}
        assert "attributes" in names
        assert "skills" in names

    def test_sfx_editor_vocabularies(self, client):
        result = _gql(client, """
            {
              triggers { value label }
              conditionTypes { value label needsTarget targetPlaceholder }
            }
        """)
        trigger_values = {t["value"] for t in result["triggers"]}
        assert "manual" in trigger_values
        assert "on_character_create" in trigger_values
        ctypes = {c["value"]: c for c in result["conditionTypes"]}
        assert "UNPLACED" in ctypes
        assert "IN_UNIVERSE" in ctypes
        assert ctypes["UNPLACED"]["needsTarget"] is False
        assert ctypes["IN_UNIVERSE"]["needsTarget"] is True
        assert ctypes["IN_UNIVERSE"]["targetPlaceholder"] == "universe key"

    def test_scheduled_events_resolver(self, client):
        from transversal import main as api_main
        from transversal.domain import (
            Effect, ScheduledEvent, Timer, TimerCombine,
        )

        repo = api_main._repo
        repo.create_scheduled_event(ScheduledEvent(
            id="se-test-1",
            target_type="entity",
            target_id="kael",
            effect=Effect(type="entity", action="targeting_ban", target="guard"),
            timers=[Timer(event="scene", remaining=2)],
            combine=TimerCombine.FIRST_TO_FIRE,
            source_sfx_id="sfx-ban",
        ))
        repo.create_scheduled_event(ScheduledEvent(
            id="se-test-2",
            target_type="trait_setting",
            target_id="ts-1",
            effect=Effect(type="modify_trait", action="set", target="trait-1", result="d6"),
            timers=[Timer(event="beat", remaining=1)],
        ))
        repo.create_scheduled_event(ScheduledEvent(
            id="se-test-3",
            target_type="trait_setting",
            target_id="ts-2",
            effect=Effect(type="modify_trait", action="step_down", target="trait-2"),
            timers=[Timer(event="scene", remaining=1)],
        ))

        result = _gql(client, """
            query($t: String, $id: ID) {
              scheduledEvents(targetType: $t, targetId: $id) {
                id targetType targetId sourceSfxId combine
                timers { event remaining }
                effect { type action target }
              }
            }
        """, {"t": "entity", "id": "kael"})

        events = result["scheduledEvents"]
        ev = next(e for e in events if e["id"] == "se-test-1")
        assert ev["targetType"] == "entity"
        assert ev["targetId"] == "kael"
        assert ev["sourceSfxId"] == "sfx-ban"
        assert ev["combine"] == "FIRST_TO_FIRE"
        assert ev["timers"] == [{"event": "scene", "remaining": 2}]
        assert ev["effect"]["action"] == "targeting_ban"

        # target_type filter only (trait_setting) excludes the entity event.
        result2 = _gql(client, """
            query($t: String) { scheduledEvents(targetType: $t) { id } }
        """, {"t": "trait_setting"})
        assert {e["id"] for e in result2["scheduledEvents"]} == {"se-test-2", "se-test-3"}

        # target_ids list filter scopes to exactly the requested owners.
        result3 = _gql(client, """
            query($t: String, $ids: [ID!]) {
              scheduledEvents(targetType: $t, targetIds: $ids) { id }
            }
        """, {"t": "trait_setting", "ids": ["ts-1"]})
        assert [e["id"] for e in result3["scheduledEvents"]] == ["se-test-2"]

    def test_traitset_limit_merges_per_entity_override(self, client):
        from transversal import main as api_main
        from transversal.domain import (
            DieType, Entity, EntityType, TraitSetting, TraitSetSetting,
        )

        repo = api_main._repo
        eid = "char-limit"
        repo.create_entity(Entity(id=eid, type=EntityType.CHARACTER, name="Limit", current_universe="earth"))
        repo.create_traitsetting(TraitSetting(
            id=f"{eid}:trait-earth-strength", entity_id=eid, trait_id="trait-earth-strength",
            traitset_id="ts-earth-attributes", dice=[DieType.D6],
        ))

        def _limit():
            r = _gql(client, """
                query($id: ID!) { entity(id: $id) { traitSettings { traitsetId traitsetLimit } } }
            """, {"id": eid})
            return r["entity"]["traitSettings"][0]["traitsetLimit"]

        # No override → registry default (attributes = 1).
        assert _limit() == 1

        # Per-entity override → effective limit.
        repo.create_traitsetsetting(TraitSetSetting(
            id=f"{eid}:ts-earth-attributes", entity_id=eid, traitset_id="ts-earth-attributes",
            from_type="entity", limit=3,
        ))
        assert _limit() == 3


class TestGraphQLMutations:
    def test_create_entity(self, client):
        result = _gql(client, """
            mutation {
                createEntity(input: {
                    name: "Kael Drift"
                    type: CHARACTER
                    universe: "earth"
                    razmerit: 3
                }) { id name razmerit type }
            }
        """)
        assert result["createEntity"]["name"] == "Kael Drift"
        assert result["createEntity"]["razmerit"] == 3
        assert result["createEntity"]["type"] == "CHARACTER"

    def test_add_trait_setting(self, client):
        # Create entity first
        entity = _gql(client, """
            mutation {
                createEntity(input: {
                    name: "Kael"
                    type: CHARACTER
                    universe: "earth"
                    razmerit: 3
                }) { id }
            }
        """)
        eid = entity["createEntity"]["id"]

        # Add trait setting
        result = _gql(client, """
            mutation($eid: ID!) {
                addTraitSetting(entityId: $eid, input: {
                    traitId: "trait-earth-hacking"
                    traitsetId: "ts-earth-skills"
                    dice: [D10]
                }) { id dice ego }
            }
        """, {"eid": eid})
        ts = result["addTraitSetting"]
        assert ts["dice"] == ["D10"]
        # default_ego=False → anchored to the entity's projection (morph).
        assert ts["ego"] == False

    def test_trait_instance_tags_are_settable(self, client):
        """B116: a trait *instance* carries tags of its own, separate from the
        ones it inherits from the registry trait."""
        entity = _gql(client, """
            mutation {
                createEntity(input: {
                    name: "Kael"
                    type: CHARACTER
                    universe: "earth"
                    razmerit: 3
                }) { id }
            }
        """)
        eid = entity["createEntity"]["id"]

        added = _gql(client, """
            mutation($eid: ID!) {
                addTraitSetting(entityId: $eid, input: {
                    traitId: "trait-earth-hacking"
                    traitsetId: "ts-earth-skills"
                    dice: [D10]
                    tags: ["protective"]
                }) { id tags registryTags }
            }
        """, {"eid": eid})["addTraitSetting"]
        assert added["tags"] == ["protective"]
        # The registry trait itself is untagged, so the inherited half is empty.
        assert added["registryTags"] == []

        updated = _gql(client, """
            mutation($id: ID!) {
                updateTraitSetting(id: $id, input: { tags: ["protective", "violent"] }) {
                    id tags
                }
            }
        """, {"id": added["id"]})["updateTraitSetting"]
        assert updated["tags"] == ["protective", "violent"]

    def test_add_ego_trait(self, client):
        entity = _gql(client, """
            mutation {
                createEntity(input: {
                    name: "Kael"
                    type: CHARACTER
                    universe: "earth"
                    razmerit: 3
                }) { id }
            }
        """)
        eid = entity["createEntity"]["id"]

        result = _gql(client, """
            mutation($eid: ID!) {
                addTraitSetting(entityId: $eid, input: {
                    traitId: "trait-earth-intelligence"
                    traitsetId: "ts-earth-attributes"
                    dice: [D8]
                    fromType: "entity"
                    statement: "Overly analytical"
                }) { dice ego statement }
            }
        """, {"eid": eid})
        ts = result["addTraitSetting"]
        assert ts["dice"] == ["D8"]
        assert ts["ego"] == True
        assert ts["statement"] == "Overly analytical"

    def test_step_up_trait(self, client):
        entity = _gql(client, """
            mutation {
                createEntity(input: {
                    name: "Kael"
                    type: CHARACTER
                    universe: "earth"
                    razmerit: 3
                }) { id }
            }
        """)
        eid = entity["createEntity"]["id"]

        ts = _gql(client, """
            mutation($eid: ID!) {
                addTraitSetting(entityId: $eid, input: {
                    traitId: "trait-earth-hacking"
                    traitsetId: "ts-earth-skills"
                    dice: [D6]
                }) { id dice }
            }
        """, {"eid": eid})
        tsid = ts["addTraitSetting"]["id"]

        stepped = _gql(client, """
            mutation($id: ID!) {
                stepUpTrait(traitSettingId: $id) { dice }
            }
        """, {"id": tsid})
        assert stepped["stepUpTrait"]["dice"] == ["D8"]

    def test_razmerit_flow(self, client):
        entity = _gql(client, """
            mutation {
                createEntity(input: {
                    name: "Kael"
                    type: CHARACTER
                    universe: "earth"
                    razmerit: 5
                }) { id razmerit }
            }
        """)
        eid = entity["createEntity"]["id"]

        # Spend
        r = _gql(client, """
            mutation($eid: ID!) {
                spendRazmerit(entityId: $eid, amount: 2, reason: "sfx") {
                    fromBalance amount
                }
            }
        """, {"eid": eid})
        assert r["spendRazmerit"]["fromBalance"] == 3

        # Earn
        r = _gql(client, """
            mutation($eid: ID!) {
                earnRazmerit(entityId: $eid, amount: 1, reason: "hitch") {
                    toBalance
                }
            }
        """, {"eid": eid})
        assert r["earnRazmerit"]["toBalance"] == 4

    def test_add_projection(self, client):
        entity = _gql(client, """
            mutation {
                createEntity(input: {
                    name: "Kael"
                    type: CHARACTER
                    universe: "earth"
                }) { id }
            }
        """)
        eid = entity["createEntity"]["id"]

        result = _gql(client, """
            mutation($eid: ID!) {
                addProjection(entityId: $eid, universe: "three_realms", type: CONSCIOUSNESS) {
                    currentUniverse
                    projections { universe transversalType }
                }
            }
        """, {"eid": eid})
        e = result["addProjection"]
        assert e["currentUniverse"] == "three_realms"
        universes = {p["universe"] for p in e["projections"]}
        assert "earth" in universes
        assert "three_realms" in universes


class TestCharacterView:
    def test_character_assembly(self, client):
        entity = _gql(client, """
            mutation {
                createEntity(input: {
                    name: "Kael Drift"
                    type: CHARACTER
                    universe: "earth"
                    razmerit: 3
                }) { id }
            }
        """)
        eid = entity["createEntity"]["id"]

        # Add hacking trait
        _gql(client, """
            mutation($eid: ID!) {
                addTraitSetting(entityId: $eid, input: {
                    traitId: "trait-earth-hacking"
                    traitsetId: "ts-earth-skills"
                    dice: [D10]
                }) { id }
            }
        """, {"eid": eid})

        # Add ego trait
        _gql(client, """
            mutation($eid: ID!) {
                addTraitSetting(entityId: $eid, input: {
                    traitId: "trait-earth-intelligence"
                    traitsetId: "ts-earth-attributes"
                    dice: [D8]
                    fromType: "entity"
                    statement: "Can't leave a puzzle alone"
                }) { id }
            }
        """, {"eid": eid})

        # Query the full character
        cv = _gql(client, """
            query($id: ID!) {
                character(id: $id) {
                    entity { name razmerit }
                    projections { universe }
                    traitSettings { dice ego traitId }
                }
            }
        """, {"id": eid})
        c = cv["character"]
        assert c["entity"]["name"] == "Kael Drift"
        assert len(c["traitSettings"]) == 2
        assert len(c["projections"]) == 1


class TestTargetCatalogGraphQL:
    def test_target_catalog(self, client):
        result = _gql(client, """
            query {
                targetCatalog {
                    elements { name label }
                    edges { name source targets cardinality label }
                    fields { element name type }
                    aggregations { name label output needsField }
                    collections { name element label singular }
                }
            }
        """)
        cat = result["targetCatalog"]
        element_names = {e["name"] for e in cat["elements"]}
        assert {"die", "traitsetting", "trait", "traitset", "entity", "projection", "location", "universe"} <= element_names

        # die → traitsetting edge, single-typed
        die_edges = [e for e in cat["edges"] if e["source"] == "die"]
        ts_edge = next(e for e in die_edges if e["name"] == "traitsetting")
        assert ts_edge["targets"] == ["traitsetting"]
        assert ts_edge["cardinality"] == "one"

        # collections seed the wizard's first step
        cols = {c["name"]: c for c in cat["collections"]}
        assert cols["self"]["singular"] is True
        assert cols["rolled_dice"]["element"] == "die"

        # count needs no field; min does
        aggs = {a["name"]: a for a in cat["aggregations"]}
        assert aggs["count"]["needsField"] is False
        assert aggs["min"]["needsField"] is True

    def test_trace_target_spec_one_trick(self, client):
        result = _gql(client, """
            query($input: TargetSpecInput!, $e: String, $c: String) {
                traceTargetSpec(input: $input, destinationElement: $e, destinationCardinality: $c) {
                    types { element cardinality }
                    errors { stepIndex message }
                    valid
                }
            }
        """, {
            "input": {
                "steps": [
                    {"kind": "select", "collection": "rolled_dice"},
                    {"kind": "filter", "field": "source_kind", "operator": "==", "value": "trait"},
                    {"kind": "navigate", "edge": "traitsetting", "dedup": True},
                ],
            },
            "e": "traitsetting",
            "c": "many",
        })
        tr = result["traceTargetSpec"]
        assert tr["errors"] == []
        assert [t["element"] for t in tr["types"]] == ["die", "die", "traitsetting"]
        assert [t["cardinality"] for t in tr["types"]] == ["many", "many", "many"]
        assert tr["valid"] is True

    def test_trace_target_spec_reports_bad_edge(self, client):
        result = _gql(client, """
            query($input: TargetSpecInput!) {
                traceTargetSpec(input: $input) {
                    types { element cardinality }
                    errors { stepIndex message }
                    valid
                }
            }
        """, {
            "input": {
                "steps": [
                    {"kind": "select", "collection": "rolled_dice"},
                    {"kind": "navigate", "edge": "nope"},
                ],
            },
        })
        tr = result["traceTargetSpec"]
        assert any("no edge die.nope" in e["message"] for e in tr["errors"])
        assert tr["types"][1]["element"] == ""
        assert tr["valid"] is False

    def test_trace_target_spec_cardinality_mismatch(self, client):
        result = _gql(client, """
            query($input: TargetSpecInput!, $e: String, $c: String) {
                traceTargetSpec(input: $input, destinationElement: $e, destinationCardinality: $c) {
                    valid errors { stepIndex message }
                }
            }
        """, {
            "input": {
                "steps": [
                    {"kind": "select", "collection": "rolled_dice"},
                    {"kind": "navigate", "edge": "traitsetting"},
                ],
            },
            "e": "traitsetting",
            "c": "one",
        })
        tr = result["traceTargetSpec"]
        assert tr["valid"] is False

    def test_trace_target_spec_choose_collapses_many_to_one(self, client):
        result = _gql(client, """
            query($input: TargetSpecInput!, $e: String, $c: String) {
                traceTargetSpec(input: $input, destinationElement: $e, destinationCardinality: $c) {
                    types { element cardinality }
                    errors { stepIndex message }
                    valid
                }
            }
        """, {
            "input": {
                "steps": [
                    {"kind": "select", "collection": "rolled_dice"},
                    {"kind": "choose", "count": 1},
                ],
            },
            "e": "die",
            "c": "one",
        })
        tr = result["traceTargetSpec"]
        assert tr["errors"] == []
        assert [t["element"] for t in tr["types"]] == ["die", "die"]
        assert [t["cardinality"] for t in tr["types"]] == ["many", "one"]
        assert tr["valid"] is True


class TestEffectTargetSpecGraphQL:
    def test_target_spec_round_trips_through_graphql(self):
        from transversal.api.graphql.schema import _effect_to_gql, _effect_input_to_domain
        from transversal.domain import Effect as DomainEffect
        from transversal.domain import EffectTiming
        from transversal.services.target_spec import LiteralStep, TargetSpec

        eff = DomainEffect(
            timing=EffectTiming.IMMEDIATE, type="modify_trait", action="gain", target="self",
            target_spec=TargetSpec(steps=[LiteralStep(element="trait", value="trait-x")]),
        )

        gql = _effect_to_gql(eff)
        assert gql.target_spec == {"steps": [{"kind": "literal", "element": "trait", "value": "trait-x", "output": None}]}

        back = _effect_input_to_domain(_make_effect_input(gql))
        assert back.target_spec is not None
        assert back.target_spec.steps[0].element == "trait"
        assert back.target_spec.steps[0].value == "trait-x"


def _make_effect_input(gql_effect):
    from transversal.api.graphql.types import EffectInput
    return EffectInput(
        timing=gql_effect.timing, type=gql_effect.type, action=gql_effect.action,
        target=gql_effect.target, entity=gql_effect.entity, result=gql_effect.result,
        target_scope=gql_effect.target_scope, entity_scope=gql_effect.entity_scope,
        target_filter=gql_effect.target_filter, die_filter=gql_effect.die_filter,
        negative=gql_effect.negative, context=gql_effect.context,
        target_spec=gql_effect.target_spec,
    )


# ── ego across a sub-trait chain ─────────────────────────────────
#
# A sub-trait is anchored to its parent, so it is ego when the *root* of its
# chain is entity-anchored. Reporting morph unconditionally was cosmetic at one
# level of nesting; under recursive containers it mislabels every descendant.

def test_sub_trait_inherits_ego_from_the_root_of_its_chain():
    from types import SimpleNamespace as NS

    from transversal.api.graphql.type_defs.traits import _resolve_ego

    class Repo:
        def __init__(self, settings):
            self._s = settings

        def get_traitsetting(self, sid):
            return self._s.get(sid)

        def get_relationship_by_key(self, key):
            return None

    root = NS(id="e:trait", from_type="entity", entity_id="e", parent_traitsetting_id=None)
    sub = NS(id="e:trait:sub", from_type="traitsetting", entity_id="e",
             parent_traitsetting_id="e:trait")
    deep = NS(id="e:trait:sub:deep", from_type="traitsetting", entity_id="e",
              parent_traitsetting_id="e:trait:sub")
    repo = Repo({"e:trait": root, "e:trait:sub": sub})

    assert _resolve_ego(root, repo) is True
    assert _resolve_ego(sub, repo) is True    # inherits the entity anchor
    assert _resolve_ego(deep, repo) is True   # …through two levels

    # A projection-anchored root makes the whole chain morph.
    body = NS(id="e:body", from_type="projection", entity_id="e", parent_traitsetting_id=None)
    body_sub = NS(id="e:body:sub", from_type="traitsetting", entity_id="e",
                  parent_traitsetting_id="e:body")
    body_repo = Repo({"e:body": body})
    assert _resolve_ego(body, body_repo) is False
    assert _resolve_ego(body_sub, body_repo) is False

    # A parent loop terminates rather than spinning.
    a = NS(id="a", from_type="traitsetting", entity_id="e", parent_traitsetting_id="b")
    b = NS(id="b", from_type="traitsetting", entity_id="e", parent_traitsetting_id="a")
    assert _resolve_ego(a, Repo({"a": a, "b": b})) is False
