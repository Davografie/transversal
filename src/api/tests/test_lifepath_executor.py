"""Tests for the roll-table life-path term executor."""

from transversal.domain import (
    DieType,
    Effect,
    EffectTiming,
    Enrollment,
    Entity,
    EntityType,
    LifePath,
    RollTable,
    RollTableEntry,
    RollTableScheme,
    TraitSetting,
)
from transversal.services.lifepath_executor import resolve_step, start_term


class FakeTrait:
    def __init__(self, trait_id, traitset_id):
        self.id = trait_id
        self.traitset_id = traitset_id


class ExecutorRepo:
    def __init__(self):
        self.lifepaths = {}
        self.tables = {}
        self.traits = {}
        self.created_traitsettings = []
        self.updated_entities = []
        self.historical_records = []

    def get_lifepath(self, path_id):
        return self.lifepaths.get(path_id)

    def get_roll_table(self, table_id):
        return self.tables.get(table_id)

    def get_traitsettings_for_entity(self, entity_id):
        return []

    def get_relationship(self, entity_id, faction_id, rel_type):
        return {"_key": f"edge:{entity_id}:{faction_id}:membership"}

    def get_relationship_traitsettings(self, edge_key):
        return []

    def get_trait(self, trait_id):
        return self.traits.get(trait_id)

    def update_entity(self, entity):
        self.updated_entities.append(entity.id)

    def create_traitsetting(self, ts):
        self.created_traitsettings.append(ts)

    def update_traitsetting(self, ts):
        pass

    def create_relationship(self, from_id, to_id, rel_type, description=""):
        pass

    def add_historical_record(self, entity_id, record_type, data, universe="", session_id=""):
        self.historical_records.append({
            "entity_id": entity_id,
            "record_type": record_type.value if hasattr(record_type, "value") else record_type,
            "data": data,
            "universe": universe,
            "session_id": session_id,
        })


def _entity(**overrides):
    kwargs = dict(id="char-1", type=EntityType.CHARACTER, name="Kael", current_universe="earth")
    kwargs.update(overrides)
    return Entity(**kwargs)


def _effect(type, action, target="", result=None, context=None):
    return Effect(
        timing=EffectTiming.IMMEDIATE, type=type, action=action,
        target=target, result=result, context=context or {},
    )


def _next(target, return_to=None):
    ctx = {"return_to": return_to} if return_to else {}
    return _effect("life_path", "next_step", target, context=ctx)


def _force_muster():
    return _effect("life_path", "force_muster")


def _gain(trait, die):
    return _effect("modify_trait", "gain", trait, die)


def _table(table_id, entries):
    return RollTable(id=table_id, name=table_id, universe="earth",
                     scheme=RollTableScheme.INDEX, entries=entries)


def _entry(label, effects):
    return RollTableEntry(label=label, effects=effects)


def test_start_term_sets_pending():
    repo = ExecutorRepo()
    repo.lifepaths["lp-1"] = LifePath(id="lp-1", name="P", universe="earth", entry_table_id="tbl-a")
    entity = _entity()
    pt = start_term(entity, "fac-1", "lp-1", repo)
    assert pt.current_table_id == "tbl-a"
    assert pt.faction_id == "fac-1"
    assert pt.path_id == "lp-1"


def test_next_step_advances():
    repo = ExecutorRepo()
    repo.lifepaths["lp-1"] = LifePath(id="lp-1", name="P", universe="earth", entry_table_id="tbl-a")
    repo.tables["tbl-a"] = _table("tbl-a", [_entry("go", [_next("tbl-b")])])
    entity = _entity()
    start_term(entity, "fac-1", "lp-1", repo)
    resolve_step(entity, repo, index=1)
    assert entity.pending_term.current_table_id == "tbl-b"


