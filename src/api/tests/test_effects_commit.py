"""Tests for commit_effects — persistence + broadcast of applied effects."""

from types import SimpleNamespace

from transversal.domain import (
    DieType,
    Effect,
    EffectTiming,
    Entity,
    EntityType,
    TraitSetting,
)
from transversal.services.effects_commit import commit_effects


class FakeTrait:
    def __init__(self, trait_id, traitset_id):
        self.id = trait_id
        self.traitset_id = traitset_id


class RecordingRepo:
    def __init__(self, traits=None, traitsettings=None, entities=None):
        self.traits = {t.id: t for t in (traits or [])}
        self.traitsettings = list(traitsettings or [])
        self.entities = {e.id: e for e in (entities or [])}
        self.created_traitsettings = []
        self.updated_traitsettings = []
        self.updated_entities = []
        self.created_relationships = []

    def get_trait(self, trait_id):
        return self.traits.get(trait_id)

    def get_traitset_by_id(self, traitset_id):
        return None

    def get_traitsettings_for_entity(self, entity_id):
        return [ts for ts in self.traitsettings if ts.entity_id == entity_id]

    def get_entity(self, entity_id):
        return self.entities.get(entity_id)

    def get_projections_for_entity(self, entity_id):
        # A travel effect's body pool falls back to the actor's bodies in the
        # destination universe — one body here, so the picker has something to
        # offer.
        if entity_id != "char-1":
            return []
        return [SimpleNamespace(id="char-1:earth", entity_id="char-1", universe="earth",
                                current_location=None, last_used_at="")]

    def update_entity(self, entity):
        self.updated_entities.append(entity.id)

    def create_traitsetting(self, ts):
        self.created_traitsettings.append(ts)

    def update_traitsetting(self, ts):
        self.updated_traitsettings.append(ts)

    def create_relationship(self, from_id, to_id, rel_type, description=""):
        self.created_relationships.append((from_id, to_id, rel_type, description))


def _entity(**overrides):
    kwargs = dict(id="char-1", type=EntityType.CHARACTER, name="Test", current_universe="earth")
    kwargs.update(overrides)
    return Entity(**kwargs)


def _effect(type, action, target="", result=None):
    return Effect(timing=EffectTiming.IMMEDIATE, type=type, action=action, target=target, result=result)


def test_commit_persists_gained_trait():
    repo = RecordingRepo(traits=[FakeTrait("iron-will", "ts-distinctions")])
    entity = _entity()
    result = commit_effects(entity, [_effect("modify_trait", "gain", "iron-will", "d6")], repo)
    assert len(result.applied) == 1
    assert len(repo.created_traitsettings) == 1
    assert repo.created_traitsettings[0].trait_id == "iron-will"
    assert "char-1" in repo.updated_entities


def test_commit_persists_razmerit_change():
    repo = RecordingRepo()
    entity = _entity(razmerit=5)
    result = commit_effects(entity, [_effect("transfer_razmerit", "earn", "self", "3")], repo)
    assert entity.razmerit == 8
    assert "char-1" in repo.updated_entities
    assert len(result.applied) == 1


def test_commit_persists_relationship():
    repo = RecordingRepo()
    entity = _entity()
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="relationship", action="create",
        target="char-2", result="ally", context={"description": "old friend"},
    )
    result = commit_effects(entity, [effect], repo)
    assert repo.created_relationships == [("char-1", "char-2", "ally", "old friend")]
    assert len(result.applied) == 1


