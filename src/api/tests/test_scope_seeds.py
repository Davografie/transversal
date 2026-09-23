"""The activation's own names, bound as typed seeds for targeting paths.

A rule's *source* token (`{trait_setting}`, `{location}`) and its *trigger's*
declared variables (`{contest_entity_opponent}`, `{effect_die}`) were authorable
from the start: the editor lists them under **Available variables** and flat
fields substitute them. They were never **bound** as typed seeds, though, so a
targeting path could not *start* from one — `{contest_entity_opponent}` worked in
a field, while `select variable {contest_entity_opponent}` errored as unknown.

One declaration types them (`target_catalog.scope_seed_names`) and the engine
fills them from the live event (`_activation_bindings`), so what the wizard
offers is what the fire resolves.
"""

from types import SimpleNamespace as NS

import pytest

from transversal.domain import Condition, ConditionType, DieType, Effect, EffectTiming, Entity, EntityType, SFX, TargetSpec
from transversal.services.target_catalog import element_for_variable, scope_seed_names
from transversal.services.target_resolver import TargetContext, resolve


# ── The declaration ───────────────────────────────────

def test_a_source_token_is_a_seed_typed_by_its_element():
    # A trait instance also exposes its **position** as a value (`{order}`): an
    # integer is not a walkable element, but it is exactly what an indexed read
    # needs, so it is declared with its field type instead of an element.
    assert scope_seed_names("manual", "trait_setting") == {
        "trait_setting": "traitsetting", "order": "int"}
    assert scope_seed_names("manual", "location") == {"location": "location"}
    # Bucket sources (table/gm) resolve to nothing at all.
    assert scope_seed_names("manual", "table") == {}
    assert scope_seed_names("manual", None) == {}

def test_trigger_variables_are_seeds_when_a_path_can_walk_them():
    # The pool-change moment declares the pool it is changing, and the opponent.
    assert scope_seed_names("on_pool_change", None) == {
        "dice_pool": "pool", "contest_entity_opponent": "entity"}
    # `on_result` declares a die AND a number: the die is walkable, the number
    # is not, so only the die is offered as a `select variable` seed.
    assert scope_seed_names("on_result", None) == {"effect_die": "die"}


def test_source_and_trigger_seeds_combine_without_colliding():
    seeds = scope_seed_names("on_pool_change", "trait_setting")
    assert seeds == {"trait_setting": "traitsetting", "order": "int",
                     "dice_pool": "pool", "contest_entity_opponent": "entity"}


def test_declared_types_map_to_catalog_elements():
    assert element_for_variable("trait_setting") == "traitsetting"
    assert element_for_variable("traitset_setting") == "traitsetsetting"
    assert element_for_variable("entity") == "entity"
    # Not walkable: a path has nothing to navigate on a number or a flag.
    assert element_for_variable("number") == ""
    assert element_for_variable("boolean") == ""
    assert element_for_variable("string") == ""
    assert element_for_variable("") == ""


# ── The fire-time binding ─────────────────────────────

def test_the_engine_binds_the_source_token_from_the_activation():
    from transversal.services.effects_engine import GameEvent
    from transversal.services.effects_engine.engine import _activation_bindings

    sfx = SFX(id="sfx-x", name="X", trigger="manual", source_kind="trait_setting")
    event = GameEvent(type="manual", entity_id="e1", universe="earth", context={})
    bindings = _activation_bindings(sfx, event, "e1:cultivation")

    assert set(bindings) == {"trait_setting"}
    assert bindings["trait_setting"].value == "e1:cultivation"
    assert bindings["trait_setting"].element == "traitsetting"


