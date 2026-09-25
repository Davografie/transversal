"""A condition's targeting-path outputs are variables the SFX's effects can use.

The motivating authoring (``sfx-d4-bonus``): "When rolling a d4 trait, gain 1
razmerit."

* the **condition** inspects *this* roll (``select rolled_dice``), keeps the d4
  traits, names them ``d4_traits``, and passes when there is at least one;
* the **effect** walks that variable from trait instances to their owning
  entities (``traitsetting → entity``) and credits one.

Before this wiring, the condition could not see the roll at all and the effect's
``entity_spec`` had no scope to resolve ``select variable`` against, so the SFX
was silent no matter how it was authored.
"""

from transversal.domain import (
    Condition,
    ConditionType,
    DieType,
    Effect,
    EffectTiming,
    Entity,
    EntityType,
    SFX,
    TargetSpec,
    TraitSetting,
)
from transversal.services import conditions as conditions_mod
from transversal.services.target_spec import (
    EvaluateStep,
    FilterStep,
    NavigateStep,
    SelectStep,
)


class FakeRepo:
    """Just the surfaces the condition path + entity hop touch."""

    def __init__(self, entities, traitsettings):
        self.entities = {e.id: e for e in entities}
        self.traitsettings = list(traitsettings)

    def get_entity(self, entity_id):
        return self.entities.get(entity_id)

    def get_traitsetting(self, ts_id):
        for ts in self.traitsettings:
            if ts.id == ts_id:
                return ts
        return None

    def get_traitsettings_for_entity(self, entity_id):
        return [ts for ts in self.traitsettings if ts.entity_id == entity_id]


def _entity(entity_id="char-1", razmerit=0):
    return Entity(
        id=entity_id, type=EntityType.CHARACTER, name=entity_id,
        current_universe="earth", razmerit=razmerit,
    )


def _ts(trait_id, die, entity_id="char-1"):
    return TraitSetting(
        id=f"{entity_id}:{trait_id}",
        entity_id=entity_id,
        trait_id=trait_id,
        dice=[die],
    )


def _die(ts_id, die="d4"):
    return {"die": die, "ts_id": ts_id, "source_kind": "trait", "role": None, "result": 3}


def _d4_traits_condition() -> Condition:
    """The authored condition: this roll includes at least one d4 trait."""
    return Condition(
        type=ConditionType.TARGET_PATH,
        spec=TargetSpec(steps=[
            SelectStep(collection="rolled_dice"),
            NavigateStep(edge="traitsetting", dedup=True),
            FilterStep(field="rating", operator="==", value="d4", output="d4_traits"),
            EvaluateStep(operator=">=", field="count", value=1),
        ]),
    )


def test_condition_sees_the_roll_and_publishes_its_output():
    repo = FakeRepo(
        entities=[_entity()],
        traitsettings=[_ts("qi", DieType.D4), _ts("focus", DieType.D8)],
    )
    bindings: dict = {}

    result = conditions_mod.evaluate_conditions(
        repo.get_entity("char-1"), [_d4_traits_condition()], repo,
        context={"rolls": [_die("char-1:qi", "d4")]},
        out_bindings=bindings,
    )

    assert result is True
    assert "d4_traits" in bindings
    assert bindings["d4_traits"].element == "traitsetting"


def test_condition_fails_when_the_roll_has_no_d4_trait():
    repo = FakeRepo(
        entities=[_entity()],
        traitsettings=[_ts("focus", DieType.D8)],
    )
    bindings: dict = {}

    result = conditions_mod.evaluate_conditions(
        repo.get_entity("char-1"), [_d4_traits_condition()], repo,
        context={"rolls": [_die("char-1:focus", "d8")]},
        out_bindings=bindings,
    )

    assert result is False


def test_condition_without_roll_context_fails_closed():
    """A path seeded from ``rolled_dice`` can't pass when no roll is in context."""
    repo = FakeRepo(entities=[_entity()], traitsettings=[_ts("qi", DieType.D4)])

    result = conditions_mod.evaluate_conditions(
        repo.get_entity("char-1"), [_d4_traits_condition()], repo, context={},
    )

    assert result is False


