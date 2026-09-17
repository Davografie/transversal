"""The bulk inverse faction association read — any tie, either direction, in one query.

``get_factions_for_entities`` / ``entityFactions`` answers the GM focus filter's
question ("which factions are associated with these characters/GMCs/assets/
locations") for a **list** of ids, which the per-entity roster read cannot do for
a type chip without unbounded fan-out.

Two semantics are load-bearing and pinned here:

1. **Any tie counts, either direction.** A posture the faction holds toward the
   entity (``faction → entity``) is an association, so this read is deliberately
   broader than the roster read — and the roster's answers are a subset of it.
2. **Direction says where a role may be written.** A roster slot is
   ``entity → faction``; a ``faction → entity`` tie is the organisation's posture.
   The live DB has **333 mirrored pairs**, so a pair often holds both — the
   fixture builds exactly that shape and requires it to collapse to one row.

Live-ArangoDB tests. They build isolated fixtures and tear them down, and skip
when ArangoDB is unavailable.
"""

import pytest

from transversal.db.repository import EntityRepository
from transversal.domain import Entity, EntityType
from transversal.services.entity_manager import EntityManager

try:
    _repo = EntityRepository()
    HAVE_DB = True
except Exception:
    _repo = None
    HAVE_DB = False

pytestmark = pytest.mark.skipif(not HAVE_DB, reason="ArangoDB not available")

F1 = "test-efrac-faction-1"
F2 = "test-efrac-faction-2"
X = "test-efrac-gmc-x"
Y = "test-efrac-gmc-y"
LOC = "test-efrac-location"
_ALL = (F1, F2, X, Y, LOC)


def _cleanup(repo):
    for eid in _ALL:
        repo.delete_entity(eid, rmtree=True)


def _ent(eid: str, etype: EntityType, name: str) -> Entity:
    return Entity(id=eid, type=etype, name=name, current_universe="earth")


def _seed(repo):
    """X and F1 are tied **both** ways; F2 holds a posture toward Y; plus
    non-faction neighbours that must never be returned."""
    _cleanup(repo)
    repo.create_entity(_ent(F1, EntityType.FACTION, "Alpha Sect"))
    repo.create_entity(_ent(F2, EntityType.FACTION, "Beta Sect"))
    repo.create_entity(_ent(X, EntityType.GMC, "X"))
    repo.create_entity(_ent(Y, EntityType.GMC, "Y"))
    repo.create_entity(_ent(LOC, EntityType.LOCATION, "A Place"))

    repo.create_relationship(X, F1, "membership")   # X's roster tie up
    repo.create_relationship(F1, X, "relation")     # the faction's posture down
    repo.create_relationship(X, F2, "relation")     # outgoing, but not a roster slot
    repo.create_relationship(F2, Y, "relation")     # incoming only, for Y
    repo.create_relationship(Y, F1, "relation")     # outgoing only, for Y

    repo.create_relationship(X, Y, "relation")      # a non-faction neighbour
    repo.create_relationship(X, LOC, "relation")    # a non-faction neighbour


def _row(rows, entity_id, faction_id):
    matches = [
        r for r in rows
        if r["entity_id"] == entity_id and r["faction_id"] == faction_id
    ]
    assert len(matches) == 1, f"expected exactly one row for {entity_id}→{faction_id}: {matches}"
    return matches[0]


def test_a_pair_tied_both_ways_collapses_to_one_row_with_both_tie_types():
    repo = _repo
    _seed(repo)

    row = _row(repo.get_factions_for_entities([X]), X, F1)

    assert row == {
        "entity_id": X, "faction_id": F1, "name": "Alpha Sect",
        "out_tie_type": "membership", "in_tie_type": "relation",
    }

    _cleanup(repo)


def test_an_outgoing_tie_alone_reports_only_the_outward_type():
    repo = _repo
    _seed(repo)

    row = _row(repo.get_factions_for_entities([X]), X, F2)

    assert row["out_tie_type"] == "relation"
    assert row["in_tie_type"] == ""

    _cleanup(repo)


def test_an_incoming_posture_alone_reports_no_outward_tie():
    """No outgoing tie means no edge a role could be written onto."""
    repo = _repo
    _seed(repo)

    row = _row(repo.get_factions_for_entities([Y]), Y, F2)

    assert row["out_tie_type"] == ""
    assert row["in_tie_type"] == "relation"

    _cleanup(repo)


def test_non_faction_neighbours_are_not_returned():
    repo = _repo
    _seed(repo)

    rows = repo.get_factions_for_entities([X, Y, LOC])

    assert {r["faction_id"] for r in rows} <= {F1, F2}

    _cleanup(repo)


def test_one_call_covers_many_entities_and_sorts_deterministically():
    repo = _repo
    _seed(repo)

    rows = repo.get_factions_for_entities([Y, X])  # order must not matter

    assert [(r["entity_id"], r["name"]) for r in rows] == [
        (X, "Alpha Sect"), (X, "Beta Sect"),
        (Y, "Alpha Sect"), (Y, "Beta Sect"),
    ]

    _cleanup(repo)


def test_empty_and_unknown_inputs_are_empty_not_errors():
    repo = _repo
    _seed(repo)

    assert repo.get_factions_for_entities([]) == []
    assert repo.get_factions_for_entities(["test-efrac-does-not-exist"]) == []

    _cleanup(repo)


def test_the_roster_read_is_a_subset_of_the_bulk_read():
    """The bulk read is a *second* read, not a widening — but it must contain
    everything the roster read knows, or a panel driven by it would lose a member."""
    repo = _repo
    _seed(repo)

    bulk = {r["faction_id"] for r in repo.get_factions_for_entities([X, Y])}
    roster = set(repo.get_entity_factions(X)) | set(repo.get_entity_factions(Y))

    assert roster <= bulk
    assert roster == {F1}  # only X's membership is a roster slot

    _cleanup(repo)


def _info(repo):
    return type("Info", (), {"context": {"entity_manager": EntityManager(repo)}})()


def test_the_graphql_resolver_exposes_the_read():
    from transversal.api.graphql.resolvers.queries_entities import QueriesEntities

    repo = _repo
    _seed(repo)

    refs = QueriesEntities().entity_factions(_info(repo), [X])

    assert [(r.entity_id, r.faction_id, r.out_tie_type, r.in_tie_type) for r in refs] == [
        (X, F1, "membership", "relation"),
        (X, F2, "relation", ""),
    ]
    assert refs[0].name == "Alpha Sect"

    _cleanup(repo)