def test_the_source_instance_binds_its_own_order_as_an_integer():
    """`{order}` is the source's *position* — the 2nd sub-trait exposes `2`.

    It has no event-carried value: it is a fact about the instance the rule lives
    on, so it is read from the resolved source. That is what lets a path say
    `filter index == {order}` without an ordering step.
    """
    from transversal.services.effects_engine import GameEvent
    from transversal.services.effects_engine.engine import _activation_bindings

    sfx = SFX(id="sfx-x", name="X", trigger="on_challenge_completed",
              source_kind="trait_setting")
    event = GameEvent(type="challenge_completed", entity_id="e1", universe="earth",
                      context={"trait_setting_id": "e1:portent-2"})
    source = NS(id="e1:portent-2", order=2)
    bindings = _activation_bindings(sfx, event, "e1:portent-2", source)

    assert bindings["order"].value == "2"
    assert bindings["order"].element == "int"


def test_an_unordered_source_binds_no_order():
    """A top-level trait has no position. `order` is deliberately not coerced to
    0, so a path that filters on it finds nobody rather than the first slot."""
    from transversal.services.effects_engine import GameEvent
    from transversal.services.effects_engine.engine import _activation_bindings

    sfx = SFX(id="sfx-x", name="X", trigger="on_challenge_completed",
              source_kind="trait_setting")
    event = GameEvent(type="challenge_completed", entity_id="e1", universe="earth",
                      context={"trait_setting_id": "e1:cultivation"})
    source = NS(id="e1:cultivation", order=None)

    assert "order" not in _activation_bindings(sfx, event, "e1:cultivation", source)


def test_the_engine_binds_a_trigger_variable_from_the_event():
    from transversal.services.effects_engine import GameEvent
    from transversal.services.effects_engine.engine import _activation_bindings

    sfx = SFX(id="sfx-x", name="X", trigger="on_pool_change")
    event = GameEvent(type="pool_changed", entity_id="e1", universe="earth",
                      context={"contest_entity_opponent": "guard-1"})
    bindings = _activation_bindings(sfx, event, None)

    assert set(bindings) == {"contest_entity_opponent"}
    assert bindings["contest_entity_opponent"].value == "guard-1"
    assert bindings["contest_entity_opponent"].element == "entity"


def test_a_name_the_event_does_not_carry_is_left_unbound():
    """At a pool save with no contest there is no opponent: a path starting from
    one should resolve to nobody, not to a blank id."""
    from transversal.services.effects_engine import GameEvent
    from transversal.services.effects_engine.engine import _activation_bindings

    sfx = SFX(id="sfx-x", name="X", trigger="on_pool_change")
    event = GameEvent(type="pool_changed", entity_id="e1", universe="earth", context={})
    assert _activation_bindings(sfx, event, None) == {}


# ── End to end through the engine ─────────────────────

class SeedRepo:
    """Just enough repo for a path to walk a bound id to its object."""

    def __init__(self):
        self.entities = {
            "e1": Entity(id="e1", name="Kael", type=EntityType.CHARACTER,
                         current_universe="earth", current_location="loc-1"),
            "loc-1": Entity(id="loc-1", name="Azure Dawn", type=EntityType.LOCATION,
                            current_universe="earth"),
        }
        self.ts = NS(id="e1:cultivation", trait_id="trait-cultivation", traitset_id="ts-cult",
                     entity_id="e1", rating="d8", dice=[DieType.D8])

    def get_entity(self, eid):
        return self.entities.get(eid)

    def get_traitsetting(self, ts_id):
        return self.ts if ts_id == "e1:cultivation" else None

    def get_effective_traitsettings(self, entity_id, universes=None):
        # Ownership resolution's read (what a manual activation falls back to
        # when the client sent no source id). Empty = this entity holds nothing
        # that could be this rule's source, so no source resolves.
        return []


def _apply_spy():
    """A recording handler for a test-only effect action."""
    from transversal.services.effects_applier import effect_registry

    applied = []
    effect_registry.register("testseed", "noop", lambda *a, **k: applied.append(1))
    return applied


