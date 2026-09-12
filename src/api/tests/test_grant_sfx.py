"""The `Grant SFX` effect — a rule can be handed to an owner.

This is the teacher case: a place's rule grants a technique to whatever the
effect's subject resolves to (an entity, or a trait instance reached by a path),
instead of the rule offering itself to a selection.
"""

from types import SimpleNamespace

from transversal.domain import (
    Effect,
    EffectTiming,
    Entity,
    EntityType,
    RatingType,
    TargetRef,
    TraitSetting,
)
from transversal.services.effects_applier import apply_effects


class Repo:
    """A double covering what ``add_sfx_to_owner`` touches."""

    def __init__(self, sfxs=None, entities=None, traitsettings=None):
        self.sfxs = {s.id: s for s in (sfxs or [])}
        self.entities = {e.id: e for e in (entities or [])}
        self.traitsettings = {t.id: t for t in (traitsettings or [])}
        self.writes = []

    def get_sfx(self, sfx_id):
        return self.sfxs.get(sfx_id)

    def get_all_sfxs(self):
        return list(self.sfxs.values())

    def get_entity(self, entity_id):
        return self.entities.get(entity_id)

    def get_traitsetting(self, ts_id):
        return self.traitsettings.get(ts_id)

    def update_entity(self, entity):
        self.writes.append(("entity", entity.id, list(entity.sfx_ids or [])))

    def update_traitsetting(self, ts):
        self.writes.append(("trait_instance", ts.id, list(ts.sfx_ids or [])))

    def get_traitsettings_for_entity(self, entity_id):
        return [t for t in self.traitsettings.values() if t.entity_id == entity_id]


def _rule(sfx_id="sfx-teaching", source_kind=None, acquire_spec=None):
    return SimpleNamespace(id=sfx_id, name=sfx_id, source_kind=source_kind,
                           acquire_spec=acquire_spec)


def _entity(eid="char-1", etype=EntityType.CHARACTER, sfx_ids=None, location=None):
    return Entity(id=eid, type=etype, name=eid, current_universe="earth",
                  sfx_ids=list(sfx_ids or []), current_location=location)


def _trait_instance(ts_id="char-1:trait-power", entity_id="char-1", sfx_ids=None):
    return TraitSetting(
        id=ts_id, entity_id=entity_id, trait_id="trait-power", traitset_id="ts-attributes",
        rating_type=RatingType.STATIC, dice=[],
        sfx_ids=list(sfx_ids or []),
    )


def _grant(ref_value="sfx-teaching", entity_spec=None):
    return Effect(
        timing=EffectTiming.IMMEDIATE, type="sfx", action="grant",
        entity="", refs={"sfx": TargetRef(name="sfx", value=ref_value)},
        entity_spec=entity_spec,
    )


def _on_self_trait_instance():
    """The subject path that reaches a trait instance rather than an entity —
    what the author picks in the wizard for the sect-training case."""
    from transversal.services.target_spec import TargetSpec
    return TargetSpec(steps=[{"kind": "select", "collection": "self_traitsettings"}])


def test_grant_lands_the_rule_on_the_subject_entity():
    entity = _entity()
    repo = Repo(sfxs=[_rule()], entities=[entity])

    result = apply_effects(entity, [_grant()], repo)

    assert entity.sfx_ids == ["sfx-teaching"]
    assert result.applied[0].summary == "granted sfx-teaching"


def test_grant_can_land_on_a_trait_instance():
    """The sect-training case: the technique goes onto the trait it is studied on.

    Reached through the effect's *subject path*, not by naming the instance — the
    reason the wizard half of this action matters.
    """
    entity = _entity()
    ts = _trait_instance()
    repo = Repo(sfxs=[_rule()], entities=[entity], traitsettings=[ts])

    apply_effects(entity, [_grant(entity_spec=_on_self_trait_instance())], repo)

    assert ts.sfx_ids == ["sfx-teaching"]
    assert repo.writes == [("trait_instance", "char-1:trait-power", ["sfx-teaching"])]


def test_grant_is_idempotent():
    entity = _entity(sfx_ids=["sfx-teaching"])
    repo = Repo(sfxs=[_rule()], entities=[entity])

    result = apply_effects(entity, [_grant()], repo)

    assert entity.sfx_ids == ["sfx-teaching"]
    assert result.applied[0].summary == "granted sfx-teaching"


def test_grant_obeys_the_surface_a_rule_declares():
    """A rule sourced on a location may not be granted to a character — the same
    refusal an attach gives, not a back door around it."""
    entity = _entity()
    repo = Repo(sfxs=[_rule(source_kind="location")], entities=[entity])

    result = apply_effects(entity, [_grant()], repo)

    assert entity.sfx_ids == []
    assert "can't attach to entity" in result.applied[0].summary


def test_a_location_subject_keeps_being_a_place():
    """An entity whose type is LOCATION attaches as the *location* surface, not
    as a plain entity — otherwise the rule's declared source would refuse it."""
    home = _entity("loc-1", EntityType.LOCATION)
    repo = Repo(sfxs=[_rule(source_kind="location")], entities=[home])

    apply_effects(home, [_grant()], repo)

    assert home.sfx_ids == ["sfx-teaching"]


def test_grant_with_no_rule_named_says_so():
    entity = _entity()
    repo = Repo(entities=[entity])

    result = apply_effects(entity, [_grant(ref_value="")], repo)

    assert entity.sfx_ids == []
    assert result.applied[0].summary == "no SFX to grant"
