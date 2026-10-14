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


def _entity(*, enrollments=(), term=None, projection=None):
    """An entity whose term and memberships hang off the *body* ([[B271]]).

    `projection` is the body id; None means the unscoped body, which is what an
    entity with no active projection resolves to.
    """
    return NS(id="char-1", life_paths=list(enrollments),
              pending_terms=({projection or "": term} if term is not None else {}),
              current_universe="three_realms", current_location="loc-1", razmerit=0,
              current_projection=projection)


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


# ── The per-row layer ([[B281]]) ─────────────────────────────────────
# Two declaration layers, resolved in order: the table's (before any row is chosen,
# so a row's *conditions* can read them) and then the chosen row's own. A value only
# one row has — a location, a rival — belongs on the row; a table's declaration
# resolves once for every row and cannot differ between them.

def _self_spec():
    return TargetSpec.model_validate({"steps": [{"kind": "select", "collection": "self"}]})


def test_a_row_declares_its_own_name():
    declared = BoundVariable(name="picked", spec=_self_spec())
    entity = _entity()
    repo = NS(get_entity=lambda eid: entity)
    row = RollTableEntry(label="e", bound_variables=[declared])
    table = _table()
    table.entries = [row]

    assert table_bindings(table, entity, repo, entry=row)["picked"].value == "char-1"
    # Without the row in hand the name is simply absent — never bound empty, so a
    # downstream path resolves to nobody rather than to a blank id.
    assert "picked" not in table_bindings(table, entity, repo)


def test_a_row_name_may_start_from_a_table_name():
    """The layers resolve in order, which is what lets the table state what the whole
    table is about once and a row narrow it."""
    anchor = BoundVariable(name="anchor", spec=_self_spec())
    narrowing = BoundVariable(name="narrowed", spec=TargetSpec.model_validate(
        {"steps": [{"kind": "select", "collection": "variable", "variable": "anchor"}]}))
    entity = _entity()
    repo = NS(get_entity=lambda eid: entity)
    row = RollTableEntry(label="e", bound_variables=[narrowing])
    table = _table(declared=[anchor])
    table.entries = [row]

    bindings = table_bindings(table, entity, repo, entry=row)
    assert bindings["anchor"].value == "char-1", "the table's layer resolves first"
    assert bindings["narrowed"].value == "char-1", "and the row's may start from it"


def test_a_row_variable_cannot_shadow_a_table_one():
    """A collision is refused rather than silently rebound: the table's value is what
    a row's condition may already have read. The editor flags the name, so this is
    the backstop, not the only notice."""
    table_var = BoundVariable(name="dupe", spec=_self_spec())
    row_var = BoundVariable(name="dupe", spec=TargetSpec.model_validate(
        {"steps": [{"kind": "literal", "element": "location", "value": "loc-2"}]}))
    entity = _entity()
    repo = NS(get_entity=lambda eid: NS(id=eid))
    row = RollTableEntry(label="e", bound_variables=[row_var])
    table = _table(declared=[table_var])
    table.entries = [row]

    bindings = table_bindings(table, entity, repo, entry=row)
    assert bindings["dupe"].value == "char-1", "the table's value stands; the row's is refused"


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


# ── A reserved name, and the row that assigns it ([[B285]]) ──────────
# A table may **reserve** a name: a type with no value. The reservation binds
# nothing; it fixes the type of the name, so every row assigning it is checked
# instead of trusted. Without it a name's type is only as consistent as every
# hand-written path that happens to use it — one row starting from a collection
# where the rest pinned a value makes the same name `many` for that row alone, and
# nothing objects.

def _locations_repo(*ids):
    class Repo:
        def get_entity(self, eid):
            return NS(id=eid)
        def list_entities_by_type(self, entity_type):
            return [NS(id=i) for i in ids]
    return Repo()


def _literal_spec(value="loc-1"):
    return TargetSpec.model_validate(
        {"steps": [{"kind": "literal", "element": "location", "value": value}]})


def test_a_reserved_name_is_assigned_by_a_row():
    reserved = BoundVariable(name="picked", element="location", cardinality="one")
    row_var = BoundVariable(name="picked", spec=_literal_spec())
    row = RollTableEntry(label="e", bound_variables=[row_var])
    table = _table(declared=[reserved])
    table.entries = [row]

    bindings = table_bindings(table, _entity(), _locations_repo(), entry=row)
    assert bindings["picked"].value == "loc-1"
    assert (bindings["picked"].element, bindings["picked"].cardinality) == ("location", "one")


