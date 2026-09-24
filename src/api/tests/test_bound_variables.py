"""Declared bound variables — named before the gate, read everywhere after.

The author's ask, authoring *Cultivation Stage*: "increase the dicepool total
limit by the tier of this rating", so the five effects they wrote by hand (one
per rating band, each gated to that band and carrying a literal `1`…`5`) collapse
to one. That needs the name to exist **before the condition gate** — which is
precisely what the inline 💡 (`TargetStep.output`) cannot do: it binds as a side
effect of a path authored for another purpose, so nothing can read it earlier.

Two halves are pinned here: the *scope* (`bind_declared` fills the activation's
one bindings dict, in declaration order, refusing to shadow a name the engine
already owns) and the *use* (a `{name}` reaches an effect's amount, and a path
may `select variable` an element-valued name).
"""

from types import SimpleNamespace as NS

from transversal.domain import (
    BoundVariable,
    Effect,
    EffectTiming,
    Entity,
    EntityType,
    SFX,
    TargetSpec,
)
from transversal.services.effects_engine import EffectsEngine, GameEvent
from transversal.services.effects_engine.firing import bind_declared
from transversal.services.target_resolver import Binding
from transversal.services.target_spec import ValueType, trace

# ── The author's path: the source's rating, cast to its tier ──────────

STAGE_TIER = TargetSpec(steps=[
    {"kind": "select", "collection": "source"},
    {"kind": "aggregate", "fn": "tier", "field": "rating"},
])


class CultivationRepo:
    """One character with one rated trait instance — the rule's source."""

    def __init__(self, rating="d8"):
        self.entity = Entity(id="kael", type=EntityType.CHARACTER, name="Kael",
                             current_universe="earth", current_location="loc-1")
        self.ts = NS(id="kael:spiritual-power", trait_id="trait-qi",
                     traitset_id="ts-cultivation", entity_id="kael",
                     projection_id=None, rating=rating, enabled=True)
        self.updated_entities = []

    def get_entity(self, eid):
        return self.entity if eid == "kael" else None

    def get_traitsetting(self, ts_id):
        return self.ts if ts_id == self.ts.id else None

    def get_trait(self, tid):
        return None

    def get_effective_traitsettings(self, entity_id, universes=None):
        return [self.ts] if entity_id == "kael" else []

    def list_member_factions_with_sfx(self, entity_id):
        return []

    def list_member_factions_with_sfx_bulk(self, entity_ids):
        return {}

    def update_entity(self, entity):
        self.updated_entities.append(entity.id)


def cultivation_sfx(**overrides) -> SFX:
    """The rule the author wants to write: one effect, the amount named."""
    kwargs = dict(
        id="sfx-qi-condensation", name="Cultivation Stage",
        trigger="on_roll", source_kind="trait_setting",
        bound_variables=[BoundVariable(name="stage_tier", spec=STAGE_TIER)],
        effects=[Effect(
            timing=EffectTiming.IMMEDIATE, type="testbv", action="record",
            result="{stage_tier}", context={"limit": "total"},
        )],
    )
    kwargs.update(overrides)
    return SFX(**kwargs)


def _spy():
    """Record what each effect carried *after* substitution."""
    from transversal.services.effects_applier import effect_registry

    seen = []
    effect_registry.register("testbv", "record",
                             lambda a, _eid, _u, _ctx: seen.append(a.result))
    return seen


def _event(context=None):
    return GameEvent(type="on_roll", entity_id="kael", universe="earth",
                     context={"source_id": "kael:spiritual-power", **(context or {})})


def _fire(sfx, repo=None):
    engine = EffectsEngine()
    engine.register(sfx)
    seen = _spy()
    engine.process_event_outcome(_event(), [sfx.id], 0, repo=repo or CultivationRepo())
    return seen


# ── The amount is the tier ────────────────────────────────────

def test_the_declared_variable_reaches_the_amount():
    """d8 → 3. Not 8 (the die's side count, which is what the rest of the system
    would have made of the same rating) and not 1 (the applier's fallback when a
    token arrives unsubstituted) — a wrong number either way, and invisible."""
    assert _fire(cultivation_sfx()) == ["3"]


def test_every_rung_reaches_the_amount():
    for rating, expected in (("d4", "1"), ("d6", "2"), ("d8", "3"),
                             ("d10", "4"), ("d12", "5")):
        assert _fire(cultivation_sfx(), CultivationRepo(rating)) == [expected], rating


def test_the_amount_lands_on_the_entity():
    """The far end of the chain: what the handler does with the substituted
    amount. `commit_effects` is the same path play uses."""
    from transversal.services.effects_commit import commit_effects

    repo = CultivationRepo()
    effect = Effect(timing=EffectTiming.IMMEDIATE, type="modify_dice_limit",
                    action="increase", result="3", context={"limit": "total"})
    commit_effects(repo.entity, [effect], repo)
    assert repo.entity.total_dice_bonus == 3


# ── The scope ─────────────────────────────────────────────────

def test_a_later_variable_may_start_from_an_earlier_one():
    """Declaration order is the dependency: `stage` names the instance, and the
    tier is read *from* it. The whole point of a section above the conditions is
    that later rows can use earlier ones."""
    sfx = cultivation_sfx(bound_variables=[
        BoundVariable(name="stage", spec=TargetSpec(steps=[
            {"kind": "select", "collection": "source"},
        ])),
        BoundVariable(name="stage_tier", spec=TargetSpec(steps=[
            {"kind": "select", "collection": "variable", "variable": "stage"},
            {"kind": "aggregate", "fn": "tier", "field": "rating"},
        ])),
    ])
    assert _fire(sfx) == ["3"]


def test_a_path_naming_nothing_leaves_the_name_unbound():
    """An empty rating must not bind `""` — for every reader, "no value" and "no
    such name" are the same state, and a blank id would resolve a downstream path
    to a stranger."""
    repo = CultivationRepo(rating="")
    bindings: dict = {}
    bind_declared(cultivation_sfx(), bindings, _event(), repo,
                  source_id="kael:spiritual-power", source_element="traitsetting")
    assert "stage_tier" not in bindings


def test_a_declared_name_binds_its_value_and_type():
    bindings: dict = {}
    bind_declared(cultivation_sfx(), bindings, _event(), CultivationRepo("d10"),
                  source_id="kael:spiritual-power", source_element="traitsetting")
    bound = bindings["stage_tier"]
    assert (bound.value, bound.element, bound.cardinality) == ("4", "int", "one")


def test_a_declared_name_may_not_shadow_the_engines_own():
    """`{order}` and the source token are what `select source` and the source
    scalars already mean. A declared variable that overwrote one would silently
    change what an existing path reads."""
    bindings = {"order": Binding(value="7", values=["7"], element="int", cardinality="one")}
    sfx = cultivation_sfx(bound_variables=[
        BoundVariable(name="order", spec=STAGE_TIER),
    ])
    bind_declared(sfx, bindings, _event(), CultivationRepo("d12"),
                  source_id="kael:spiritual-power", source_element="traitsetting")
    assert bindings["order"].value == "7"


def test_every_declared_variable_is_typed_for_the_builder():
    """What the wizard will offer: an `int` a filter can compare and an amount can
    use. The type comes from the same catalogue the trace reads, so a declared
    variable is typed exactly as the path that produced it."""
    types, errors = trace(STAGE_TIER, source_element="traitsetting")
    assert errors == []
    assert types[-1] == ValueType("int", "one")
