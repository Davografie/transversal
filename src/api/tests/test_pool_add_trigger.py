"""``on_pool_add`` — "the trait this rule lives on was just added".

The author's ask: *"to prevent checking too many SFX every time the pool changes,
it would make more sense to have the trigger 'on added to pool', extending the
source, so the SFX only triggers when **this** trait setting is added to the
pool."*

That is what this is: a trigger *about its source*. A rule on a fire technique
does not care about every pool save — it cares about its own arrival — so the
fact is decided structurally (before the conditions, which is the point) instead
of being one more path to evaluate on every change. The dice are the `added_dice`
seed, read from this rule's point of view, so the effect needs no filter either —
and a `2d8` trait instance brings two of them.
"""

from types import SimpleNamespace as NS

from transversal.domain import (
    Condition,
    ConditionType,
    Effect,
    EffectTiming,
    Entity,
    EntityType,
    SFX,
    TargetSpec,
)
from transversal.services import scene_state as ss_module
from transversal.services.effects_engine import EffectsEngine, GameEvent
from transversal.services.scene_state import SceneStateStore


class Repo:
    def __init__(self):
        self.entities = {
            "kael": Entity(id="kael", name="Kael", type=EntityType.CHARACTER,
                           current_location="loc-1", current_universe="earth"),
        }
        self.traitsettings = {
            "kael:fire-palm": NS(id="kael:fire-palm", trait_id="trait-fire-palm",
                                 traitset_id="ts-tech", entity_id="kael", projection_id=None,
                                 rating="d8", tags=[], sfx_ids=[]),
            "kael:iron-bark": NS(id="kael:iron-bark", trait_id="trait-iron-bark",
                                 traitset_id="ts-tech", entity_id="kael", projection_id=None,
                                 rating="d6", tags=[], sfx_ids=[]),
        }
        self.traits = {
            "trait-fire-palm": NS(id="trait-fire-palm", traitset_id="ts-tech", tags=["fire"]),
            "trait-iron-bark": NS(id="trait-iron-bark", traitset_id="ts-tech", tags=["wood"]),
        }

    def get_entity(self, eid):
        return self.entities.get(eid)

    def update_entity(self, entity):
        self.entities[entity.id] = entity
        return entity

    def get_traitsetting(self, ts_id):
        return self.traitsettings.get(ts_id)

    def get_trait(self, tid):
        return self.traits.get(tid)

    def get_effective_traitsettings(self, entity_id, universes=None):
        return [ts for ts in self.traitsettings.values() if ts.entity_id == entity_id]


def _register_like_startup(repo):
    from transversal.services.effects_applier import registry as applier_registry

    class _EM:
        pass

    em = _EM()
    em.repo = repo
    applier_registry._register_core_handlers(em, None)


def die(ts_id, rating="d8", index=0):
    return {"die": rating, "ts_id": ts_id, "source_kind": "trait",
            "pool_location": "loc-1", "pool_owner": "kael", "pool_index": index}


def sfx(target_steps=None) -> SFX:
    """The rule: *when this trait is added, step the dice it brought down.*

    No filter, and no singular token: `added_dice` is read from this rule's own
    point of view, and a trait instance can contribute more than one die.
    """
    return SFX(
        id="sfx-on-add", name="On Add Probe", trigger="on_pool_add", source_kind="trait_setting",
        effects=[Effect(timing=EffectTiming.IMMEDIATE, type="modify_roll", action="step_down_die",
                        target="", target_spec=TargetSpec(steps=target_steps or [
                            {"kind": "select", "collection": "added_dice"}]))],
    )


def run(added, pool, target_steps=None):
    repo = Repo()
    _register_like_startup(repo)
    ss_module._store = SceneStateStore()
    ss_module._store.save_pool("loc-1", "kael", pool)
    engine = EffectsEngine()
    engine.register(sfx(target_steps))
    event = GameEvent(type="pool_changed", entity_id="kael", universe="earth",
                      context={"source_id": "kael:fire-palm", "dice_pool": "pool:kael",
                               "rolls": pool, "added_dice": added,
                               "contest_entity_opponent": "guard-1"})
    engine.process_event_outcome(event, ["sfx-on-add"], 0, repo=repo)
    return ss_module._store


