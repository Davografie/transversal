"""Tests for authoring-time SFX validation."""

from transversal.domain import (
    Condition,
    ConditionType,
    Effect,
    EffectTiming,
    SFX,
    TargetRef,
    TargetSpec,
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


def test_context_condition_on_a_boundary_trigger_warns():
    sfx = SFX(
        id="sfx-x", name="X", trigger="on_beat",
        conditions=[Condition(type=ConditionType.HIGH_STAKES, target="high")],
    )
    assert validate_sfx(sfx) == [
        "Condition 1: 'High stakes' can never pass — it reads 'high_stakes', and a "
        "boundary supplies no context"
    ]


def test_context_condition_on_a_boundary_effect_warns():
    sfx = SFX(
        id="sfx-x", name="X", trigger="manual",
        effects=[Effect(
            timing=EffectTiming.END_OF_SCENE, type="modify_trait", action="step_down",
            target="{choose_trait}",
            conditions=[Condition(type=ConditionType.PHASE, target="adding")],
        )],
    )
    assert any("a boundary supplies no context" in w for w in validate_sfx(sfx))


def test_context_condition_on_a_roll_effect_is_fine():
    """A roll-timed effect fires from the roll, which brings its own context."""
    sfx = SFX(
        id="sfx-x", name="X", trigger="on_session_start",
        effects=[Effect(
            timing=EffectTiming.ON_RESULT, type="modify_trait", action="step_down",
            target="{choose_trait}",
            conditions=[Condition(type=ConditionType.HIGH_STAKES, target="high")],
        )],
    )
    assert not any("can never pass" in w for w in validate_sfx(sfx))


def test_phase_on_a_roll_timed_effect_warns():
    """The roll context carries no phase — the map's reason for existing."""
    sfx = SFX(
        id="sfx-x", name="X", trigger="manual",
        effects=[Effect(
            timing=EffectTiming.ON_RESULT, type="modify_trait", action="step_down",
            target="{choose_trait}",
            conditions=[Condition(type=ConditionType.PHASE, target="adding")],
        )],
    )
    assert any(
        "it reads 'phase', and there is no context at this moment" in w
        for w in validate_sfx(sfx)
    )


def test_roll_reading_path_on_a_non_rolling_trigger_warns():
    from transversal.domain import TargetSpec
    spec = TargetSpec(steps=[{"kind": "select", "collection": "rolled_dice"}])
    sfx = SFX(
        id="sfx-x", name="X", trigger="manual",
        conditions=[Condition(type=ConditionType.TARGET_PATH, spec=spec)],
    )
    assert any("it reads 'rolls'" in w for w in validate_sfx(sfx))


def test_user_role_needs_no_context():
    """It prefers context['role'] but falls back to the controlling player."""
    sfx = SFX(
        id="sfx-x", name="X", trigger="on_beat",
        conditions=[Condition(type=ConditionType.USER_ROLE, target="player")],
    )
    assert validate_sfx(sfx) == []


def test_live_shapes_are_allowed():
    """The gates the seeded catalogue actually uses must not be flagged."""
    from transversal.domain import TargetSpec
    heal = SFX(
        id="sfx-heal", name="Heal", trigger="manual",
        effects=[Effect(
            timing=EffectTiming.ON_RESULT, type="modify_trait", action="step_down",
            target="{choose_trait}",
            conditions=[Condition(type=ConditionType.TEST_OUTCOME, target="success")],
        )],
    )
    assert not any("can never pass" in w for w in validate_sfx(heal))

    crimson = SFX(
        id="sfx-crimson-scars", name="Crimson Scars", trigger="manual",
        conditions=[Condition(type=ConditionType.PHASE, target="adding")],
    )
    assert not any("can never pass" in w for w in validate_sfx(crimson))

    # A consequence-menu move: gated by the outcome the menu assembled, and by a
    # hitch marker for the hitch menu. Both are placement="menu".
    for condition in (
        Condition(type=ConditionType.CONTEST_OUTCOME, target="player"),
        Condition(type=ConditionType.CONTEST_OUTCOME, target="give_in"),
        Condition(type=ConditionType.HITCH),
        Condition(type=ConditionType.USER_ROLE, target="architect"),
    ):
        menu_sfx = SFX(
            id="sfx-menu", name="Menu move", trigger="manual", placement="menu",
            conditions=[condition],
        )
        assert not any("can never pass" in w for w in validate_sfx(menu_sfx)), condition


def test_unbound_step_value_warns():
    """A name nothing binds matches nothing — law-bridge's '{universe}'."""
    sfx = SFX(
        id="sfx-x", name="X", trigger="manual",
        effects=[Effect(
            timing=EffectTiming.IMMEDIATE, type="attune", action="enable",
            target_spec=TargetSpec(steps=[
                {"kind": "select", "collection": "self"},
                {"kind": "navigate", "edge": "projections"},
                {"kind": "filter", "field": "universe", "operator": "==",
                 "value": "{chosen_universe}"},
            ]),
        )],
    )
    warnings = validate_sfx(sfx)
    assert any("'{chosen_universe}' is not bound by anything" in w for w in warnings), warnings


def test_bound_step_value_passes_when_an_earlier_reference_binds_it():
    universe = TargetRef(value="", spec=TargetSpec(steps=[
        {"kind": "select", "collection": "entities"},
        {"kind": "choose", "count": 1, "output": "chosen_universe"},
    ]))
    projection = TargetRef(value="", spec=TargetSpec(steps=[
        {"kind": "select", "collection": "self"},
        {"kind": "navigate", "edge": "projections"},
        {"kind": "filter", "field": "universe", "operator": "==",
         "value": "{chosen_universe}"},
    ]))
    sfx = SFX(
        id="sfx-x", name="X", trigger="manual",
        effects=[Effect(
            timing=EffectTiming.IMMEDIATE, type="attune", action="enable",
            refs={"universe": universe, "projection": projection},
        )],
    )
    assert not any("not bound" in w for w in validate_sfx(sfx))


def test_select_source_warns_without_a_resolving_source():
    """The editor hides the seed; nothing stopped a draft carrying it anyway."""
    from transversal.domain import TargetSpec
    spec = TargetSpec(steps=[{"kind": "select", "collection": "source"}])
    sfx = SFX(
        id="sfx-x", name="X", trigger="manual",
        effects=[Effect(
            timing=EffectTiming.IMMEDIATE, type="modify_trait", action="step_down",
            target_spec=spec,
        )],
    )
    assert any("'select source' resolves to nothing" in w for w in validate_sfx(sfx))

    # A bucket source (table/gm) exposes no source either.
    sfx.source_kind = "table"
    assert any("'select source' resolves to nothing" in w for w in validate_sfx(sfx))

    # A trait-setting source resolves, so the seed is fine there.
    sfx.source_kind = "trait_setting"
    assert not any("select source" in w for w in validate_sfx(sfx))


def test_source_rating_on_an_entity_sfx_warns():
    """A source-reading condition with the wrong source can never pass."""
    sfx = SFX(
        id="sfx-x", name="X", trigger="manual", source_kind="entity",
        conditions=[Condition(type=ConditionType.SOURCE_RATING, operator=">=", value="d8")],
    )
    assert validate_sfx(sfx) == [
        "'Source rating' can never pass here: it reads the SFX's source, and this "
        "SFX's source is 'entity'"
    ]


def test_source_rating_on_a_trait_sfx_passes():
    sfx = SFX(
        id="sfx-x", name="X", trigger="manual", source_kind="trait_setting",
        conditions=[Condition(type=ConditionType.SOURCE_RATING, operator=">=", value="d8")],
    )
    assert validate_sfx(sfx) == []


def test_source_rating_warns_on_an_effect_condition_too():
    sfx = SFX(
        id="sfx-x", name="X", trigger="manual", source_kind="entity",
        effects=[Effect(
            timing=EffectTiming.IMMEDIATE, type="modify_trait", action="step_down",
            target="{choose_trait}",
            conditions=[Condition(type=ConditionType.SOURCE_RATING, value="d8")],
        )],
    )
    assert any("never pass here" in w for w in validate_sfx(sfx))


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


def test_a_location_sourced_rule_owned_by_a_character_warns(monkeypatch):
    """The whole reason `location` is its own owner surface: a place-owned rule
    must not silently sit on a character, where its source would resolve to them."""
    import transversal.services.sfx_owner as sfo
    monkeypatch.setattr(sfo, "owned_surfaces", lambda repo, sid: {"entity"})
    sfx = _sfx()
    sfx.source_kind = "location"
    assert validate_sfx(sfx, repo=object()) == [
        "Source is 'location' but this SFX is owned by entity, not 'location' — select source / source rating will resolve to nothing"
    ]


def test_a_location_sourced_rule_owned_by_a_place_is_fine(monkeypatch):
    import transversal.services.sfx_owner as sfo
    monkeypatch.setattr(sfo, "owned_surfaces", lambda repo, sid: {"location"})
    sfx = _sfx()
    sfx.source_kind = "location"
    assert validate_sfx(sfx, repo=object()) == []