def test_a_condition_path_can_start_from_the_source_token():
    """The whole point: *the trait this rule is attached to* is a path seed."""
    from transversal.services.effects_engine import EffectsEngine, GameEvent

    spec = TargetSpec(steps=[
        {"kind": "select", "collection": "variable", "variable": "trait_setting"},
        {"kind": "navigate", "edge": "entity"},
    ])
    sfx = SFX(
        id="sfx-x", name="X", trigger="manual", source_kind="trait_setting",
        conditions=[Condition(type=ConditionType.TARGET_PATH, spec=spec)],
        effects=[Effect(timing=EffectTiming.IMMEDIATE, type="testseed", action="noop")],
    )
    engine = EffectsEngine()
    engine.register(sfx)
    applied = _apply_spy()
    repo = SeedRepo()

    # With the source resolved (a manual activation passes its id), the gate can
    # evaluate: the path walks the trait instance to its owner.
    event = GameEvent(type="manual", entity_id="e1", universe="earth",
                      context={"source_id": "e1:cultivation"})
    engine.process_event_outcome(event, ["sfx-x"], 0, repo=repo)
    assert applied == [1]

    # An id that resolves to nothing binds nothing usable: the path comes back
    # empty and the gate does not pass — the honest answer, not an exception.
    applied.clear()
    event = GameEvent(type="manual", entity_id="e1", universe="earth",
                      context={"source_id": "e1:gone"})
    engine.process_event_outcome(event, ["sfx-x"], 0, repo=repo)
    assert applied == []


def test_a_path_can_start_from_the_opponent_in_the_moment():
    from transversal.services.effects_engine import EffectsEngine, GameEvent

    spec = TargetSpec(steps=[
        {"kind": "select", "collection": "variable", "variable": "contest_entity_opponent"},
        {"kind": "navigate", "edge": "location"},
    ])
    sfx = SFX(
        id="sfx-y", name="Y", trigger="on_pool_change",
        conditions=[Condition(type=ConditionType.TARGET_PATH, spec=spec)],
        effects=[Effect(timing=EffectTiming.IMMEDIATE, type="testseed", action="noop")],
    )
    engine = EffectsEngine()
    engine.register(sfx)
    applied = _apply_spy()
    repo = SeedRepo()

    event = GameEvent(type="pool_changed", entity_id="e1", universe="earth",
                      context={"contest_entity_opponent": "e1"})
    engine.process_event_outcome(event, ["sfx-y"], 0, repo=repo)
    assert applied == [1], "the opponent's location should resolve through the bound seed"


def test_armed_effects_keep_the_activation_seeds():
    """A roll-timed effect fires after the moment that armed it has passed, so the
    seeds are snapshotted with the rest of the activation — the same reason
    ``source_id`` is carried there."""
    from transversal.services.roll_deferral import _armed, arm_passive, arm_sfx
    from transversal.services.target_resolver import Binding

    seeds = {"trait_setting": Binding(value="e1:cultivation", element="traitsetting", cardinality="one")}
    effect = Effect(timing=EffectTiming.ON_ROLL, type="modify_trait", action="step_up", target="self")
    try:
        _armed.clear()
        arm_sfx("e1", [effect], source_sfx_id="sfx-x", source_kind="trait_setting",
                source_id="e1:cultivation", bindings=seeds)
        assert _armed["e1"][0].bindings == seeds

        from transversal.services import roll_deferral
        roll_deferral._global_armed.clear()
        arm_passive([effect], source_sfx_id="sfx-x", bindings=seeds)
        assert roll_deferral._global_armed[0].bindings == seeds
    finally:
        _armed.clear()
        from transversal.services import roll_deferral
        roll_deferral._global_armed.clear()


def test_the_bound_seed_types_the_path_for_the_tracer():
    """`select variable` type-checks against the seed, not against nothing."""
    from transversal.services import target_spec as ts

    spec = TargetSpec(steps=[{"kind": "select", "collection": "variable",
                              "variable": "contest_entity_opponent"}])
    types, errors = ts.trace(spec, variables={"contest_entity_opponent": "entity"})
    assert errors == []
    assert types[-1] == ts.ValueType("entity", "one")
