"""Tests for the legacy-target → spec migrator.

A legacy choice compiles to the *declared* scope path (``target_scopes``) plus a
terminal choose/random step, so a migrated rule selects what it always selected.
"""

from transversal.services.target_legacy import (
    from_legacy_target,
    migrate_effect,
    migrate_sfx,
)
from transversal.services.target_spec import LiteralStep, SelectStep, TargetSpec


def test_empty_target_is_empty_spec():
    spec = from_legacy_target("", "trait")
    assert spec == TargetSpec(steps=[])


def test_self_maps_to_select_self():
    spec = from_legacy_target("self", "entity")
    assert spec.steps == [SelectStep(collection="self")]


def test_literal_id_maps_to_literal_step():
    spec = from_legacy_target("trait-environmental-hazard-58be", "trait")
    assert spec.steps == [LiteralStep(element="trait", value="trait-environmental-hazard-58be")]


def test_a_choice_compiles_to_the_declared_scope_path():
    spec = from_legacy_target("{choose:location}", "location")
    # The bare scope defers the actor (bind it, read its universe, narrow), then
    # the seed, then the choice.
    assert [s.kind for s in spec.steps] == ["select", "navigate", "select", "filter", "choose"]
    assert spec.steps[0].collection == "self"
    assert spec.steps[2].collection == "locations"


def test_a_scope_narrows_the_compiled_path():
    from transversal.services.target_legacy import from_legacy_choice

    spec = from_legacy_choice("{choose_trait}", "traitset:ts-skills")
    assert [s.kind for s in spec.steps] == ["literal", "navigate", "choose"]
    assert spec.steps[0].element == "traitset" and spec.steps[0].value == "ts-skills"
    assert spec.steps[1].edge == "traits"


def test_random_compiles_to_a_random_aggregate():
    from transversal.services.target_legacy import from_legacy_choice

    spec = from_legacy_choice("{random_occupant}", None)
    assert spec.steps[-1].kind == "aggregate" and spec.steps[-1].fn == "random"


def test_the_compiled_path_defers_the_actor() -> None:
    """A stored rule fires for whoever activates it, so the compiled path binds
    the actor (`select self`) instead of hard-coding one."""
    from transversal.services.target_legacy import from_legacy_choice

    spec = from_legacy_choice("{choose_occupant}", None)
    assert [s.kind for s in spec.steps] == ["select", "select", "filter", "choose"]
    assert spec.steps[0].collection == "self" and spec.steps[0].output
    assert spec.steps[2].value == f"{{{spec.steps[0].output}}}"


def test_variable_target_is_unmappable():
    # {effect_die} is a variable, not a target — leave legacy.
    assert from_legacy_target("{effect_die}", "die") is None


def test_unmappable_kind_returns_none():
    # life_path/roll_table have no element type in the catalog.
    assert from_legacy_target("lp-123", "life_path") is None


def test_choose_trait_is_reachable_now():
    # "All traits" exists (the registry seed), so a bare trait choice compiles.
    spec = from_legacy_target("{choose:trait}", "trait")
    assert [s.kind for s in spec.steps][-1] == "choose"


def test_a_token_that_only_looks_like_a_choice_is_left_alone():
    # `{random_starter_location}` parses like a random target but is a variable
    # policy token; it must not be rewritten into a path that selects nothing.
    from transversal.services.target_legacy import from_legacy_choice

    assert from_legacy_choice("{random_starter_location}", "universe:earth") is None


class _FakeSfx:
    def __init__(self, effects):
        self.effects = effects

    def model_copy(self, update):
        return _FakeSfx(update.get("effects", self.effects))


def _effect(**overrides):
    from transversal.domain import Effect, EffectTiming

    kwargs = dict(timing=EffectTiming.IMMEDIATE, type="modify_trait", action="gain")
    kwargs.update(overrides)
    return Effect(**kwargs)


def test_migration_compiles_a_choice_and_drops_its_scope():
    effect = _effect(target="{choose_trait}", target_scope="traitset:ts-skills")
    migrated, changed = migrate_effect(effect)
    assert changed is True
    assert migrated.target == ""
    assert migrated.target_scope is None
    assert [s.kind for s in migrated.target_spec.steps] == ["literal", "navigate", "choose"]


def test_migration_drops_an_inert_scope_on_a_literal_target():
    effect = _effect(target="trait-x", target_scope="traitset:ts-skills",
                     target_filter={"starter_location": True})
    migrated, changed = migrate_effect(effect)
    assert changed is True
    assert migrated.target == "trait-x"          # the literal is untouched
    assert migrated.target_scope is None and migrated.target_filter == {}
    assert migrated.target_spec is None


def test_migration_leaves_a_variable_target_and_a_clean_effect_alone():
    variable = _effect(target="{effect_die}", result="d6")
    assert migrate_effect(variable) == (variable, False)

    clean = _effect(target_spec=from_legacy_target("{choose:trait}", "trait"))
    assert migrate_effect(clean) == (clean, False)


def test_migration_is_idempotent():
    sfx = _FakeSfx([_effect(target="{choose_trait}", target_scope="traitset:ts-skills")])
    migrated, changed = migrate_sfx(sfx)
    assert changed is True
    again, changed_again = migrate_sfx(migrated)
    assert changed_again is False
    assert [s.kind for s in again.effects[0].target_spec.steps] == ["literal", "navigate", "choose"]
