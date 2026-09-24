"""The names a roll-table entry's effects resolve against (B164, route 2).

Two kinds, one scope: ambient facts the engine holds (the term's faction, *this
table's path* faction, the roll) and names the table declares for itself. The
path faction comes from the entity's **enrollment**, which records faction × path —
so it does not depend on which term happens to be in progress, and it is right for
an entity enrolled in several paths.
"""

from types import SimpleNamespace as NS

from transversal.domain import BoundVariable, Effect, EffectTiming, Enrollment, PendingTerm, RollTable, RollTableEntry
from transversal.services.roll_table import table_bindings
from transversal.services.target_spec import TargetSpec


def _entity(*, enrollments=(), term=None):
    return NS(id="char-1", life_paths=list(enrollments), pending_term=term,
              current_universe="three_realms", current_location="loc-1", razmerit=0,
              current_projection=None)


def _table(table_id="rt-x", life_path=None, declared=()):
    return RollTable(id=table_id, name="X", life_path=life_path,
                     bound_variables=list(declared),
                     entries=[RollTableEntry(label="e")])


def _owned(table_path, entity, **kw):
    return table_bindings(_table(life_path=table_path, **kw), entity, repo=None)


def test_a_path_owned_table_uses_its_own_path_faction_not_the_current_term():
    """The author's case: a term started in another path must not re-anchor this
    table. The enrollment says which faction *this path* is served in."""
    entity = _entity(
        enrollments=[Enrollment(faction_id="fac-verdant", path_id="lp-verdant"),
                     Enrollment(faction_id="fac-rogue", path_id="lp-rogue")],
        term=PendingTerm(faction_id="fac-rogue", path_id="lp-rogue",
                         current_table_id="rt-rogue-advance"),
    )
    bindings = _owned("lp-verdant", entity)
    assert bindings["path_faction"].value == "fac-verdant"
    assert bindings["term_faction"].value == "fac-rogue", "both are available, distinctly"


def test_a_shared_table_falls_back_to_the_invoking_term():
    entity = _entity(enrollments=[Enrollment(faction_id="fac-verdant", path_id="lp-verdant")],
                     term=PendingTerm(faction_id="fac-verdant", path_id="lp-verdant",
                                      current_table_id="rt-continue"))
    bindings = table_bindings(_table(), entity, repo=None)
    assert bindings["path_faction"].value == "fac-verdant"


def test_the_roll_and_table_are_in_scope():
    bindings = table_bindings(_table("rt-continue"), _entity(), repo=None,
                              roll=4, tier=None, index=2)
    assert bindings["table_id"].value == "rt-continue"
    assert bindings["roll"].value == "4"


def test_a_name_that_resolves_to_nothing_is_unbound_not_empty():
    """A shared table on an entity with no term and no path has no faction to give,
    and an unbound name makes a downstream path resolve to nobody rather than to a
    blank id."""
    bindings = table_bindings(_table(), _entity(), repo=None)
    assert "path_faction" not in bindings
    assert "term_faction" not in bindings


def test_a_declared_variable_joins_the_scope():
    declared = BoundVariable(name="me", spec=TargetSpec.model_validate(
        {"steps": [{"kind": "select", "collection": "self"}]}))
    entity = _entity()
    repo = NS(get_entity=lambda eid: entity)
    bindings = table_bindings(_table(declared=[declared]), entity, repo)
    assert bindings["me"].value == "char-1"


def test_a_declared_variable_cannot_shadow_an_ambient_name():
    declared = BoundVariable(name="term_faction", spec=TargetSpec.model_validate(
        {"steps": [{"kind": "select", "collection": "self"}]}))
    entity = _entity(term=PendingTerm(faction_id="fac-real", path_id="lp-1",
                                      current_table_id="rt-x"))
    repo = NS(get_entity=lambda eid: entity)
    bindings = table_bindings(_table(declared=[declared]), entity, repo)
    assert bindings["term_faction"].value == "fac-real"