def test_commit_apply_then_resolve_roundtrip():
    """The two-step flow the effect wizard uses: apply → pending → resolve → re-apply.

    A *target* choice is a path with a ``choose`` step and travels as a structured
    choice (see ``test_effects_engine``); what still defers through a pending
    choice is a context-policy pick like a travel effect's body.
    """
    from transversal.services.effects_applier import resolve_choice

    repo = RecordingRepo()
    entity = _entity()
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="travel", action="move",
        target="loc-x",
        context={"transversal_type": "consciousness", "projection": "{choose_projection}"},
    )

    # First pass: the body choice is recorded, nothing applied/persisted.
    result = commit_effects(entity, [effect], repo)
    assert len(result.pending_choices) == 1
    assert result.pending_choices[0].kind == "projection"
    assert result.pending_choices[0].field == "context.projection"

    # Second pass: resolve the choice to a concrete body and re-apply.
    resolved = resolve_choice(result.pending_choices[0], "char-1:earth")
    assert resolved.context["projection"] == "char-1:earth"


def test_trait_updated_context_names_the_instance_that_changed(monkeypatch):
    """`trait_updated` reaches the effects engine with the *setting* id.

    The SSE payload always carried it; the engine context dropped it, so an
    `on_trait_change` rule could see which registry trait changed but never which
    instance. That is fatal for a container whose children share one generic trait
    (an agenda's steps): with five portents there is no way to tell step 3 from
    step 5.
    """
    from types import SimpleNamespace

    from transversal.services import effects_commit as ec
    from transversal.services import scheduled_events as se

    captured = {}
    monkeypatch.setattr(ec, "resync_pool_dice_for_trait", lambda *a, **k: None)
    monkeypatch.setattr(ec, "_publish", lambda event, data: captured.setdefault("sse", (event, data)))
    monkeypatch.setattr(se, "dispatch_event",
                        lambda repo, event, **kw: captured.setdefault("dispatch", (event, kw)))

    ts = SimpleNamespace(id="e1:portent-3", entity_id="e1", trait_id="trait-portent",
                         traitset_id="ts-agenda", dice=[DieType.D6])
    ec._publish_trait_changed(ts, "earth")

    event, sse_data = captured["sse"]
    assert event == "trait_updated"
    assert sse_data["trait_setting_id"] == "e1:portent-3"

    event, kwargs = captured["dispatch"]
    assert event == "trait_updated"
    assert kwargs["context"]["trait_setting"] == "e1:portent-3"
    # The registry trait still rides along. `traitset` no longer does: a setting
    # records no set of its own ([[B200]]), it is not a declared context key for
    # this trigger, and no rule references `{traitset}`.
    assert kwargs["context"]["trait"] == "trait-portent"


def test_the_trait_change_trigger_declares_the_instance():
    """Declared, so the editor offers `{trait_setting}` and the engine binds it —
    a context key nobody declares is plumbing nobody can use."""
    from transversal.services.menu_contexts import trigger_variables

    names = {v.name for v in trigger_variables("on_trait_change")}
    assert {"trait", "traitset", "trait_setting"} <= names


def test_removing_a_trait_tells_clients(monkeypatch):
    """A removal had no broadcast at all, so a sheet already open kept rendering
    the trait an effect had taken away ([[B74]]).

    The event is the one the client already handles — `trait_updated` → refetch
    the sheet — with the dice emptied so the assembled pool drops its die too.
    """
    from transversal.services import effects_commit as ec

    captured = {}
    monkeypatch.setattr(ec, "resync_pool_dice_for_trait",
                        lambda eid, tid, dice: captured.setdefault("resync", (eid, tid, dice)))
    monkeypatch.setattr(ec, "_publish",
                        lambda event, data: captured.setdefault("sse", (event, data)))

    ts = SimpleNamespace(id="char-1:scar", entity_id="char-1", trait_id="trait-scar",
                         traitset_id="ts-x", dice=[DieType.D6])
    ec._publish_trait_removed(ts, "earth")

    event, data = captured["sse"]
    assert event == "trait_updated"
    assert data["trait_setting_id"] == "char-1:scar"
    assert data["new_dice"] == [] and data["new_rating"] is None
    assert data["removed"] is True
    # The pool's die for it goes with it.
    assert captured["resync"] == ("char-1", "char-1:scar", [])
