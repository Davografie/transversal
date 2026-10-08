"""A reference's question must carry what its **answer** needs.

Answering a mid-path `choose` does not resume the engine: `resolveEffectTargets`
rebuilds the resolution context from what the client echoes back, and a path that
starts `select source` resolves only if `source_kind`/`source_id` came along.

They did not. The engine emitted every reference question with an empty source, so
the first press asked (the engine's own context *did* have the source) and the
answer then resolved `select source` to nobody — **no application, no question, no
note**. That is what `sfx-transverse` did on every press: the author answered
"which body", and nothing happened.
"""

from __future__ import annotations

from types import SimpleNamespace as NS

import pytest

from transversal.domain import Effect, EffectTiming, SFX, TargetRef
from transversal.services.effects_engine import EffectsEngine, GameEvent
from transversal.services.effects_engine import resolve_effect_spec_choices
from transversal.services.target_spec import (
    ChooseStep,
    NavigateStep,
    SelectStep,
    TargetSpec,
)


class _Repo:
    """One actor with one body placed in another universe."""

    def __init__(self):
        self.entities = {
            "kael": NS(id="kael", type="character", current_universe="earth",
                       current_location="loc-0", current_projection="kael:earth"),
            "loc-9": NS(id="loc-9", type="location", current_universe="three_realms"),
        }
        self.projections = [
            NS(id="kael:three_realms", entity_id="kael", universe="three_realms",
               current_location="loc-9", transversal_type="CONSCIOUSNESS"),
        ]

    def get_entity(self, eid):
        return self.entities.get(eid)

    def get_projection(self, pid):
        return next((p for p in self.projections if p.id == pid), None)

    def get_projections_for_entity(self, eid):
        return [p for p in self.projections if p.entity_id == eid]


@pytest.fixture(autouse=True)
def _own_repo(monkeypatch):
    """Keep this module hermetic: the applier re-resolves through ``main``."""
    import transversal.main as main

    repo = _Repo()
    monkeypatch.setattr(main, "_get_repo", lambda: repo, raising=False)
    monkeypatch.setattr(main, "_repo", repo, raising=False)
    return repo


def _travel_effect() -> Effect:
    """`travel/move` shaped like `sfx-transverse`: destination *through a body*.

    `select source → navigate projections → choose output "target_projection" →
    navigate location`, and a second reference that reads the name it produced.
    """
    return Effect(
        timing=EffectTiming.IMMEDIATE, type="travel", action="move",
        context={"transversal_type": "consciousness"},
        refs={
            "recipient": TargetRef(spec=TargetSpec(steps=[
                SelectStep(collection="source"),
            ])),
            "location": TargetRef(spec=TargetSpec(steps=[
                SelectStep(collection="source"),
                NavigateStep(edge="projections"),
                ChooseStep(count=1, output="target_projection"),
                NavigateStep(edge="location"),
            ])),
            "projection": TargetRef(spec=TargetSpec(steps=[
                SelectStep(collection="variable", variable="target_projection"),
            ])),
        },
    )


def _press(repo):
    effect = _travel_effect()
    engine = EffectsEngine()
    engine.register(SFX(id="sfx-x", name="Transverse", trigger="manual",
                        source_kind="entity", effects=[effect]))
    outcome = engine.process_event_outcome(
        GameEvent(type="manual", entity_id="kael", universe="earth"),
        available_sfx_ids=["sfx-x"], razmerit_balance=10, repo=repo,
    )
    return effect, outcome


def test_a_reference_question_carries_the_source_its_answer_needs(_own_repo):
    """What the press asks must include the source, or the answer cannot rebuild it."""
    _effect, outcome = _press(_own_repo)
    assert outcome.applied == [], "nothing is applied while a question is open"

    choices = [c for c in outcome.structured if c.field == "refs.location"]
    assert choices, "the destination path asks which body to travel through"
    choice = choices[0]
    assert (choice.source_kind, choice.source_id) == ("entity", "kael"), (
        "an empty source here is unresolvable on resume, silently"
    )


def test_answering_the_question_resolves_the_destination(_own_repo):
    """The whole journey: press, then answer exactly as the sheet echoes it back."""
    effect, outcome = _press(_own_repo)
    choice = next(c for c in outcome.structured if c.field == "refs.location")

    applied, pending = resolve_effect_spec_choices(
        effect, choice.field, {choice.step_index: ["kael:three_realms"]},
        _own_repo.get_entity("kael"), _own_repo,
        source_kind=choice.source_kind, source_id=choice.source_id,
        source_sfx_id="sfx-x",
    )

    assert pending == []
    assert len(applied) == 1, "the answer resolved to nobody"
    assert applied[0].target == "loc-9", "the destination is where the chosen body is"
    assert applied[0].refs["projection"].value == "kael:three_realms"