def test_an_effect_anchors_through_the_scope():
    """The point of the scope: an entry's effect names the faction by *name*.

    `select self → relationships → filter contact_id == {path_faction}` anchors the
    trait to this table's path faction, which is what a shared table needs (it
    cannot write a faction) and what a path-owned one should read.
    """
    from transversal.services.effects_applier import apply_effects

    edge = "edge:char-1:fac-verdant:membership"
    entity = _entity(enrollments=[Enrollment(faction_id="fac-verdant", path_id="lp-verdant")],
                     term=PendingTerm(faction_id="fac-rogue", path_id="lp-rogue",
                                      current_table_id="rt-verdant-advance"))

    class Repo:
        def get_entity(self, eid):
            return entity
        def get_trait(self, trait_id):
            return NS(id=trait_id, traitset_id="ts-rel")
        def get_traitset_by_id(self, traitset_id):
            return None
        def get_traitsettings_for_entity(self, entity_id):
            return []
        def get_relationship_traitsettings(self, key):
            return []
        def get_projection_traitsettings(self, pid):
            return []
        def get_sub_traitsettings(self, pid):
            return []
        def list_relationships_for_entity(self, eid):
            return [{"id": edge, "_key": edge, "type": "membership",
                     "contact_id": "fac-verdant", "owner_id": eid}]
        def get_relationship(self, eid, other, rel_type=None):
            return {"_key": edge}

    bindings = table_bindings(_table(life_path="lp-verdant"), entity, Repo())
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_trait", action="gain_or_step_up",
        target="trait-rel-rank", result="d4",
        owner_spec=TargetSpec.model_validate({"steps": [
            {"kind": "select", "collection": "self"},
            {"kind": "navigate", "edge": "relationships"},
            {"kind": "filter", "field": "contact_id", "operator": "==",
             "value": "{path_faction}"},
        ]}),
    )
    from transversal.services.effects_applier.datatypes import BINDINGS_CONTEXT_KEY

    result = apply_effects(entity, [effect], Repo(), {BINDINGS_CONTEXT_KEY: bindings})
    made = result.new_trait_settings[0]
    assert (made.from_type, made.entity_id) == ("relationship", edge)


def test_a_tiered_entry_carries_its_effect_die():
    """The author's requirement: an entry's effect can use the die its *tier*
    carries (marginal d4, success d6, exceptional d8, perfect d10) — and on a menu
    pick the tier comes from the entry itself, not from a roll argument."""
    from transversal.domain import OutcomeTier

    entry = NS(label="Promoted", tier=OutcomeTier.SUCCESS, min_value=3, max_value=4)
    bindings = table_bindings(_table("rt-verdant-advance"), _entity(), repo=None, entry=entry)

    assert bindings["entry_tier"].value == "success"
    assert bindings["entry_effect_die"].value == "d6"
    assert bindings["entry_label"].value == "Promoted"
    assert bindings["entry_min"].value == "3"


def test_a_fail_tier_has_no_effect_die_to_bind():
    from transversal.domain import OutcomeTier

    bindings = table_bindings(_table(), _entity(), repo=None,
                              entry=NS(label="Expelled", tier=OutcomeTier.FAIL))
    assert bindings["entry_tier"].value == "fail"
    assert "entry_effect_die" not in bindings, "fail carries no die — unbound, not blank"


def test_an_entry_effect_can_name_the_entry_effect_die_in_a_flat_field():
    """The seam that made this unusable before: the engine substitutes ``{name}`` in
    flat fields, but a roll-table entry goes through the *direct* entry point, where
    nothing did. So `result: "{entry_effect_die}"` was a literal that named no die."""
    from transversal.domain import Effect, EffectTiming, OutcomeTier
    from transversal.services.effects_applier import apply_effects
    from transversal.services.effects_applier.datatypes import BINDINGS_CONTEXT_KEY

    entity = _entity()

    class Repo:
        def get_entity(self, eid):
            return entity
        def get_trait(self, trait_id):
            return NS(id=trait_id, traitset_id="ts-rel")
        def get_traitset_by_id(self, traitset_id):
            return None
        def get_traitsettings_for_entity(self, entity_id):
            return []
        def get_relationship_traitsettings(self, key):
            return []
        def get_projection_traitsettings(self, pid):
            return []
        def get_sub_traitsettings(self, pid):
            return []
        def find_traitsetting_collision(self, *a, **k):
            return None

    entry = NS(label="Promoted", tier=OutcomeTier.EXCEPTIONAL)
    bindings = table_bindings(_table(), entity, Repo(), entry=entry)
    effect = Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait", action="gain",
                    target="trait-rel-rank", result="{entry_effect_die}")
    result = apply_effects(entity, [effect], Repo(), {BINDINGS_CONTEXT_KEY: bindings})

    assert result.new_trait_settings[0].dice[0].value == "d8", "exceptional carries d8"


def test_a_table_source_can_walk_to_its_life_path():
    """The table is the entry-effect's source, so `select source` is the table and
    the path it belongs to is one hop away — which is where the faction comes from
    (via the entity's enrollment for that path)."""
    from transversal.services.target_resolver import TargetContext, resolve, resolved_id

    table = NS(id="rt-verdant-advance", life_path="lp-verdant", entries=[])
    repo = NS(get_lifepath=lambda lid: NS(id=lid, name="Verdant Disciple")
              if lid == "lp-verdant" else None)
    spec = TargetSpec.model_validate({"steps": [
        {"kind": "select", "collection": "source"},
        {"kind": "navigate", "edge": "life_path"},
    ]})
    ctx = TargetContext(subject=None, repo=repo, source=table, source_element="roll_table")
    assert [resolved_id(v) for v in resolve(spec, ctx).values] == ["lp-verdant"]
