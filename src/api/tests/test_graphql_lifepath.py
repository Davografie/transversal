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
        self.historical_records: list = []

    def get_entity(self, eid):
        return self.entities.get(eid)

    def update_entity(self, e):
        self.entities[e.id] = e
        return e

    def get_lifepath(self, lid):
        return self.lifepaths.get(lid)

    def create_lifepath(self, lp):
        self.lifepaths[lp.id] = lp
        return lp

    def update_lifepath(self, lp):
        self.lifepaths[lp.id] = lp
        return lp

    def list_all_lifepaths(self):
        return list(self.lifepaths.values())

    def get_roll_table(self, tid):
        return self.tables.get(tid)

    def list_roll_tables(self, life_path_id=None):
        if life_path_id is not None:
            return [t for t in self.tables.values() if t.life_path == life_path_id]
        return list(self.tables.values())

    def create_roll_table(self, t):
        self.tables[t.id] = t
        return t

    def update_roll_table(self, t):
        self.tables[t.id] = t
        return t

    def delete_roll_table(self, tid):
        return self.tables.pop(tid, None) is not None

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

    def add_historical_record(self, entity_id, record_type, data, universe="", session_id=""):
        self.historical_records.append({
            "entity_id": entity_id,
            "record_type": record_type.value if hasattr(record_type, "value") else record_type,
            "data": data,
            "universe": universe,
            "session_id": session_id,
        })


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
    assert repo.entities["char-1"].pending_terms[""].current_table_id == "tbl-a"

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


def test_roll_table_write_mutations():
    repo = _build()

    created = _run(repo, """
        mutation($input: RollTableInput!) {
            saveRollTable(input: $input) { id name scheme die entries { label } }
        }
    """, {"input": {
        "name": "New Table", "universe": "earth", "scheme": "INDEX", "die": "D6",
        "entries": [{"label": "first"}],
    }})

    table = created["saveRollTable"]
    tid = table["id"]
    assert tid.startswith("rt-")
    assert table["name"] == "New Table"
    assert table["scheme"] == "INDEX"
    assert tid in repo.tables

    updated = _run(repo, """
        mutation($input: RollTableInput!) {
            saveRollTable(input: $input) { id name entries { label } }
        }
    """, {"input": {
        "id": tid, "name": "Renamed", "scheme": "INDEX", "die": "D6",
        "entries": [{"label": "changed"}],
    }})

    assert updated["saveRollTable"]["name"] == "Renamed"
    assert updated["saveRollTable"]["entries"][0]["label"] == "changed"

    deleted = _run(repo, """
        mutation($id: ID!) { deleteRollTable(id: $id) }
    """, {"id": tid})

    assert deleted["deleteRollTable"] is True
    assert tid not in repo.tables


def test_a_roll_table_die_takes_the_table_notation():
    """A table selects on its own die — a d20, a d66, any dN — not the ladder.

    The field is a plain string precisely so widening it cannot widen
    ``DieType``: that enum is what *trait ratings* are authored from, and a d20
    has no business being one. Ladder names still arrive from older callers
    (``"D6"``) and are canonicalised rather than rejected.
    """
    repo = _build()

    for sent, kept in (("D6", "d6"), ("d20", "d20"), ("d66", "d66"), ("d7", "d7"), ("D100", "d100")):
        created = _run(repo, """
            mutation($input: RollTableInput!) {
                saveRollTable(input: $input) { id name die }
            }
        """, {"input": {
            "name": f"{kept} table", "universe": "earth", "scheme": "RANGE", "die": sent,
            "entries": [{"label": "only", "minValue": 1, "maxValue": 100}],
        }})

        saved = created["saveRollTable"]
        assert saved["die"] == kept, sent
        assert str(repo.tables[saved["id"]].die) == kept, sent


