"""Tests for portal edge effects + the fire-portal endpoint."""

import pytest
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient

from transversal.api.rest.locations import _effect_from_wire, router as locations_router
from transversal.domain import EffectTiming, Entity, EntityType, TimerCombine
import transversal.api.rest.locations as locations_module


# ── _effect_from_wire ───────────────────────────────

def test_effect_from_wire_maps_camelcase_and_enum_names():
    eff = _effect_from_wire({
        "timing": "IMMEDIATE",
        "type": "travel",
        "action": "move",
        "target": "{random:location}",
        "entity": "self",
        "result": None,
        "negative": False,
        "context": {"transversal_type": "inapposite"},
        "duration": None,
    })
    assert eff.timing == EffectTiming.IMMEDIATE
    assert eff.type == "travel"
    assert eff.action == "move"
    assert eff.target == "{random:location}"
    assert eff.entity == "self"
    assert eff.context == {"transversal_type": "inapposite"}
    assert eff.duration is None


def test_effect_from_wire_duration_and_lowercase_enum_values():
    eff = _effect_from_wire({
        "timing": "end_of_scene",
        "type": "transfer_razmerit",
        "action": "earn",
        "target": "self",
        "entity": "",
        "duration": {"timers": [{"event": "scene", "remaining": 2}], "combine": "all_transpired"},
    })
    assert eff.timing == EffectTiming.END_OF_SCENE
    assert eff.duration.combine == TimerCombine.ALL_TRANSPIRED
    assert eff.duration.timers[0].event == "scene"
    assert eff.duration.timers[0].remaining == 2


def test_effect_from_wire_carries_the_structured_specs():
    """The destination of a portal effect lives in `targetSpec`, not in `target`.

    Dropping it left the effect with nowhere to go, so the applier reported
    `applied: []` and the traveller did not move — the Eindhoven Airport →
    Турышка аэропорт case, which did nothing even once the 404 was fixed
    (2026-09-26). The spec is the whole point of the effect.
    """
    eff = _effect_from_wire({
        "timing": "IMMEDIATE", "type": "travel", "action": "move",
        "target": "", "entity": "",
        "context": {"transversal_type": "inapposite"},
        "targetSpec": {"steps": [
            {"kind": "select", "collection": "locations"},
            {"kind": "filter", "field": "id", "operator": "in", "value": ["loc-a", "loc-b"]},
            {"kind": "choose"},
        ]},
        "refs": {"projection": {"value": "", "spec": None, "scope": None}},
        "dieFilter": {"role": None},
    })

    assert eff.target_spec is not None, "the spec must survive the wire adapter"
    assert len(eff.target_spec.steps) == 3
    assert "projection" in eff.refs
    assert eff.die_filter == {"role": None}


# ── fire_portal ─────────────────────────────────────

class _FakeEdges:
    def __init__(self, edge):
        self.edge = edge

    def get(self, key):
        return self.edge if (self.edge or {}).get("_key") == key else None


class _FakeRepo:
    def __init__(self, entity, edge, extra_entities=None):
        self.entity = entity
        self._relationships = _FakeEdges(edge)
        self._entities = {entity.id: entity}
        for e in (extra_entities or []):
            self._entities[e.id] = e

    def get_entity(self, eid):
        return self._entities.get(eid)

    def get_relationship(self, from_id, to_id, rel_type):
        """The triple lookup the endpoint must use — see the legacy-key test.

        Deliberately keyed on `_from`/`_to`/`type` and **not** on `_key`: a fake that
        matched the canonical key is what let the by-key bug ship, because every
        fixture edge happened to be canonical while the live one was not.
        """
        e = self._relationships.edge or {}
        if (e.get("_from") == f"entities/{from_id}"
                and e.get("_to") == f"entities/{to_id}"
                and e.get("type") == rel_type):
            return e
        return None


