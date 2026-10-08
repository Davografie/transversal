"""Do the positional path and the declared reference path decide the same thing?

[[B261]] ends by deleting the positional fields, and that is only safe if an
effect applying through the **references** branch does exactly what the same
effect did through the **target** branch. The two branches are not the same code:
the target branch is `_apply_immediate_spec`, the references branch walks the
primary targets and then the refs and applies once per (target x reference).

So this file takes one effect, expresses its target twice -- as `target_spec` and
as the declared reference the migration would move it into -- and asserts the
engine decides the same thing both times: the same applications, in the same
order, with the same concrete target values.

Handlers are replaced by a tracking registry, because what is under test is the
engine's *decision*, not what a handler does with it.
"""

from __future__ import annotations

from types import SimpleNamespace as NS

import pytest

from transversal.domain import Effect, EffectTiming, SFX, TargetRef
from transversal.services.effects_engine import EffectsEngine, GameEvent
from transversal.services.target_spec import FilterStep, SelectStep, TargetSpec

#: `modify_roll/step_up_die` declares a `die` reference, so the same target can be
#: written either way: `effect.target_spec` (positional) or `refs["die"]`.
ACTION = {"type": "modify_roll", "action": "step_up_die"}
REF_NAME = "die"


class _Repo:
    def __init__(self, owners=("kael", "gmc-1", "gmc-2")):
        self.entities = {
            i: NS(id=i, current_location="loc-1", current_universe="earth")
            for i in owners
        }

    def get_entity(self, eid):
        return self.entities.get(eid)

    def list_entities_by_location(self, _loc):
        return list(self.entities.values())


@pytest.fixture(autouse=True)
def _own_repo(monkeypatch):
    """Hermetic: the applier re-resolves through the shared `main._get_repo()`."""
    import transversal.main as main

    repo = _Repo()
    monkeypatch.setattr(main, "_get_repo", lambda: repo, raising=False)
    monkeypatch.setattr(main, "_repo", repo, raising=False)
    return repo


@pytest.fixture(autouse=True)
def _tracking_registry(monkeypatch):
    """A handler for every action, so applying is observable but inert."""
    from transversal.services.effects_applier import EffectRegistry
    from transversal.services.effects_applier import registry as registry_mod

    seen = []
    reg = EffectRegistry()
    reg.register("*", "*", lambda action, eid, universe, ctx: seen.append(action))
    monkeypatch.setattr(registry_mod, "effect_registry", reg, raising=False)
    import transversal.services.effects_engine.engine as engine_mod
    monkeypatch.setattr(engine_mod._effects_applier, "effect_registry", reg, raising=False)
    return seen


def _fire(effect, repo, structured=None):
    engine = EffectsEngine()
    engine.register(SFX(id="sfx-x", name="X", trigger="manual", effects=[effect]))
    return engine.process_event_outcome(
        GameEvent(type="manual", entity_id="kael", universe="earth"),
        available_sfx_ids=["sfx-x"], razmerit_balance=10, repo=repo,
        arm_deferred=False,
    )


def _spec(*steps) -> TargetSpec:
    return TargetSpec(steps=list(steps))


def _positional(spec: TargetSpec) -> Effect:
    return Effect(timing=EffectTiming.IMMEDIATE, **ACTION, target_spec=spec)


def _referenced(spec: TargetSpec) -> Effect:
    """The same selection, written as the reference the migration would use."""
    return Effect(timing=EffectTiming.IMMEDIATE, **ACTION,
                  refs={REF_NAME: TargetRef(spec=spec)})


def _decided(outcome):
    """What the engine decided: one entry per application, with its target."""
    return [(e.type, e.action, e.target, e.result) for e in outcome.applied]


def _both(spec, repo):
    return (_decided(_fire(_positional(spec), repo)),
            _decided(_fire(_referenced(spec), repo)))


def _one(spec_steps, repo):
    return _both(_spec(*spec_steps), repo)


OCCUPANTS = SelectStep(collection="occupants")
ONLY_GMC_1 = FilterStep(field="id", operator="==", value="gmc-1")
ONLY_NOBODY = FilterStep(field="id", operator="==", value="nobody")


def test_a_single_target_decides_the_same_either_way(_own_repo):
    positional, referenced = _one([OCCUPANTS, ONLY_GMC_1], _own_repo)
    assert positional == referenced
    assert len(positional) == 1


def test_a_fan_out_decides_the_same_either_way(_own_repo):
    positional, referenced = _one([OCCUPANTS], _own_repo)
    assert positional == referenced, "same applications, same targets, same order"
    assert len(positional) == 3, "one per occupant"


def test_nothing_found_decides_the_same_either_way(_own_repo):
    positional, referenced = _one([OCCUPANTS, ONLY_NOBODY], _own_repo)
    assert positional == referenced == [], "both fail closed"


def test_a_question_is_raised_the_same_either_way(_own_repo):
    """The decision includes *asking*: both shapes stop and ask the same question.

    The `field` differs on purpose, and it is the one thing that **must**: it is
    the key the answer is routed back under (the client echoes the choice's field
    into `resolveEffectTargets`), so it follows the vocabulary — `target` for the
    positional form, `refs.die` for the reference. What has to match is the
    question itself: the same candidates and the same amount.
    """
    from transversal.services.target_spec import ChooseStep

    spec = _spec(OCCUPANTS, ChooseStep(count=1))
    positional = _fire(_positional(spec), _own_repo)
    referenced = _fire(_referenced(spec), _own_repo)
    assert positional.applied == referenced.applied == []

    def questions(outcome):
        return [(len(c.candidates), c.count, c.element) for c in outcome.structured]

    assert questions(positional) == questions(referenced)
    assert [c.field for c in positional.structured] == ["target"]
    assert [c.field for c in referenced.structured] == [f"refs.{REF_NAME}"]


# --- the exception: BOTH paths on one effect ---------------------------------

def test_a_subject_path_that_resolves_to_nothing_fails_open_but_a_ref_fails_closed(_own_repo):
    """**The content migration's known exception, found by dry-running it live.**

    `resolve_effect_entity` is deliberately fail-**open**: a subject spec that
    resolves to nothing "leaves the effect as authored so the existing 'resolved
    to nothing' report still fires" — and the effect then acts on the acting
    entity. `resolve_refs` is deliberately fail-**closed**: a ref resolving to
    zero values returns no effects at all.

    So moving a subject path into a reference changes what happens when the path
    finds nobody: the positional form still applies (to the actor), the reference
    form applies nothing. Two stored effects in the live corpus are in exactly
    this state (`sfx-three-realms-arrival`, `sfx-banish`), and one of them also
    fans out differently once the subject joins the cartesian product.

    This test exists so the exception is *recorded and checked*, not discovered
    again during the migration. Deciding it is part of running the migration.
    """
    from transversal.services.target_spec import ChooseStep  # noqa: F401

    target = _spec(OCCUPANTS, ONLY_GMC_1)          # resolves to one
    nobody = _spec(OCCUPANTS, ONLY_NOBODY)         # resolves to nothing

    positional = Effect(timing=EffectTiming.IMMEDIATE, **ACTION,
                        target_spec=target, entity_spec=nobody)
    referenced = Effect(timing=EffectTiming.IMMEDIATE, **ACTION,
                        refs={REF_NAME: TargetRef(spec=target),
                              "recipient": TargetRef(spec=nobody)})

    # The positional form applies (the subject falls back to the actor)…
    assert len(_decided(_fire(positional, _own_repo))) == 1
    # …and the reference form does not (one ref resolved to nobody).
    assert _decided(_fire(referenced, _own_repo)) == []