def test_a_reserved_variable_is_refused_when_a_row_breaks_it():
    """The write boundary, end to end ([[B285]]).

    A table reserves `picked_location` as `location/one`; a row assigning it from a
    collection resolves `location/many`. That mutation is refused rather than stored,
    because every caller shares this boundary and a reservation nobody enforces is
    decoration. The read half is asserted too: the declared type round-trips, which is
    what stops the editor's next save erasing it.
    """
    from transversal.services.effects_engine import EffectsEngine

    repo = _build()

    created = _run(repo, """
        mutation($input: RollTableInput!) {
            saveRollTable(input: $input) {
                id
                boundVariables { name element cardinality spec }
            }
        }
    """, {"input": {
        "name": "Regions", "universe": "earth", "scheme": "RANGE", "die": "d100",
        "boundVariables": [{"name": "picked_location", "element": "location",
                            "cardinality": "one"}],
        "entries": [{"label": "India", "minValue": 1, "maxValue": 100, "boundVariables": [{
            "name": "picked_location",
            "spec": {"steps": [{"kind": "literal", "element": "location",
                                "value": "loc-india"}]},
        }]}],
    }})

    table = created["saveRollTable"]
    assert table["boundVariables"] == [
        {"name": "picked_location", "element": "location", "cardinality": "one", "spec": None}
    ], "a reservation is a type with no value, and its type survives the round trip"

    before = dict(repo.tables)
    result = graphql_sync(
        schema._schema,
        "mutation($input: RollTableInput!) { saveRollTable(input: $input) { id } }",
        context_value={
            "entity_manager": FakeEM(repo),
            "razmerit_service": None,
            "effects_engine": EffectsEngine(),
        },
        variable_values={"input": {
            "id": table["id"], "name": "Regions", "universe": "earth",
            "scheme": "RANGE", "die": "d100",
            "boundVariables": [{"name": "picked_location", "element": "location",
                                "cardinality": "one"}],
            "entries": [{"label": "India", "minValue": 1, "maxValue": 100,
                         "boundVariables": [{
                             "name": "picked_location",
                             "spec": {"steps": [{"kind": "select", "collection": "locations"}]},
                         }]}],
        }},
    )

    assert result.errors, "a row that breaks the reservation must not save"
    message = str(result.errors[0])
    assert "location/many" in message and "India" in message, message
    assert repo.tables == before, "nothing was written"


def test_a_roll_table_die_rejects_a_value_that_is_not_a_notation():
    """The authoring surface may be a text field, so the edge is validated."""
    from transversal.services.effects_engine import EffectsEngine

    repo = _build()
    before = set(repo.tables)

    result = graphql_sync(
        schema._schema,
        "mutation($input: RollTableInput!) { saveRollTable(input: $input) { id die } }",
        context_value={
            "entity_manager": FakeEM(repo),
            "razmerit_service": None,
            "effects_engine": EffectsEngine(),
        },
        variable_values={"input": {
            "name": "bad", "scheme": "RANGE", "die": "2d6",
            "entries": [{"label": "only", "minValue": 1, "maxValue": 6}],
        }},
    )

    assert result.errors, "a die that is not a notation must not save"
    assert set(repo.tables) == before


def test_save_life_path_persists_its_steps():
    """Regression: `saveLifePath` with steps raised NameError and could never save.

    The converter that maps a step input existed in `converters.py`; the mutation
    never imported it, so every call carrying `steps` died with
    `name '_life_path_step_input_to_domain' is not defined`. The GM life-path
    editor sends steps, so it could not be saved at all.

    Nothing caught it because **no test executed this mutation with steps**. The
    value documents validate against the schema — and a document validating is not
    a resolver running. The build was green, the schema check was green, and the
    first person to press Save found it.
    """
    repo = _build()

    data = _run(repo, """
        mutation($steps: [LifePathStepInput!], $es: String) {
          saveLifePath(
            id: "lp-1", name: "Life on Earth", universe: "earth",
            description: "Where you are from.", entryTableId: "",
            entryStep: $es, steps: $steps
          )
        }
    """, {
        "es": "s1",
        "steps": [
            {
                "id": "s1", "tableId": "tbl-a", "label": "Where", "next": "",
                "bindings": [{
                    "key": "0", "next": "s2", "exitKind": "", "exitPath": "",
                    "enroll": True, "effects": [],
                }],
            },
            {"id": "s2", "tableId": "tbl-b", "label": "Then", "next": "", "bindings": []},
        ],
    })

    assert data["saveLifePath"]["ok"] is True
    saved = repo.lifepaths["lp-1"]
    assert saved.entry_step == "s1"
    assert [s.id for s in saved.steps] == ["s1", "s2"]
    assert saved.steps[0].table_id == "tbl-a"
    binding = saved.steps[0].bindings[0]
    assert (binding.key, binding.next, binding.enroll) == ("0", "s2", True)


