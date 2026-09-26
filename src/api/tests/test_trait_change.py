"""Changing a trait instance's definition — the one operation behind both callers.

The sheet's trait editor and the ``change_trait`` effect action share
``services.trait_change.repoint_trait_setting``. These tests pin the rules that
function owns, so neither caller can drift away from them:

- the instance keeps everything that is its own and changes what it *is*;
- its set follows the new definition;
- a container may only become another container;
- a definition the owner already holds is not a legal destination;
- an unknown definition and an unchanged instance are no-ops, not errors —
  a timed revert has to be allowed to land on the value it is restoring.

Pure unit tests over a fake repository: no Arango, so they run everywhere.
"""

import pytest

from transversal.domain import CONTAINER_TAG, DieType, TraitSetting
from transversal.services.trait_change import (
    TraitChangeError,
    TraitChangeRefused,
    is_container_trait,
    repoint_trait_setting,
)


class FakeTrait:
    def __init__(self, trait_id, traitset_id="ts-x", name=None, tags=None):
        self.id = trait_id
        self.traitset_id = traitset_id
        self.name = name or trait_id
        self.tags = list(tags or [])


class FakeTraitset:
    def __init__(self, traitset_id, allow_duplicates=False):
        self.id = traitset_id
        self.allow_duplicates = allow_duplicates


class FakeRepo:
    """Only what the repoint needs — the point is that the operation is small."""

    def __init__(self, traits=(), traitsets=(), traitsettings=()):
        self.traits = {t.id: t for t in traits}
        self.traitsets = {t.id: t for t in traitsets}
        self.traitsettings = list(traitsettings)

    def get_trait(self, trait_id):
        return self.traits.get(trait_id)

    def get_traitset_by_id(self, traitset_id):
        return self.traitsets.get(traitset_id)

    def find_traitsetting_collision(self, entity_id, trait_id, statement="", allow_duplicates=False):
        """The *instance* question — kept because the effects path asks it."""
        existing = [ts for ts in self.traitsettings
                    if ts.entity_id == entity_id and ts.trait_id == trait_id]
        if not existing:
            return None
        if not allow_duplicates:
            return existing[0]
        return next((ts for ts in existing if (ts.statement or "") == (statement or "")), None)

    def may_hold_another(self, entity_id, trait_id, allow_duplicates=False):
        """The *set* question — what the repoint and the create path ask."""
        if allow_duplicates:
            return True
        return not [ts for ts in self.traitsettings
                    if ts.entity_id == entity_id and ts.trait_id == trait_id]


def _setting(trait_id, **overrides):
    kwargs = dict(
        id="char-1:" + trait_id,
        entity_id="char-1",
        trait_id=trait_id,
        traitset_id="ts-old",
        dice=[DieType.D8],
        statement="my blade",
        notes="gm only",
        tags=["mine"],
        sfx_ids=["sfx-keen"],
    )
    kwargs.update(overrides)
    return TraitSetting(**kwargs)


# ── What the instance keeps ──────────────────────────────────────────

def test_the_instance_keeps_what_is_its_own():
    """The whole point of the move: it changes what the instance *is*, not what it
    has. Every one of these fields is the instance's, and a repoint that dropped
    any of them would silently destroy a player's state."""
    repo = FakeRepo(traits=[FakeTrait("trait-blade", "ts-weapons"),
                            FakeTrait("trait-fire-blade", "ts-elements")])
    ts = _setting("trait-blade")
    change = repoint_trait_setting(ts, "trait-fire-blade", repo)

    assert change.changed
    assert change.was_trait_id == "trait-blade"
    assert change.is_trait_id == "trait-fire-blade"
    assert ts.entity_id == "char-1"
    assert ts.dice == [DieType.D8]
    assert ts.statement == "my blade"
    assert ts.notes == "gm only"
    assert ts.tags == ["mine"]
    assert ts.sfx_ids == ["sfx-keen"]


