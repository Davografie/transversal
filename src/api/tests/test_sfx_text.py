"""Derived SFX card text — [[SFX Natural Language Plan]].

Golden-text tests over the shapes the live catalogue actually uses, plus guard
tests that keep the card vocabulary honest (every card phrase is keyed to a real
action/trigger, and no edge noun double-pluralizes).
"""

from transversal.domain import Condition, ConditionType, Effect, EffectTiming, SFX
from transversal.services import effects_registry as reg
from transversal.services import menu_contexts as mc
from transversal.services import target_catalog as tc
from transversal.services.sfx_text import (
    condition_text,
    effect_text,
    path_phrase,
    pluralize,
    render_phrase,
    sfx_text,
)

# A resolver over the test ids used below.
NAMES = {
    "trait-fire": "Fire",
    "trait-qi": "Qi Condensation",
    "trait-environmental-hazard": "Environmental Hazard",
    "ts-fire-kael": "Fire",
    "loc-rusted-gate": "Rusted Gate",
}
resolve = NAMES.get


def spec(*steps) -> dict:
    return {"steps": list(steps)}


# The live `sfx-d4-bonus` condition: rolled dice → their traits → keep d4,
# naming the result `d4_traits`, then test that there is at least one.
D4_CONDITION = spec(
    {"kind": "select", "collection": "rolled_dice"},
    {"kind": "navigate", "edge": "traitsetting", "dedup": True},
    {"kind": "filter", "field": "rating", "operator": "==", "value": "d4", "output": "d4_traits"},
    {"kind": "evaluate", "operator": ">=", "field": "count", "value": 1},
)

# The live `sfx-one-trick` effect path.
ONE_TRICK_PATH = spec(
    {"kind": "select", "collection": "rolled_dice"},
    {"kind": "filter", "field": "source_kind", "operator": "==", "value": "trait"},
    {"kind": "navigate", "edge": "traitsetting", "dedup": True},
    {"kind": "filter", "field": "rating_type", "operator": "==", "value": "static"},
    {"kind": "filter", "field": "polarity", "operator": "==", "value": "positive"},
)


class TestPaths:
    def test_d4_condition_reads_as_a_predicate(self):
        cond = Condition(type=ConditionType.TARGET_PATH, spec=D4_CONDITION)
        assert condition_text(cond, resolve=resolve) == "there is at least one d4 trait"

    def test_one_trick_path_composes_to_one_noun_phrase(self):
        phrase = path_phrase(TargetSpec_of(ONE_TRICK_PATH), resolve=resolve)
        assert render_phrase(phrase, "each") == "each static positive trait instance you rolled"

    def test_navigate_absorbs_its_source(self):
        """die → traitsetting keeps the source as a relative clause, not a nested noun."""
        phrase = path_phrase(TargetSpec_of({"steps": [
            {"kind": "select", "collection": "rolled_dice"},
            {"kind": "navigate", "edge": "traitsetting"},
        ]}), resolve=resolve)
        assert render_phrase(phrase, "") == "trait instances you rolled"

    def test_self_navigate_is_possessive_then_falls_back(self):
        """One possessive hop, then back to "the X of your Y"."""
        phrase = path_phrase(TargetSpec_of({"steps": [
            {"kind": "select", "collection": "self"},
            {"kind": "navigate", "edge": "location"},
        ]}), resolve=resolve)
        assert render_phrase(phrase, "the") == "your location"

        phrase = path_phrase(TargetSpec_of({"steps": [
            {"kind": "select", "collection": "self"},
            {"kind": "navigate", "edge": "location"},
            {"kind": "navigate", "edge": "difficulty_pool"},
        ]}), resolve=resolve)
        assert render_phrase(phrase, "the") == "the GM difficulty pool of your location"

    def test_terminal_output_name_is_the_phrase(self):
        """Naming a step *is* the mechanism: the author's name wins."""
        phrase = path_phrase(TargetSpec_of({"steps": [
            {"kind": "select", "collection": "rolled_dice"},
            {"kind": "navigate", "edge": "traitsetting"},
            {"kind": "filter", "field": "rating", "operator": "==", "value": "d6",
             "output": "gritty_dice"},
        ]}), resolve=resolve)
        assert render_phrase(phrase, "each") == "each gritty die"

    def test_select_variable_renders_the_authors_name(self):
        phrase = path_phrase(
            TargetSpec_of({"steps": [{"kind": "select", "collection": "variable",
                                      "variable": "d4_traits"}]}),
            variables={"d4_traits": {"element": "traitsetting", "cardinality": "many"}},
            resolve=resolve,
        )
        assert render_phrase(phrase, "each") == "each d4 trait"

    def test_choose_is_a_quantifier_not_a_fact(self):
        phrase = path_phrase(TargetSpec_of({"steps": [
            {"kind": "select", "collection": "entities"},
            {"kind": "navigate", "edge": "traitsettings"},
            {"kind": "filter", "field": "polarity", "operator": "==", "value": "negative"},
            {"kind": "choose", "count": 1},
        ]}), resolve=resolve)
        assert render_phrase(phrase, "the") == "one of the negative trait instances of each entity"

    def test_unresolvable_id_is_shown_raw(self):
        phrase = path_phrase(TargetSpec_of({"steps": [
            {"kind": "literal", "element": "entity", "value": "char-9:nobody"},
        ]}), resolve=resolve)
        assert render_phrase(phrase, "the") == "char-9:nobody"

    def test_resolved_trait_id_reads_with_its_noun(self):
        phrase = path_phrase(TargetSpec_of({"steps": [
            {"kind": "literal", "element": "trait", "value": "trait-fire"},
        ]}), resolve=resolve)
        assert render_phrase(phrase, "the") == "the Fire trait"

    def test_existence_thresholds(self):
        base = [
            {"kind": "select", "collection": "self_traitsettings"},
        ]
        for value, operator, expected in [
            (1, ">=", "there is at least one of your trait instances"),
            (3, ">=", "there are at least 3 of your trait instances"),
            (0, "==", "there is no trait instance of yours"),
            (2, ">", "there are more than 2 of your trait instances"),
        ]:
            spec_ = {"steps": [*base, {"kind": "evaluate", "operator": operator,
                                       "field": "count", "value": value}]}
            cond = Condition(type=ConditionType.TARGET_PATH, spec=spec_)
            assert condition_text(cond) == expected, (value, operator)


