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
    Trait,
    TraitSetSetting,
    TraitSetting,
)
from transversal.services.effects_applier import apply_effects


class Repo:
    """A double covering what ``add_sfx_to_owner`` touches."""

    def __init__(self, sfxs=None, entities=None, traitsettings=None, traits=None):
        self.sfxs = {s.id: s for s in (sfxs or [])}
        self.entities = {e.id: e for e in (entities or [])}
        self.traitsettings = {t.id: t for t in (traitsettings or [])}
        self.traits = {t.id: t for t in (traits or [])}
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

    def get_trait(self, trait_id):
        return self.traits.get(trait_id)

    def update_trait(self, trait):
        # `_set_owner_sfx_ids` then propagates the default to holders; that walk
        # reads the instances of the trait, so the double answers it with none.
        self.writes.append(("trait", trait.id, list(trait.default_sfx_ids or [])))

    def get_traitsettings_by_trait(self, trait_id):
        return [t for t in self.traitsettings.values() if t.trait_id == trait_id]

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
        id=ts_id, entity_id=entity_id, trait_id="trait-power",
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


# ── The owner surfaces beyond an entity ([[B326]]) ───────
# `add_sfx_to_owner` has always known how to write all of them; what was missing
# was a way to *reach* them — the recipient reference declared `entity` only, so
# the wizard could not land on a trait, and the handler had no branch that would
# have recognised one anyway.

def _trait(trait_id="trait-power", default_sfx_ids=None):
    return Trait(id=trait_id, name="Power", traitset_id="ts-abilities",
                 default_sfx_ids=list(default_sfx_ids or []))


def _to_a_trait():
    """The path that reaches a trait **definition**: the instance's registry trait.

    This is what the wizard builds now that the recipient reference accepts it —
    `instance → trait` is a declared edge, so the rule can be attached to the
    definition rather than to one character who happens to hold it.
    """
    from transversal.services.target_spec import TargetSpec
    return TargetSpec(steps=[
        {"kind": "select", "collection": "self_traitsettings"},
        {"kind": "navigate", "edge": "trait"},
    ])


def test_a_rule_can_be_granted_to_a_trait_definition():
    """A trait's `defaultSfxIds` is the surface every holder of it is offered —
    the teacher case one level up: the rule is attached to the *definition*, not
    to one character who happens to have it."""
    entity = _entity()
    trait = _trait()
    repo = Repo(sfxs=[_rule()], entities=[entity],
                traitsettings=[_trait_instance()], traits=[trait])

    result = apply_effects(
        entity, [_grant(ref_value="sfx-teaching", entity_spec=_to_a_trait())], repo)

    assert trait.default_sfx_ids == ["sfx-teaching"]
    assert "granted" in result.applied[0].summary
    # Two writes, and both are the point: the definition gains the default, and
    # `add_sfx_to_owner` **propagates it to the instances that already exist** —
    # so a holder is offered the technique without being touched one by one.
    assert repo.writes == [
        ("trait", "trait-power", ["sfx-teaching"]),
        ("trait_instance", "char-1:trait-power", ["sfx-teaching"]),
    ]


def test_owner_surface_for_knows_a_trait_and_a_trait_set():
    """The two surfaces the handler did not have. A trait set instance is the
    *setting* (`entity:traitset`), not the set definition — that is what owns
    `sfxIds`."""
    from transversal.services.effects_applier.handlers_sfx import owner_surface_for

    assert owner_surface_for(_trait()) == ("trait", "trait-power")
    setting = TraitSetSetting(id="char-1:ts-abilities", entity_id="char-1",
                              traitset_id="ts-abilities")
    assert owner_surface_for(setting) == ("trait_set", "char-1:ts-abilities")


def test_a_bare_trait_id_is_resolved_by_asking_the_repo():
    """A path hands the handler an **id**, so the surface has to be recovered by
    asking. A trait is not an entity, which is why the getter order matters."""
    from transversal.services.effects_applier.handlers_sfx import _owner_for_subject

    repo = Repo(traits=[_trait()])
    assert _owner_for_subject(repo, "trait-power") == ("trait", "trait-power")


def test_the_grant_declares_every_owner_surface_it_can_write():
    """The declaration is what decides whether an author can *reach* a surface:
    the wizard's path builder stops at the elements a reference names."""
    from transversal.services.effects_registry.lookup import get_action_meta_for

    meta = get_action_meta_for("sfx", "grant")
    recipient = next(r for r in meta.refs if r.name == "recipient")
    assert set(recipient.elements) == {
        "entity", "location", "projection", "traitsetting", "traitsetsetting", "trait",
    }
    assert recipient.role == "entity"   # the positional field it still supersedes

def test_the_recipient_reference_reaches_a_trait_too():
    """The form the editor actually writes: a *named reference*, not the
    positional `entity` field. The reference resolves and writes itself back into
    `entity`, so the handler cannot tell which way it was authored — which is the
    point of one vocabulary ([[B261]])."""
    entity = _entity()
    trait = _trait()
    repo = Repo(sfxs=[_rule()], entities=[entity],
                traitsettings=[_trait_instance()], traits=[trait])
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="sfx", action="grant",
        refs={"sfx": TargetRef(name="sfx", value="sfx-teaching"),
              "recipient": TargetRef(name="recipient", spec=_to_a_trait())},
    )

    apply_effects(entity, [effect], repo)

    assert trait.default_sfx_ids == ["sfx-teaching"]
