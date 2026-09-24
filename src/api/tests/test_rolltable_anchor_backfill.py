"""The B164 migration: a roll-table tie anchor moves from the context pair to the
owner path.

The pair (`context.relationship` + `relationship_type`) has no declarer left — no
action offers it — so a stored rule using it is uneditable, and the applier branch
that reads it exists only for this content. The migration rewrites it as a path the
editor can show and the targeting wizard can pick.
"""

from transversal.domain import Effect, EffectTiming, RollTable, RollTableEntry


def _effect(**context):
    return Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait",
                  action="gain_or_step_up", target="trait-rel-tenure", result="d4",
                  context=context or None)


class FakeRepo:
    def __init__(self, tables):
        self.tables = list(tables)
        self.updates = 0

    def list_roll_tables(self, life_path_id=None):
        return list(self.tables)

    def update_roll_table(self, table):
        self.updates += 1
        self.tables = [table if t.id == table.id else t for t in self.tables]
        return table


def _table(effect):
    return RollTable(id="rt-continue", name="Continue",
                     entries=[RollTableEntry(label="Serve another term", effects=[effect])])


def test_a_literal_faction_becomes_an_owner_path():
    from transversal.services.roll_table import backfill_rolltable_anchor_paths

    repo = FakeRepo([_table(_effect(relationship="fac-verdant-steps"))])
    assert backfill_rolltable_anchor_paths(repo) == 1

    effect = repo.tables[0].entries[0].effects[0]
    # Emptied, not null: `Effect.context` is a dict, and a stored null fails to
    # validate on the next read — which took the whole table out of the API.
    assert effect.context == {}, "the legacy pair is gone, not left behind"
    assert effect.owner_spec is not None
    assert effect.owner_spec.steps[0].collection == "self"
    assert effect.owner_spec.steps[1].edge == "relationships"
    contact = effect.owner_spec.steps[2]
    assert (contact.field, contact.value) == ("contact_id", "fac-verdant-steps")
    # The legacy lookup defaulted to `membership`, so the path says so: without it
    # the path would also match an edge of another kind to the same faction.
    kind = effect.owner_spec.steps[3]
    assert (kind.field, kind.value) == ("type", "membership")
    assert repo.updates == 1


def test_an_authored_relationship_type_is_kept():
    from transversal.services.roll_table import backfill_rolltable_anchor_paths

    repo = FakeRepo([_table(_effect(relationship="fac-1", relationship_type="relation"))])
    backfill_rolltable_anchor_paths(repo)
    assert repo.tables[0].entries[0].effects[0].owner_spec.steps[3].value == "relation"


def test_it_is_idempotent():
    from transversal.services.roll_table import backfill_rolltable_anchor_paths

    repo = FakeRepo([_table(_effect(relationship="fac-1"))])
    assert backfill_rolltable_anchor_paths(repo) == 1
    assert backfill_rolltable_anchor_paths(repo) == 0, "a second pass must find nothing to do"
    assert repo.updates == 1, "and must not write the table again"


def test_a_runtime_token_is_left_alone():
    """A shared table cannot name a faction; `{term_faction}` is the one anchor a
    literal filter cannot express, so it stays put (and is logged)."""
    from transversal.services.roll_table import backfill_rolltable_anchor_paths

    repo = FakeRepo([_table(_effect(relationship="{term_faction}"))])
    assert backfill_rolltable_anchor_paths(repo) == 0
    effect = repo.tables[0].entries[0].effects[0]
    assert effect.owner_spec is None
    assert effect.context["relationship"] == "{term_faction}"
    assert repo.updates == 0


def test_an_effect_that_already_has_an_owner_path_is_untouched():
    from transversal.services.roll_table import backfill_rolltable_anchor_paths
    from transversal.services.target_spec import TargetSpec

    effect = _effect(relationship="fac-1").model_copy(
        update={"owner_spec": TargetSpec.model_validate({"steps": [
            {"kind": "select", "collection": "self"}]})})
    repo = FakeRepo([_table(effect)])
    assert backfill_rolltable_anchor_paths(repo) == 0


def test_cost_effects_are_migrated_too():
    """A cost is paid on the same anchor as the benefit, so both halves move."""
    from transversal.services.roll_table import backfill_rolltable_anchor_paths

    cost = _effect(relationship="fac-1")
    cost.action = "step_down"
    table = RollTable(id="rt-x", name="X", entries=[
        RollTableEntry(label="e", cost_effects=[cost], effects=[_effect(relationship="fac-1")])])
    repo = FakeRepo([table])
    assert backfill_rolltable_anchor_paths(repo) == 2


def test_the_migrated_effect_round_trips_through_the_model():
    """The bug this pins: the backfill wrote `context: null`, which the domain model
    refuses to read back (`context` is a dict) — so the table vanished from the API
    while the in-memory assertions above still passed. Validate the saved shape."""
    from transversal.domain import RollTable
    from transversal.services.roll_table import backfill_rolltable_anchor_paths

    repo = FakeRepo([_table(_effect(relationship="fac-1"))])
    backfill_rolltable_anchor_paths(repo)
    stored = repo.tables[0].model_dump()
    assert RollTable.model_validate(stored).entries[0].effects[0].owner_spec is not None
