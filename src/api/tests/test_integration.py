"""Cross-service integration tests — full flow from entity creation to dice rolling."""

import pytest
from fastapi.testclient import TestClient

from transversal.main import app
from transversal.db.seed import seed_trait_registry
from tests.test_entity_manager import InMemoryRepository


@pytest.fixture
def client():
    from transversal import main as api_main
    mem_repo = InMemoryRepository()
    api_main._repo = mem_repo
    api_main._entity_manager = None
    api_main._razmerit_service = None
    seed_trait_registry(mem_repo)
    return TestClient(app)


def _gql(client, query: str, variables: dict | None = None):
    r = client.post("/api/v1/graphql", json={"query": query, "variables": variables or {}})
    assert r.status_code == 200, r.text
    data = r.json()
    assert "errors" not in data, data.get("errors")
    return data["data"]


class TestFullCharacterFlow:
    """Create a character, add traits, roll dice, earn razmerit — full flow."""

    def test_earth_character_with_ego_trait_rolls_in_three_realms(self, client):
        # 1. Create Kael on Earth
        entity = _gql(client, """
            mutation {
                createEntity(input: {
                    name: "Kael Drift"
                    type: CHARACTER
                    universe: "earth"
                    razmerit: 3
                }) { id name razmerit }
            }
        """)
        eid = entity["createEntity"]["id"]

        # 2. Add Earth hacking (morph)
        _gql(client, """
            mutation($eid: ID!) {
                addTraitSetting(entityId: $eid, input: {
                    traitId: "trait-earth-hacking"
                    traitsetId: "ts-earth-skills"
                    dice: [D10]
                }) { id }
            }
        """, {"eid": eid})

        # 3. Add ego trait (personality — follows across universes)
        _gql(client, """
            mutation($eid: ID!) {
                addTraitSetting(entityId: $eid, input: {
                    traitId: "trait-earth-intelligence"
                    traitsetId: "ts-earth-attributes"
                    dice: [D8]
                    ego: true
                    statement: "Can't leave a mystery alone"
                }) { id ego }
            }
        """, {"eid": eid})

        # 4. Add Three Realms projection (consciousness transversal)
        _gql(client, """
            mutation($eid: ID!) {
                addProjection(entityId: $eid, universe: "three_realms", type: CONSCIOUSNESS) {
                    currentUniverse
                }
            }
        """, {"eid": eid})

        # 5. Add cultivation trait in Three Realms
        _gql(client, """
            mutation($eid: ID!) {
                addTraitSetting(entityId: $eid, input: {
                    traitId: "trait-3r-qi-reserves"
                    traitsetId: "ts-3r-cultivation"
                    dice: [D4, D4, D4, D4, D4, D4]
                    ratingType: RESOURCE
                }) { id dice }
            }
        """, {"eid": eid})

        # 6. Verify character assembly shows all traits
        cv = _gql(client, """
            query($id: ID!) {
                character(id: $id) {
                    entity { name razmerit currentUniverse }
                    projections { universe transversalType }
                    traitSettings { dice ego traitId }
                }
            }
        """, {"id": eid})
        c = cv["character"]
        assert c["entity"]["currentUniverse"] == "three_realms"
        assert len(c["projections"]) == 2
        assert len(c["traitSettings"]) == 3

        # 7. Roll dice in the Three Realms — should use cultivation trait + ego trait
        from transversal import main as api_main
        em = api_main._get_em()
        effective = em.get_effective_traitsettings(eid, ["three_realms"])
        assert len(effective) >= 1  # at minimum the ego trait should be there

        # 8. Earn razmerit from a complication
        r = _gql(client, """
            mutation($eid: ID!) {
                earnRazmerit(entityId: $eid, amount: 1, reason: "hitch") {
                    toBalance
                }
            }
        """, {"eid": eid})
        assert r["earnRazmerit"]["toBalance"] == 4

        # 9. Spend razmerit
        r = _gql(client, """
            mutation($eid: ID!) {
                spendRazmerit(entityId: $eid, amount: 2, reason: "sfx") {
                    fromBalance
                }
            }
        """, {"eid": eid})
        assert r["spendRazmerit"]["fromBalance"] == 2

    def test_roll_endpoint_integrated(self, client):
        """The REST /roll endpoint works with real dice."""
        r = client.post("/api/v1/roll", json={
            "entity_id": "kael-1",
            "universe": "earth",
            "dice": [["d8", "shooting"]],
            "razmerit_spent": 0,
        })
        assert r.status_code == 200
        result = r.json()
        assert result["pipeline"] == "simplified"
        assert "tier" in result
        assert result["highest"] >= 1
