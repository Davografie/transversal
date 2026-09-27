"""Both ends of the registry carry an ``explanation``.

The old app had one on each: ``explanation`` on a trait, ``explainer`` on a trait
set. The trait half has been in the model and in the migration since the registry
landed — and **nothing read or wrote it**, so 118 live explanations were
invisible. The traitset half arrived under the name ``description``, which is not
what it is; it is now ``explanation`` and the old key folds at load.

"The registry only" is the point (the human, 2026-09-26): the explanation
describes the *definition*, so it lives on ``Trait``/``TraitSet`` and
deliberately not on ``TraitSetting``/``TraitSetSetting`` — an instance's own text
is its ``statement`` and ``notes``.

Three layers, because each has failed before in this codebase:
  * the domain fold, which is what keeps 10 live documents readable unchanged;
  * the GraphQL surface, where a *converter* can silently drop a field (the
    `TraitRef` construction sites are four, and a missed one reads as empty);
  * a live-ArangoDB round trip, including a genuinely legacy stored document.
"""

import pytest
from fastapi.testclient import TestClient

from transversal.domain import Trait, TraitSet

U = "expl-test-u"
TS = "ts-expl-test"
TRAIT = "trait-expl-test"


# ── The domain fold ──────────────────────────────────────

def test_legacy_description_key_reads_as_explanation():
    """A document written before the rename still answers."""
    ts = TraitSet.model_validate(
        {"id": TS, "name": "legacy", "universes": [U],
         "description": "why you do the things you do"})
    assert ts.explanation == "why you do the things you do"


def test_explanation_wins_when_both_keys_are_present():
    ts = TraitSet.model_validate(
        {"id": TS, "name": "both", "universes": [U],
         "explanation": "new text", "description": "old text"})
    assert ts.explanation == "new text"


def test_the_stale_description_key_does_not_survive_a_dump():
    """So the next write of the document drops it for good."""
    ts = TraitSet.model_validate(
        {"id": TS, "name": "legacy", "universes": [U], "description": "old text"})
    assert "description" not in ts.model_dump()
    assert ts.model_dump()["explanation"] == "old text"


def test_an_absent_explanation_is_empty_not_null():
    assert TraitSet(id=TS, name="bare", universes=[U]).explanation == ""
    assert Trait(id=TRAIT, name="bare", universes=[U], traitset_id=TS).explanation == ""


# ── The GraphQL surface (in-memory repo) ─────────────────

@pytest.fixture
def client():
    """TestClient over the in-memory repository, as `test_graphql.py` builds it."""
    from transversal.main import app
    from tests.seed_registry import seed_test_trait_registry
    from tests.test_entity_manager import InMemoryRepository

    from transversal import main as api_main

    mem_repo = InMemoryRepository()
    api_main._repo = mem_repo
    api_main._entity_manager = None  # force re-init
    api_main._razmerit_service = None
    seed_test_trait_registry(mem_repo)
    return TestClient(app)


def _gql(client, query: str, variables: dict | None = None):
    r = client.post("/api/v1/graphql", json={"query": query, "variables": variables or {}})
    assert r.status_code == 200, r.text
    data = r.json()
    assert "errors" not in data, data.get("errors")
    return data["data"]


