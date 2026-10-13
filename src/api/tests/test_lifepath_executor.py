"""Tests for the roll-table life-path term executor."""

from transversal.domain import (
    DieType,
    Effect,
    EffectTiming,
    Enrollment,
    Entity,
    EntityType,
    LifePath,
    LifePathBinding,
    LifePathStep,
    PendingTerm,
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
        self.entities = {}
        self.created_traitsettings = []
        self.updated_entities = []
        self.historical_records = []
        self.scheduled_events = []

    def get_entity(self, entity_id):
        return self.entities.get(entity_id)

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

    def create_scheduled_event(self, event):
        self.scheduled_events.append(event)
        return event

    def list_all_scheduled_events(self):
        return list(self.scheduled_events)

    def update_scheduled_event(self, event):
        return event

    def delete_scheduled_event(self, event_id):
        self.scheduled_events = [e for e in self.scheduled_events if e.id != event_id]
        return True

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
    assert entity.pending_terms[""].current_table_id == "tbl-b"


def _wrapped(path_id, steps, entry_step):
    return LifePath(id=path_id, name="P", universe="earth",
                    entry_step=entry_step, steps=steps)


def test_wrapped_step_follows_the_paths_edge_not_the_entrys():
    """A wrapped path owns its graph: the entry's own next_step is ignored.

    Two sources of truth for one edge is how the canvas and the runtime end up
    disagreeing, so the path's declaration wins outright.
    """
    repo = ExecutorRepo()
    repo.lifepaths["lp-1"] = _wrapped("lp-1", [
        LifePathStep(id="s1", table_id="tbl-a", bindings=[
            LifePathBinding(key="0", next="s2"),
        ]),
        LifePathStep(id="s2", table_id="tbl-b"),
    ], entry_step="s1")
    repo.tables["tbl-a"] = _table("tbl-a", [_entry("go", [_next("tbl-elsewhere")])])
    repo.tables["tbl-b"] = _table("tbl-b", [_entry("end", [])])

    entity = _entity()
    start_term(entity, "fac-1", "lp-1", repo)
    resolve_step(entity, repo, index=1)
    assert entity.pending_terms[""].current_step_id == "s2"
    assert entity.pending_terms[""].current_table_id == "tbl-b"  # not tbl-elsewhere


def test_multi_exit_needs_no_return_address():
    """`Survive`'s two outcomes diverge — the case the return stack could not do.

    This is the old `test_named_exit_return_map` rewritten in the wrapper model.
    That version pushed a map of named exits onto the checkpoint and resolved
    `{return:injured}` when the shared table ran; here the path simply says where
    each row goes, so there is nothing to return *to*. The machinery is not
    replaced by something cleverer — it is unnecessary.
    """
    repo = ExecutorRepo()
    repo.lifepaths["lp-1"] = _wrapped("lp-1", [
        LifePathStep(id="s1", table_id="tbl-a", bindings=[
            LifePathBinding(key="0", next="s-survive"),
        ]),
        LifePathStep(id="s-survive", table_id="tbl-survive", bindings=[
            LifePathBinding(key="0", next="s-advance"),
            LifePathBinding(key="1", next="s-mishap"),
        ]),
        LifePathStep(id="s-advance", table_id="tbl-advance"),
        LifePathStep(id="s-mishap", table_id="tbl-mishap"),
    ], entry_step="s1")
    repo.tables["tbl-a"] = _table("tbl-a", [_entry("call", [_next("tbl-survive")])])
    repo.tables["tbl-survive"] = _table("tbl-survive", [
        _entry("survived", [_next("")]), _entry("injured", [_next("")]),
    ])
    repo.tables["tbl-advance"] = _table("tbl-advance", [_entry("done", [])])
    repo.tables["tbl-mishap"] = _table("tbl-mishap", [_entry("hurt", [])])

    # Survived → advance.
    entity = _entity()
    start_term(entity, "fac-1", "lp-1", repo)
    resolve_step(entity, repo, index=1)
    resolve_step(entity, repo, index=1)
    assert entity.pending_terms[""].current_table_id == "tbl-advance"

    # Injured → mishap. The same wrapped table, a different row, a different
    # destination — with no map on the checkpoint either time.
    entity = _entity()
    start_term(entity, "fac-1", "lp-1", repo)
    resolve_step(entity, repo, index=1)
    resolve_step(entity, repo, index=2)
    assert entity.pending_terms[""].current_table_id == "tbl-mishap"


def test_binding_next_empty_leaves_the_path():
    repo = ExecutorRepo()
    repo.lifepaths["lp-1"] = _wrapped("lp-1", [
        LifePathStep(id="s1", table_id="tbl-a", bindings=[
            LifePathBinding(key="0", next=""),  # bound, and it says "end here"
        ]),
    ], entry_step="s1")
    repo.tables["tbl-a"] = _table("tbl-a", [_entry("rejected", [])])

    entity = _entity()
    start_term(entity, "fac-1", "lp-1", repo)
    resolve_step(entity, repo, index=1)
    # A finished term leaves *no* checkpoint rather than an empty one.
    assert entity.pending_terms == {}


def test_exit_kind_musters_without_a_muster_effect():
    """`muster` is a destination with a meaning, not an effect on the row.

    Every muster/force_muster row in the live content carries nothing else and no
    next_step, which is what settled this shape.
    """
    repo = ExecutorRepo()
    repo.lifepaths["lp-1"] = _wrapped("lp-1", [
        LifePathStep(id="s1", table_id="tbl-a", bindings=[
            LifePathBinding(key="0", exit_kind="muster"),
            LifePathBinding(key="1", exit_kind="force_muster"),
        ]),
    ], entry_step="s1")
    # Note the rows carry NO effects at all — the path supplies the outcome.
    repo.tables["tbl-a"] = _table("tbl-a", [_entry("respectful", []), _entry("disgraced", [])])

    entity = _entity(life_paths=[Enrollment(faction_id="fac-1", path_id="lp-1")])
    start_term(entity, "fac-1", "lp-1", repo)
    resolve_step(entity, repo, index=2)
    assert entity.pending_terms == {}
    assert entity.life_paths[0].mustered is True
    assert entity.life_paths[0].mishap_muster is True


def test_enroll_is_per_row_so_the_rejected_are_not_enrolled():
    """The case against a path-level enroll flag, as a test.

    `rt-verdant-qualify` enrols its Accepted rows and not its Rejected ones, so
    the flag lives on the binding.
    """
    repo = ExecutorRepo()
    repo.lifepaths["lp-1"] = _wrapped("lp-1", [
        LifePathStep(id="s1", table_id="tbl-a", bindings=[
            LifePathBinding(key="0", enroll=True, next="s2"),
            LifePathBinding(key="1", next=""),  # rejected: no enroll
        ]),
        LifePathStep(id="s2", table_id="tbl-b"),
    ], entry_step="s1")
    repo.tables["tbl-a"] = _table("tbl-a", [_entry("accepted", []), _entry("rejected", [])])
    repo.tables["tbl-b"] = _table("tbl-b", [_entry("end", [])])

    accepted = _entity()
    start_term(accepted, "fac-1", "lp-1", repo)
    resolve_step(accepted, repo, index=1)
    assert [(e.faction_id, e.path_id) for e in accepted.life_paths] == [("fac-1", "lp-1")]

    rejected = _entity()
    start_term(rejected, "fac-1", "lp-1", repo)
    resolve_step(rejected, repo, index=2)
    assert rejected.life_paths == []


def test_binding_effects_apply_after_the_rows_own():
    """The delta lands on top of the row, and both are recorded."""
    repo = ExecutorRepo()
    repo.traits["t-row"] = FakeTrait("t-row", "ts-1")
    repo.traits["t-delta"] = FakeTrait("t-delta", "ts-1")
    repo.lifepaths["lp-1"] = _wrapped("lp-1", [
        LifePathStep(id="s1", table_id="tbl-a", bindings=[
            LifePathBinding(key="0", next="", effects=[_gain("t-delta", "d6")]),
        ]),
    ], entry_step="s1")
    repo.tables["tbl-a"] = _table("tbl-a", [_entry("row", [_gain("t-row", "d6")])])

    entity = _entity()
    start_term(entity, "fac-1", "lp-1", repo)
    resolve_step(entity, repo, index=1)
    gained = {ts.trait_id for ts in repo.created_traitsettings}
    assert {"t-row", "t-delta"} <= gained


def test_a_bindings_effect_can_use_a_name_the_row_exposes():
    """[[B281]]'s point, end to end: the **row** declares a name, and the *life path
    binding's* effect — not the row's own — is what consumes it.

    `resolve_step` applies the row's effects and the binding's in one scope, so a
    name declared on the entry reaches the binding with no extra plumbing. This is
    the link that would break *silently*: were `entry` not passed to
    `table_bindings`, the binding would see the table's names and not the row's, and
    the effect would simply target nothing.
    """
    from transversal.domain import BoundVariable
    from transversal.services.target_spec import TargetSpec

    repo = ExecutorRepo()
    repo.traits["t-picked"] = FakeTrait("t-picked", "ts-1")
    repo.lifepaths["lp-1"] = _wrapped("lp-1", [
        LifePathStep(id="s1", table_id="tbl-a", bindings=[
            LifePathBinding(key="row", next="", effects=[
                _effect("modify_trait", "gain", target="{picked}", result="d6"),
            ]),
        ]),
    ], entry_step="s1")
    declared = BoundVariable(name="picked", spec=TargetSpec.model_validate(
        {"steps": [{"kind": "literal", "element": "trait", "value": "t-picked"}]}))
    repo.tables["tbl-a"] = _table("tbl-a", [
        RollTableEntry(key="row", label="row", bound_variables=[declared]),
    ])

    entity = _entity()
    start_term(entity, "fac-1", "lp-1", repo)
    resolve_step(entity, repo, index=1)

    gained = {ts.trait_id for ts in repo.created_traitsettings}
    assert gained == {"t-picked"}, "the binding's effect resolved the row's name"


def test_a_step_effect_applies_whatever_row_resolved():
    """[[B281]]: an effect authored on the **step** rather than on a binding, so it
    is written once and applies to every row the table can produce."""
    repo = ExecutorRepo()
    repo.traits["t-step"] = FakeTrait("t-step", "ts-1")
    repo.lifepaths["lp-1"] = _wrapped("lp-1", [
        LifePathStep(id="s1", table_id="tbl-a", effects=[_gain("t-step", "d6")]),
    ], entry_step="s1")
    repo.tables["tbl-a"] = _table("tbl-a", [
        RollTableEntry(key="a", label="A"),
        RollTableEntry(key="b", label="B"),
    ])

    for index in (1, 2):
        entity = _entity()
        start_term(entity, "fac-1", "lp-1", repo)
        before = len(repo.created_traitsettings)
        resolve_step(entity, repo, index=index)
        gained = [ts.trait_id for ts in repo.created_traitsettings[before:]]
        assert gained == ["t-step"], f"row {index}: the step effect ran exactly once"


def test_a_step_effect_consumes_a_name_the_row_exposed():
    """The point of authoring it on the step: **one** effect, for a table whose rows
    expose different things.

    The resolved row's declarations are in the same scope, so the step effect can
    target `select variable picked` — and on a row that exposes no such name the
    path resolves to **zero targets**, which `_apply_spec_effect` applies zero
    times. That is a clean no-op, and it is what makes "write it once" safe.

    ⚠ This is true of the **path** form (`target_spec` / `owner_spec`), which is the
    documented way to consume a bound variable — *not* of writing `{picked}` into a
    flat field like `target`. `_substitute_effect_context` leaves a token it cannot
    resolve in place, so a flat-field reference to an unbound name runs the effect
    against the literal string `"{picked}"`. See the note on `LifePathStep.effects`.
    """
    from transversal.domain import BoundVariable
    from transversal.services.target_spec import TargetSpec

    repo = ExecutorRepo()
    repo.entities["loc-india"] = FakeTrait("loc-india", "ts-loc")
    step_effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="relationship", action="create",
        result="origin",
        target_spec=TargetSpec.model_validate({"steps": [
            {"kind": "select", "collection": "variable", "variable": "picked"}]}),
    )
    repo.lifepaths["lp-1"] = _wrapped("lp-1", [
        LifePathStep(id="s1", table_id="tbl-a", effects=[step_effect]),
    ], entry_step="s1")
    declared = BoundVariable(name="picked", spec=TargetSpec.model_validate(
        {"steps": [{"kind": "literal", "element": "location", "value": "loc-india"}]}))
    repo.tables["tbl-a"] = _table("tbl-a", [
        RollTableEntry(key="exposes", label="Exposes", bound_variables=[declared]),
        RollTableEntry(key="silent", label="Silent"),
    ])

    # The row that exposes it: the step's effect acts on what the row named.
    exposing = _entity()
    start_term(exposing, "fac-1", "lp-1", repo)
    applied = resolve_step(exposing, repo, index=1)["applied"]
    assert applied, "the step effect resolved the row's name and did something"

    # The row that does not: the same authored effect applies to nobody.
    silent = _entity()
    start_term(silent, "fac-1", "lp-1", repo)
    assert resolve_step(silent, repo, index=2)["applied"] == [], \
        "no name exposed → the effect is a no-op, not a literal `{picked}`"


