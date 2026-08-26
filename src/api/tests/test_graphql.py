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
            query { traitsByUniverse(universe: "three_realms") { id name locationRestricted } }
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
