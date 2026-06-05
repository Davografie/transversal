"""Integration tests for the GraphQL layer."""

import pytest
from fastapi.testclient import TestClient

from transversal.main import app
from transversal.db.seed import seed_trait_registry
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
    seed_trait_registry(mem_repo)

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
        assert "hacking" in names
        assert "agility" in names
        assert "qi_reserves" not in names  # Three Realms only

    def test_traits_by_universe_three_realms(self, client):
        result = _gql(client, """
            query { traitsByUniverse(universe: "three_realms") { id name locationRestricted } }
        """)
        names = {t["name"] for t in result["traitsByUniverse"]}
        assert "qi_reserves" in names
        assert "sword_intent" in names
        assert "hacking" not in names

    def test_traitsets_by_universe(self, client):
        result = _gql(client, """
            query { traitsetsByUniverse(universe: "earth") { id name } }
        """)
        names = {ts["name"] for ts in result["traitsetsByUniverse"]}
        assert "attributes" in names
        assert "skills" in names


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
                    dieType: D10
                    rating: "d10"
                }) { id dieType rating ego }
            }
        """, {"eid": eid})
        ts = result["addTraitSetting"]
        assert ts["dieType"] == "D10"
        assert ts["rating"] == "d10"
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
                    dieType: D8
                    rating: "d8"
                    ego: true
                    statement: "Overly analytical"
                }) { dieType ego statement }
            }
        """, {"eid": eid})
        ts = result["addTraitSetting"]
        assert ts["dieType"] == "D8"
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
                    dieType: D6
                    rating: "d6"
                }) { id dieType }
            }
        """, {"eid": eid})
        tsid = ts["addTraitSetting"]["id"]

        stepped = _gql(client, """
            mutation($id: ID!) {
                stepUpTrait(traitSettingId: $id) { dieType }
            }
        """, {"id": tsid})
        assert stepped["stepUpTrait"]["dieType"] == "D8"

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
                    dieType: D10
                    rating: "d10"
                }) { id }
            }
        """, {"eid": eid})

        # Add ego trait
        _gql(client, """
            mutation($eid: ID!) {
                addTraitSetting(entityId: $eid, input: {
                    traitId: "trait-earth-intelligence"
                    traitsetId: "ts-earth-attributes"
                    dieType: D8
                    rating: "d8"
                    ego: true
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
                    traitSettings { dieType ego traitId }
                }
            }
        """, {"id": eid})
        c = cv["character"]
        assert c["entity"]["name"] == "Kael Drift"
        assert len(c["traitSettings"]) == 2
        assert len(c["projections"]) == 1
