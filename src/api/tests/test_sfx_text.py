"""Derived SFX card text — [[SFX Natural Language Plan]].

Golden-text tests over the shapes the live catalogue actually uses, plus guard
tests that keep the card vocabulary honest (every card phrase is keyed to a real
action/trigger, and no edge noun double-pluralizes).
"""

from transversal.domain import Condition, ConditionType, Effect, EffectTiming, SFX, TargetSpec
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
    def test_the_opposing_side_reads_as_their_dice(self):
        """The cycle rule's second condition: a path seeded from the other side's
        pool reads as *their* dice, not as yours — the card has to keep the two
        sides apart, because both conditions sit on one rule."""
        s = spec(
            {"kind": "select", "collection": "opposing_dice"},
            {"kind": "navigate", "edge": "traitsetting", "dedup": True},
            {"kind": "filter", "field": "tags", "operator": "contains", "value": "metal"},
        )
        phrase = path_phrase(TargetSpec_of(s), resolve=resolve)
        # And it does *not* read "you rolled" — the party comes from the seed.
        assert render_phrase(phrase, "each") == "each trait instance they rolled tagged metal"

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
            "if this trait is rated d6, increase the total dice limit by 2"

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

    def test_die_scope_is_claimed_even_with_a_target_path(self):
        """A die filter runs the effect per die now, including through a path.

        The applier resolves a die-scoped effect's target path per die with that
        die as the roll, so the card must say so.
        """
        effect = Effect(
            type="modify_trait", action="step_down", die_filter={"role": None},
            target_spec=spec({"kind": "select", "collection": "rolled_dice"}),
        )
        text = effect_text(effect)
        assert "for each unchosen die" in text

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

    def test_a_target_ending_in_the_preposition_does_not_double_it(self):
        """A source-scoped path can end with the very word that joins the clause.

        The "lands on" clause is joined by a preposition, and the live
        `sfx-teach` read "…sits on on one of the occupants…". The seam takes a
        comma instead of a second copy of the word.
        """
        effect = Effect(
            type="modify_trait", action="gain",
            target_spec=spec({"kind": "select", "collection": "source"}),
            entity_spec=spec(
                {"kind": "select", "collection": "source"},
                {"kind": "navigate", "edge": "location"},
            ),
        )
        text = effect_text(effect, resolve=resolve, source_element="entity")
        assert " on on " not in text
        assert text == (
            "gain the entity this SFX sits on, on the location of the entity this SFX sits on"
        )

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

    def test_stakes_condition_reads_as_a_gate(self):
        sfx = SFX(
            id="sfx-stakes", name="Stakes", trigger="manual",
            conditions=[Condition(type=ConditionType.PHASE, target="adding"),
                        Condition(type=ConditionType.HIGH_STAKES, target="high")],
            effects=[Effect(type="transfer_razmerit", action="spend", result="1")],
        )
        assert sfx_text(sfx) == (
            "Activated, if the dice pool is in its adding phase and the contest is "
            "high stakes: spend 1 razmerit."
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
        assert "if this trait is rated d4, increase the total dice limit by 1" in text
        assert "if this trait is rated d12, increase the total dice limit by 5" in text


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
        assert text.startswith("attune one of the occupants here")
        # ...and the capability (path 2) is what it attunes them to, not a universe.
        assert "their counterpart" in text
        assert "three_realms" not in text

    def test_a_stated_grant_uses_the_author_name(self):
        """`sfx-crimson-scars`: "create a Crimson Scar", not "gain the trait"."""
        effect = Effect(
            type="modify_trait", action="gain", target="trait-environmental-hazard",
            result="d6", negative=True, context={"statement": "Crimson Scar"},
            entity_spec=spec(
                {"kind": "select", "collection": "rolled_dice"},
                {"kind": "navigate", "edge": "traitsetting"},
                {"kind": "navigate", "edge": "entity"},
                {"kind": "navigate", "edge": "location"},
            ),
        )
        text = effect_text(effect)
        assert text.startswith("create a Crimson Scar")
        assert "environmental hazard" not in text

    def test_a_bound_value_reads_as_the_thing(self):
        """A filter against a bound name relates to it; it does not restate it.

        Rendered as a comparison, law-bridge read "with universe equal to the
        universe".
        """
        from transversal.services.target_spec import ValueType
        effect = Effect(
            type="attune", action="enable",
            target_spec=spec(
                {"kind": "select", "collection": "self"},
                {"kind": "navigate", "edge": "projections"},
                {"kind": "filter", "field": "universe", "operator": "==",
                 "value": "{chosen_universe}"},
            ),
        )
        text = effect_text(effect, variables={"chosen_universe": ValueType("universe", "one")})
        assert "in the chosen universe" in text
        assert "equal to" not in text

    def test_select_variable_keeps_its_bound_type(self):
        """Without the bound type the later steps can't rewrite the phrase."""
        from transversal.services.target_spec import ValueType
        effect = Effect(
            type="attune", action="enable",
            target_spec=spec(
                {"kind": "select", "collection": "variable", "variable": "self"},
                {"kind": "navigate", "edge": "projections"},
            ),
        )
        text = effect_text(effect, variables={"self": ValueType("entity", "one")})
        assert "your projections" in text

    def test_top_step_reads_as_the_most_recently_used(self):
        """The ordering function is how "the body you were last in" is written."""
        effect = Effect(
            type="attune", action="enable",
            target_spec=spec(
                {"kind": "select", "collection": "self"},
                {"kind": "navigate", "edge": "projections"},
                {"kind": "aggregate", "fn": "top", "field": "last_used_at"},
            ),
        )
        assert effect_text(effect) == "attune your most recently used projection"

    def test_bottom_reads_as_the_least_recently_used(self):
        effect = Effect(
            type="attune", action="enable",
            target_spec=spec(
                {"kind": "select", "collection": "self"},
                {"kind": "navigate", "edge": "projections"},
                {"kind": "aggregate", "fn": "bottom", "field": "last_used_at"},
            ),
        )
        assert effect_text(effect) == "attune your least recently used projection"

    def test_copy_trait_reads_as_a_gift(self):
        """`sfx-teach`: hand another entity a copy of a trait you have."""
        from transversal.domain import TargetRef

        effect = Effect(
            type="modify_trait", action="copy",
            entity_spec=spec(
                {"kind": "select", "collection": "occupants"},
                {"kind": "choose", "count": 1},
            ),
            refs={"trait": TargetRef(value="", spec=spec(
                {"kind": "select", "collection": "self_traitsettings"},
                {"kind": "choose", "count": 1},
            ))},
        )
        assert effect_text(effect) == (
            "give one of the occupants here a copy of one of the trait instances"
        )

    def test_the_universe_fallback_still_reads(self):
        effect = Effect(type="attune", action="enable", target="loc-rusted-gate",
                        result="three_realms")
        assert effect_text(effect, resolve=resolve) == "attune Rusted Gate to three_realms"


def test_a_tag_filter_reads_as_tagged():
    """B116: matching on a tag is membership of the label, not the field name —
    "your trait instances tagged violent", not "with tag including violent"."""
    phrase = path_phrase(TargetSpec_of({"steps": [
        {"kind": "select", "collection": "self_traitsettings"},
        {"kind": "filter", "field": "tags", "operator": "contains", "value": "violent"},
    ]}), resolve=resolve)
    assert render_phrase(phrase, "") == "your trait instances tagged violent"


def test_a_variable_seeded_path_keeps_its_qualifiers_and_its_party():
    """The card is the author's check, and a `select variable` seed used to render
    as "you": because a pronoun phrase drops its qualifiers, *every step after the
    seed* vanished — a rule read "if there is a you", with the tags filter that
    was the whole condition gone. And the opponent's pool read as the actor's.

    Now the seed is named ("this trait"), the same declaration the engine binds
    types it (`scope_seed_names`), and a hop to the *same word*
    (instance → registry trait) says nothing instead of "a trait of this trait".
    """
    from transversal.domain import EffectTiming

    sfx = SFX(
        id="sfx-x", name="Water Suppresses Fire",
        trigger="on_pool_change", source_kind="trait_setting",
        conditions=[Condition(type=ConditionType.TARGET_PATH, spec=TargetSpec(steps=[
            {"kind": "select", "collection": "variable", "variable": "trait_setting"},
            {"kind": "navigate", "edge": "trait", "dedup": False},
            {"kind": "filter", "field": "tags", "operator": "contains", "value": "fire"},
        ]))],
        effects=[Effect(timing=EffectTiming.IMMEDIATE, type="modify_roll",
                        action="step_down_die", target="",
                        target_spec=TargetSpec(steps=[
                            {"kind": "select", "collection": "added_dice"},
                        ]))],
    )
    text = sfx_text(sfx)
    assert "this trait tagged fire" in text          # the qualifier survives
    assert "step down each die just added" in text   # and the effect names its die


def test_the_opponents_pool_does_not_read_as_the_actors():
    """`{contest_entity_opponent}` is someone else: a path through their pool must
    not say "you rolled" (that default belongs to the *seed*, and the seeds each
    carry their own party)."""
    sfx = SFX(
        id="sfx-x", name="X", trigger="on_pool_change",
        conditions=[Condition(type=ConditionType.TARGET_PATH, spec=TargetSpec(steps=[
            {"kind": "select", "collection": "variable", "variable": "contest_entity_opponent"},
            {"kind": "navigate", "edge": "pool", "dedup": False},
            {"kind": "navigate", "edge": "dice", "dedup": False},
            {"kind": "navigate", "edge": "traitsetting", "dedup": False},
            {"kind": "filter", "field": "tags", "operator": "contains", "value": "water"},
        ]))],
    )
    text = sfx_text(sfx)
    assert "the opposing entity" in text
    assert "tagged water" in text
    assert "you rolled" not in text


def test_several_tags_read_as_or():
    """The tags editor can hold more than one tag, and the card says what the
    filter means (`contains` over a list = *any of*)."""
    phrase = path_phrase(TargetSpec_of({"steps": [
        {"kind": "select", "collection": "self_traitsettings"},
        {"kind": "filter", "field": "tags", "operator": "contains", "value": ["violent", "calm"]},
    ]}), resolve=resolve)
    assert render_phrase(phrase, "") == "your trait instances tagged violent or calm"


def test_a_tag_filter_on_the_registry_trait_reads_the_same():
    """Reaching the registry trait through an instance works and the tag clause is
    the same; the head noun ("traits of your trait instances") is the known
    deep-path compression ceiling, not the filter's doing."""
    phrase = path_phrase(TargetSpec_of({"steps": [
        {"kind": "select", "collection": "self_traitsettings"},
        {"kind": "navigate", "edge": "trait"},
        {"kind": "filter", "field": "tags", "operator": "contains", "value": "violent"},
    ]}), resolve=resolve)
    assert render_phrase(phrase, "") == "traits of your trait instances tagged violent"


def test_the_effect_die_comparison_pair_reads_symmetrically():
    """P1.8's two comparison actions name the same comparison, in opposite
    directions — 'reduce … by the effect die' / 'increase … by the effect die'."""
    assert effect_text(Effect(type="modify_trait", action="reduce_by_effect",
                              target="trait-fire"), resolve=resolve) == \
        "reduce the Fire trait by the effect die"
    assert effect_text(Effect(type="modify_trait", action="increase_by_effect",
                              target="trait-fire"), resolve=resolve) == \
        "increase the Fire trait by the effect die"


def test_arrival_conditions_read_as_the_moment():
    """Each arrival kind names the way they got there, not the raw token."""
    cases = {
        "transversal": "you arrived through a portal",
        "hierarchy": "you arrived through the location hierarchy",
        "move": "you were placed here",
        "effect": "an effect moved you here",
    }
    for kind, expected in cases.items():
        cond = Condition(type=ConditionType.ARRIVAL_KIND, target=kind)
        assert condition_text(cond, resolve=resolve) == expected, kind
    # An unknown token still reads as something, naming it.
    assert condition_text(Condition(type=ConditionType.ARRIVAL_KIND, target="bogus")) == \
        'you arrived as "bogus"'


def test_a_type_filter_retypes_the_phrase():
    """A proven type changes the noun, so the rest of the path reads in the
    narrower vocabulary — "the location", not "the entity" — and the type is not
    said twice."""
    phrase = path_phrase(TargetSpec_of({"steps": [
        {"kind": "select", "collection": "self"},
        {"kind": "navigate", "edge": "traitsettings"},
        {"kind": "navigate", "edge": "entity"},
        {"kind": "filter", "field": "type", "operator": "==", "value": "location"},
        {"kind": "navigate", "edge": "occupants"},
    ]}), resolve=resolve)
    assert phrase.element == "entity"  # occupants are entities again
    assert render_phrase(phrase, "each") == "each occupant of each location of your trait instances"


def test_several_enum_values_read_as_alternatives():
    """An enum filter that accepts a list says so on the card."""
    cond = Condition(type=ConditionType.ENTITY_TYPE, targets=["character", "gmc"])
    assert condition_text(cond, resolve=resolve) == "you are a character or a gmc"

    # ...and a path filter over an enum reads the same way.
    phrase = path_phrase(TargetSpec_of({"steps": [
        {"kind": "select", "collection": "rolled_dice"},
        {"kind": "navigate", "edge": "traitsetting"},
        {"kind": "filter", "field": "polarity", "operator": "in",
         "value": ["positive", "negative"]},
    ]}), resolve=resolve)
    assert render_phrase(phrase, "each") == "each positive or negative trait instance you rolled"


def test_reach_is_not_shown_on_the_card():
    """The card states the ability. *Who the rule reaches* is not part of what it
    does, so reach never reaches the rendered text — it lives in the editor and is
    read where ownership is decided."""
    from transversal.domain import ReachDeclaration
    from transversal.services.target_spec import TargetSpec

    effect = Effect(type="modify_trait", action="step_up", target="trait-fire")
    sfx = SFX(id="sfx-reaches", name="Sect Technique", trigger="on_roll",
              source_kind="trait_setting", effects=[effect])
    without = sfx_text(sfx, resolve=resolve)
    assert "gained only where" not in without

    sfx.reach = [ReachDeclaration(spec=TargetSpec(steps=[
        {"kind": "select", "collection": "locations"},
        {"kind": "filter", "field": "id", "operator": "==", "value": "loc-rusted-gate"},
        {"kind": "navigate", "edge": "occupants"},
    ]))]
    assert sfx_text(sfx, resolve=resolve) == without


def test_a_random_sample_reads_as_an_indefinite_noun():
    """`random` samples the collection, so the card says "a random die" / "some
    random dice" — not the definite "the random die" a collapse would use."""
    def card(count):
        return sfx_text(SFX(
            id="sfx-x", name="X", trigger="manual",
            effects=[Effect(
                timing=EffectTiming.IMMEDIATE, type="location", action="set", target="",
                target_spec=TargetSpec(steps=[
                    {"kind": "select", "collection": "rolled_dice"},
                    {"kind": "aggregate", "fn": "random", "count": count},
                ]),
            )],
        ))

    assert "a random die" in card(1)
    assert "some random dice" in card(3)


# ── The Change a Die family's card ─────────────────────────────

RATING_DIE_PATH = [
    {"kind": "select", "collection": "self_traitsettings"},
    {"kind": "navigate", "edge": "rating_dice"},
    {"kind": "aggregate", "fn": "top", "field": "rating"},
]


def _change(action, context=None, result=None):
    return Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_roll", action=action,
        target="", result=result, context=context or {},
        target_spec=TargetSpec(steps=RATING_DIE_PATH),
    )