def test_fire_portal_applies_edge_effects(monkeypatch):
    entity = Entity(id="char-1", type=EntityType.CHARACTER, name="Kael", current_universe="earth")
    edge = {
        "_key": "edge:loc-a:loc-b:transversal",
        "_from": "entities/loc-a",
        "_to": "entities/loc-b",
        "type": "transversal",
        "effects": [
            {"timing": "IMMEDIATE", "type": "travel", "action": "move",
             "target": "loc-b", "context": {"transversal_type": "inapposite"}},
        ],
    }
    repo = _FakeRepo(entity, edge)
    monkeypatch.setattr(locations_module, "_repo", lambda: repo)

    captured = {}

    def fake_commit_effects(e, effects, r, **kwargs):
        captured["effects"] = effects
        captured["arrival_kind"] = kwargs.get("arrival_kind")
        class _R:
            applied = []
            pending_choices = []
        return _R()

    monkeypatch.setattr("transversal.services.effects_commit.commit_effects", fake_commit_effects)

    class _FakeEm:
        """The travel the endpoint must still perform, recorded not executed."""

        def travel(self, entity_id, to_id, transversal_type=None, projection_policy=None):
            captured["travel"] = (entity_id, to_id, transversal_type)
            return entity.model_copy(update={"current_location": to_id})

    monkeypatch.setattr(locations_module, "_em", lambda: _FakeEm())

    app = FastAPI()
    app.include_router(locations_router)
    client = TestClient(app)

    r = client.post("/api/v1/locations/loc-a/portal/loc-b/fire", json={"entity_id": "char-1"})
    assert r.status_code == 200, r.text
    assert len(captured["effects"]) == 1
    # A portal crossing is a transversal arrival, not a generic effect move.
    assert captured["arrival_kind"] == "transversal"
    assert captured["effects"][0].type == "travel"
    assert captured["effects"][0].target == "loc-b"
    assert captured["effects"][0].context == {"transversal_type": "inapposite"}
    # …and the traveller is still delivered: a portal with effects is a link too.
    assert captured["travel"] == ("char-1", "loc-b", "inapposite")


def test_fire_portal_finds_an_edge_stored_under_a_legacy_key(monkeypatch):
    """The live shape of the bug: the one authored portal with effects is `26763380`.

    Not the canonical `edge:loc-a:loc-b:transversal`. The endpoint looked the edge up
    by that derived key, got None, and 404'd on a portal that is plainly there — so
    Eindhoven Airport → Турышка аэропорт animated, lit its effect, and applied
    nothing. A by-triple lookup cannot care what the key looks like.
    """
    entity = Entity(id="char-1", type=EntityType.CHARACTER, name="Kael", current_universe="earth")
    edge = {
        "_key": "26763380",                      # ← the legacy/random key
        "_from": "entities/loc-a",
        "_to": "entities/loc-b",
        "type": "transversal",
        "effects": [
            {"timing": "IMMEDIATE", "type": "travel", "action": "move",
             "target": "loc-b", "context": {"transversal_type": "inapposite"}},
        ],
    }
    repo = _FakeRepo(entity, edge)
    monkeypatch.setattr(locations_module, "_repo", lambda: repo)

    captured = {}

    def fake_commit_effects(e, effects, r, **kwargs):
        captured["effects"] = effects
        class _R:
            applied = []
            pending_choices = []
        return _R()

    monkeypatch.setattr("transversal.services.effects_commit.commit_effects", fake_commit_effects)

    class _FakeEm:
        """The travel the endpoint must still perform, recorded not executed."""

        def travel(self, entity_id, to_id, transversal_type=None, projection_policy=None):
            captured["travel"] = (entity_id, to_id, transversal_type)
            return entity.model_copy(update={"current_location": to_id})

    monkeypatch.setattr(locations_module, "_em", lambda: _FakeEm())

    app = FastAPI()
    app.include_router(locations_router)
    client = TestClient(app)

    r = client.post("/api/v1/locations/loc-a/portal/loc-b/fire", json={"entity_id": "char-1"})
    assert r.status_code == 200, r.text
    assert len(captured["effects"]) == 1, "the legacy-keyed portal must still fire"
    assert captured["travel"] == ("char-1", "loc-b", "inapposite")


def test_fire_portal_still_404s_when_there_is_no_portal(monkeypatch):
    """The lookup must not become a rubber stamp — a missing portal is a real 404."""
    entity = Entity(id="char-1", type=EntityType.CHARACTER, name="Kael", current_universe="earth")
    repo = _FakeRepo(entity, None)
    monkeypatch.setattr(locations_module, "_repo", lambda: repo)

    app = FastAPI()
    app.include_router(locations_router)
    client = TestClient(app)

    r = client.post("/api/v1/locations/loc-a/portal/loc-b/fire", json={"entity_id": "char-1"})
    assert r.status_code == 404
    assert "not found" in r.json()["detail"]



