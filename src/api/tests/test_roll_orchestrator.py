"""Tests for automatic SFX firing after roll/contest resolution."""

from types import SimpleNamespace

import transversal.services.roll_orchestrator as roll_orchestrator

from transversal.domain import (
    Condition,
    ConditionType,
    DieRoll,
    DieType,
    Effect,
    EffectTiming,
    OutcomeTier,
    SFX,
    SimplifiedResult,
)
from transversal.services.effects_applier import choose_kind, is_choose_target
from transversal.services.effects_engine import EffectsEngine, GameEvent
from transversal.services.roll_orchestrator import fire_roll_sfx


class Repo:
    """In-memory double covering the surfaces the resolver + orchestrator read."""

    def __init__(self, entities=None):
        self.entities = entities or {}

    def get_entity(self, entity_id):
        return self.entities.get(entity_id)

    def get_projection(self, projection_id):
        return None

    def get_sfx_owner(self, owner_id):
        return None

    def get_effective_traitsettings(self, entity_id, universes):
        return []

    def get_trait(self, trait_id):
        return None

    def get_effective_traitsetsettings(self, entity_id, universes):
        return []

    def get_sfx(self, sfx_id):
        return None

    def list_all_scheduled_events(self):
        return []


def _simplified(tier=OutcomeTier.SUCCESS, hitches=None, botch=False):
    return SimplifiedResult(
        rolls=[DieRoll(die=DieType.D8, result=7, label="a")],
        highest=7,
        tier=tier,
        effect_die=DieType.D6,
        hitches=hitches or [],
        botch=botch,
        hitches_count=0,
    )


def test_fire_roll_sfx_fires_matching_trigger():
    repo = Repo({"e1": SimpleNamespace(razmerit=10, sfx_ids=["sfx-success"], current_projection=None)})
    engine = EffectsEngine()
    engine.register(SFX(
        id="sfx-success", name="Thrive", trigger="on_success",
        effects=[Effect(timing=EffectTiming.IMMEDIATE, type="modify_roll",
                        action="step_up_die", target="next")],
    ))

    applied = fire_roll_sfx(engine, repo, "e1", "earth", _simplified())
    assert [a.action for a in applied] == ["step_up_die"]


def test_roll_match_trigger_can_gate_on_the_roll_tier():
    """`on_success` matches on the resolver's tier — its conditions must see it.

    The trigger match already reads `roll_result.tier`; before this the event
    context carried only the dice, so a `roll tier` gate on those triggers read
    nothing and silently never passed.
    """
    repo = Repo({"e1": SimpleNamespace(razmerit=10, sfx_ids=["sfx-tiered"], current_projection=None)})
    engine = EffectsEngine()
    engine.register(SFX(
        id="sfx-tiered", name="Tiered", trigger="on_success",
        conditions=[Condition(type=ConditionType.ROLL_TIER, operator="==", value="success")],
        effects=[Effect(timing=EffectTiming.IMMEDIATE, type="modify_roll",
                        action="step_up_die", target="next")],
    ))

    applied = fire_roll_sfx(engine, repo, "e1", "earth", _simplified(tier=OutcomeTier.SUCCESS))
    assert [a.action for a in applied] == ["step_up_die"]

    # A failing roll doesn't match the trigger at all.
    assert fire_roll_sfx(engine, repo, "e1", "earth", _simplified(tier=OutcomeTier.FAIL)) == []


def test_fire_roll_sfx_missing_entity_is_noop():
    repo = Repo()
    engine = EffectsEngine()
    engine.register(SFX(
        id="sfx-success", name="Thrive", trigger="on_success",
        effects=[Effect(timing=EffectTiming.IMMEDIATE, type="modify_roll",
                        action="step_up_die", target="next")],
    ))

    assert fire_roll_sfx(engine, repo, "ghost", "earth", _simplified()) == []


def test_process_event_outcome_returns_pending_for_choose_target():
    engine = EffectsEngine()
    engine.register(SFX(
        id="sfx-choose", name="Choose", trigger="on_success",
        effects=[Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait",
                        action="gain", target="{choose_trait}")],
    ))
    event = GameEvent(type="on_roll", entity_id="e1", universe="earth", roll_result=_simplified())

    outcome = engine.process_event_outcome(event, ["sfx-choose"], 10)
    assert outcome.applied == []
    assert [p.effect.target for p in outcome.pending] == ["{choose_trait}"]


def test_fire_roll_sfx_emits_choose_target_instead_of_applying(monkeypatch):
    repo = Repo({"e1": SimpleNamespace(razmerit=10, sfx_ids=["sfx-choose"], current_projection=None)})
    engine = EffectsEngine()
    engine.register(SFX(
        id="sfx-choose", name="Choose", trigger="on_success",
        effects=[Effect(timing=EffectTiming.IMMEDIATE, type="modify_trait",
                        action="gain", target="{choose_trait}")],
    ))
    emitted = []
    monkeypatch.setattr(
        roll_orchestrator, "_emit_pending_choices",
        lambda entity_id, universe, effects, structured=None: emitted.extend(effects),
    )

    applied = fire_roll_sfx(engine, repo, "e1", "earth", _simplified())
    assert applied == []
    assert [p.effect.target for p in emitted] == ["{choose_trait}"]