def test_force_muster_marks_enrollment():
    repo = ExecutorRepo()
    repo.lifepaths["lp-1"] = LifePath(id="lp-1", name="P", universe="earth", entry_table_id="tbl-a")
    repo.tables["tbl-a"] = _table("tbl-a", [_entry("die", [_force_muster()])])
    entity = _entity(life_paths=[Enrollment(faction_id="fac-1", path_id="lp-1", mustered=False)])
    start_term(entity, "fac-1", "lp-1", repo)
    resolve_step(entity, repo, index=1)
    assert entity.pending_terms == {}
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
    assert entity.pending_terms == {}
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
    assert len(repo.scheduled_events) == 1
    assert summary["scheduled"] == 1
    assert repo.scheduled_events[0].effect.timing == EffectTiming.END_OF_SCENE


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


# ── a term belongs to the body living it ([[B271]]) ─────────────────────────

def test_starting_a_term_in_one_body_leaves_another_body_alone():
    """The reported bug, as a test: a term follows the body, not the character.

    Before this, one checkpoint sat on the entity and followed the character into
    every universe — which is why an Earth projection showed a Three Realms term.
    """
    from transversal.services.lifepath_scope import pending_term_for

    repo = ExecutorRepo()
    for pid, tid in (("lp-a", "tbl-a"), ("lp-b", "tbl-b")):
        repo.lifepaths[pid] = _wrapped(pid, [LifePathStep(id="s1", table_id=tid)], entry_step="s1")
        repo.tables[tid] = _table(tid, [_entry("row", [])])

    entity = _entity(current_projection="body-1")
    start_term(entity, "fac-a", "lp-a", repo)

    assert set(entity.pending_terms) == {"body-1"}
    assert entity.pending_terms["body-1"].path_id == "lp-a"
    # The other body is not mid-term, and starting its own does not disturb this.
    assert pending_term_for(entity, "body-2") is None
    start_term(entity, "fac-b", "lp-b", repo, projection_id="body-2")
    assert entity.pending_terms["body-1"].path_id == "lp-a"
    assert entity.pending_terms["body-2"].path_id == "lp-b"


