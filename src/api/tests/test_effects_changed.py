"""The ``effects_changed`` event — the activation splash's note face ([[B229]]).

The wire contract is [[ui-ux]]'s ([[UI-UX Design]] § *Activation splash*), and the
surface is already built and specced against it; this is the effects layer's half.
The shape is load-bearing in three places, so each is pinned here:

* ``kind`` picks the **dwell** — ``summary`` for a rule that has run its course,
  ``change`` for a brief note — so getting it wrong makes a report vanish early or
  linger, and nothing errors.
* ``entity_id`` is the **audience**: a change to someone else's sheet is not the
  reader's to see, so the shell filters on exactly this.
* ``lines`` is what each effect did or why it did nothing ([[B236]]).
"""

from types import SimpleNamespace

from transversal.domain import Effect, EffectTiming, SFX
from transversal.services.effects_engine import EffectsEngine, GameEvent
from transversal.services.effects_engine.firing import _note_lines


class TestTheLines:
    def test_a_record_reads_as_its_verb_and_its_outcome(self):
        assert _note_lines([{"action": "play_as_rating", "note": "t plays as d4"}]) == [
            "play_as_rating: t plays as d4"]

    def test_a_refusal_reads_as_a_reason(self):
        """The half the author could not see: a no-op said so in its own words."""
        assert _note_lines([{"action": "consolidate_dice",
                             "note": "no second d8 in x's rating to merge"}]) == [
            "consolidate_dice: no second d8 in x's rating to merge"]

    def test_a_record_with_no_note_is_left_out_rather_than_invented(self):
        """A razmerit op never reaches the commit path, so nothing recorded what it
        did. A missing line is honest; a written one would not be."""
        assert _note_lines([{"action": "earn", "note": ""},
                            {"action": "play_as_rating", "note": "t plays as d4"}]) == [
            "play_as_rating: t plays as d4"]

    def test_nothing_recorded_is_no_lines(self):
        assert _note_lines([]) == []
        assert _note_lines(None) == []


class TestTheEvent:
    @staticmethod
    def _capture(monkeypatch):
        published = []
        monkeypatch.setattr(
            "transversal.services.session_manager.session_manager.list_active",
            lambda: [SimpleNamespace(id="s1")],
        )
        monkeypatch.setattr(
            "transversal.api.sse.bus.event_bus.publish",
            lambda evt: published.append(evt),
        )
        return published

    def test_the_payload_is_the_contract(self, monkeypatch):
        from transversal.services.effects_engine.firing import _emit_effects_changed

        published = self._capture(monkeypatch)
        _emit_effects_changed(entity_id="e1", title="Hinder", kind="summary",
                              lines=["play_as_rating: t plays as d4"])

        assert len(published) == 1
        evt = published[0]
        assert evt.event == "effects_changed"
        assert evt.data["entity_id"] == "e1"
        assert evt.data["title"] == "Hinder"
        assert evt.data["kind"] == "summary"
        assert evt.data["lines"] == ["play_as_rating: t plays as d4"]

    def test_a_summary_does_not_widen_the_audience_to_the_room(self, monkeypatch):
        """`location_id` widens the audience to everyone standing there, which is
        right for a change *in* a room and wrong for a report about one character's
        own activation."""
        from transversal.services.effects_engine.firing import _emit_effects_changed

        published = self._capture(monkeypatch)
        _emit_effects_changed(entity_id="e1", title="Hinder", kind="summary",
                              lines=["did a thing"])
        assert published[0].data["location_id"] == ""

    def test_nothing_to_report_is_not_an_event(self, monkeypatch):
        from transversal.services.effects_engine.firing import _emit_effects_changed

        published = self._capture(monkeypatch)
        _emit_effects_changed(entity_id="e1", title="Hinder", kind="summary", lines=[])
        assert published == []


class TestTheEngineEmitsIt:
    """Seeded once per outcome and sliced per rule, like the notes it reports."""

    def test_an_applied_rule_reports_its_own_effects(self, monkeypatch):
        from transversal.services.effects_applier.datatypes import (
            EFFECT_NOTES_CONTEXT_KEY,
        )

        called = []
        monkeypatch.setattr(
            "transversal.services.effects_engine._emit_effects_changed",
            lambda **kw: called.append(kw),
        )
        monkeypatch.setattr(
            "transversal.services.effects_engine._emit_sfx_triggered",
            lambda *a, **k: None,
        )

        engine = EffectsEngine()

        class Recorder:
            """Stands in for the applier registry, appending a note per effect."""

            def apply(self, action, entity_id, universe, context):
                context[EFFECT_NOTES_CONTEXT_KEY].append(
                    {"type": action.type, "action": action.action,
                     "target": action.target, "note": "turned into a d10"})

        engine.register(SFX(
            id="sfx-report", name="Consolidate", trigger="manual",
            effects=[Effect(timing=EffectTiming.IMMEDIATE, type="modify_roll",
                            action="consolidate_dice", target="rating:0:x")],
        ))
        import transversal.services.effects_engine.engine as engine_module
        original = engine_module._effects_applier.effect_registry
        engine_module._effects_applier.effect_registry = Recorder()
        try:
            engine.process_event_outcome(
                GameEvent(type="manual", entity_id="e1", universe="earth"),
                ["sfx-report"], 0, repo=_Repo(),
            )
        finally:
            engine_module._effects_applier.effect_registry = original

        assert len(called) == 1
        assert called[0]["entity_id"] == "e1"
        assert called[0]["title"] == "Consolidate"
        # The longer dwell: a rule that has run its course, not a passing change.
        assert called[0]["kind"] == "summary"
        assert called[0]["lines"] == ["consolidate_dice: turned into a d10"]

    def test_a_rule_that_applied_nothing_reports_nothing(self, monkeypatch):
        """Asserted on what is *published*, not on the call: the guard against an
        empty report lives in one place — the emitter — rather than at every call
        site, so the observable behaviour is what a test should pin."""
        published = []
        monkeypatch.setattr(
            "transversal.services.session_manager.session_manager.list_active",
            lambda: [SimpleNamespace(id="s1")],
        )
        monkeypatch.setattr(
            "transversal.api.sse.bus.event_bus.publish",
            lambda evt: published.append(evt),
        )
        monkeypatch.setattr(
            "transversal.services.effects_engine._emit_sfx_triggered",
            lambda *a, **k: None,
        )

        engine = EffectsEngine()

        class Refuser:
            def apply(self, action, entity_id, universe, context):
                return None  # never reaches the commit path, so no note

        engine.register(SFX(
            id="sfx-quiet", name="Quiet", trigger="manual",
            effects=[Effect(timing=EffectTiming.IMMEDIATE, type="transfer_razmerit",
                            action="earn", result="1")],
        ))
        import transversal.services.effects_engine.engine as engine_module
        original = engine_module._effects_applier.effect_registry
        engine_module._effects_applier.effect_registry = Refuser()
        try:
            engine.process_event_outcome(
                GameEvent(type="manual", entity_id="e1", universe="earth"),
                ["sfx-quiet"], 0, repo=_Repo(),
            )
        finally:
            engine_module._effects_applier.effect_registry = original

        assert [e for e in published if e.event == "effects_changed"] == [], (
            "a rule with nothing to report must not splash")


class _Repo:
    """The engine reads nothing off the repo for this path, but it is not None."""

    def get_entity(self, entity_id):
        return None
