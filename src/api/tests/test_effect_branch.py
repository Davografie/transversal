"""Choice nodes ([[B5]]): an effect that is *asked*, not applied.

The author's model: every effect is a node, the rule knows which node is active, and
a satisfied node moves to the next. A branch is the node where the player answers —
so it reports its options and stops, and the answer's own effects are applied by
`resolve_branch_effects`.
"""

from types import SimpleNamespace as NS

from transversal.domain import Effect, EffectBranch, EffectTiming
from transversal.services.effects_applier import (
    apply_effects, branch_options, resolve_branch_effects,
)


def _entity(razmerit=0):
    return NS(id="char-1", razmerit=razmerit, current_universe="earth",
              current_location="loc-1", current_projection=None, life_paths=[],
              pending_term=None)


class Repo:
    """Just enough for a branch: nothing is applied, so nothing is looked up."""

    def get_entity(self, eid):
        return _entity()


def _branch(**kw):
    return Effect(
        timing=EffectTiming.IMMEDIATE, type="branch", action="choose",
        branches=[EffectBranch(id="keep", label="Let the rating stand"),
                  EffectBranch(id="change", label="Change the statement",
                               effects=[Effect(type="modify_trait", action="set_statement",
                                               target="trait-challenge",
                                               result="the mountain remembers")])],
        **kw,
    )


def test_a_branch_is_asked_rather_than_applied():
    entity = _entity()
    result = apply_effects(entity, [_branch()], Repo())

    assert [a for a in result.applied] == [], "a choice node applies nothing itself"
    assert len(result.pending_branches) == 1
    pending = result.pending_branches[0]
    assert pending.options == [("keep", "Let the rating stand"),
                               ("change", "Change the statement")]
    assert pending.effect is not None


def test_the_answer_runs_that_option_s_effects():
    effect = _branch()
    chosen = resolve_branch_effects(effect, "change")
    assert [e.action for e in chosen] == ["set_statement"]
    assert chosen[0].result == "the mountain remembers"
    # The default branch does nothing, which is a legitimate outcome: for the
    # author's case the rating simply stands.
    assert resolve_branch_effects(effect, "keep") == []


def test_an_answer_may_name_the_option_by_id_position_or_label():
    effect = _branch()
    assert [e.action for e in resolve_branch_effects(effect, "2")] == ["set_statement"]
    assert [e.action for e in resolve_branch_effects(effect, "Change the statement")] == [
        "set_statement"]


def test_an_unmade_or_unknown_choice_yields_nothing():
    effect = _branch()
    assert resolve_branch_effects(effect, "") == []
    assert resolve_branch_effects(effect, "no-such-option") == []


def test_options_default_their_id_and_label_rather_than_rendering_blank():
    effect = Effect(type="branch", action="choose",
                    branches=[EffectBranch(), EffectBranch(label="Second")])
    assert branch_options(effect) == [("1", "Option 1"), ("2", "Second")]
    assert resolve_branch_effects(effect, "1") == []


def test_a_choice_with_no_options_says_so():
    result = apply_effects(_entity(), [Effect(type="branch", action="choose")], Repo())
    assert result.pending_branches == []
    assert "no options" in result.applied[0].summary


def test_set_statement_rewrites_the_instance_and_records_the_prior():
    """Branch B's action: what the trait *is*, not how it is rated."""
    from transversal.services.effects_applier import apply_effects as apply_
    from transversal.domain import TraitSetting

    ts = TraitSetting(id="char-1:trait-challenge", entity_id="char-1",
                      traitset_id="ts-challenge", trait_id="trait-challenge",
                      statement="the mountain endures", dice=["d8"])
    entity = _entity()

    class StatementRepo(Repo):
        def get_traitsetting(self, tid):
            return ts if tid == ts.id else None

        def get_traitsettings_for_entity(self, eid):
            return [ts]

        def get_traitsetting_by_id(self, tid):
            return ts if tid == ts.id else None

    result = apply_([entity], [], StatementRepo()) if False else apply_(
        entity,
        [Effect(type="modify_trait", action="set_statement", target=ts.id,
                result="the mountain remembers")],
        StatementRepo(),
    )
    assert ts.statement == "the mountain remembers"
    assert ts in result.updated_trait_settings
    assert "remembers" in result.applied[0].summary