def test_fire_portal_delivers_even_when_its_effects_ask_a_question(monkeypatch):
    """A portal is a link: question or not, firing it takes you where it points.

    The live case (Eindhoven Airport, 2026-10-17): the one effect-carrying portal
    stopped at a `choose` and left the traveller standing at the gate, so an
    airport could not be used as a hub.
    """
    from transversal.services.effects_applier.datatypes import PendingChoice

    entity = Entity(id="char-1", type=EntityType.CHARACTER, name="Kael",
                    current_universe="earth", current_location="loc-a")
    edge = {
        "_key": "edge:loc-a:loc-b:transversal",
        "_from": "entities/loc-a", "_to": "entities/loc-b", "type": "transversal",
        "effects": [{"timing": "IMMEDIATE", "type": "travel", "action": "move"}],
    }
    repo = _FakeRepo(entity, edge)
    monkeypatch.setattr(locations_module, "_repo", lambda: repo)

    captured = {}

    def fake_commit_effects(e, effects, r, **kwargs):
        class _R:
            applied = []
            pending_choices = [PendingChoice(effect=effects[0], kind="location", field="target")]
        return _R()

    monkeypatch.setattr("transversal.services.effects_commit.commit_effects", fake_commit_effects)

    class _FakeEm:
        def travel(self, entity_id, to_id, transversal_type=None, projection_policy=None):
            captured["travel"] = (entity_id, to_id)
            return entity.model_copy(update={"current_location": to_id})

    monkeypatch.setattr(locations_module, "_em", lambda: _FakeEm())

    app = FastAPI()
    app.include_router(locations_router)
    client = TestClient(app)

    r = client.post("/api/v1/locations/loc-a/portal/loc-b/fire", json={"entity_id": "char-1"})
    body = r.json()
    assert r.status_code == 200, r.text
    assert captured["travel"] == ("char-1", "loc-b"), "the traveller must be delivered"
    assert body["status"] == "pending", "the question is still outstanding"
    assert body["location_id"] == "loc-b"


def test_an_effect_that_moves_the_traveller_wins_over_the_portals_own_destination(monkeypatch):
    """A portal whose effect travels somewhere *else* must not be double-moved."""
    entity = Entity(id="char-1", type=EntityType.CHARACTER, name="Kael",
                    current_universe="earth", current_location="loc-a")
    edge = {
        "_key": "edge:loc-a:loc-b:transversal",
        "_from": "entities/loc-a", "_to": "entities/loc-b", "type": "transversal",
        "effects": [{"timing": "IMMEDIATE", "type": "travel", "action": "move"}],
    }
    repo = _FakeRepo(entity, edge)
    monkeypatch.setattr(locations_module, "_repo", lambda: repo)
    travelled = []

    def fake_commit_effects(e, effects, r, **kwargs):
        e.current_location = "loc-c"           # the effect moved them itself
        class _R:
            applied = [SimpleNamespace(summary="travelled to loc-c")]
            pending_choices = []
        return _R()

    monkeypatch.setattr("transversal.services.effects_commit.commit_effects", fake_commit_effects)

    class _FakeEm:
        def travel(self, *a, **kw):
            travelled.append(a)
            return entity

    monkeypatch.setattr(locations_module, "_em", lambda: _FakeEm())

    app = FastAPI()
    app.include_router(locations_router)
    client = TestClient(app)

    r = client.post("/api/v1/locations/loc-a/portal/loc-b/fire", json={"entity_id": "char-1"})
    assert r.status_code == 200, r.text
    assert travelled == [], "the portal must not travel the traveller again"
    assert r.json()["location_id"] == "loc-c"