def test_a_removed_die_names_the_die_and_not_a_pool():
    """A die has two homes now, so the card cannot say "from the pool" — the
    target phrase is what says which home the die is in."""
    text = effect_text(_change("remove_die"))
    assert text.startswith("remove the rating die")
    assert "pool" not in text


def test_a_counted_step_says_how_many_steps():
    assert effect_text(_change("step_up_die", {"count": "1"})) == (
        "step up the rating die with the highest rating by one step")
    assert effect_text(_change("step_up_die", {"count": "3"})) == (
        "step up the rating die with the highest rating by 3 steps")
    # A count that is itself a variable reads as a number of steps, not a literal.
    assert "by a number of steps equal to the effect die" in effect_text(
        _change("step_down_die", {"count": "{effect_die}"}))


def test_double_and_split_say_how_many_dice_they_make():
    """`double 2` on a d8 gives 3d8; `split 2` gives 3d6 — so the count is dice
    *made*, not times doubled."""
    assert effect_text(_change("double_die", {"count": "2"})).endswith("into 3 dice")
    assert effect_text(_change("split_die", {"count": "2"})).endswith("into 3 dice, each a step smaller")
    # At the default there is nothing extra to say.
    assert effect_text(_change("double_die")) == "double the rating die with the highest rating"


def test_set_die_says_the_size_and_reroll_names_its_die():
    assert effect_text(_change("set_die", result="d12")) == (
        "set the rating die with the highest rating to d12")
    assert effect_text(_change("reroll_die")).startswith("reroll the rating die")