def test_the_set_follows_the_definition():
    """An instance that kept the old set would point at a trait that is not in it."""
    repo = FakeRepo(traits=[FakeTrait("trait-blade", "ts-weapons"),
                            FakeTrait("trait-fire-blade", "ts-elements")])
    ts = _setting("trait-blade", traitset_id="ts-weapons")
    change = repoint_trait_setting(ts, "trait-fire-blade", repo)

    # Nothing is copied onto the setting any more ([[B200]]): the set follows
    # because the pointer moved, and is read through the trait from then on.
    assert ts.trait_id == "trait-fire-blade"
    assert change.was_traitset_id == "ts-weapons"
    assert change.is_traitset_id == "ts-elements"
    assert change.traitset_moved


def test_relationship_anchored_instances_change_the_same_way():
    """A relationship's trait is anchored by its edge key, and repointing it is the
    same operation — the anchor is not the function's business, only the definition
    is. This is the guarantee that the two write paths stay homogeneous."""
    repo = FakeRepo(traits=[FakeTrait("trait-bond", "ts-relations"),
                            FakeTrait("trait-debt", "ts-relations")])
    ts = _setting("trait-bond", id="rel-9:trait-bond", entity_id="rel-9",
                  from_type="relationship", traitset_id="ts-relations")
    change = repoint_trait_setting(ts, "trait-debt", repo)

    assert change.changed
    assert ts.trait_id == "trait-debt"
    assert ts.from_type == "relationship"
    assert ts.entity_id == "rel-9"


# ── The two no-ops ───────────────────────────────────────────────────

def test_an_unknown_definition_is_a_no_op_not_an_error():
    """A revert must be able to land on a definition, and a caller's reference may
    name one that has since been deleted — that is reported, not raised."""
    repo = FakeRepo()
    ts = _setting("trait-blade")
    change = repoint_trait_setting(ts, "trait-gone", repo)

    assert not change.changed
    assert change.reason == "missing"
    assert change.requested_trait_id == "trait-gone"
    assert ts.trait_id == "trait-blade"


def test_repointing_to_the_same_definition_is_a_no_op():
    repo = FakeRepo(traits=[FakeTrait("trait-blade")])
    ts = _setting("trait-blade")
    change = repoint_trait_setting(ts, "trait-blade", repo)

    assert not change.changed
    assert change.reason == "already"
    assert ts.trait_id == "trait-blade"


# ── The container rule ───────────────────────────────────────────────

def test_a_container_may_only_change_into_another_container():
    repo = FakeRepo(traits=[
        FakeTrait("trait-roots", tags=[CONTAINER_TAG]),
        FakeTrait("trait-agenda", tags=[CONTAINER_TAG]),
        FakeTrait("trait-portents"),
    ])
    ts = _setting("trait-roots")

    # container → container is allowed
    change = repoint_trait_setting(ts, "trait-agenda", repo)
    assert change.changed

    # container → ordinary is refused
    with pytest.raises(TraitChangeRefused):
        repoint_trait_setting(ts, "trait-portents", repo)
    assert ts.trait_id == "trait-agenda", "a refused change must not half-apply"


def test_an_ordinary_trait_may_not_become_a_container():
    """The mirror of the rule: a trait cannot gain contents it was never given."""
    repo = FakeRepo(traits=[FakeTrait("trait-portents"),
                            FakeTrait("trait-roots", tags=[CONTAINER_TAG])])
    ts = _setting("trait-portents")

    with pytest.raises(TraitChangeRefused):
        repoint_trait_setting(ts, "trait-roots", repo)
    assert ts.trait_id == "trait-portents"