def test_effect_entity_spec_walks_condition_variable_to_the_entity(monkeypatch):
    """The whole chain: condition names the d4 traits, the effect credits their owner."""
    import transversal.services.effects_applier as applier_mod
    from transversal.services.effects_engine import EffectsEngine, GameEvent

    captured = []

    class CaptureRegistry:
        def apply(self, effect, entity_id, universe, context):
            captured.append(effect)

    monkeypatch.setattr(applier_mod, "effect_registry", CaptureRegistry())

    owner = _entity("char-1", razmerit=0)
    repo = FakeRepo(entities=[owner], traitsettings=[_ts("qi", DieType.D4)])

    sfx = SFX(
        id="sfx-d4-bonus",
        name="d4 bonus",
        description="When rolling a d4 trait, gain 1 razmerit.",
        trigger="on_roll",
        source_kind="table",
        conditions=[_d4_traits_condition()],
        effects=[
            Effect(
                timing=EffectTiming.IMMEDIATE,
                type="transfer_razmerit",
                action="earn",
                target="self",
                result="1",
                # Authored hop: the traits the condition named → their owning entity.
                entity_spec=TargetSpec(steps=[
                    SelectStep(collection="variable", variable="d4_traits"),
                    NavigateStep(edge="entity"),
                ]),
            ),
        ],
    )

    engine = EffectsEngine()
    engine.register(sfx)
    event = GameEvent(
        type="on_roll", entity_id="char-1", universe="earth",
        context={"rolls": [_die("char-1:qi", "d4")]},
    )

    outcome = engine.process_event_outcome(event, [sfx.id], owner.razmerit, repo=repo)

    assert len(captured) == 1
    applied = captured[0]
    # The spec is gone and a concrete entity id remains — what the razmerit
    # handler reads to decide who is credited.
    assert applied.entity == "char-1"
    assert applied.entity_spec is None
    assert applied.action == "earn"


def test_effect_entity_spec_resolves_to_nothing_without_the_condition():
    """No d4 in the roll → the gate stops the SFX before the effect runs."""
    import transversal.services.effects_applier as applier_mod
    from transversal.services.effects_engine import EffectsEngine, GameEvent

    captured = []

    class CaptureRegistry:
        def apply(self, effect, entity_id, universe, context):
            captured.append(effect)

    old = applier_mod.effect_registry
    applier_mod.effect_registry = CaptureRegistry()
    try:
        owner = _entity("char-1")
        repo = FakeRepo(entities=[owner], traitsettings=[_ts("focus", DieType.D8)])
        sfx = SFX(
            id="sfx-d4-bonus", name="d4 bonus", trigger="on_roll",
            source_kind="table",
            conditions=[_d4_traits_condition()],
            effects=[Effect(
                timing=EffectTiming.IMMEDIATE, type="transfer_razmerit",
                action="earn", target="self", result="1",
                entity_spec=TargetSpec(steps=[
                    SelectStep(collection="variable", variable="d4_traits"),
                    NavigateStep(edge="entity"),
                ]),
            )],
        )
        engine = EffectsEngine()
        engine.register(sfx)
        event = GameEvent(
            type="on_roll", entity_id="char-1", universe="earth",
            context={"rolls": [_die("char-1:focus", "d8")]},
        )

        engine.process_event_outcome(event, [sfx.id], 0, repo=repo)

        assert captured == []
    finally:
        applier_mod.effect_registry = old


def test_razmerit_effects_honour_the_authored_entity():
    """``earn``/``spend`` act on the authored entity, not silently on the actor."""
    from transversal.services.effects_applier import _razmerit_entity

    class _E:
        def __init__(self, entity):
            self.entity = entity

    # Blank / self / an unresolved placeholder → the acting entity (unchanged).
    assert _razmerit_entity(_E(""), "char-1") == "char-1"
    assert _razmerit_entity(_E("self"), "char-1") == "char-1"
    assert _razmerit_entity(_E("{buying_entity}"), "char-1") == "char-1"
    # A concrete id (a literal, or one the engine resolved from an entity_spec)
    # is who pays / is paid.
    assert _razmerit_entity(_E("char-2"), "char-1") == "char-2"
