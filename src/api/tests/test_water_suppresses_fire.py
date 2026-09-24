"""The author's `sfx-water-suppresses-fire`, run **verbatim**, end to end.

It is a valid rule that cannot fire yet — it is attached to nothing (its source
is `trait_setting`, so it has to live on a trait instance). This test runs the
rule as authored against a small world, which does two things: it answers "would
this work?" independently of the attaching, and it makes every link the rule
leans on fail here rather than in play — the trigger, the activation seeds, the
`pool → dice` hop, the tags union, and the step-die applier.

The two halves are the author's sentence: *"if you add a fire trait to your pool
while your opponent has a water trait in theirs, your trait steps down."*
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

# ── The rule, exactly as it is authored in the live world ──────────────

FIRE_CONDITION = TargetSpec(steps=[
    {"kind": "select", "collection": "variable", "variable": "trait_setting"},
    {"kind": "navigate", "edge": "trait", "dedup": False},
    {"kind": "filter", "field": "tags", "operator": "contains", "value": "fire"},
])

WATER_CONDITION = TargetSpec(steps=[
    {"kind": "select", "collection": "variable", "variable": "contest_entity_opponent"},
    {"kind": "navigate", "edge": "pool", "dedup": False},
    {"kind": "navigate", "edge": "dice", "dedup": False},
    {"kind": "navigate", "edge": "traitsetting", "dedup": False},
    {"kind": "filter", "field": "tags", "operator": "contains", "value": "water"},
])

STEP_DOWN_THE_ADDED_DIE = TargetSpec(steps=[
    {"kind": "select", "collection": "added_dice"},
])

# The same effect, naming *which* added die: the one from the rule's own trait.
STEP_DOWN_THE_ADDED_FIRE_DIE = TargetSpec(steps=[
    {"kind": "select", "collection": "added_dice"},
    {"kind": "filter", "field": "ts_id", "operator": "==", "value": "{trait_setting}"},
])


def authored_sfx(target: TargetSpec = STEP_DOWN_THE_ADDED_DIE) -> SFX:
    return SFX(
        id="sfx-water-suppresses-fire", name="Water Suppresses Fire",
        trigger="on_pool_change", source_kind="trait_setting",
        conditions=[
            Condition(type=ConditionType.TARGET_PATH, spec=FIRE_CONDITION),
            Condition(type=ConditionType.TARGET_PATH, spec=WATER_CONDITION),
        ],
        effects=[Effect(timing=EffectTiming.IMMEDIATE, type="modify_roll",
                        action="step_down_die", target="", target_spec=target)],
    )


# ── A small world: a fire technique, an opponent with a water one ──────

class Repo:
    def __init__(self):
        # Real entities: the commit path reads (and persists) their full state.
        self.entities = {
            "kael": Entity(id="kael", name="Kael", type=EntityType.CHARACTER,
                           current_location="loc-1", current_universe="earth"),
            "guard-1": Entity(id="guard-1", name="Guard", type=EntityType.GMC,
                              current_location="loc-1", current_universe="earth"),
        }
        self.traitsettings = {
            "kael:fire-palm": NS(id="kael:fire-palm", trait_id="trait-fire-palm",
                                 traitset_id="ts-tech", entity_id="kael", projection_id=None,
                                 rating="d8", tags=[]),
            # A second technique of the character's — *not* fire, and not the rule's
            # home. The rule lives on the fire one; this is what gets added.
            "kael:iron-bark": NS(id="kael:iron-bark", trait_id="trait-iron-bark",
                                 traitset_id="ts-tech", entity_id="kael", projection_id=None,
                                 rating="d6", tags=[]),
            "guard-1:water-palm": NS(id="guard-1:water-palm", trait_id="trait-water-palm",
                                     traitset_id="ts-tech", entity_id="guard-1", projection_id=None,
                                     rating="d10", tags=[]),
        }
        self.traits = {
            "trait-fire-palm": NS(id="trait-fire-palm", traitset_id="ts-tech", tags=["fire"]),
            "trait-iron-bark": NS(id="trait-iron-bark", traitset_id="ts-tech", tags=["wood"]),
            "trait-water-palm": NS(id="trait-water-palm", traitset_id="ts-tech", tags=["water"]),
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


    def list_member_factions_with_sfx(self, entity_id):
        return []

    def list_member_factions_with_sfx_bulk(self, entity_ids):
        return {}

def event(added: list[dict], rolls: list[dict]) -> GameEvent:
    """The context `on_pool_change` builds, with the author's source resolved."""
    return GameEvent(
        type="pool_changed", entity_id="kael", universe="earth",
        context={
            "source_id": "kael:fire-palm",
            "dice_pool": "pool:kael",
            "rolls": rolls,
            "added_dice": added,
            "contest_entity_opponent": "guard-1",
        },
    )


