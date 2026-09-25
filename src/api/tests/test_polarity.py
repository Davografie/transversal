"""Tests for baked trait polarity defaults and propagation."""

from transversal.domain import Polarity, Trait, TraitSet, TraitSetting
from transversal.services.polarity import (
    default_polarity,
    propagate_trait_polarity,
    propagate_traitset_polarity,
)


def _trait(polarity=None):
    return Trait(id="trait-a", name="a", traitset_id="ts-1", universes=[], polarity=polarity)


def _traitset(polarity=None):
    return TraitSet(id="ts-1", name="ts", universes=[], polarity=polarity)


def _ts(trait_id="trait-a", polarity=Polarity.POSITIVE, id_suffix=""):
    return TraitSetting(
        id=f"e:{trait_id}{id_suffix}",
        entity_id="e",
        trait_id=trait_id,
        polarity=polarity,
    )


class FakeRepo:
    def __init__(self, settings_by_trait=None, traits_by_traitset=None):
        self._settings_by_trait = settings_by_trait or {}
        self._traits_by_traitset = traits_by_traitset or {}
        self.updated = []

    def get_traitsettings_by_trait(self, trait_id):
        return self._settings_by_trait.get(trait_id, [])

    def get_traits_by_traitset(self, traitset_id):
        return self._traits_by_traitset.get(traitset_id, [])

    def update_traitsetting(self, ts):
        self.updated.append(ts)


def test_default_polarity_chain():
    assert default_polarity(None, None) == Polarity.POSITIVE
    assert default_polarity(_trait(None), _traitset(None)) == Polarity.POSITIVE
    assert default_polarity(_trait(None), _traitset(Polarity.NEGATIVE)) == Polarity.NEGATIVE
    assert default_polarity(_trait(Polarity.POSITIVE), _traitset(Polarity.NEGATIVE)) == Polarity.POSITIVE
    assert default_polarity(_trait(Polarity.NEGATIVE), _traitset(Polarity.POSITIVE)) == Polarity.NEGATIVE


def test_propagate_trait_polarity_flips_inherited_settings():
    inherited = _ts(polarity=Polarity.NEGATIVE, id_suffix="-a")
    overridden = _ts(polarity=Polarity.POSITIVE, id_suffix="-b")
    repo = FakeRepo(settings_by_trait={"trait-a": [inherited, overridden]})

    changed = propagate_trait_polarity(
        repo, "trait-a", old_trait_polarity=None, new_trait_polarity=Polarity.POSITIVE,
        traitset_polarity=Polarity.NEGATIVE,
    )

    assert changed == 1
    assert inherited.polarity == Polarity.POSITIVE
    assert overridden.polarity == Polarity.POSITIVE  # unchanged
    assert repo.updated == [inherited]


def test_propagate_traitset_polarity_skips_trait_overrides():
    ts_a = _ts(polarity=Polarity.POSITIVE, id_suffix="-a")       # inherits set
    ts_a_neg = _ts(polarity=Polarity.NEGATIVE, id_suffix="-aneg")
    ts_b = _ts(trait_id="trait-b", polarity=Polarity.POSITIVE, id_suffix="-b")

    trait_a = Trait(id="trait-a", name="a", traitset_id="ts-1", universes=[], polarity=None)
    trait_b = Trait(id="trait-b", name="b", traitset_id="ts-1", universes=[], polarity=Polarity.NEGATIVE)

    repo = FakeRepo(
        settings_by_trait={"trait-a": [ts_a, ts_a_neg], "trait-b": [ts_b]},
        traits_by_traitset={"ts-1": [trait_a, trait_b]},
    )

    changed = propagate_traitset_polarity(
        repo, "ts-1", old_traitset_polarity=None, new_traitset_polarity=Polarity.NEGATIVE,
    )

    assert changed == 1
    assert ts_a.polarity == Polarity.NEGATIVE
    assert ts_a_neg.polarity == Polarity.NEGATIVE  # unchanged
    assert ts_b.polarity == Polarity.POSITIVE      # trait override shields it
    assert repo.updated == [ts_a]
