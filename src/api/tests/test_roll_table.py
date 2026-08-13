"""Tests for roll-table resolution and entry effect application."""

from transversal.domain import (
    DieType,
    Effect,
    EffectTiming,
    Entity,
    EntityType,
    OutcomeTier,
    RollTable,
    RollTableEntry,
    RollTableScheme,
)
from transversal.services.effects_applier import apply_effects
from transversal.services.roll_table import resolve_table


def _table(scheme, entries, **overrides):
    kwargs = dict(id="tbl-1", name="Test", universe="earth", scheme=scheme)
    kwargs.update(overrides)
    return RollTable(entries=entries, **kwargs)


def _entry(**overrides):
    return RollTableEntry(**overrides)


# ── Selection schemes ────────────────────────────────

def test_range_selects_entry():
    table = _table(
        RollTableScheme.RANGE,
        [
            _entry(label="low", min_value=1, max_value=5),
            _entry(label="high", min_value=6, max_value=10),
        ],
    )
    assert resolve_table(table, roll=7).label == "high"


def test_range_no_match():
    table = _table(
        RollTableScheme.RANGE,
        [_entry(label="low", min_value=1, max_value=5)],
    )
    assert resolve_table(table, roll=9) is None


def test_index_selects_by_roll():
    table = _table(
        RollTableScheme.INDEX,
        [_entry(label="first"), _entry(label="second"), _entry(label="third")],
    )
    assert resolve_table(table, roll=2).label == "second"


def test_tier_selects_entry():
    table = _table(
        RollTableScheme.TIER,
        [
            _entry(label="fail", tier=OutcomeTier.FAIL),
            _entry(label="win", tier=OutcomeTier.SUCCESS),
        ],
    )
    assert resolve_table(table, tier=OutcomeTier.SUCCESS).label == "win"


def test_weight_cumulative():
    table = _table(
        RollTableScheme.WEIGHT,
        [
            _entry(label="rare", weight=1),
            _entry(label="common", weight=3),
        ],
    )
    assert resolve_table(table, roll=1).label == "rare"
    assert resolve_table(table, roll=4).label == "common"


def test_manual_index_wins():
    table = _table(
        RollTableScheme.RANGE,
        [
            _entry(label="low", min_value=1, max_value=5),
            _entry(label="high", min_value=6, max_value=10),
        ],
    )
    # Manual click on the second row overrides a roll that would select the first.
    assert resolve_table(table, roll=2, index=2).label == "high"


# ── Entry effects resolve through apply_effects ───────

class FakeTrait:
    def __init__(self, trait_id, traitset_id):
        self.id = trait_id
        self.traitset_id = traitset_id


class FakeRepo:
    def __init__(self, traits=None):
        self.traits = {t.id: t for t in (traits or [])}

    def get_trait(self, trait_id):
        return self.traits.get(trait_id)

    def get_traitsettings_for_entity(self, entity_id):
        return []


def test_entry_effects_apply():
    effect = Effect(
        timing=EffectTiming.IMMEDIATE,
        type="modify_trait", action="gain", target="iron-will", result="d6",
    )
    table = _table(
        RollTableScheme.INDEX,
        [_entry(label="reward", effects=[effect])],
    )
    entry = resolve_table(table, roll=1)
    assert entry is not None

    entity = Entity(id="char-1", type=EntityType.CHARACTER, name="Kael", current_universe="earth")
    repo = FakeRepo(traits=[FakeTrait("iron-will", "ts-distinctions")])
    result = apply_effects(entity, entry.effects, repo)

    assert len(result.new_trait_settings) == 1
    assert result.new_trait_settings[0].trait_id == "iron-will"
    assert result.new_trait_settings[0].dice == [DieType.D6]
