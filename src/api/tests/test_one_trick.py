"""End-to-end proof for the One Trick passive rule.

One Trick is *authored* as an SFX (``on_session_start`` trigger, an ``on_roll``
``step_down`` effect with a ``rolled_dice → traitsetting`` target spec plus a
``rating_type == static`` guard, and a ``beat`` revert duration). These tests
verify the whole chain — session start arms it globally → a roll resolves the
spec and fans out one ``step_down`` per rolled static trait instance (deduped).

The SFX is constructed inline (it is hand-authored content, not a code seed), so
the tests assert the *shape* the wizard produces, not a seed function.
"""

from types import SimpleNamespace

import transversal.main as main
import transversal.services.roll_deferral as roll_deferral


class OneTrickRepo:
    """Minimal double covering the resolution surfaces One Trick touches."""

    def __init__(self):
        self.sfxs = {}
        self.entity = SimpleNamespace(id="char-1")
        self.traitsettings = {
            "char-1:martial": SimpleNamespace(
                id="char-1:martial", trait_id="martial", entity_id="char-1",
                rating_type="static",
            ),
            "char-1:qi": SimpleNamespace(
                id="char-1:qi", trait_id="qi", entity_id="char-1",
                rating_type="static",
            ),
            "char-1:focus": SimpleNamespace(
                id="char-1:focus", trait_id="focus", entity_id="char-1",
                rating_type="resource",
            ),
        }

    def get_sfx(self, sid):
        return self.sfxs.get(sid)

    def create_sfx(self, sfx):
        self.sfxs[sfx.id] = sfx

    def get_all_sfxs(self):
        return list(self.sfxs.values())

    def get_entity(self, eid):
        return self.entity

    def get_traitsetting(self, ts_id):
        return self.traitsettings.get(ts_id)


def one_trick_sfx():
    """The hand-authored One Trick passive rule (4-step spec, dedup + static guard)."""
    from transversal.domain import Effect, EffectDuration, EffectTiming, SFX, Timer
    from transversal.services.target_spec import FilterStep, NavigateStep, SelectStep, TargetSpec

    step_down = Effect(
        timing=EffectTiming.ON_ROLL,
        type="modify_trait",
        action="step_down",
        target="",  # set to the resolved traitsetting id at fire time
        target_spec=TargetSpec(steps=[
            SelectStep(collection="rolled_dice"),
            FilterStep(field="source_kind", value="trait"),
            NavigateStep(edge="traitsetting", dedup=True),
            FilterStep(field="rating_type", value="static"),
        ]),
        duration=EffectDuration(timers=[Timer(event="beat", remaining=1)]),
    )
    return SFX(
        id="sfx-one-trick",
        name="One Trick",
        description="Reusing traits has diminishing returns — every trait you roll steps down one step until end of beat.",
        trigger="on_session_start",
        effects=[step_down],
        duration=None,  # armed for the whole session (not a per-roll budget)
    )


def test_one_trick_spec_shape():
    sfx = one_trick_sfx()

    assert sfx.trigger == "on_session_start"
    assert sfx.duration is None  # armed for the whole session, no roll budget
    assert len(sfx.effects) == 1

    eff = sfx.effects[0]
    assert eff.type == "modify_trait"
    assert eff.action == "step_down"
    assert eff.timing.value == "on_roll"
    # The hand-authored shape: select rolled dice → only trait dice → owning
    # traitsetting (deduped) → only static ratings.
    steps = eff.target_spec.steps
    assert [(s.kind, getattr(s, "edge", None), getattr(s, "field", None), getattr(s, "dedup", False))
            for s in steps] == [
        ("select", None, None, False),
        ("filter", None, "source_kind", False),
        ("navigate", "traitsetting", None, True),
        ("filter", None, "rating_type", False),
    ]
    assert eff.duration is not None and eff.duration.timers[0].event == "beat"


def test_one_trick_end_to_end(monkeypatch):
    from transversal.services.state_events import fire_session_start

    roll_deferral.reset()
    repo = OneTrickRepo()
    repo.create_sfx(one_trick_sfx())
    monkeypatch.setattr(main, "_get_repo", lambda: repo)

    fire_session_start()
    assert len(roll_deferral.list_global_armed()) == 1

    applied = []

    class FakeRegistry:
        def apply(self, effect, entity_id, universe, context):
            applied.append(effect)

    monkeypatch.setattr("transversal.services.effects_applier.effect_registry", FakeRegistry())

    rolls = [
        {"ts_id": "char-1:martial", "source_kind": "trait", "result": 7},
        {"ts_id": "char-1:qi", "source_kind": "trait", "result": 3},
        {"ts_id": "char-1:martial", "source_kind": "trait", "result": 5},  # dup → deduped
        {"ts_id": "char-1:focus", "source_kind": "trait", "result": 6},    # resource → filtered by rating_type
        {"ts_id": "char-1:other", "source_kind": "manual", "result": 6},   # filtered by source_kind
    ]
    roll_deferral.fire_armed("char-1", "on_roll", "earth", {"rolls": rolls})

    assert [e.target for e in applied] == ["char-1:martial", "char-1:qi"]