class TestConditions:
    def test_narrative_is_flavour(self):
        cond = Condition(type=ConditionType.NARRATIVE, narrative="Once per session")
        assert condition_text(cond) == "Once per session"

    def test_simple_gates(self):
        assert condition_text(Condition(type=ConditionType.UNPLACED)) == \
            "you are not at a location yet"
        assert condition_text(Condition(type=ConditionType.IN_UNIVERSE, target="earth")) == \
            "you are in earth"
        assert condition_text(Condition(type=ConditionType.USER_ROLE, target="architect")) == \
            "an architect is acting"
        assert condition_text(Condition(type=ConditionType.PHASE, target="adding")) == \
            "the dice pool is in its adding phase"
        assert condition_text(Condition(type=ConditionType.HAS_RAZMERIT,
                                        operator=">=", value="2")) == \
            "you have at least 2 razmerit"


class TestEffects:
    def test_step_down_with_a_path(self):
        effect = Effect(type="modify_trait", action="step_down",
                        target_spec=ONE_TRICK_PATH, timing=EffectTiming.ON_RESULT)
        assert effect_text(effect, resolve=resolve) == \
            "whenever a roll is resolved, step down each static positive trait instance " \
            "you rolled by one step"

    def test_razmerit_amount_and_default(self):
        assert effect_text(Effect(type="transfer_razmerit", action="earn", target="self",
                                  result="2")) == "gain 2 razmerit"
        # No authored amount → the action's field default rides along.
        assert effect_text(Effect(type="transfer_razmerit", action="spend",
                                  target="self")) == "spend 1 razmerit"

    def test_placeholder_targets(self):
        assert effect_text(Effect(type="modify_trait", action="cortex_gain",
                                  target="{choose_trait}", result="{effect_die}")) == \
            "gain a trait you choose as a complication at the effect die"
        assert effect_text(Effect(type="location", action="set",
                                  target="{random:location}")) == "move to a random location"

    def test_empty_target_falls_back_to_the_declared_field(self):
        """An unauthored target still reads as a complete clause."""
        assert effect_text(Effect(type="modify_pool", action="resolve")) == \
            "resolve the dice pool"
        assert effect_text(Effect(type="entity", action="targeting_ban")) == \
            "impose a targeting ban on the acting entity"

    def test_effect_duration_is_the_undo_timer(self):
        effect = Effect(type="modify_trait", action="step_down", target="trait-fire",
                        duration={"timers": [{"event": "beat", "remaining": 2}]})
        text = effect_text(effect, resolve=resolve)
        assert text.startswith("step down the Fire trait")
        assert "reverts after 2 beat" in text

    def test_trailing_timing(self):
        effect = Effect(type="modify_trait", action="step_down", target="trait-fire",
                        timing=EffectTiming.END_OF_SESSION)
        assert effect_text(effect, resolve=resolve) == \
            "step down the Fire trait by one step, at the end of the session"

    def test_effect_conditions_gate_the_clause(self):
        """An effect-level condition is a gate, not decoration."""
        effect = Effect(type="modify_dice_limit", action="increase", result="2",
                        conditions=[Condition(type=ConditionType.SOURCE_RATING,
                                              operator="==", value="d6")])
        assert effect_text(effect, source_element="traitsetting") == \
            "if this trait is rated d6, increase the dice limit by 2"

    def test_die_scope_names_the_subset(self):
        """``die_filter {role: None}`` is the codebase's "left unchosen"."""
        effect = Effect(type="modify_trait", action="gain", target="trait-fire",
                        result="d6", die_filter={"role": None}, timing=EffectTiming.ON_RESULT)
        assert effect_text(effect, resolve=resolve) == \
            "whenever a roll is resolved, for each unchosen die, gain the Fire trait (d6)"

    def test_die_scoped_path_reads_that_die(self):
        """In a per-die effect the die *is* the roll, so the path says "that die"."""
        effect = Effect(
            type="modify_trait", action="gain", target="trait-environmental-hazard",
            result="d6", die_filter={"role": None}, timing=EffectTiming.ON_RESULT,
            entity_spec=spec(
                {"kind": "select", "collection": "rolled_dice"},
                {"kind": "navigate", "edge": "owner"},
                {"kind": "navigate", "edge": "location"},
            ),
        )
        assert effect_text(effect, resolve=resolve) == (
            "whenever a roll is resolved, for each unchosen die, gain the Environmental "
            "Hazard trait on the location of the pool owner of that die (d6)"
        )

    def test_die_scope_is_not_claimed_when_the_applier_ignores_it(self):
        """`_apply_armed` checks target_spec first, so a die filter there is inert."""
        effect = Effect(
            type="modify_trait", action="step_down", die_filter={"role": None},
            target_spec=spec({"kind": "select", "collection": "rolled_dice"}),
        )
        text = effect_text(effect)
        assert "unchosen" not in text
        assert "each die in your roll" in text

    def test_entity_spec_reads_as_where_it_lands(self):
        effect = Effect(
            type="modify_trait", action="gain", target="trait-fire", result="d6",
            entity_spec=spec(
                {"kind": "select", "collection": "rolled_dice"},
                {"kind": "navigate", "edge": "traitsetting"},
                {"kind": "navigate", "edge": "entity"},
                {"kind": "navigate", "edge": "location"},
            ),
        )
        text = effect_text(effect, resolve=resolve)
        assert text.startswith("gain the Fire trait on")
        assert "location" in text and "owner" in text

    def test_domain_attunement_says_it_reaches_past_its_carrier(self):
        self_scope = Effect(type="attune", action="enable", target="loc-rusted-gate",
                            result="three_realms")
        assert effect_text(self_scope, resolve=resolve) == \
            "attune Rusted Gate to three_realms"
        domain = self_scope.model_copy(update={"context": {"scope": "domain"}})
        assert effect_text(domain, resolve=resolve) == \
            "attune Rusted Gate to three_realms, reaching everyone there"

    def test_narrative_effect_condition_is_flavour(self):
        effect = Effect(type="modify_trait", action="step_down", target="trait-fire",
                        conditions=[Condition(type=ConditionType.NARRATIVE,
                                              narrative="Only in a storm")])
        assert effect_text(effect, resolve=resolve) == \
            "step down the Fire trait by one step (Only in a storm)"