def test_a_reserved_name_cannot_be_made_many_by_one_row():
    """The author's case, and both halves are asserted so the test cannot pass
    vacuously: the same row binds as `location/many` when nobody has reserved the
    name, and is refused once the table says it is `location/one`."""
    # `select locations` is a many-cardinality collection and nothing collapses it,
    # which is exactly how a row ends up a different type from its siblings.
    row_var = BoundVariable(name="picked", spec=TargetSpec.model_validate(
        {"steps": [{"kind": "select", "collection": "locations"}]}))
    row = RollTableEntry(label="e", bound_variables=[row_var])
    entity, repo = _entity(), _locations_repo("loc-1", "loc-2")

    unreserved = _table()
    unreserved.entries = [row]
    drifted = table_bindings(unreserved, entity, repo, entry=row)
    assert (drifted["picked"].element, drifted["picked"].cardinality) == ("location", "many"), \
        "without a reservation the row is trusted — this is the drift"

    reserved = BoundVariable(name="picked", element="location", cardinality="one")
    table = _table(declared=[reserved])
    table.entries = [row]
    assert "picked" not in table_bindings(table, entity, repo, entry=row), \
        "the reservation is the promise, so a path that breaks it is refused"


def test_a_reservation_binds_no_value_of_its_own():
    """A reservation is a slot, not a default: the table declares one and the name
    is still absent without a row, so a row's conditions cannot read a value nobody
    assigned."""
    reserved = BoundVariable(name="picked", element="location", cardinality="one")
    table = _table(declared=[reserved])

    assert "picked" not in table_bindings(table, _entity(), _locations_repo("loc-1"))


def test_an_unreserved_row_name_still_binds_at_run_time():
    """The deliberate asymmetry: the **write** boundary refuses a row name the table
    never reserved, and the read tolerates what is already stored.

    Refusing here instead would blank the names of live content the moment this
    landed, before any editor could author the reservation — the same "read old
    data, enforce on write" split the unwrapped-path and legacy-term shims use.
    """
    row_var = BoundVariable(name="picked", spec=_literal_spec())
    row = RollTableEntry(label="e", bound_variables=[row_var])
    table = _table()          # reserves nothing
    table.entries = [row]

    bindings = table_bindings(table, _entity(), _locations_repo(), entry=row)
    assert bindings["picked"].value == "loc-1"


def test_a_table_source_walks_to_the_path_the_term_is_in():
    """A table is the source of its row's effects, but it no longer owns a path.

    Several paths may wrap the same table, or none ([[B266]]), so `navigate
    life_path` cannot read an ownership field — the answer is the path the term is
    actually in, from the acting entity's checkpoint, which is also what makes the
    faction behind it recoverable.
    """
    from transversal.services.target_resolver import TargetContext, resolve, resolved_id

    table = NS(id="rt-shared", entries=[])
    wrapped = NS(id="lp-a", entry_table_id="", steps=[NS(table_id="rt-shared")])
    entity = NS(pending_terms={"": NS(path_id="lp-a")}, current_projection=None)
    repo = NS(get_lifepath=lambda lid: wrapped if lid == "lp-a" else None,
              list_all_lifepaths=lambda: [wrapped])
    spec = TargetSpec.model_validate({"steps": [
        {"kind": "select", "collection": "source"},
        {"kind": "navigate", "edge": "life_path"},
    ]})
    ctx = TargetContext(subject=entity, repo=repo, source=table, source_element="roll_table")
    assert [resolved_id(v) for v in resolve(spec, ctx).values] == ["lp-a"]


def test_a_table_no_term_wraps_resolves_a_unique_path_or_nothing():
    """Outside a term, one wrapping path is an answer; several are not.

    Returning the first of several would silently pick a faction, so the resolver
    declines instead — the same reason an unasked walkability gate reads null
    rather than true.
    """
    from transversal.services.target_resolver import TargetContext, resolve, resolved_id

    table = NS(id="rt-shared", entries=[])
    one = NS(id="lp-a", entry_table_id="", steps=[NS(table_id="rt-shared")])
    two = NS(id="lp-b", entry_table_id="", steps=[NS(table_id="rt-shared")])
    spec = TargetSpec.model_validate({"steps": [
        {"kind": "select", "collection": "source"},
        {"kind": "navigate", "edge": "life_path"},
    ]})

    unique = TargetContext(subject=None, source=table, source_element="roll_table",
                           repo=NS(get_lifepath=lambda lid: None,
                                   list_all_lifepaths=lambda: [one]))
    assert [resolved_id(v) for v in resolve(spec, unique).values] == ["lp-a"]

    ambiguous = TargetContext(subject=None, source=table, source_element="roll_table",
                              repo=NS(get_lifepath=lambda lid: None,
                                      list_all_lifepaths=lambda: [one, two]))
    assert resolve(spec, ambiguous).values == []


# ── The caller's layers: a path and a step ([[B290]]) ────────────────
# The wrapper nests — a path wraps steps, a step wraps a table, a table wraps rows —
# so the declaration layers resolve outermost first:
#
#     path  →  step  →  table  →  row
#
# The caller's layers are what let a **shared** table read the context its caller
# supplies, so `rt-advance` reads `{sect}` instead of hardcoding a faction. They are
# optional and absent rather than empty: a step is the only thing that knows which of
# a path's steps is speaking (a path may wrap one table twice), and a table may also
# be rolled with no step at all (`roll_table_menu`, outside any term).