# ── Declared bound variables read as what they mean ───────────

def _tier_of_the_rating():
    return TargetSpec(steps=[
        {"kind": "select", "collection": "source"},
        {"kind": "aggregate", "fn": "tier", "field": "rating"},
    ])


def test_a_declared_variable_is_stated_and_then_named():
    """The author's *Cultivation Stage*: the card has to say what the tier *is*
    (a reader cannot see the declaration) and then use the author's own name for
    it. Both halves matter — the definition alone leaves the use unexplained, the
    use alone leaves a bare noun."""
    from transversal.domain import BoundVariable

    sfx = SFX(
        id="sfx-qi", name="Cultivation Stage", trigger="on_roll",
        source_kind="trait_setting",
        bound_variables=[BoundVariable(name="cultivation_tier", spec=_tier_of_the_rating())],
        effects=[Effect(
            timing=EffectTiming.IMMEDIATE, type="modify_dice_limit", action="increase",
            result="{cultivation_tier}", context={"limit": "total"},
        )],
    )

    text = sfx_text(sfx)
    assert "the cultivation tier is the tier of the rating" in text
    assert "increase the total dice limit by the cultivation tier" in text
    # Not the raw token, and not the section's absence.
    assert "{" not in text


def test_a_declared_variable_with_a_broken_path_is_not_stated():
    """A path that does not type-check binds nothing, so the card must not claim
    it does — the effect still names it, and the validator says why."""
    from transversal.domain import BoundVariable

    sfx = SFX(
        id="sfx-x", name="X", trigger="on_roll", source_kind="trait_setting",
        bound_variables=[BoundVariable(
            name="stage_tier",
            spec=TargetSpec(steps=[{"kind": "aggregate", "fn": "tier", "field": "rating"}]),
        )],
        effects=[],
    )
    assert "stage tier is" not in sfx_text(sfx)


