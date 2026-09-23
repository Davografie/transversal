"""The loop guard: a rule re-entering the change it is already handling.

An auto-triggered rule whose effect causes another event **of the thing it is
acting on** is re-entering itself — a trait it steps up, a challenge it fills.
That is a loop, and it is offered to the table rather than recursed.

The important half is *only then*. A rule acting on a second, different thing —
an agenda rule filling its parent challenge — is a **new application**, not a
loop. The guard this replaced was keyed `(entity_id, event_type)` and refused
*any* same-type nesting, so it silently swallowed the agenda's terminal "the
agenda is complete" event and, with it, every rule cascade that passed through
the same kind of change twice.
"""

from transversal.domain import Effect, EffectTiming, SFX
from transversal.services.effects_engine import EffectsEngine, GameEvent
from transversal.services.effects_engine.shared import RULE_CHAIN


def _register(applier) -> EffectsEngine:
    from transversal.services.effects_applier import effect_registry

    effect_registry.register("testloop", "again", applier)
    return EffectsEngine()


def _rule(sfx_id: str, trigger: str) -> SFX:
    return SFX(
        id=sfx_id, name=sfx_id, trigger=trigger,
        effects=[Effect(timing=EffectTiming.IMMEDIATE, type="testloop",
                        action="again", target="")],
    )


def _event(event_type: str, subject: str) -> GameEvent:
    return GameEvent(type=event_type, entity_id="e1", universe="earth",
                     context={"trait_setting": subject})


def test_a_rule_re_entering_its_own_change_is_offered_not_recursed():
    """The rule changes the very trait it watches, so its own effect asks the
    engine to process that change again *while it is still applying*."""
    applied: list[str] = []
    nested = []

    engine = _register(lambda a, eid, u, ctx: None)
    engine.register(_rule("sfx-loop", "on_trait_change"))

    def _again(a, eid, u, ctx):
        applied.append("round")
        nested.append(engine.process_event_outcome(
            _event("trait_updated", "e1:x"), ["sfx-loop"], 0))

    from transversal.services.effects_applier import effect_registry

    effect_registry.register("testloop", "again", _again)

    outer = engine.process_event_outcome(
        _event("trait_updated", "e1:x"), ["sfx-loop"], 0)

    assert applied == ["round"], "the first round applies exactly once"
    assert outer.loops == [], "the first round is not a loop"
    assert len(nested[0].loops) == 1, "the re-entry is detected, not recursed"
    loop = nested[0].loops[0]
    assert loop.sfx_id == "sfx-loop"
    assert loop.iteration == 2, "the table is told which round this would be"
    assert applied == ["round"], "and nothing was applied for it"


def test_a_rule_acting_on_a_different_thing_is_not_a_loop():
    """The agenda's shape: the portent's completion fills the container, which
    completes *too*. Same entity, same event type, different thing — so the
    container's completion must run its rules, not be refused."""
    applied: list[str] = []
    nested = []

    engine = _register(lambda a, eid, u, ctx: None)
    engine.register(_rule("sfx-escalator", "on_challenge_completed"))

    def _again(a, eid, u, ctx):
        applied.append("applied")
        if len(applied) == 1:
            # Only the first round causes the next event; the second is the
            # consequence, and it must not cause a third.
            nested.append(engine.process_event_outcome(
                GameEvent(type="challenge_completed", entity_id="e1",
                          universe="earth",
                          context={"trait_setting": "e1:container"}),
                ["sfx-escalator"], 0))

    from transversal.services.effects_applier import effect_registry

    effect_registry.register("testloop", "again", _again)

    outer = engine.process_event_outcome(
        GameEvent(type="challenge_completed", entity_id="e1", universe="earth",
                  context={"trait_setting": "e1:portent"}),
        ["sfx-escalator"], 0)

    assert outer.loops == []
    assert nested[0].loops == [], (
        "a different subject is a new application, not a loop — blocking it is "
        "how the agenda's terminal event went missing"
    )
    assert applied == ["applied", "applied"], (
        "the nested application must actually run"
    )


def test_the_chain_is_left_clean_after_a_run():
    """The frame is scoped to the effect dispatch, so a finished activation
    leaves nothing behind for the next one on the same request."""
    engine = _register(lambda a, eid, u, ctx: None)
    engine.register(_rule("sfx-plain", "on_trait_change"))

    engine.process_event_outcome(_event("trait_updated", "e1:x"), ["sfx-plain"], 0)

    assert RULE_CHAIN.get() == ()