def test_resolving_moves_only_the_acting_bodys_term():
    repo = ExecutorRepo()
    repo.lifepaths["lp-a"] = _wrapped("lp-a", [
        LifePathStep(id="s1", table_id="tbl-a", bindings=[LifePathBinding(key="0", next="s2")]),
        LifePathStep(id="s2", table_id="tbl-a2"),
    ], entry_step="s1")
    repo.tables["tbl-a"] = _table("tbl-a", [_entry("go", [])])
    repo.tables["tbl-a2"] = _table("tbl-a2", [_entry("end", [])])
    repo.lifepaths["lp-b"] = _wrapped("lp-b", [
        LifePathStep(id="s1", table_id="tbl-b", bindings=[LifePathBinding(key="0", next="s2")]),
        LifePathStep(id="s2", table_id="tbl-b2"),
    ], entry_step="s1")
    repo.tables["tbl-b"] = _table("tbl-b", [_entry("row", [])])
    repo.tables["tbl-b2"] = _table("tbl-b2", [_entry("end", [])])

    entity = _entity(current_projection="body-1")
    start_term(entity, "fac-a", "lp-a", repo)
    entity.current_projection = "body-2"
    start_term(entity, "fac-b", "lp-b", repo)

    # Acting as body-2: only its term advances.
    resolve_step(entity, repo, index=1)
    assert entity.pending_terms["body-2"].current_step_id == "s2"
    assert entity.pending_terms["body-1"].current_step_id == "s1", "body-1 did not move"