# ── The card tells the truth about an amount ──────────────────
# Found by authoring *Cultivation Stage*: the card said "increase the dice limit
# by your dice pool", because the effect's `pool` ref (which names *whose* limits
# move) was read out as the amount. Three separable defects, pinned here.

def _pool_ref():
    return {"pool": {"value": "", "spec": {
        "steps": [{"kind": "select", "collection": "self"},
                  {"kind": "navigate", "edge": "pool"}]}}}


def _limit_effect(result="{cultivation rank}", limit="total", refs=True):
    return Effect(type="modify_dice_limit", action="increase", result=result,
                  context={"limit": limit}, refs=_pool_ref() if refs else None)


def test_a_subject_reference_is_not_read_out_as_the_amount():
    """`increase_dice_limit`'s `pool` ref names the pool whose limits move; the
    amount is its own field. With the ref present the card must still state the
    amount — it used to say "by your dice pool" and never mention it."""
    assert effect_text(_limit_effect()) == \
        "increase the total dice limit by the cultivation rank"


def test_the_action_default_still_speaks_when_no_amount_is_authored():
    """An empty amount means the action's default (1, and `_apply_dice_limit`
    agrees) — not whatever a reference happened to resolve to."""
    assert effect_text(_limit_effect(result="")) == \
        "increase the total dice limit by 1"