def test_emit_pending_choices_includes_target_filter(monkeypatch):
    from transversal.services.effects_engine import PendingSfxEffect

    eff = Effect(
        timing=EffectTiming.IMMEDIATE, type="location", action="set",
        target="{choose_location}", target_scope="universe:earth",
        target_filter={"starter_location": True},
    )
    pending = [PendingSfxEffect(effect=eff, sfx_name="Starter", sfx_description="")]

    published = []
    monkeypatch.setattr(
        "transversal.services.session_manager.session_manager.list_active",
        lambda: [SimpleNamespace(id="s1")],
    )
    monkeypatch.setattr(
        "transversal.api.sse.bus.event_bus.publish",
        lambda evt: published.append(evt),
    )

    roll_orchestrator._emit_pending_choices("e1", "earth", pending)

    assert len(published) == 1
    choice = published[0].data["choices"][0]
    assert choice["filter"] == {"starter_location": True}
    assert choice["effect"]["targetFilter"] == {"starter_location": True}


def test_is_choose_target_and_choose_kind():
    assert is_choose_target("{choose_trait}") is True
    assert is_choose_target("{random:location}") is False
    assert is_choose_target("self") is False
    assert choose_kind("{choose_trait}") == "trait"
    assert choose_kind("self") is None


def test_fire_roll_sfx_gated_by_condition():
    repo = Repo({"e1": SimpleNamespace(razmerit=10, sfx_ids=["sfx-cond"], current_projection=None, current_location="loc-a")})
    engine = EffectsEngine()
    engine.register(SFX(
        id="sfx-cond", name="Cond", trigger="on_success",
        conditions=[Condition(type=ConditionType.AT_LOCATION, target="loc-a")],
        effects=[Effect(timing=EffectTiming.IMMEDIATE, type="modify_roll",
                        action="step_up_die", target="next")],
    ))

    assert len(fire_roll_sfx(engine, repo, "e1", "earth", _simplified())) == 1

    # Wrong location -> condition gates it out.
    repo.entities["e1"].current_location = "loc-b"
    assert fire_roll_sfx(engine, repo, "e1", "earth", _simplified()) == []


def test_fire_result_sfx_exposes_roll_state_in_context(monkeypatch):
    """on_result fires with effect_die/total plus the rolled dice (role + tier)."""
    import transversal.main as main
    from transversal.services.effects_engine import EventOutcome

    captured = []

    class FakeEngine:
        def process_event_outcome(self, event, sfx_ids, razmerit, repo=None):
            captured.append(event)
            return EventOutcome()

    rolls = [
        {"die": "d8", "result": 7, "role": None, "tier": "success", "effect_die": "d6", "ts_id": "ts-crimson"},
        {"die": "d8", "result": 5, "role": "total", "tier": "marginal", "effect_die": "d4", "ts_id": "ts-other"},
    ]

    monkeypatch.setattr(main, "_get_engine", lambda: FakeEngine())
    monkeypatch.setattr(main, "_get_repo", lambda: SimpleNamespace(
        get_entity=lambda eid: SimpleNamespace(razmerit=3, sfx_ids=[], current_projection=None, current_universe="earth"),
    ))
    monkeypatch.setattr(roll_orchestrator, "get_available_sfx_ids", lambda *a, **k: [])
    monkeypatch.setattr(roll_orchestrator, "_emit_pending_choices", lambda *a, **k: None)

    applied = roll_orchestrator.fire_result_sfx("e1", "earth", rolls, effect_die="d6", total=12)

    assert applied == []
    assert len(captured) == 1
    ev = captured[0]
    assert ev.type == "on_result"
    assert ev.context["effect_die"] == "d6"
    assert ev.context["total"] == 12
    assert ev.context["rolls"] == rolls


def test_fire_roll_sfx_passes_rolls_to_fire_armed(monkeypatch):
    """on_roll deferred effects receive the real rolled dice, not an empty context."""
    import transversal.services.roll_deferral as roll_deferral

    repo = Repo({"e1": SimpleNamespace(razmerit=10, sfx_ids=[], current_projection=None)})
    engine = EffectsEngine()

    captured = {}
    monkeypatch.setattr(
        roll_deferral, "fire_armed",
        lambda entity_id, event, universe, context: captured.update(context),
    )

    rolls = [{"die": "d8", "result": 7, "role": None, "ts_id": "ts-x"}]
    fire_roll_sfx(engine, repo, "e1", "earth", SimpleNamespace(rolls=rolls, hitches=[], botch=False))

    assert captured["rolls"] == rolls