def test_return_to_continuation():
    repo = ExecutorRepo()
    repo.lifepaths["lp-1"] = LifePath(id="lp-1", name="P", universe="earth", entry_table_id="tbl-a")
    repo.tables["tbl-a"] = _table("tbl-a", [_entry("call", [_next("tbl-shared", return_to="tbl-c")])])
    repo.tables["tbl-shared"] = _table("tbl-shared", [_entry("return", [_next("")])])
    entity = _entity()
    start_term(entity, "fac-1", "lp-1", repo)
    resolve_step(entity, repo, index=1)
    assert entity.pending_term.current_table_id == "tbl-shared"
    assert entity.pending_term.continuation == ["tbl-c"]
    resolve_step(entity, repo, index=1)
    assert entity.pending_term.current_table_id == "tbl-c"


def test_named_exit_return_map():
    repo = ExecutorRepo()
    repo.lifepaths["lp-1"] = LifePath(id="lp-1", name="P", universe="earth", entry_table_id="tbl-a")
    repo.tables["tbl-a"] = _table("tbl-a", [_entry(
        "call", [_next("tbl-survive", return_to={"survived": "tbl-advance", "injured": "tbl-mishap"})],
    )])
    repo.tables["tbl-survive"] = _table("tbl-survive", [
        _entry("survived", [_next("{return:survived}")]),
        _entry("injured", [_next("{return:injured}")]),
    ])
    entity = _entity()
    start_term(entity, "fac-1", "lp-1", repo)

    # Call into the shared table → return map is stored.
    resolve_step(entity, repo, index=1)
    assert entity.pending_term.current_table_id == "tbl-survive"
    assert entity.pending_term.return_map == {"survived": "tbl-advance", "injured": "tbl-mishap"}

    # "survived" exit → advance, map cleared.
    resolve_step(entity, repo, index=1)
    assert entity.pending_term.current_table_id == "tbl-advance"
    assert entity.pending_term.return_map == {}

    # "injured" exit resolves too (fresh call).
    entity.pending_term.current_table_id = "tbl-a"
    resolve_step(entity, repo, index=1)
    resolve_step(entity, repo, index=2)
    assert entity.pending_term.current_table_id == "tbl-mishap"


def test_force_muster_marks_enrollment():
    repo = ExecutorRepo()
    repo.lifepaths["lp-1"] = LifePath(id="lp-1", name="P", universe="earth", entry_table_id="tbl-a")
    repo.tables["tbl-a"] = _table("tbl-a", [_entry("die", [_force_muster()])])
    entity = _entity(life_paths=[Enrollment(faction_id="fac-1", path_id="lp-1", mustered=False)])
    start_term(entity, "fac-1", "lp-1", repo)
    resolve_step(entity, repo, index=1)
    assert entity.pending_term is None
    assert entity.life_paths[0].mustered is True
    assert entity.life_paths[0].mishap_muster is True


def test_mutation_applies():
    repo = ExecutorRepo()
    repo.lifepaths["lp-1"] = LifePath(id="lp-1", name="P", universe="earth", entry_table_id="tbl-a")
    repo.traits["iron-will"] = FakeTrait("iron-will", "ts-x")
    repo.tables["tbl-a"] = _table("tbl-a", [_entry("gain", [_gain("iron-will", "d6")])])
    entity = _entity()
    start_term(entity, "fac-1", "lp-1", repo)
    resolve_step(entity, repo, index=1)
    assert len(repo.created_traitsettings) == 1
    assert repo.created_traitsettings[0].trait_id == "iron-will"
    assert repo.created_traitsettings[0].dice == [DieType.D6]


def test_enroll_records_enrollment():
    repo = ExecutorRepo()
    repo.lifepaths["lp-1"] = LifePath(id="lp-1", name="P", universe="earth", entry_table_id="tbl-a")
    repo.tables["tbl-a"] = _table("tbl-a", [_entry("join", [_effect("life_path", "enroll"), _next("tbl-b")])])
    entity = _entity()
    start_term(entity, "fac-1", "lp-1", repo)
    resolve_step(entity, repo, index=1)
    assert len(entity.life_paths) == 1
    assert entity.life_paths[0].faction_id == "fac-1"
    assert entity.life_paths[0].path_id == "lp-1"
    assert entity.life_paths[0].mustered is False


