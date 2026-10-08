"""B260/B261 — the questions arrive in the order the panel declares.

Move Trait reads *"Trait to Move"* then *"Give To"* (`refs_first=True`), so the
trait has to be asked before the recipient. The engine resolved the subject path
first and, when it raised a choice, skipped the references entirely — so the
table was asked "who" before "what", the reverse of the form it was reading.
"""

from __future__ import annotations

from types import SimpleNamespace as NS

import pytest

from transversal.domain import Effect, EffectTiming, SFX, TargetRef
from transversal.services.effects_engine import EffectsEngine, GameEvent
from transversal.services.effects_registry.lookup import refs_before_fields
from transversal.services.target_spec import ChooseStep, SelectStep, TargetSpec


class _Repo:
    """Two people in one place — enough for a `choose` to be a real question."""

    def __init__(self):
        self.entities = {
            "kael": NS(id="kael", current_location="loc-1", current_universe="earth"),
            "gmc-1": NS(id="gmc-1", current_location="loc-1", current_universe="earth"),
        }

    def get_entity(self, eid):
        return self.entities.get(eid)

    def list_entities_by_location(self, _loc):
        return list(self.entities.values())


@pytest.fixture(autouse=True)
def _own_repo(monkeypatch):
    """Keep this module hermetic.

    Passing ``repo=`` to the engine is not enough: the *applier* re-resolves a
    spec through ``transversal.main._get_repo()`` on its way to commit, and other
    suites leave that global pointed at their own fake — which is how these tests
    passed alone and failed in the full run.
    """
    import transversal.main as main

    repo = _Repo()
    monkeypatch.setattr(main, "_get_repo", lambda: repo, raising=False)
    monkeypatch.setattr(main, "_repo", repo, raising=False)
    return repo


def _choose_from_occupants() -> TargetSpec:
    return TargetSpec(steps=[SelectStep(collection="occupants"), ChooseStep(count=1)])


def _gift_shaped_effect() -> Effect:
    """`modify_trait/move` exactly as Gift carries it: a subject path that has to
    ask, and a trait reference that has to ask."""
    return Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_trait", action="move",
        entity_spec=_choose_from_occupants(),
        refs={"trait": TargetRef(spec=_choose_from_occupants())},
    )


def _fire(effect: Effect, repo):
    engine = EffectsEngine()
    engine.register(SFX(id="sfx-x", name="X", trigger="manual", effects=[effect]))
    return engine.process_event_outcome(
        GameEvent(type="manual", entity_id="kael", universe="earth"),
        available_sfx_ids=["sfx-x"], razmerit_balance=10, repo=repo,
    )


def test_a_refs_first_action_asks_its_reference_before_its_subject(_own_repo):
    outcome = _fire(_gift_shaped_effect(), _own_repo)
    assert outcome.structured, "expected a question"
    assert outcome.structured[0].field == "refs.trait", (
        "the trait is the action's subject-of-record and reads first in the panel"
    )


def test_only_one_question_is_asked_at_a_time(_own_repo):
    """Asking the reference must not also ask the subject — the effect has to stay
    whole for the answer to re-resolve, and the resume walks both."""
    outcome = _fire(_gift_shaped_effect(), _own_repo)
    assert [c.field for c in outcome.structured] == ["refs.trait"]


def test_a_blocked_effect_is_not_applied(_own_repo):
    """An open question must short-circuit the whole dispatch chain.

    Asking the reference first left `blocked` true, and a restructured chain that
    guarded only the *references* branch fell through to the plain apply — so the
    effect ran before anyone had answered it. The stale global repo in the full
    suite is what surfaced it; alone, the apply silently succeeded.
    """
    outcome = _fire(_gift_shaped_effect(), _own_repo)
    assert outcome.applied == [], "nothing may be applied while a question is open"


def test_the_subject_is_still_asked_when_the_reference_has_nothing_to_ask(monkeypatch, _own_repo):
    """A reference that resolves silently must not swallow the subject's question."""
    from transversal.services.effects_engine import engine as engine_mod

    monkeypatch.setattr(engine_mod, "resolve_refs", lambda effect, *a, **k: [effect])
    outcome = _fire(_gift_shaped_effect(), _own_repo)
    assert [c.field for c in outcome.structured] == ["entity"]


def test_an_action_that_declares_fields_first_is_unchanged(_own_repo):
    """`refs_first` is the declaration; without it the subject still leads."""
    effect = _gift_shaped_effect()
    effect = effect.model_copy(update={"action": "gain"})   # gain has no refs_first
    effect.refs = {}
    outcome = _fire(effect, _own_repo)
    assert [c.field for c in outcome.structured] == ["entity"]


# --- the declaration reader --------------------------------------------------

def test_refs_before_fields_reads_both_declarations():
    from transversal.services.effects_registry.lookup import get_action_meta_for

    assert refs_before_fields(get_action_meta_for("modify_trait", "move")) is True
    assert refs_before_fields(get_action_meta_for("modify_trait", "gain")) is False
    # `field_order` naming a ref first says the same thing.
    meta = get_action_meta_for("modify_dice_limit", "increase")
    assert refs_before_fields(meta) is True
    assert refs_before_fields(None) is False