class TestExplanationOverGraphQL:
    def test_a_traitsets_explanation_round_trips(self, client):
        created = _gql(client, f"""
            mutation {{
              createTraitset(id: "{TS}", name: "expl", universes: ["{U}"],
                             explanation: "iconic phrases or roles that define your character") {{
                id explanation
              }}
            }}
        """)["createTraitset"]
        assert created["explanation"] == "iconic phrases or roles that define your character"

        read = _gql(client, f"""
            {{ traitsetsByUniverse(universe: "{U}") {{ id explanation }} }}
        """)["traitsetsByUniverse"]
        assert [t["explanation"] for t in read if t["id"] == TS] == [
            "iconic phrases or roles that define your character"]

    def test_the_deprecated_description_argument_still_writes(self, client):
        """[[mcp-architect]]'s `create_traitset` mutation document declares
        `$description` and always sends it, so the rename must not break it before
        they flip the tool property. `explanation` wins if both are sent."""
        created = _gql(client, f"""
            mutation {{
              createTraitset(id: "{TS}", name: "expl", universes: ["{U}"],
                             description: "via the old name") {{ id explanation }}
            }}
        """)["createTraitset"]
        assert created["explanation"] == "via the old name"

    def test_a_traits_explanation_round_trips(self, client):
        _gql(client, f"""
            mutation {{
              createTraitset(id: "{TS}", name: "expl", universes: ["{U}"]) {{ id }}
            }}
        """)
        created = _gql(client, f"""
            mutation {{
              createTrait(input: {{id: "{TRAIT}", name: "Commune", universes: ["{U}"],
                                  traitsetId: "{TS}", explanation: "with spirits"}}) {{
                id explanation
              }}
            }}
        """)["createTrait"]
        assert created["explanation"] == "with spirits"

        read = _gql(client, f"""
            {{ traitsByUniverse(universe: "{U}") {{ id explanation }} }}
        """)["traitsByUniverse"]
        assert [t["explanation"] for t in read if t["id"] == TRAIT] == ["with spirits"]

    def test_a_traitset_reads_its_traits_explanation(self, client):
        """The `TraitSetRef.traits` resolver builds its own `TraitRef` — the
        fourth construction site, and the one an editor uses to list a set."""
        _gql(client, f"""
            mutation {{
              createTraitset(id: "{TS}", name: "expl", universes: ["{U}"]) {{ id }}
            }}
        """)
        _gql(client, f"""
            mutation {{
              createTrait(input: {{id: "{TRAIT}", name: "Commune", universes: ["{U}"],
                                  traitsetId: "{TS}", explanation: "with spirits"}}) {{ id }}
            }}
        """)
        sets = _gql(client, f"""
            {{ traitsetsByUniverse(universe: "{U}") {{
                 id explanation traits {{ id explanation }}
            }} }}
        """)["traitsetsByUniverse"]
        mine = [s for s in sets if s["id"] == TS][0]
        assert [t["explanation"] for t in mine["traits"]] == ["with spirits"]


# ── Live ArangoDB: the write paths and a genuinely legacy document ──

try:
    from transversal.db.arango import TRAITSETS
    from transversal.db.repository import EntityRepository

    _repo = EntityRepository()
    HAVE_DB = True
except Exception:  # pragma: no cover - the whole class skips
    _repo = None
    HAVE_DB = False


@pytest.mark.skipif(not HAVE_DB, reason="ArangoDB not available")
class TestExplanationInArango:
    """The repository's own create/update, which the in-memory double does not
    implement — and one document written the way the migration wrote it."""

    def setup_method(self):
        self.repo = _repo
        self._cleanup()
        self.repo.create_traitset(TraitSet(id=TS, name="expl", universes=[U]))
        self.repo.create_trait(Trait(id=TRAIT, name="Commune", universes=[U],
                                     traitset_id=TS))

    def teardown_method(self):
        self._cleanup()

    def _cleanup(self):
        self.repo.delete_trait(TRAIT)
        self.repo.delete_traitset(TS)

    def test_a_traitsets_explanation_survives_a_stored_round_trip(self):
        ts = self.repo.get_traitset_by_id(TS)
        ts.explanation = "why you do the things you do"
        self.repo.update_traitset(ts)
        assert self.repo.get_traitset_by_id(TS).explanation == "why you do the things you do"

    def test_a_traits_explanation_survives_a_stored_round_trip(self):
        t = self.repo.get_trait(TRAIT)
        t.explanation = "with spirits"
        self.repo.update_trait(t)
        assert self.repo.get_trait(TRAIT).explanation == "with spirits"

    def test_a_document_stored_under_the_old_key_is_read_and_then_cleaned(self):
        """The live shape: 10 traitsets hold their text in `description`.

        Reading is what has to work without a migration, so this writes the key
        the way `migrate_registry` did and asserts both halves — the read, and the
        `description` key leaving on the next write.
        """
        self.repo.db.collection(TRAITSETS).update(
            {"_key": TS, "description": "the tools and equipment for personal use"})
        assert self.repo.get_traitset_by_id(TS).explanation == (
            "the tools and equipment for personal use")

        ts = self.repo.get_traitset_by_id(TS)
        self.repo.update_traitset(ts)
        raw = self.repo.db.collection(TRAITSETS).get(TS)
        assert raw["explanation"] == "the tools and equipment for personal use"
        assert "description" not in raw