def _register_like_startup(repo):
    """Register the app's core effect handlers, as `transversal.main` does at
    startup. The engine dispatches through the *registry*, and without this every
    action lands on its wildcard passthrough — which is exactly how the step-die
    actions used to be inert, so a test that skipped this would pass a rule that
    does nothing."""
    from transversal.services.effects_applier import registry as applier_registry

    class _EM:
        pass

    em = _EM()
    em.repo = repo
    applier_registry._register_core_handlers(em, None)


def run(added, rolls, repo=None, target=STEP_DOWN_THE_ADDED_DIE):
    repo = repo or Repo()
    _register_like_startup(repo)
    ss_module._store = SceneStateStore()
    ss_module._store.save_pool("loc-1", "guard-1", [
        {"die": "d10", "ts_id": "guard-1:water-palm", "source_kind": "trait"},
    ])
    ss_module._store.save_pool("loc-1", "kael", rolls)
    engine = EffectsEngine()
    engine.register(authored_sfx(target))
    engine.process_event_outcome(event(added, rolls), ["sfx-water-suppresses-fire"], 0, repo=repo)
    return ss_module._store


def teardown_function(_fn):
    ss_module._store = SceneStateStore()


# ── The rule, firing ───────────────────────────────────────────────────

def test_the_rule_steps_down_the_die_just_added():
    """Both halves pass — the source is a fire technique, the opponent's pool
    holds one of water — and the die that was *just added* comes down a step."""
    added = [{"die": "d8", "ts_id": "kael:fire-palm", "source_kind": "trait",
              "pool_location": "loc-1", "pool_owner": "kael", "pool_index": 1}]
    rolls = [{"die": "d6", "ts_id": None, "source_kind": "manual"}, added[0]]

    store = run(added, rolls)

    pool = store.get_pool("loc-1", "kael")
    assert [d["die"] for d in pool] == ["d6", "d6"]      # the added d8 came down
    assert pool[0]["die"] == "d6"                        # the pre-existing die did not


def test_it_does_not_fire_without_a_water_opponent():
    """Take the water out of their pool and the second half fails — the rule is
    a *suppression*, not a tax on adding dice."""
    added = [{"die": "d8", "ts_id": "kael:fire-palm", "source_kind": "trait",
              "pool_location": "loc-1", "pool_owner": "kael", "pool_index": 0}]
    _register_like_startup(Repo())
    ss_module._store = SceneStateStore()
    ss_module._store.save_pool("loc-1", "guard-1", [
        {"die": "d8", "ts_id": None, "source_kind": "manual"},
    ])
    ss_module._store.save_pool("loc-1", "kael", added)
    engine = EffectsEngine()
    engine.register(authored_sfx())

    engine.process_event_outcome(event(added, added), ["sfx-water-suppresses-fire"], 0, repo=Repo())

    assert ss_module._store.get_pool("loc-1", "kael")[0]["die"] == "d8"