def test_mustering_one_body_does_not_muster_another():
    """Membership is per body ([[B271]]): the same path through two bodies is two facts."""
    repo = ExecutorRepo()
    repo.lifepaths["lp-a"] = _wrapped("lp-a", [
        LifePathStep(id="s1", table_id="tbl-a", bindings=[
            LifePathBinding(key="0", enroll=True, exit_kind="muster"),
        ]),
    ], entry_step="s1")
    repo.tables["tbl-a"] = _table("tbl-a", [_entry("muster out", [])])

    entity = _entity(current_projection="body-1")
    # Both bodies already hold the same membership.
    entity.life_paths = [
        Enrollment(faction_id="fac-a", path_id="lp-a", projection_id="body-1"),
        Enrollment(faction_id="fac-a", path_id="lp-a", projection_id="body-2"),
    ]
    start_term(entity, "fac-a", "lp-a", repo)
    resolve_step(entity, repo, index=1)

    by_body = {e.projection_id: e for e in entity.life_paths}
    assert by_body["body-1"].mustered is True
    assert by_body["body-2"].mustered is False, "the other body is still serving"
    assert entity.pending_terms == {}, "only the acting body's checkpoint is gone"


def test_an_unscoped_term_still_serves_whichever_body_asks():
    """The compatibility shim: pre-migration content is not stranded.

    A term stored under the unscoped key belongs to no particular body, so it is
    handed to whoever asks — but a *scoped* term is never given to another body.
    """
    from transversal.services.lifepath_scope import pending_term_for

    entity = _entity(current_projection="body-1")
    entity.pending_terms = {"": PendingTerm(faction_id="fac", path_id="lp", current_table_id="t")}
    assert pending_term_for(entity, "body-2") is not None
    assert pending_term_for(entity, "body-3") is not None

    entity.pending_terms = {"body-1": PendingTerm(faction_id="fac", path_id="lp", current_table_id="t")}
    assert pending_term_for(entity, "body-2") is None, "a scoped term is not shared"