def test_which_limit_is_named_because_the_two_differ():
    """`total` and `effect` are different effects; a card that cannot tell them
    apart is wrong half the time. Absent → `total`, matching the applier."""
    assert effect_text(_limit_effect(limit="effect")) == \
        "increase the effect dice limit by the cultivation rank"
    assert effect_text(_limit_effect(limit=None)) == \
        "increase the total dice limit by the cultivation rank"


def test_an_action_with_no_result_field_still_names_its_object_by_reference():
    """The other half of the rule: `move`/`copy`/`change` have **no** result
    field, so a reference is exactly how they say what they act on. Precedence
    must not take that away."""
    move = Effect(type="modify_trait", action="move", target="me",
                  refs={"trait": {"value": "", "spec": {
                      "steps": [{"kind": "select", "collection": "self_traitsettings"}]}}})
    assert "move " in effect_text(move)
    assert "your trait instance" in effect_text(move)


def test_a_result_field_that_declares_a_superseding_ref_still_uses_it():
    """Attune is the declared exception, and the declaration is the registry's
    own `hidden_when_ref`: its named-universe field is the *fallback* the resolved
    projection supersedes. Losing this would break the card this mechanism was
    built for."""
    from transversal.services.effects_registry import EFFECT_ACTION_REGISTRY as REG
    attune = next(m for m in REG if m.effect_type == "attune")
    field = next(f for f in attune.fields if f.name == "result")
    assert field.hidden_when_ref == "projection", "the declaration this reads"
    assert effect_text(Effect(
        type="attune", action="enable", target="kael",
        refs={"projection": {"value": "", "spec": {"steps": [
            {"kind": "select", "collection": "self"},
            {"kind": "navigate", "edge": "projections"}]}}},
    )) != "attune kael to "


