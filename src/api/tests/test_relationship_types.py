"""The relationship-type vocabulary — one answer for two pickers.

[[B72]] / [[B73]]: *Create Relationship*'s **Relationship Type** was free text and a
path's `relationship.type` filter was a bare string. A type is **content** — the
code declares `membership`/`agency`/… and a GM authors the rest (`relation`, a
custom tie) — so neither place can offer a fixed enum, and a typo in either reads
as *"nothing matches"* rather than as a mistake.

The vocabulary therefore comes from the graph, with the code's own wiring first so
the system's types read at the top of a picker.
"""

import pytest

from transversal.services import target_catalog as tc
from transversal.services.effects_registry import EFFECT_ACTION_REGISTRY
from transversal.api.graphql.resolvers.converters import _gql_field_def

try:
    from transversal.db.repository import EntityRepository
    _repo = EntityRepository()
    HAVE_DB = True
except Exception:  # pragma: no cover - environment without Arango
    _repo = None
    HAVE_DB = False


class FakeRepo:
    def __init__(self, types):
        self._types = types

    def list_relationship_types(self):
        return list(self._types)


def _create_relationship_result_field():
    meta = next(m for m in EFFECT_ACTION_REGISTRY if m.action_id == "create_relationship")
    return next(f for f in meta.fields if f.name == "result")


# ── The wiring ────────────────────────────────────────────────

def test_the_filter_field_declares_the_suggest_source():
    """Without it the step is a free-text box, and a typo silently matches nothing."""
    field = tc.field("relationship", "type")
    assert field is not None
    assert field.suggest == "relationship_types"


def test_the_action_field_is_a_picker_fed_by_the_same_vocabulary():
    field = _create_relationship_result_field()
    assert field.field_type == "select", "free text creates edges nothing can find"
    assert field.options_from == "relationship_types"


def test_the_served_action_metadata_carries_the_options():
    served = _gql_field_def(_create_relationship_result_field(),
                            FakeRepo(["membership", "relation"]))
    assert served.field_type == "select"
    assert served.options == ["membership", "relation"]


def test_a_repo_that_cannot_answer_leaves_the_field_usable():
    """An empty vocabulary falls back to the field's own options rather than
    raising — a picker that cannot load must not take the editor down with it."""
    served = _gql_field_def(_create_relationship_result_field(), FakeRepo([]))
    assert served.options == []


# ── The vocabulary itself (live graph) ────────────────────────

@pytest.mark.skipif(not HAVE_DB, reason="ArangoDB not available")
def test_the_declared_types_come_first_and_content_follows():
    """The code's own wiring reads before whatever a GM added — and a declared type
    nothing uses is still offered, or a rule for it could never be authored."""
    from transversal.domain import STRUCTURAL_RELATIONSHIP_TYPES

    types = _repo.list_relationship_types()
    assert types, "the graph has relationships"
    head = types[:len(STRUCTURAL_RELATIONSHIP_TYPES)]
    assert set(head) == set(STRUCTURAL_RELATIONSHIP_TYPES)
    assert types.count("relation") >= 1
    assert len(types) == len(set(types)), "no duplicates"


@pytest.mark.skipif(not HAVE_DB, reason="ArangoDB not available")
def test_every_type_in_the_graph_is_offered():
    """Whatever is really on an edge is in the list — otherwise a filter could not
    name an edge that exists."""
    live = {
        t for t in _repo.db.aql.execute(
            "FOR r IN relationships RETURN DISTINCT r.type")
        if t
    }
    assert live <= set(_repo.list_relationship_types()), live - set(_repo.list_relationship_types())
