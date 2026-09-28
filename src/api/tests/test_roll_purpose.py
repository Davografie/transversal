"""Roll purpose, derived from trait tags ([[B235]]).

The author's ruling, 2026-09-28: *"roll purpose can be derived from trait tags."*
So a roll carries no authored intent — the pool's traits say what the roll is for,
which keeps the gate a *rule* rather than a claim the client makes about itself.

The published SFX need this constantly: *"when you roll to inflict Damaged"*,
*"on a roll to create an asset"*, *"when helping others recover"*. Before this an
author could only say it by walking ``pool → dice → traitsetting → filter tags``,
which asks a structural question where the rule means a semantic one.
"""

from types import SimpleNamespace

from transversal.domain import Condition, ConditionType
from transversal.services.conditions import CONDITION_TYPES, evaluate_condition
from transversal.services.roll_purpose import roll_purpose


class _Repo:
    """Minimal repo: a trait instance knows its trait, a trait knows its tags."""

    def __init__(self, settings, traits):
        self._settings = settings
        self._traits = traits

    def get_traitsetting(self, ts_id):
        return self._settings.get(ts_id)

    def get_trait(self, trait_id):
        return self._traits.get(trait_id)


def _repo(settings, traits):
    return _Repo(
        {k: SimpleNamespace(trait_id=v[0], tags=v[1]) for k, v in settings.items()},
        {k: SimpleNamespace(tags=v) for k, v in traits.items()},
    )


class TestTheDerivation:
    def test_reads_the_tags_of_every_trait_in_the_pool(self):
        repo = _repo(
            settings={"s1": ("t-sword", []), "s2": ("t-charm", [])},
            traits={"t-sword": ["weapon", "combat"], "t-charm": ["social"]},
        )
        assert roll_purpose([{"ts_id": "s1"}, {"ts_id": "s2"}], repo) == [
            "weapon", "combat", "social"]

    def test_instance_tags_come_too(self):
        """A particular blade being a weapon is a fact about the instance."""
        repo = _repo(settings={"s1": ("t-blade", ["silver"])}, traits={"t-blade": ["weapon"]})
        assert roll_purpose([{"ts_id": "s1"}], repo) == ["silver", "weapon"]

    def test_the_same_trait_twice_does_not_repeat_its_tags(self):
        repo = _repo(settings={"s1": ("t-sword", [])}, traits={"t-sword": ["weapon"]})
        assert roll_purpose([{"ts_id": "s1"}, {"ts_id": "s1"}], repo) == ["weapon"]

    def test_a_die_with_no_trait_contributes_nothing(self):
        """Manual dice, difficulty dice, and a deleted trait's instance."""
        repo = _repo(settings={}, traits={})
        assert roll_purpose([{"ts_id": ""}, {"ts_id": None}, {"ts_id": "gone"}], repo) == []

    def test_an_empty_purpose_is_a_real_answer_not_an_unknown(self):
        """No tagged trait in the pool is the honest reading of "not an attack"."""
        repo = _repo(settings={"s1": ("t-plain", [])}, traits={"t-plain": []})
        assert roll_purpose([{"ts_id": "s1"}], repo) == []

    def test_it_reads_models_as_well_as_dicts(self):
        """The live path yields dicts and the legacy resolver yields DieRolls."""
        repo = _repo(settings={"s1": ("t-sword", [])}, traits={"t-sword": ["weapon"]})
        assert roll_purpose([SimpleNamespace(ts_id="s1")], repo) == ["weapon"]

    def test_no_repo_is_an_empty_purpose(self):
        assert roll_purpose([{"ts_id": "s1"}], None) == []


class TestTheCondition:
    @staticmethod
    def _gate(operator, target, purpose):
        cond = Condition(type=ConditionType.ROLL_PURPOSE, operator=operator, target=target)
        return evaluate_condition(None, cond, None, context={"purpose": purpose})

    def test_contains_is_any_of(self):
        assert self._gate("contains", "combat", ["weapon", "combat"]) is True
        assert self._gate("contains", "combat", ["social"]) is False

    def test_not_contains_is_none_of(self):
        assert self._gate("not contains", "combat", ["social"]) is True
        assert self._gate("not contains", "combat", ["weapon", "combat"]) is False

    def test_several_tags_are_any_of(self):
        """The target takes several values, like every other filter."""
        cond = Condition(type=ConditionType.ROLL_PURPOSE, operator="contains",
                         targets=["combat", "social"])
        assert evaluate_condition(None, cond, None, context={"purpose": ["social"]}) is True

    def test_not_contains_on_an_untagged_pool_passes(self):
        """An empty purpose is "nothing here matches", so the negative reading holds."""
        assert self._gate("not contains", "combat", []) is True
        assert self._gate("contains", "combat", []) is False

    def test_no_target_does_not_pass(self):
        assert self._gate("contains", "", ["combat"]) is False

    def test_it_reads_the_context_key_it_declares(self):
        from transversal.services.conditions import context_keys_for

        assert context_keys_for(trigger="on_result") is not None
        meta = next(d for d in CONDITION_TYPES if d.value == ConditionType.ROLL_PURPOSE.name)
        assert meta.requires_context_any_of == ("purpose",)
        # Only the two list operators: `==` or `in` on a list would be silently wrong.
        assert set(meta.operators) == {"contains", "not contains"}
        assert meta.value_kind == ""
        assert meta.target_placeholder == "tag"