def test_a_cast_keeps_the_superlative_the_path_earned():
    """`top(rating)` says *which* rating; the `tier` cast transforms it. The cast
    used to replace the phrase outright, so "the highest" vanished and the card
    read as if any rating would do."""
    spec = TargetSpec(steps=[
        {"kind": "select", "collection": "source"},
        {"kind": "navigate", "edge": "rating_dice", "dedup": True},
        {"kind": "aggregate", "fn": "top", "field": "rating"},
        {"kind": "aggregate", "fn": "tier", "field": "rating"},
    ])
    assert render_phrase(path_phrase(spec, source_element="traitsetting")) == \
        "the tier of the highest rating"
    # Without the ranking step there is no superlative to keep.
    plain = TargetSpec(steps=[
        {"kind": "select", "collection": "source"},
        {"kind": "aggregate", "fn": "tier", "field": "rating"},
    ])
    assert render_phrase(path_phrase(plain, source_element="traitsetting")) == \
        "the tier of the rating"


def test_a_hop_onto_a_state_reads_as_a_clause_not_a_possession():
    """`entity → contest` is a *state*: "there is at least one of your contest"
    is what a possessive noun phrase does to one. The hop declares the clause, and
    only a condition reads it — a target position keeps the noun phrase."""
    condition = Condition(type=ConditionType.TARGET_PATH, spec=TargetSpec(steps=[
        {"kind": "select", "collection": "self"},
        {"kind": "navigate", "edge": "contest"},
    ]))
    assert condition_text(condition) == "you are in a contest"
    # The same hop as a *target* is still a noun phrase.
    phrase = path_phrase(condition.spec, source_element="traitsetting")
    assert phrase.state == "you are in a contest"
    assert render_phrase(phrase) == "your contest"


def test_the_state_reading_does_not_claim_another_party():
    """The clause is about the actor, so it is only used where the phrase *is* the
    actor. From someone else's seed the noun phrase is the honest reading."""
    spec = TargetSpec(steps=[
        {"kind": "select", "collection": "occupants"},
        {"kind": "navigate", "edge": "contest"},
    ])
    assert condition_text(Condition(type=ConditionType.TARGET_PATH, spec=spec)) != \
        "you are in a contest"


def test_starting_a_contest_names_the_opponent():
    """The contest-start action is the missing half of the contest vocabulary
    (B105) — and it has to read as plainly as the challenge button it replaces."""
    effect = Effect(type="contest", action="start", target="char-2")
    assert effect_text(effect, resolve={"char-2": "Wei Zhao"}.get) == \
        "start a contest with Wei Zhao"


def test_starting_a_contest_reads_the_opponent_token():
    """A contest-triggered rule names the other side with the event's own token."""
    effect = Effect(type="contest", action="start", target="{contest_entity_opponent}")
    assert effect_text(effect) == "start a contest with the opposing entity"


class _ResolverRepo:
    """Just enough repository for the name resolver (it is duck-typed)."""

    def __init__(self, settings=None, traits=None):
        self._settings = settings or {}
        self._traits = traits or {}

    def get_traitsetting(self, ts_id):
        return self._settings.get(ts_id)

    def get_trait(self, trait_id):
        return self._traits.get(trait_id)


class _Named:
    def __init__(self, name):
        self.name = name


class _Setting:
    def __init__(self, trait_id, statement=""):
        self.trait_id = trait_id
        self.statement = statement


def _resolver(repo):
    from transversal.services.sfx_text import repo_name_resolver
    return repo_name_resolver(repo)


def test_a_trait_instance_reads_as_its_statement():
    """A copy/move card's whole subject is the referenced instance; a raw
    `char-1:trait-9` is the least readable thing the renderer can print."""
    repo = _ResolverRepo(
        settings={"char-1:medicine": _Setting("trait-med", statement="Field surgery")},
        traits={"trait-med": _Named("Medicine")},
    )
    assert _resolver(repo)("char-1:medicine") == "Field surgery"


def test_a_trait_instance_without_a_statement_reads_as_its_trait():
    repo = _ResolverRepo(
        settings={"char-1:medicine": _Setting("trait-med")},
        traits={"trait-med": _Named("Medicine")},
    )
    assert _resolver(repo)("char-1:medicine") == "Medicine"