def test_the_fire_response_can_be_handed_back_to_resolve_effect_targets(monkeypatch):
    """The question must come home in the **wire** shape ([[navigation]], 2026-10-17).

    `resolveEffectTargets` is stateless and client-carried: the client sends the
    effect back and the server re-resolves it with the answers. So the fire response
    has to carry an `EffectInput`-shaped effect — camelCase — and the engine's own
    round-trip vocabulary beside it. It used to carry `effect.model_dump()`, the
    *domain* shape, and five field names differ (`dieFilter`, `targetSpec`,
    `entitySpec`, `ownerSpec`, `resultSpec`), so the echo would have been rejected as
    an input, or accepted with every spec silently empty.
    """
    from transversal.services.effects_engine.wire import effect_to_wire_dict
    from transversal.domain import Effect, TargetRef
    from transversal.services.effects_applier.datatypes import PendingChoice
    from transversal.services.target_spec import SelectStep, TargetSpec

    # The mapper on its own: camelCase, and a spec dumped rather than dropped.
    domain_effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="travel", action="move",
        die_filter={"role": None},
        refs={"location": TargetRef(spec=TargetSpec(steps=[SelectStep(collection="locations")]))},
    )
    wire = effect_to_wire_dict(domain_effect)
    assert "dieFilter" in wire and "die_filter" not in wire
    assert wire["dieFilter"] == {"role": None}

    # And the endpoint's payload: the pool, the round trip, and the source.
    entity = Entity(id="char-1", type=EntityType.CHARACTER, name="Kael",
                    current_universe="earth", current_location="loc-a")
    edge = {"_key": "edge:loc-a:loc-a:transversal", "_from": "entities/loc-a",
            "_to": "entities/loc-a", "type": "transversal",
            "effects": [{"timing": "IMMEDIATE", "type": "travel", "action": "move"}]}
    repo = _FakeRepo(entity, edge)
    monkeypatch.setattr(locations_module, "_repo", lambda: repo)

    def fake_commit_effects(e, effects, r, **kwargs):
        class _R:
            applied = []
            pending_choices = [PendingChoice(
                effect=effects[0], kind="location", field="refs.location",
                candidates=[{"id": "loc-1", "name": "Zurich Airport"}],
                count=1, structured=True, step_index=2,
                answers_so_far=[{"stepIndex": 0, "ids": ["loc-a"]}])]
        return _R()

    monkeypatch.setattr("transversal.services.effects_commit.commit_effects", fake_commit_effects)

    class _FakeEm:
        def travel(self, entity_id, to_id, transversal_type=None, projection_policy=None):
            return entity.model_copy(update={"current_location": to_id})

    monkeypatch.setattr(locations_module, "_em", lambda: _FakeEm())

    app = FastAPI()
    app.include_router(locations_router)
    client = TestClient(app)

    r = client.post("/api/v1/locations/loc-a/portal/loc-a/fire", json={"entity_id": "char-1"})
    assert r.status_code == 200, r.text
    choice = r.json()["pendingChoices"][0]
    assert [c["id"] for c in choice["candidates"]] == ["loc-1"]
    assert choice["count"] == 1
    assert choice["structured"] is True
    assert choice["stepIndex"] == 2
    assert choice["answersSoFar"] == [{"stepIndex": 0, "ids": ["loc-a"]}]
    # The source is the **edge** — a portal question comes from the portal.
    assert choice["sourceKind"] == "relationship"
    assert choice["sourceId"] == "edge:loc-a:loc-a:transversal"
    # …and the effect is an input, not a domain dump.
    assert "dieFilter" in choice["effect"] and "die_filter" not in choice["effect"]
    assert "targetSpec" in choice["effect"]


def test_a_portal_question_is_broadcast_as_an_auto_choice(monkeypatch):
    """A portal is an **automatic** trigger, so its question goes to the splash.

    Nobody pressed a card — the traveller stepped through — and the client already
    decides where an automatic question lands (`origin="auto"` → the splash panel's
    picker). Emitting it means the portal needs no viewport-side wiring at all
    (the author's rule for this surface, 2026-10-17).
    """
    from transversal.api.rest.locations import _broadcast_pending_choices
    from transversal.domain import Effect
    from transversal.services.effects_applier.datatypes import PendingChoice

    captured = {}

    def fake_emit(entity_id, universe, effects, structured=None, loops=None, origin="roll"):
        captured.update(dict(entity=entity_id, universe=universe, effects=effects,
                             structured=structured or [], loops=loops or [],
                             origin=origin))

    monkeypatch.setattr("transversal.services.roll_orchestrator._emit_pending_choices", fake_emit)

    effect = Effect(timing=EffectTiming.IMMEDIATE, type="travel", action="move")
    pending = [PendingChoice(
        effect=effect, kind="location", field="refs.location",
        candidates=[{"id": "loc-1", "name": "Zurich Airport"}],
        count=1, structured=True, step_index=2)]
    _broadcast_pending_choices("char-1", "earth", pending,
                               {"_key": "edge:loc-a:loc-a:transversal"})

    assert captured["origin"] == "auto", "a portal question is not a roll question"
    assert captured["entity"] == "char-1"
    choice = captured["structured"][0]
    assert choice.element == "location"
    assert [c["id"] for c in choice.candidates] == ["loc-1"]
    assert choice.count == 1 and choice.step_index == 2
    # The source is the portal, so a follow-up knows where it came from.
    assert (choice.source_kind, choice.source_id) == (
        "relationship", "edge:loc-a:loc-a:transversal")


def test_a_portal_with_nothing_pending_broadcasts_nothing(monkeypatch):
    """No question, no event — an empty `sfx_choice_required` would open a blank picker."""
    from transversal.api.rest.locations import _broadcast_pending_choices

    called = []
    monkeypatch.setattr("transversal.services.roll_orchestrator._emit_pending_choices",
                        lambda *a, **k: called.append(a))
    _broadcast_pending_choices("char-1", "earth", [], {"_key": "edge"})
    assert called == []