def teardown_function(_fn):
    ss_module._store = SceneStateStore()


# ── It fires for its own trait, and only its own ───────────────────────

def test_it_fires_when_its_own_trait_was_added():
    fire = die("kael:fire-palm", "d8", index=1)
    store = run([fire], [{"die": "d6", "ts_id": None, "source_kind": "manual"}, fire])
    assert [d["die"] for d in store.get_pool("loc-1", "kael")] == ["d6", "d6"]


def test_it_does_not_fire_when_a_different_trait_was_added():
    """The whole point: another technique arriving is not this rule's business,
    and nothing about it is evaluated."""
    other = die("kael:iron-bark", "d6")
    store = run([other], [other])
    assert store.get_pool("loc-1", "kael")[0]["die"] == "d6"


def test_it_takes_the_dice_of_its_own_trait_when_several_arrive():
    """A save can add more than one die — including *two from the same trait*,
    which is what a `2d8` rating does. `added_dice` is that trait's dice, so the
    effect needs no filter to hit exactly them."""
    fire_a = die("kael:fire-palm", "d8", index=0)
    fire_b = die("kael:fire-palm", "d8", index=1)
    other = die("kael:iron-bark", "d6", index=2)
    store = run([fire_a, fire_b, other], [fire_a, fire_b, other])
    # Both fire dice came down; the other technique's die is untouched.
    assert [d["die"] for d in store.get_pool("loc-1", "kael")] == ["d6", "d6", "d6"]


def test_a_2d8_trait_instance_brings_two_dice_and_both_are_taken():
    """The author's correction: a trait instance can be `2d8`, so the seed is a
    *list* — a singular binding would have stepped one of the two down and left
    the other standing."""
    one = die("kael:fire-palm", "d10", index=0)
    two = die("kael:fire-palm", "d10", index=1)
    store = run([one, two], [one, two])
    assert [d["die"] for d in store.get_pool("loc-1", "kael")] == ["d8", "d8"]


def test_an_unresolved_source_never_fires():
    """No home means it cannot have been added — the honest answer rather than
    firing on any pool change."""
    repo = Repo()
    _register_like_startup(repo)
    ss_module._store = SceneStateStore()
    fire = die("kael:fire-palm", "d8")
    ss_module._store.save_pool("loc-1", "kael", [fire])
    engine = EffectsEngine()
    engine.register(sfx())
    # No `source_id` in the context, and the ownership fallback finds nothing.
    event = GameEvent(type="pool_changed", entity_id="kael", universe="earth",
                      context={"rolls": [fire], "added_dice": [fire]})
    engine.process_event_outcome(event, ["sfx-on-add"], 0, repo=Repo())
    assert ss_module._store.get_pool("loc-1", "kael")[0]["die"] == "d8"


# ── The declaration ────────────────────────────────────────────────────

def test_the_trigger_says_which_sources_it_can_work_with():
    """It is about its source, so a source kind that has no such thing would make
    it a gate that can never pass — declared, so the editor can grey it out."""
    from transversal.services.menu_contexts import trigger_card, trigger_variables
    from transversal.services.menu_contexts import TRIGGERS

    meta = next(t for t in TRIGGERS if t.value == "on_pool_add")
    assert meta.requires_source_elements == ("traitsetting",)
    assert trigger_card("on_pool_add") == "When this trait is added to your dice pool"
    # No singular `{added_die}`: the dice are the `added_dice` collection, plural.
    assert [v.name for v in trigger_variables("on_pool_add")] == [
        "dice_pool", "contest_entity_opponent"]


def test_the_moment_is_the_pool_save_and_it_is_a_seed():
    from transversal.services.conditions import context_keys_for
    from transversal.services.effects_engine.triggers import triggers_for_event
    from transversal.services.target_catalog import scope_seed_names

    assert "on_pool_add" in (triggers_for_event("pool_changed") or set())
    assert {"rolls", "opposing_rolls", "added_dice"} <= (context_keys_for(trigger="on_pool_add") or set())
    assert "added_die" not in scope_seed_names("on_pool_add", "trait_setting")