def test_save_life_path_without_steps_leaves_the_wrapper_alone():
    """The leave-alone convention the editor relies on: omitting `steps` keeps them.

    A caller editing only a name must not silently unwrap every table the path
    declares, and the migration/MCP paths depend on this too.
    """
    repo = _build()
    repo.lifepaths["lp-1"].steps = _existing_steps()

    _run(repo, """
        mutation {
          saveLifePath(id: "lp-1", name: "Renamed", universe: "earth",
                       description: "d", entryTableId: "")
        }
    """)
    assert repo.lifepaths["lp-1"].name == "Renamed"
    assert [s.id for s in repo.lifepaths["lp-1"].steps] == ["s1"], "steps were dropped"


def _existing_steps():
    from transversal.domain import LifePathStep

    return [LifePathStep(id="s1", table_id="tbl-a", label="Where")]


_TRAIT_LITERAL = {"steps": [{"kind": "literal", "element": "trait", "value": "t-sect"}]}


def test_save_life_path_round_trips_its_own_declarations():
    """[[B290]]: a path and a step both declare names, and both survive a save.

    A field that is written but not read is a delete waiting for a save — the editor
    writes the whole document, so a declaration the read half forgets is erased the
    next time the panel saves for any reason ([[B279]], [[B281]], [[B285]]). The
    `override` flag travels with the declaration it marks, and only here.
    """
    repo = _build()

    data = _run(repo, """
        mutation($b: [BoundVariableInput!], $steps: [LifePathStepInput!]) {
          saveLifePath(
            id: "lp-1", name: "Path", universe: "earth", description: "d",
            entryTableId: "", entryStep: "s1", steps: $steps, boundVariables: $b
          )
        }
    """, {
        "b": [{"name": "sect", "spec": _TRAIT_LITERAL, "override": True}],
        "steps": [{
            "id": "s1", "tableId": "tbl-a", "label": "Where",
            "boundVariables": [{"name": "advance_tr", "spec": _TRAIT_LITERAL}],
        }],
    })

    assert data["saveLifePath"]["ok"] is True
    saved = repo.lifepaths["lp-1"]
    assert [(d.name, d.override) for d in saved.bound_variables] == [("sect", True)]
    assert [(d.name, d.override) for d in saved.steps[0].bound_variables] == [("advance_tr", False)]

    read = _run(repo, """
        query {
          lifePaths {
            id
            boundVariables { name override }
            steps { id boundVariables { name override } }
          }
        }
    """)
    lp = next(p for p in read["lifePaths"] if p["id"] == "lp-1")
    assert lp["boundVariables"] == [{"name": "sect", "override": True}]
    assert lp["steps"][0]["boundVariables"] == [{"name": "advance_tr", "override": False}]


def test_save_life_path_without_declarations_leaves_them_alone():
    """The same leave-alone convention `steps` uses, for the same reason: a caller
    editing only a name must not blank the names every shared table it wraps is
    written against."""
    from transversal.domain import BoundVariable

    repo = _build()
    repo.lifepaths["lp-1"].bound_variables = [BoundVariable(name="sect", element="entity")]

    _run(repo, """
        mutation {
          saveLifePath(id: "lp-1", name: "Renamed", universe: "earth",
                       description: "d", entryTableId: "")
        }
    """)

    assert repo.lifepaths["lp-1"].name == "Renamed"
    assert [d.name for d in repo.lifepaths["lp-1"].bound_variables] == ["sect"]


def test_an_override_is_kept_only_where_a_layer_can_honour_it():
    """`override` says "I mean to replace the table's name" — meaningful on a life
    path or a step, the caller of a shared table. A table's or a row's declaration
    cannot replace anything outside itself, so the flag is cleared there rather than
    stored as a promise no layer can keep."""
    repo = _build()

    created = _run(repo, """
        mutation($input: RollTableInput!) {
            saveRollTable(input: $input) {
                boundVariables { name override }
                entries { boundVariables { name override } }
            }
        }
    """, {"input": {
        "name": "T", "universe": "earth", "scheme": "INDEX", "die": "D6",
        "boundVariables": [{"name": "sect", "element": "trait", "override": True}],
        "entries": [{"label": "r", "boundVariables": [
            {"name": "sect", "spec": _TRAIT_LITERAL, "override": True}]}],
    }})

    table = created["saveRollTable"]
    assert table["boundVariables"][0] == {"name": "sect", "override": False}
    assert table["entries"][0]["boundVariables"][0] == {"name": "sect", "override": False}