def _lit(name, value, *, override=False, element="trait"):
    return BoundVariable(name=name, override=override, spec=TargetSpec.model_validate(
        {"steps": [{"kind": "literal", "element": element, "value": value}]}))


def _trait_repo(entity=None):
    return NS(get_entity=lambda eid: entity or NS(id=eid),
              get_trait=lambda tid: NS(id=tid, traitset_id="ts"))


def _caller(path_vars=(), step_vars=()):
    return (NS(id="lp-a", bound_variables=list(path_vars)),
            NS(id="s1", table_id="rt-x", bound_variables=list(step_vars)))


def test_a_path_supplies_a_name_a_shared_table_reads():
    """The ticket's motivating case: the shared table declares nothing and hardcodes
    nothing, and the path is what tells it which sect this term is about."""
    path, step = _caller([_lit("sect", "fac-verdant")])
    bindings = table_bindings(_table(), _entity(), _trait_repo(), path=path, step=step)
    assert bindings["sect"].value == "fac-verdant"


def test_a_step_supplies_a_name_and_may_start_from_the_paths():
    path, step = _caller(
        [_lit("sect", "fac-verdant")],
        [BoundVariable(name="sect_name", spec=TargetSpec.model_validate(
            {"steps": [{"kind": "select", "collection": "variable", "variable": "sect"}]}))],
    )
    bindings = table_bindings(_table(), _entity(), _trait_repo(), path=path, step=step)
    assert bindings["sect"].value == "fac-verdant"
    assert bindings["sect_name"].value == "fac-verdant", \
        "the step's layer resolves after the path's, so it may start from it"


def test_the_path_beats_the_tables_own_declaration_of_the_same_name():
    """Outer-first: the caller is specific to this term, the table is the shared
    content, so the path's value stands and the table's is refused."""
    path, step = _caller([_lit("sect", "fac-verdant")])
    table = _table(declared=[_lit("sect", "fac-table")])

    bindings = table_bindings(table, _entity(), _trait_repo(), path=path, step=step)
    assert bindings["sect"].value == "fac-verdant"


def test_an_override_suppresses_the_tables_declaration_entirely():
    """The explicit override — and why it is not redundant with outer-first.

    The caller's declaration resolves to **nothing** on this activation. Unmarked,
    the name silently falls back to the table's value, so `{sect}` would mean one
    thing when the caller's path resolved and another when it did not. Marked as an
    override, the table's declaration is gone *before any layer resolves*: the name
    is left unbound, and it means the same thing for the whole activation — which is
    also what lets the table's row conditions and every effect after them agree.
    """
    unresolvable = {"steps": [{"kind": "select", "collection": "variable",
                               "variable": "missing"}]}
    table = _table(declared=[_lit("sect", "fac-table")])
    entity, repo = _entity(), _trait_repo()

    plain = _caller(step_vars=[BoundVariable(
        name="sect", spec=TargetSpec.model_validate(unresolvable))])
    assert table_bindings(table, entity, repo, path=plain[0],
                          step=plain[1])["sect"].value == "fac-table", \
        "unmarked, a caller declaration that resolves nothing falls back to the table's"

    marked = _caller(step_vars=[BoundVariable(
        name="sect", spec=TargetSpec.model_validate(unresolvable), override=True)])
    assert "sect" not in table_bindings(table, entity, repo, path=marked[0], step=marked[1]), \
        "marked, the table's declaration is suppressed — unbound, never the table's value"


def test_a_path_override_suppresses_the_tables_declaration_too():
    """The path is the outermost caller, and "path and step over table" is offered at
    both ([[B290]])."""
    path, step = _caller([_lit("sect", "fac-verdant", override=True)])
    table = _table(declared=[_lit("sect", "fac-table")])

    bindings = table_bindings(table, _entity(), _trait_repo(), path=path, step=step)
    assert bindings["sect"].value == "fac-verdant"


def test_only_a_caller_can_override_the_table():
    """A row cannot override the table, structurally: the row does not exist yet when
    its conditions run, so "the row's value replaces the table's" cannot be decided
    up front. The flag on a row is ignored rather than half-honoured."""
    row = RollTableEntry(label="e", bound_variables=[_lit("sect", "fac-row", override=True)])
    table = _table(declared=[_lit("sect", "fac-table")])
    table.entries = [row]

    bindings = table_bindings(table, _entity(), _trait_repo(), entry=row)
    assert bindings["sect"].value == "fac-table", \
        "only a path or a step may mark an override; a row's flag changes nothing"


def test_a_caller_layer_absent_means_the_table_still_resolves_alone():
    """`table_bindings` called the way `roll_table_menu` calls it — no path, no step —
    works unchanged, because the caller's layers are optional rather than required."""
    bindings = table_bindings(_table(declared=[_lit("sect", "fac-table")]),
                              _entity(), _trait_repo())
    assert bindings["sect"].value == "fac-table"