class EnrollEdgeRepo(ExecutorRepo):
    def __init__(self):
        super().__init__()
        self.created_relationships = []

    def get_relationship(self, entity_id, faction_id, rel_type):
        return None

    def create_relationship(self, from_id, to_id, rel_type, description=""):
        self.created_relationships.append((from_id, to_id, rel_type))


def test_enroll_creates_membership_edge():
    repo = EnrollEdgeRepo()
    repo.lifepaths["lp-1"] = LifePath(id="lp-1", name="P", universe="earth", entry_table_id="tbl-a")
    repo.tables["tbl-a"] = _table("tbl-a", [_entry("join", [_effect("life_path", "enroll")])])
    entity = _entity()
    start_term(entity, "fac-1", "lp-1", repo)
    resolve_step(entity, repo, index=1)
    assert ("char-1", "fac-1", "membership") in repo.created_relationships


def test_muster_marks_mustered_without_mishap():
    repo = ExecutorRepo()
    repo.lifepaths["lp-1"] = LifePath(id="lp-1", name="P", universe="earth", entry_table_id="tbl-a")
    repo.tables["tbl-a"] = _table("tbl-a", [_entry("leave", [_effect("life_path", "muster")])])
    entity = _entity(life_paths=[Enrollment(faction_id="fac-1", path_id="lp-1", mustered=False)])
    start_term(entity, "fac-1", "lp-1", repo)
    resolve_step(entity, repo, index=1)
    assert entity.pending_term is None
    assert entity.life_paths[0].mustered is True
    assert entity.life_paths[0].mishap_muster is False


class FakeEngine:
    def __init__(self):
        self.scheduled = []

    def schedule_effect(self, entity_id, universe, effect, sfx_name="", context=None):
        self.scheduled.append((entity_id, universe, effect, sfx_name))


def test_deferred_effect_is_scheduled():
    repo = ExecutorRepo()
    repo.lifepaths["lp-1"] = LifePath(id="lp-1", name="P", universe="earth", entry_table_id="tbl-a")
    deferred = Effect(
        timing=EffectTiming.END_OF_SCENE,
        type="modify_trait", action="gain", target="iron-will", result="d6",
    )
    repo.tables["tbl-a"] = _table("tbl-a", [_entry("gain later", [deferred])])
    entity = _entity()
    start_term(entity, "fac-1", "lp-1", repo)
    engine = FakeEngine()

    summary = resolve_step(entity, repo, index=1, engine=engine)

    # Not applied immediately — queued for the end of the scene.
    assert len(repo.created_traitsettings) == 0
    assert len(engine.scheduled) == 1
    assert summary["scheduled"] == 1
    assert engine.scheduled[0][2].timing == EffectTiming.END_OF_SCENE


def test_resolve_step_records_historical_outcome():
    repo = ExecutorRepo()
    repo.lifepaths["lp-1"] = LifePath(id="lp-1", name="Azure Dawn", universe="earth", entry_table_id="tbl-a")
    repo.tables["tbl-a"] = _table("tbl-a", [_entry("Martial Arts", [_next("tbl-b")])])
    entity = _entity()
    start_term(entity, "fac-1", "lp-1", repo)

    resolve_step(entity, repo, index=1)

    assert len(repo.historical_records) == 1
    rec = repo.historical_records[0]
    assert rec["entity_id"] == "char-1"
    assert rec["record_type"] == "roll_table"
    assert rec["data"]["life_path_name"] == "Azure Dawn"
    assert rec["data"]["table_name"] == "tbl-a"
    assert rec["data"]["entry_label"] == "Martial Arts"
    assert rec["data"]["index"] == 1
