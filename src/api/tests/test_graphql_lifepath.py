"""GraphQL wiring tests for life path term execution."""

from graphql import graphql_sync

from transversal.api.graphql.schema import schema
from transversal.domain import (
    Effect,
    EffectTiming,
    Entity,
    EntityType,
    LifePath,
    RollTable,
    RollTableEntry,
    RollTableScheme,
)


class FakeEM:
    def __init__(self, repo):
        self.repo = repo


class GqlRepo:
    """Minimal repo backing startTerm/resolveStep for a two-table chain."""

    def __init__(self):
        self.entities: dict[str, Entity] = {}
        self.lifepaths: dict[str, LifePath] = {}
        self.tables: dict[str, RollTable] = {}
        self.traitsettings: list = []

    def get_entity(self, eid):
        return self.entities.get(eid)

    def update_entity(self, e):
        self.entities[e.id] = e
        return e

    def get_lifepath(self, lid):
        return self.lifepaths.get(lid)

    def get_roll_table(self, tid):
        return self.tables.get(tid)

    def list_roll_tables(self, life_path_id=None):
        if life_path_id is not None:
            return [t for t in self.tables.values() if t.life_path == life_path_id]
        return list(self.tables.values())

    def get_traitsettings_for_entity(self, eid):
        return self.traitsettings

    def create_traitsetting(self, ts):
        self.traitsettings.append(ts)
        return ts

    def update_traitsetting(self, ts):
        return ts

    def get_relationship(self, a, b, t):
        return None

    def get_relationship_traitsettings(self, edge_key):
        return []

    def create_relationship(self, a, b, t, description=""):
        return {}

    def get_trait(self, tid):
        return None


def _entry(label, effects):
    return RollTableEntry(label=label, effects=effects)


def _next(target=""):
    return Effect(
        timing=EffectTiming.IMMEDIATE,
        type="life_path", action="next_step", target=target,
    )


def _build():
    repo = GqlRepo()
    repo.entities["char-1"] = Entity(
        id="char-1", type=EntityType.CHARACTER, name="Kael", current_universe="earth",
    )
    repo.lifepaths["lp-1"] = LifePath(
        id="lp-1", name="Path", universe="earth", entry_table_id="tbl-a",
    )
    repo.tables["tbl-a"] = RollTable(
        id="tbl-a", name="A", universe="earth", scheme=RollTableScheme.INDEX,
        entries=[_entry("to b", [_next("tbl-b")])],
    )
    repo.tables["tbl-b"] = RollTable(
        id="tbl-b", name="B", universe="earth", scheme=RollTableScheme.INDEX,
        entries=[_entry("end", [_next("")])],
    )
    return repo


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


def test_start_term_and_resolve_step_wiring():
    repo = _build()

    started = _run(repo, """
        mutation($eid: ID!, $fid: ID!, $pid: ID!) {
            startTerm(entityId: $eid, factionId: $fid, pathId: $pid) {
                factionId pathId currentTableId continuation
            }
        }
    """, {"eid": "char-1", "fid": "fac-1", "pid": "lp-1"})

    pt = started["startTerm"]
    assert pt["factionId"] == "fac-1"
    assert pt["pathId"] == "lp-1"
    assert pt["currentTableId"] == "tbl-a"
    assert repo.entities["char-1"].pending_term.current_table_id == "tbl-a"

    first = _run(repo, """
        mutation($eid: ID!, $index: Int) {
            resolveStep(entityId: $eid, index: $index) {
                done applied pendingChoices mustered mishapMuster
                tableId entryLabel pendingTerm { currentTableId }
            }
        }
    """, {"eid": "char-1", "index": 1})

    step = first["resolveStep"]
    assert step["done"] is False
    assert step["tableId"] == "tbl-a"
    assert step["pendingTerm"]["currentTableId"] == "tbl-b"

    second = _run(repo, """
        mutation($eid: ID!, $index: Int) {
            resolveStep(entityId: $eid, index: $index) {
                done tableId pendingTerm { currentTableId }
            }
        }
    """, {"eid": "char-1", "index": 1})

    assert second["resolveStep"]["done"] is True


def test_roll_table_queries():
    from transversal.domain import Condition, ConditionType

    repo = _build()
    repo.tables["tbl-a"].life_path = "lp-1"
    repo.tables["tbl-a"].entries[0].conditions = [Condition(type=ConditionType.ALWAYS)]

    listed = _run(repo, """
        query($lp: String) {
            rollTables(lifePathId: $lp) {
                id name lifePath scheme die
                entries { label conditions { type } effects { action target } }
            }
        }
    """, {"lp": "lp-1"})

    tables = listed["rollTables"]
    assert len(tables) == 1
    assert tables[0]["id"] == "tbl-a"
    assert tables[0]["scheme"] == "INDEX"
    assert tables[0]["entries"][0]["label"] == "to b"
    assert tables[0]["entries"][0]["conditions"][0]["type"] == "ALWAYS"
    assert tables[0]["entries"][0]["effects"][0]["action"] == "next_step"

    one = _run(repo, """
        query($id: ID!) {
            rollTable(id: $id) { id name scheme die entries { label effects { action target } } }
        }
    """, {"id": "tbl-a"})

    assert one["rollTable"]["id"] == "tbl-a"
    assert one["rollTable"]["entries"][0]["effects"][0]["target"] == "tbl-b"