class TestSfx:
    def test_d4_bonus(self):
        sfx = SFX(
            id="sfx-d4-bonus", name="d4 bonus", trigger="on_roll",
            conditions=[Condition(type=ConditionType.TARGET_PATH, spec=D4_CONDITION)],
            effects=[Effect(type="transfer_razmerit", action="earn", target="self", result="1")],
        )
        assert sfx_text(sfx, resolve=resolve) == \
            "Whenever a roll happens, if there is at least one d4 trait: gain 1 razmerit."

    def test_one_trick(self):
        sfx = SFX(
            id="sfx-one-trick", name="One Trick", trigger="on_session_start",
            effects=[Effect(type="modify_trait", action="step_down",
                            target_spec=ONE_TRICK_PATH, timing=EffectTiming.ON_RESULT)],
        )
        assert sfx_text(sfx, resolve=resolve) == \
            "At the start of each session: whenever a roll is resolved, step down each " \
            "static positive trait instance you rolled by one step."

    def test_heal_targets_the_difficulty_pool(self):
        sfx = SFX(
            id="sfx-heal", name="Heal", trigger="manual",
            effects=[Effect(type="modify_pool", action="add_dice", target_spec=spec(
                {"kind": "select", "collection": "self"},
                {"kind": "navigate", "edge": "location"},
                {"kind": "navigate", "edge": "difficulty_pool"},
            ))],
        )
        assert sfx_text(sfx) == \
            "Activated: add dice to the GM difficulty pool of your location."

    def test_narrative_limit_trails_in_parentheses(self):
        sfx = SFX(
            id="sfx-x", name="X", trigger="manual",
            conditions=[Condition(type=ConditionType.NARRATIVE,
                                  narrative="Must be in contact with the Jian")],
            effects=[Effect(type="transfer_razmerit", action="spend", target="self", result="1")],
        )
        assert sfx_text(sfx) == \
            "Activated: spend 1 razmerit. (Must be in contact with the Jian)"

    def test_conditions_are_conjoined(self):
        sfx = SFX(
            id="sfx-y", name="Y", trigger="on_character_create",
            conditions=[Condition(type=ConditionType.UNPLACED),
                        Condition(type=ConditionType.IN_UNIVERSE, target="earth")],
            effects=[Effect(type="location", action="set", target="{random:location}")],
        )
        assert sfx_text(sfx) == (
            "When a character is created, if you are not at a location yet and you are in "
            "earth: move to a random location."
        )

    def test_shared_framing_is_stated_once(self):
        """Rating-gated effects revert together, so the card says so once.

        The live `sfx-qi-condensation` shape: five dice-limit bumps, each gated on
        the source's rating, all sharing one undo timer.
        """
        ratings = ["d4", "d6", "d8", "d10", "d12"]
        sfx = SFX(
            id="sfx-qi-condensation", name="Cultivation Stage", trigger="on_roll",
            source_kind="trait_setting",
            effects=[
                Effect(type="modify_dice_limit", action="increase", result=str(i + 1),
                       duration={"timers": [{"event": "rolls", "remaining": 1}]},
                       conditions=[Condition(type=ConditionType.SOURCE_RATING,
                                             operator="==", value=rating)])
                for i, rating in enumerate(ratings)
            ],
        )
        text = sfx_text(sfx)
        assert text.count("reverts") == 1
        assert "each reverts at the next roll" in text
        assert "if this trait is rated d4, increase the dice limit by 1" in text
        assert "if this trait is rated d12, increase the dice limit by 5" in text


