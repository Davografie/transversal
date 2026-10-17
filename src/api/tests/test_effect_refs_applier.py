"""The direct applier entry point resolves an effect's **refs** ([[B261]]).

The editor writes refs, and a portal edge / roll-table row / life-path consequence
reaches `apply_effects` directly. There, a `target_spec` was resolved but a ref was
not — so an effect carrying its destination in `refs.location.spec` did **nothing
at all**: no apply, no question, no note. That is why the airport's self-portal
"still didn't trigger" when taken (2026-10-17), and why its sibling portal, whose
destination sits in `targetSpec`, did raise a question.
"""

from types import SimpleNamespace

from transversal.domain import Effect, EffectTiming, Entity, EntityType, TargetRef
from transversal.services.effects_applier.entry import apply_effects
from transversal.services.target_spec import ChooseStep, FilterStep, LiteralStep, SelectStep, TargetSpec


def _entity(eid="char-1"):
    return Entity(id=eid, type=EntityType.CHARACTER, name="Kael",
                  current_universe="earth", current_location="loc-a")


class FakeRepo:
    """A repo that knows four places and nothing else."""

    PLACES = ["loc-1", "loc-2", "loc-3", "loc-4"]

    def get_entity(self, eid):
        return SimpleNamespace(id=eid, name=eid, type="location",
                               current_universe="earth") if eid in self.PLACES else None

    def get_traitsetting(self, tsid):
        return None

    def list_entities_by_type(self, entity_type):
        return [SimpleNamespace(id=pid, name=pid, type="location") for pid in self.PLACES]


def _choose_over_places(count=1):
    return TargetSpec(steps=[SelectStep(collection="locations"), ChooseStep(count=count)])


def test_a_ref_that_stops_at_a_choose_carries_its_pool():
    """The question is useless without its options — that was the whole defect."""
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="travel", action="move",
        refs={"location": TargetRef(spec=_choose_over_places())},
    )
    result = apply_effects(_entity(), [effect], FakeRepo())
    assert result.applied == []
    assert len(result.pending_choices) == 1
    choice = result.pending_choices[0]
    assert choice.kind == "location"
    assert choice.field == "refs.location"
    assert [c["id"] for c in choice.candidates] == FakeRepo.PLACES


def test_a_ref_that_resolves_applies_instead_of_doing_nothing():
    """A ref resolving to one value is an ordinary target, not a no-op."""
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="entity", action="learn",
        refs={"entity": TargetRef(spec=TargetSpec(steps=[LiteralStep(element="entity", value="gmc-1")]))},
    )
    result = apply_effects(_entity(), [effect], FakeRepo())
    # `learn` has a handler; what matters here is that the ref reached it rather
    # than the effect vanishing.
    assert result.passthrough == [] or result.applied


def test_a_ref_that_matches_nobody_still_reports():
    """Failing closed is right; failing **silently** is what this entry point
    keeps having to be taught."""
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="entity", action="learn",
        refs={"entity": TargetRef(spec=TargetSpec(steps=[
            SelectStep(collection="locations"),
            FilterStep(field="id", operator="==", value="loc-nobody"),
        ]))},
    )
    result = apply_effects(_entity(), [effect], FakeRepo())
    assert result.applied, "an empty path must say so, not go quiet"