def test_a_pre_b271_term_is_adopted_rather_than_stranded():
    """Legacy content still resolves, and the body playing it claims it.

    The deprecated `pending_term` is unscoped by definition — that is the bug it
    predates — so it is handed to whoever asks. Resolving has to *adopt* it, or the
    flow helpers (which ask whether their term is still the stored one) would treat
    an unkeyed term as already ended and silently finish the term on first use.
    """
    repo = ExecutorRepo()
    repo.lifepaths["lp-a"] = _wrapped("lp-a", [
        LifePathStep(id="s1", table_id="tbl-a", bindings=[LifePathBinding(key="0", next="s2")]),
        LifePathStep(id="s2", table_id="tbl-a2"),
    ], entry_step="s1")
    repo.tables["tbl-a"] = _table("tbl-a", [_entry("go", [])])
    repo.tables["tbl-a2"] = _table("tbl-a2", [_entry("end", [])])

    entity = _entity(current_projection="body-1")
    entity.pending_term = PendingTerm(
        faction_id="fac-a", path_id="lp-a", current_step_id="s1", current_table_id="tbl-a")

    result = resolve_step(entity, repo, index=1)
    assert result["done"] is False
    assert entity.pending_terms["body-1"].current_step_id == "s2", "adopted by the acting body"


def test_a_checkpoint_naming_a_table_resolves_to_the_step_that_wraps_it():
    """Regression: `step 'rt-…' not found in path 'lp-…'`.

    A term stored before `current_step_id` existed holds only `current_table_id`.
    The wrapper migration then gave every path **steps** — which is exactly why the
    old "a path with no steps is legacy" shim stopped firing: the checkpoint still
    named a table, the path had step ids, and resolving died. The bridge has to be
    the table→step mapping, not the absence of steps.
    """
    repo = ExecutorRepo()
    repo.lifepaths["lp-a"] = _wrapped("lp-a", [
        LifePathStep(id="s1", table_id="tbl-a"),
        LifePathStep(id="s7", table_id="tbl-escalation", bindings=[
            LifePathBinding(key="0", next="s1"),
        ]),
    ], entry_step="s1")
    repo.tables["tbl-a"] = _table("tbl-a", [_entry("start", [])])
    repo.tables["tbl-escalation"] = _table("tbl-escalation", [_entry("escalate", [])])

    entity = _entity()
    # A pre-wrapper checkpoint: the table, and no step id at all.
    entity.pending_terms = {"": PendingTerm(
        faction_id="fac", path_id="lp-a", current_table_id="tbl-escalation")}

    result = resolve_step(entity, repo, index=1)
    assert result.get("error") is None, result.get("error")
    # …and the checkpoint heals to the step id on the way through.
    assert entity.pending_terms[""].current_step_id == "s1"
    assert entity.pending_terms[""].current_table_id == "tbl-a"


def test_find_step_prefers_a_step_id_over_a_table_id():
    """A step id always wins, so a table id can never shadow one."""
    repo = ExecutorRepo()
    lp = _wrapped("lp-a", [
        LifePathStep(id="tbl-x", table_id="tbl-real"),
        LifePathStep(id="s2", table_id="tbl-x"),
    ], entry_step="tbl-x")
    from transversal.services.lifepath_executor import find_step

    # "tbl-x" is both a step id and another step's table: the id wins.
    assert find_step(lp, "tbl-x").table_id == "tbl-real"