class TestVocabularyGuards:
    """The card vocabulary is data — these keep it honest as it grows."""

    def test_every_trigger_has_a_card_phrase(self):
        missing = [t.value for t in mc.TRIGGERS if t.value not in mc.TRIGGER_CARDS]
        assert not missing, f"triggers without card phrases: {missing}"

    def test_trigger_cards_key_real_triggers(self):
        known = {t.value for t in mc.TRIGGERS}
        assert set(mc.TRIGGER_CARDS) <= known

    def test_effect_cards_key_real_actions(self):
        known = {(m.effect_type, m.effect_action) for m in reg.EFFECT_ACTION_REGISTRY}
        assert set(reg.EFFECT_ACTION_CARDS) <= known

    def test_no_edge_noun_double_pluralizes(self):
        """A derived noun must not come from an already-plural label."""
        for edge in tc.EDGES:
            _singular, plural = tc.edge_noun(edge)
            assert plural != pluralize(plural), f"{edge.name}: {plural!r}"

    def test_every_collection_has_a_head_noun(self):
        for col in tc.COLLECTIONS:
            assert col.noun or col.pronoun, f"{col.name} has no card noun"

    def test_catalog_still_validates(self):
        assert tc.validate() == []


def TargetSpec_of(payload: dict):
    """Build a TargetSpec from a plain dict (keeps the tests readable)."""
    from transversal.services.target_spec import TargetSpec

    return TargetSpec.model_validate(payload)


class TestTwoPathAttune:
    """Attune carries two paths: who it applies to, and where it comes from."""

    def test_the_capability_comes_from_the_second_path(self):
        from transversal.domain import TargetRef

        effect = Effect(
            type="attune", action="enable",
            target_spec=spec(
                {"kind": "select", "collection": "occupants"},
                {"kind": "choose", "count": 1},
            ),
            refs={"projection": TargetRef(name="projection", spec=spec(
                {"kind": "select", "collection": "variable", "variable": "their_counterpart"},
                {"kind": "navigate", "edge": "projections"},
            ))},
        )
        text = effect_text(effect)
        # The who (path 1) renders as the effect's target...
        assert text.startswith("attune one of the entities here")
        # ...and the capability (path 2) is what it attunes them to, not a universe.
        assert "their counterpart" in text
        assert "three_realms" not in text

    def test_the_universe_fallback_still_reads(self):
        effect = Effect(type="attune", action="enable", target="loc-rusted-gate",
                        result="three_realms")
        assert effect_text(effect, resolve=resolve) == "attune Rusted Gate to three_realms"