def test_a_container_may_be_recognised_by_its_instance_tag():
    """The frontend unions the instance's own tags with the definition's, so an
    instance tagged in place is a container there — the rule has to agree, or the
    editor would offer a change the write path refuses."""
    repo = FakeRepo(traits=[FakeTrait("trait-roots", tags=[CONTAINER_TAG]),
                            FakeTrait("trait-agenda", tags=[CONTAINER_TAG]),
                            FakeTrait("trait-portents")])
    ts = _setting("trait-portents", tags=[CONTAINER_TAG])

    change = repoint_trait_setting(ts, "trait-agenda", repo)
    assert change.changed

    with pytest.raises(TraitChangeRefused):
        repoint_trait_setting(ts, "trait-portents", repo)


def test_is_container_trait_reads_the_registry_tags():
    assert is_container_trait(FakeTrait("t", tags=[CONTAINER_TAG]))
    assert not is_container_trait(FakeTrait("t", tags=["violent"]))
    assert not is_container_trait(FakeTrait("t"))


# ── Collisions ───────────────────────────────────────────────────────

def test_a_definition_the_owner_already_holds_is_refused():
    """Otherwise the repoint silently produces a twin — two rows claiming the same
    trait, which the set's one-per-trait rule exists to prevent."""
    held = _setting("trait-fire-blade", id="char-1:trait-fire-blade")
    repo = FakeRepo(
        traits=[FakeTrait("trait-blade", "ts-weapons"),
                FakeTrait("trait-fire-blade", "ts-elements")],
        traitsets=[FakeTraitset("ts-weapons"), FakeTraitset("ts-elements")],
        traitsettings=[held],
    )
    ts = _setting("trait-blade")

    with pytest.raises(TraitChangeError):
        repoint_trait_setting(ts, "trait-fire-blade", repo)
    assert ts.trait_id == "trait-blade"


def test_a_duplicate_allowing_set_takes_any_number():
    """A set that allows duplicates permits the repoint **however many** instances
    it already holds, and whatever their statements say.

    The statement used to *be* a duplicate's identity, so a matching one collided.
    It is not any more (the human, 2026-09-25): the set is what decides, and a
    duplicate needs no distinguishing text — so both the same statement and a
    different one are legal, and only a one-per-trait set refuses."""
    held = _setting("trait-fire-blade", id="char-1:trait-fire-blade", statement="other")
    repo = FakeRepo(
        traits=[FakeTrait("trait-blade", "ts-weapons"),
                FakeTrait("trait-fire-blade", "ts-elements")],
        traitsets=[FakeTraitset("ts-elements", allow_duplicates=True)],
        traitsettings=[held],
    )

    # Different statement → legal
    ts = _setting("trait-blade", statement="my blade")
    assert repoint_trait_setting(ts, "trait-fire-blade", repo).changed

    # The *same* statement → also legal; this is the case that used to be refused.
    other = _setting("trait-blade", id="char-1:trait-blade-2", statement="other")
    assert repoint_trait_setting(other, "trait-fire-blade", repo).changed


def test_a_definition_held_by_another_owner_does_not_collide():
    """The rule is per owner — another character holding the definition says
    nothing about this one."""
    elsewhere = _setting("trait-fire-blade", id="char-2:trait-fire-blade",
                         entity_id="char-2")
    repo = FakeRepo(
        traits=[FakeTrait("trait-blade", "ts-weapons"),
                FakeTrait("trait-fire-blade", "ts-elements")],
        traitsets=[FakeTraitset("ts-elements")],
        traitsettings=[elsewhere],
    )
    ts = _setting("trait-blade")

    assert repoint_trait_setting(ts, "trait-fire-blade", repo).changed


def test_the_instance_does_not_collide_with_itself():
    """The instance being repointed is not a duplicate of itself, whatever its set
    says about duplicates."""
    repo = FakeRepo(
        traits=[FakeTrait("trait-blade", "ts-weapons"),
                FakeTrait("trait-fire-blade", "ts-elements")],
        traitsets=[FakeTraitset("ts-elements")],
        traitsettings=[],
    )
    ts = _setting("trait-blade")
    repo.traitsettings.append(ts)

    assert repoint_trait_setting(ts, "trait-fire-blade", repo).changed