def test_an_unknown_id_still_falls_back_to_itself():
    repo = _ResolverRepo()
    assert _resolver(repo)("char-1:medicine") is None


def test_a_per_die_scope_can_say_whose_die_it_is():
    """A rule that works from its *own* die says so in the filter (`{trait_setting}`
    → "this trait"), and it reads as part of the noun, not as a second predicate."""
    effect = Effect(type="modify_trait", action="gain", target="trait-scar", result="d6",
                    die_filter={"role": None, "ts_id": "{trait_setting}"})
    assert "for each unchosen die from this trait" in effect_text(effect)
    # The phrase cannot depend on the order the keys were authored in.
    flipped = effect.model_copy(
        update={"die_filter": {"ts_id": "{trait_setting}", "role": None}})
    assert effect_text(flipped) == effect_text(effect)


def test_a_lone_die_filter_reads_exactly_as_before():
    effect = Effect(type="modify_trait", action="gain", target="trait-scar", result="d6",
                    die_filter={"role": None})
    assert "for each unchosen die," in effect_text(effect)


def test_exactly_one_is_not_read_as_at_least_one():
    """`count == 1` compares the collection's length, so a roll carrying two
    matching traits fails the gate. The card said "at least one" for both `>= 1`
    and `== 1`, which promised a rule wider than it is — the live `sfx-d4-bonus`
    is the case that exposed it (its card claimed existence, its gate required one).
    """
    def condition(op):
        return Condition(type=ConditionType.TARGET_PATH, spec=TargetSpec(steps=[
            {"kind": "select", "collection": "rolled_dice"},
            {"kind": "navigate", "edge": "traitsetting"},
            {"kind": "evaluate", "operator": op, "field": "count", "value": 1},
        ]))

    assert "at least one" in condition_text(condition(">="))
    exact = condition_text(condition("=="))
    assert "exactly one" in exact
    assert "at least one" not in exact


def test_more_than_zero_still_reads_as_existence():
    condition = Condition(type=ConditionType.TARGET_PATH, spec=TargetSpec(steps=[
        {"kind": "select", "collection": "rolled_dice"},
        {"kind": "navigate", "edge": "traitsetting"},
        {"kind": "evaluate", "operator": ">", "field": "count", "value": 0},
    ]))
    assert "at least one" in condition_text(condition)


def test_a_target_path_on_a_self_effect_reads_as_its_frequency():
    """``earn``/``spend`` and their kin have no ``{target}`` slot in the template,
    but the applier still runs the effect once per resolved target — so for them
    the path *is* the frequency, and a card that dropped it promised one payment
    where the rule pays one per thing (the live `sfx-d4-bonus`: one razmerit per
    d4 trait, not one per roll).
    """
    effect = Effect(
        timing=EffectTiming.ON_ROLL, type="transfer_razmerit", action="earn",
        target="self", result="1",
        conditions=[Condition(type=ConditionType.TARGET_PATH,
                              spec=TargetSpec(steps=D4_CONDITION["steps"]))],
        target_spec=TargetSpec(steps=[
            {"kind": "select", "collection": "variable", "variable": "d4_traits"}]),
    )
    text = effect_text(effect)
    assert "for each d4 trait" in text
    assert text.endswith("gain 1 razmerit")


def test_an_effect_object_path_is_never_read_as_a_frequency():
    """The other half of the rule: when the template *does* name the target, the
    same path is the effect's object, and adding "for each" would say the effect
    happens on the object's behalf instead of to it."""
    effect = Effect(type="modify_trait", action="step_down",
                    target_spec=TargetSpec(steps=ONE_TRICK_PATH["steps"]))
    text = effect_text(effect)
    assert text.startswith("step down")
    assert "for each" not in text


def test_the_traveller_leads_the_clause():
    """``travel`` cannot hang its mover off a preposition: the entity it lands on
    is the one that moves, so it reads as the sentence's actor. Before this the
    action had no template at all and the card dropped both the mover and the
    destination ("Activated: travel.")."""
    effect = Effect(
        type="travel", action="move",
        target_spec=TargetSpec(steps=[{"kind": "select", "collection": "universes"}]),
        entity_spec=TargetSpec(steps=[{"kind": "select", "collection": "occupants"}]),
    )
    text = effect_text(effect)
    assert "travels to" in text
    assert not text.startswith("travel")


