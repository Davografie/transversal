"""Tests for authoring-time SFX validation."""

from transversal.domain import (
    Condition,
    ConditionType,
    Effect,
    EffectTiming,
    SFX,
)
from transversal.services.sfx_validation import validate_sfx


def _sfx(trigger="manual", placement=None, effects=None, conditions=None):
    return SFX(
        id="sfx-x", name="X", trigger=trigger, placement=placement,
        effects=effects or [],
        conditions=conditions or [],
    )


def test_known_variables_pass():
    sfx = _sfx(
        placement="menu",
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


def test_target_spec_satisfies_required_target():
    from transversal.services.target_spec import NavigateStep, SelectStep, TargetSpec

    sfx = _sfx(
        trigger="on_session_start",
        effects=[Effect(
            timing=EffectTiming.ON_ROLL, type="modify_trait", action="step_down",
            target="",
            target_spec=TargetSpec(steps=[
                SelectStep(collection="rolled_dice"),
                NavigateStep(edge="traitsetting", dedup=True),
            ]),
        )],
    )
    warnings = validate_sfx(sfx)
    assert not any("missing required field 'target'" in w for w in warnings)


def _sfx_with_source(source_kind, effect_entity="{trait_setting}"):
    return SFX(
        id="sfx-x", name="X", trigger="manual", source_kind=source_kind,
        effects=[Effect(
            timing=EffectTiming.IMMEDIATE, type="modify_trait", action="step_down",
            target="{choose_trait}", entity=effect_entity,
        )],
    )


def test_source_variable_known_when_source_kind_declared():
    # {trait_setting} is unknown for a plain manual SFX…
    sfx = _sfx_with_source(None)
    assert "Effect 1: unknown variable {trait_setting}" in validate_sfx(sfx)

    # …but declared by source_kind=trait_setting, it is in scope.
    sfx = _sfx_with_source("trait_setting")
    assert validate_sfx(sfx) == []


def test_each_source_kind_exposes_its_variable():
    from transversal.services.target_catalog import source_variable
    assert source_variable("trait_setting") == "trait_setting"
    assert source_variable("traitset_setting") == "traitset_setting"
    assert source_variable("entity") == "entity"
    assert source_variable("projection") == "projection"
    assert source_variable("bogus") is None
    assert source_variable("") is None


def test_listener_spec_scope_without_path_warns():
    sfx = _sfx()
    sfx.arming_scope = "listener_spec"
    assert validate_sfx(sfx) == ["Arming scope is 'listener_spec' but no listener path is set"]


def test_source_kind_ownership_mismatch_warns(monkeypatch):
    import transversal.services.sfx_owner as sfo
    monkeypatch.setattr(sfo, "owned_surfaces", lambda repo, sid: {"entity"})
    sfx = _sfx()
    sfx.source_kind = "trait_setting"
    assert validate_sfx(sfx, repo=object()) == [
        "Source is 'trait_setting' but this SFX is owned by entity, not 'trait_instance' — select source / source rating will resolve to nothing"
    ]


def test_source_kind_matching_owner_no_warning(monkeypatch):
    import transversal.services.sfx_owner as sfo
    monkeypatch.setattr(sfo, "owned_surfaces", lambda repo, sid: {"trait_instance"})
    sfx = _sfx()
    sfx.source_kind = "trait_setting"
    assert validate_sfx(sfx, repo=object()) == []


def test_ownership_guard_skipped_when_unowned_or_no_repo(monkeypatch):
    import transversal.services.sfx_owner as sfo
    monkeypatch.setattr(sfo, "owned_surfaces", lambda repo, sid: set())
    sfx = _sfx()
    sfx.source_kind = "trait_setting"
    assert validate_sfx(sfx, repo=object()) == []  # unowned → skip
    assert validate_sfx(sfx) == []  # no repo → skip