def test_process_event_outcome_surfaces_structured_choose():
    """A terminal `choose` in an immediate target_spec becomes a StructuredChoice."""
    from transversal.services.target_spec import ChooseStep, NavigateStep, SelectStep, TargetSpec

    class Repo2:
        def __init__(self):
            self.entity = SimpleNamespace(
                id="e1", razmerit=10, current_location="loc1",
                current_universe="earth", current_projection=None, sfx_ids=["sfx-pick"],
            )
            self.traitsettings = [
                SimpleNamespace(id="e1:ts-a", entity_id="e1", trait_id="trait-a", rating="d6"),
                SimpleNamespace(id="e1:ts-b", entity_id="e1", trait_id="trait-b", rating="d8"),
            ]

        def get_entity(self, eid):
            return self.entity if eid == "e1" else None

        def get_traitsettings_for_entity(self, eid):
            return self.traitsettings if eid == "e1" else []

    repo = Repo2()
    engine = EffectsEngine()
    engine.register(SFX(
        id="sfx-pick", name="Pick", trigger="manual",
        effects=[Effect(
            timing=EffectTiming.IMMEDIATE, type="modify_trait", action="step_up",
            target_spec=TargetSpec(steps=[
                SelectStep(collection="self"),
                NavigateStep(edge="traitsettings"),
                ChooseStep(),
            ]),
        )],
    ))
    event = GameEvent(type="manual", entity_id="e1", universe="earth")

    outcome = engine.process_event_outcome(event, ["sfx-pick"], 10, repo=repo)

    assert outcome.applied == []
    assert len(outcome.structured) == 1
    c = outcome.structured[0]
    assert c.field == "target"
    assert c.element == "traitsetting"
    assert [x["id"] for x in c.candidates] == ["e1:ts-a", "e1:ts-b"]


def test_resolve_refs_surfaces_structured_choice():
    """A terminal `choose` in a named ref becomes a StructuredChoice with refs field."""
    from transversal.domain import TargetRef
    from transversal.services.target_resolver import TargetContext
    from transversal.services.target_spec import ChooseStep, SelectStep, TargetSpec
    from transversal.services.effects_engine import resolve_refs

    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_pool", action="add_dice",
        refs={"pool": TargetRef(value="", spec=TargetSpec(steps=[
            SelectStep(collection="rolled_dice"),
            ChooseStep(),
        ]))},
    )
    structured = []
    resolved = resolve_refs(effect, TargetContext(
        subject=None, repo=None,
        collections={"rolled_dice": [
            {"ts_id": "a", "rating": "d6"}, {"ts_id": "b", "rating": "d8"},
        ]},
    ), structured)

    assert resolved == []
    assert len(structured) == 1
    assert structured[0].field == "refs.pool"
    assert structured[0].element == "die"
    assert [x["id"] for x in structured[0].candidates] == ["a", "b"]


def test_resolve_refs_fans_out_over_many():
    """A ref resolving to many yields one effect per value (fan-out)."""
    from transversal.domain import TargetRef
    from transversal.services.target_resolver import TargetContext
    from transversal.services.target_spec import SelectStep, TargetSpec
    from transversal.services.effects_engine import resolve_refs

    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_pool", action="add_trait_rating",
        refs={"trait": TargetRef(spec=TargetSpec(steps=[SelectStep(collection="rolled_dice")]))},
    )
    resolved = resolve_refs(effect, TargetContext(
        subject=None, repo=None,
        collections={"rolled_dice": [
            {"ts_id": "a", "rating": "d6"}, {"ts_id": "b", "rating": "d8"},
        ]},
    ))

    assert [r.refs["trait"].value for r in resolved] == ["a", "b"]
    assert all(r.refs["trait"].spec is None for r in resolved)


def test_resolve_refs_fan_out_is_cartesian():
    """Two multi refs fan out as the cartesian product; a literal ref is fixed."""
    from transversal.domain import TargetRef
    from transversal.services.target_resolver import TargetContext
    from transversal.services.target_spec import SelectStep, TargetSpec
    from transversal.services.effects_engine import resolve_refs

    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_pool", action="add_trait_rating",
        refs={
            "trait": TargetRef(spec=TargetSpec(steps=[SelectStep(collection="rolled_dice")])),
            "pool": TargetRef(spec=TargetSpec(steps=[SelectStep(collection="rolled_dice")])),
        },
    )
    resolved = resolve_refs(effect, TargetContext(
        subject=None, repo=None,
        collections={"rolled_dice": [{"ts_id": "a", "rating": "d6"}, {"ts_id": "b", "rating": "d8"}]},
    ))

    pairs = [(r.refs["trait"].value, r.refs["pool"].value) for r in resolved]
    assert sorted(pairs) == [("a", "a"), ("a", "b"), ("b", "a"), ("b", "b")]


def test_resolve_refs_empty_resolution_returns_nothing():
    """A ref resolving to zero values fans out to no effects."""
    from transversal.domain import TargetRef
    from transversal.services.target_resolver import TargetContext
    from transversal.services.target_spec import SelectStep, TargetSpec
    from transversal.services.effects_engine import resolve_refs

    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_pool", action="add_trait_rating",
        refs={"trait": TargetRef(spec=TargetSpec(steps=[SelectStep(collection="rolled_dice")]))},
    )
    resolved = resolve_refs(effect, TargetContext(
        subject=None, repo=None, collections={"rolled_dice": []},
    ))

    assert resolved == []