def test_it_does_not_fire_when_the_source_is_not_a_fire_technique():
    """The first half is about the rule's *own* trait — a metal technique does
    not get suppressed by water here."""
    added = [{"die": "d8", "ts_id": "kael:fire-palm", "source_kind": "trait",
              "pool_location": "loc-1", "pool_owner": "kael", "pool_index": 0}]
    repo = Repo()
    repo.traits["trait-fire-palm"] = NS(id="trait-fire-palm", traitset_id="ts-tech", tags=["metal"])
    _register_like_startup(repo)
    ss_module._store = SceneStateStore()
    ss_module._store.save_pool("loc-1", "guard-1", [
        {"die": "d10", "ts_id": "guard-1:water-palm", "source_kind": "trait"},
    ])
    ss_module._store.save_pool("loc-1", "kael", added)
    engine = EffectsEngine()
    engine.register(authored_sfx())

    engine.process_event_outcome(event(added, added), ["sfx-water-suppresses-fire"], 0, repo=repo)

    assert ss_module._store.get_pool("loc-1", "kael")[0]["die"] == "d8"

# ── What the conditions do *not* say ───────────────────────────────────

def test_only_the_rules_own_trait_dice_are_taken():
    """`added_dice` is read from the rule's own point of view (2026-09-12, later):
    the dice *this* rule's source contributed. The author's rule needs no filter —
    a die from another technique is not its business, and a `2d8` technique brings
    both of its dice."""
    manual = {"die": "d6", "ts_id": None, "source_kind": "manual",
              "pool_location": "loc-1", "pool_owner": "kael", "pool_index": 0}
    fire = {"die": "d8", "ts_id": "kael:fire-palm", "source_kind": "trait",
            "pool_location": "loc-1", "pool_owner": "kael", "pool_index": 1}

    store = run([manual, fire], [manual, fire])

    assert [d["die"] for d in store.get_pool("loc-1", "kael")] == ["d6", "d6"]


def test_with_the_filter_only_the_fire_die_comes_down():
    """Naming the rule's own trait in the target is what makes it a *fire*
    suppression: the untagged die is left alone."""
    manual = {"die": "d6", "ts_id": None, "source_kind": "manual",
              "pool_location": "loc-1", "pool_owner": "kael", "pool_index": 0}
    fire = {"die": "d8", "ts_id": "kael:fire-palm", "source_kind": "trait",
            "pool_location": "loc-1", "pool_owner": "kael", "pool_index": 1}

    store = run([manual, fire], [manual, fire], target=STEP_DOWN_THE_ADDED_FIRE_DIE)

    assert [d["die"] for d in store.get_pool("loc-1", "kael")] == ["d6", "d6"]

def test_adding_another_trait_is_not_this_rules_business():
    """The author's exact question, re-answered after `added_dice` became per-rule:
    *"I have trait A with this SFX, and I add trait B — does the SFX on A fire?"*

    The *trigger* still fires (it is about the pool changing, and A's conditions
    still hold), but the effect now reads `added_dice` from its own point of view —
    the dice *A* contributed — so B's die is not touched. That is the reading the
    author expected all along; it is the seed's job now, not a filter's.
    """
    iron_bark = {"die": "d6", "ts_id": "kael:iron-bark", "source_kind": "trait",
                 "pool_location": "loc-1", "pool_owner": "kael", "pool_index": 0}

    store = run([iron_bark], [iron_bark])

    assert store.get_pool("loc-1", "kael")[0]["die"] == "d6"


def test_with_the_filter_a_die_from_another_trait_is_left_alone():
    """The other half of the same question: with the effect naming A, adding B is
    still *a* pool change — the rule fires, and then does nothing, because nothing
    it was aimed at moved."""
    iron_bark = {"die": "d6", "ts_id": "kael:iron-bark", "source_kind": "trait",
                 "pool_location": "loc-1", "pool_owner": "kael", "pool_index": 0}

    store = run([iron_bark], [iron_bark], target=STEP_DOWN_THE_ADDED_FIRE_DIE)

    assert store.get_pool("loc-1", "kael")[0]["die"] == "d6"
