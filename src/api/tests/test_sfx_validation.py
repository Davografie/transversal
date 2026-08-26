"""Tests for authoring-time SFX validation."""

from transversal.domain import (
    Condition,
    ConditionType,
    Effect,
    EffectTiming,
    SFX,
)
from transversal.services.sfx_validation import validate_sfx


def _sfx(trigger="hitch", effects=None, conditions=None):
    return SFX(
        id="sfx-x", name="X", trigger=trigger,
        effects=effects or [],
        conditions=conditions or [],
    )


def test_known_variables_pass():
    sfx = _sfx(
        trigger="hitch",
        effects=[Effect(
            timing=EffectTiming.IMMEDIATE, type="modify_trait", action="gain_or_step_up",
            target="{choose_trait}", entity="{hitch_entity}", result="d4",
        )],
    )
    assert validate_sfx(sfx) == []


def test_unknown_effect_variable_warns():
    sfx = _sfx(
        trigger="hitch",
        effects=[Effect(
            timing=EffectTiming.IMMEDIATE, type="modify_trait", action="gain",
            target="{choose_trait}", entity="{typo_entity}", result="d4",
        )],
    )
    assert validate_sfx(sfx) == ["Effect 1: unknown variable {typo_entity}"]


def test_unknown_condition_variable_warns():
    sfx = _sfx(
        trigger="hitch",
        conditions=[Condition(
            type=ConditionType.HAS_TRAIT, subject="{typo_buyer}", target="iron-will",
        )],
    )
    assert validate_sfx(sfx) == ["Condition 1: unknown variable {typo_buyer}"]


def test_reserved_tokens_not_flagged():
    sfx = _sfx(
        trigger="hitch",
        effects=[
            Effect(
                timing=EffectTiming.IMMEDIATE, type="location", action="set",
                target="{random:location}", target_scope="universe:current",
            ),
            Effect(
                timing=EffectTiming.IMMEDIATE, type="modify_roll", action="play_as_rating",
                target="{source_trait}", result="d8",
            ),
        ],
    )
    assert validate_sfx(sfx) == []


def test_roll_context_variables_allowed_only_for_roll_timings():
    on_result = Effect(
        timing=EffectTiming.ON_RESULT, type="modify_trait", action="gain",
        target="hazard", result="{triggered_die_effect_die}", entity="{effect_die}",
    )
    assert validate_sfx(_sfx(trigger="manual", effects=[on_result])) == []

    immediate = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_trait", action="gain",
        target="hazard", result="{triggered_die_effect_die}",
    )
    warnings = validate_sfx(_sfx(trigger="manual", effects=[immediate]))
    assert any("unknown variable {triggered_die_effect_die}" in w for w in warnings)


def test_empty_is_valid():
    assert validate_sfx(_sfx()) == []


def test_filter_kind_mismatch_warns():
    sfx = _sfx(
        trigger="hitch",
        effects=[Effect(
            timing=EffectTiming.IMMEDIATE, type="modify_trait", action="gain",
            target="{choose_trait}", result="d6", target_filter={"starter_location": True},
        )],
    )
    warnings = validate_sfx(sfx)
    assert any("filter 'starter_location' does not apply to trait targets" in w for w in warnings)


def test_missing_required_field_warns():
    sfx = _sfx(
        trigger="hitch",
        effects=[Effect(
            timing=EffectTiming.IMMEDIATE, type="modify_trait", action="gain",
            target="", result="d6",
        )],
    )
    warnings = validate_sfx(sfx)
    assert any("missing required field 'target'" in w for w in warnings)