def test_every_action_that_declares_a_target_has_a_card_template():
    """The class behind the Banish card: an action with no template falls back to
    its own label, which has no slots, so an authored target or result is dropped
    from the card. Two live rules read as their bare verb because of it ("Activated:
    travel."). This refuses a *new* action that could do the same."""
    from transversal.services import effects_registry as reg
    from transversal.services.effects_registry.cards import EFFECT_ACTION_CARDS

    missing = []
    for meta in reg.EFFECT_ACTION_REGISTRY:
        if getattr(meta, "retired", False):
            continue
        declares_target = ("target" in {f.name for f in meta.fields}) or bool(meta.path_element)
        if not declares_target:
            continue
        if (meta.effect_type, meta.effect_action) not in EFFECT_ACTION_CARDS:
            missing.append(f"{meta.effect_type}/{meta.effect_action} ({meta.label})")
    assert not missing, "actions whose target would vanish from the card: " + ", ".join(sorted(missing))


def test_each_actions_target_path_reaches_its_card():
    """And the guard is not satisfied by a template that ignores the slot: for
    every action declaring a target, an effect carrying a target *path* names it."""
    from transversal.services import effects_registry as reg

    unnamed = []
    for meta in reg.EFFECT_ACTION_REGISTRY:
        if getattr(meta, "retired", False):
            continue
        if "target" not in {f.name for f in meta.fields} and not meta.path_element:
            continue
        effect = Effect(
            type=meta.effect_type, action=meta.effect_action, result="d4",
            target_spec=TargetSpec(steps=[
                {"kind": "literal", "element": "traitsetting", "value": "ts-fire-kael"}]),
        )
        text = effect_text(effect, resolve=resolve)
        if "Fire" not in text:
            unnamed.append(f"{meta.effect_type}/{meta.effect_action}: {text!r}")
    assert not unnamed, "target path dropped from the card: " + "; ".join(unnamed)


def test_set_polarity_says_which_polarity():
    """The polarity is a context choice with a default, so a card that omits it
    hides a decision — the `positive`/`negative` flip is the whole effect."""
    positive = Effect(type="modify_trait", action="set_polarity", target="ts-fire-kael")
    assert effect_text(positive, resolve=resolve) == "set the polarity of the Fire trait to positive"
    negative = Effect(type="modify_trait", action="set_polarity", target="ts-fire-kael",
                      context={"polarity": "negative"})
    assert effect_text(negative, resolve=resolve) == "set the polarity of the Fire trait to negative"


def test_the_anchor_of_a_gained_trait_reads_when_it_has_one():
    """"Gain a rank on the tie to that faction" is the whole point of the
    relationship/subtrait verbs, and their `{owner}` slot was never filled — the
    card raised ``KeyError: 'owner'`` instead of rendering. Nothing live used
    them, which is how it stayed hidden."""
    edge = TargetSpec(steps=[
        {"kind": "select", "collection": "self"},
        {"kind": "navigate", "edge": "relationships"},
        {"kind": "filter", "field": "contact_id", "operator": "==", "value": "trait-fire"},
    ])
    effect = Effect(type="modify_trait", action="gain_relationship", target="ts-fire-kael",
                    result="d4", owner_spec=edge)
    text = effect_text(effect, resolve=resolve)
    assert "on your relationships with Fire" in text
    # With no anchor path the trait anchors to the entity, so the clause goes
    # rather than dangling ("gain the Fire trait on").
    unanchored = effect.model_copy(update={"owner_spec": None})
    assert effect_text(unanchored, resolve=resolve) == "gain the Fire trait (d4)"


def test_a_rating_row_is_read_as_the_row_it_is():
    """A rating is a row of dice, and the card must not call a challenge "d6".

    `result` carries only the row's first die, so reading that alone would name a
    three-die challenge by one of its dice ([[B307]]).
    """
    row = Effect(type="modify_trait", action="cortex_gain", target="trait-fire",
                 result="d6", context={"dice": ["d6", "d6", "d6"]})
    assert "at d6 ×3" in effect_text(row)
    # A row of mixed dice is listed whole rather than counted.
    mixed = row.model_copy(update={"context": {"dice": ["d6", "d8"]}})
    assert "at d6, d8" in effect_text(mixed)
    # A one-die row still reads as the die, exactly as before.
    single = row.model_copy(update={"context": {"dice": ["d8"]}})
    assert "at d8" in effect_text(single)
