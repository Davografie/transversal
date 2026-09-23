"""An immediate effect's ``target_spec`` must start from the rule's own source.

The engine resolves the activation source **once** (``_resolve_activation_source``):
an explicit ``source_id`` in the event wins (manual activation), otherwise the
source is found by **ownership** — the instance that grants the rule. The
reference path (``_fire_context``) and the deferred path are handed that resolved
source. The plain ``target_spec`` path was not: it re-derived the source from
``event.context["source_id"]`` alone.

On an *automatic* trigger no source id travels in the event, so ``select source``
found nothing — and because a query with ``source_element is None`` reports
``select source requires a declared source_kind``, the spec resolved to **zero
values**, the effect was silently dropped, and the rule still logged a match.

That is the portent agenda's failure: ``on_challenge_completed`` carries no
``source_id``, so ``select source → subtraits → …`` resolved to nobody.
"""

from types import SimpleNamespace as NS

from transversal.domain import (
    Effect,
    EffectTiming,
    Entity,
    EntityType,
    SFX,
    TargetSpec,
)
from transversal.services.effects_engine import EffectsEngine, GameEvent


# ── The path the portent rules use ─────────────────────────────────────

# `Advance the Agenda`: the lowest-order portent that is not yet enabled.
THE_LOWEST_DISABLED_PORTENT = TargetSpec(steps=[
    {"kind": "select", "collection": "source"},
    {"kind": "navigate", "edge": "subtraits", "dedup": False},
    {"kind": "filter", "field": "enabled", "operator": "==", "value": False},
    {"kind": "aggregate", "fn": "bottom", "field": "order"},
])


def authored_sfx() -> SFX:
    return SFX(
        id="sfx-activate-next-portent", name="Advance the Agenda",
        trigger="on_challenge_completed", source_kind="trait_setting",
        effects=[Effect(timing=EffectTiming.IMMEDIATE, type="testimm",
                        action="noop", target="",
                        target_spec=THE_LOWEST_DISABLED_PORTENT)],
    )


# ── A small world: a Portents container that owns the rule ─────────────

class PortentsRepo:
    """The container grants the rule; the portents hang under it.

    ``get_effective_traitsettings`` is ownership resolution's read — the same one
    a manual activation falls back to when the client sent no source id.
    """

    def __init__(self):
        self.entities = {
            "iron-roots": Entity(id="iron-roots", name="Iron Roots",
                                 type=EntityType.FACTION,
                                 current_universe="earth", current_location="loc-1"),
        }
        self.traitsettings = {
            "iron-roots:portents": NS(
                id="iron-roots:portents", trait_id="trait-portents",
                traitset_id="ts-agenda", entity_id="iron-roots",
                parent_traitsetting_id=None, enabled=True,
                # The agenda's slots, **in order** — and deliberately not the
                # portents' own pacing dice, so a wrong index is visible.
                capacity=["d10", "d6", "d8", "d4"],
                sfx_ids=["sfx-activate-next-portent"],
            ),
            # Portent 1 is the one this event just finished: enabled.
            "iron-roots:portent-1": NS(
                id="iron-roots:portent-1", trait_id="trait-portent",
                traitset_id="ts-agenda", entity_id="iron-roots",
                parent_traitsetting_id="iron-roots:portents",
                enabled=True, order=1, capacity=["d4"],
                sfx_ids=["sfx-portents-escalator"],
            ),
            "iron-roots:portent-2": NS(
                id="iron-roots:portent-2", trait_id="trait-portent",
                traitset_id="ts-agenda", entity_id="iron-roots",
                parent_traitsetting_id="iron-roots:portents",
                enabled=False, order=2, capacity=["d8"],
                sfx_ids=["sfx-portents-escalator"],
            ),
            "iron-roots:portent-3": NS(
                id="iron-roots:portent-3", trait_id="trait-portent",
                traitset_id="ts-agenda", entity_id="iron-roots",
                parent_traitsetting_id="iron-roots:portents",
                enabled=False, order=3, capacity=["d6"],
                sfx_ids=["sfx-portents-escalator"],
            ),
            "iron-roots:portent-4": NS(
                id="iron-roots:portent-4", trait_id="trait-portent",
                traitset_id="ts-agenda", entity_id="iron-roots",
                parent_traitsetting_id="iron-roots:portents",
                enabled=False, order=4, capacity=["d10"],
                sfx_ids=["sfx-portents-escalator"],
            ),
        }

    def get_entity(self, eid):
        return self.entities.get(eid)

    def get_traitsetting(self, ts_id):
        return self.traitsettings.get(ts_id)

    def get_trait(self, tid):
        return None

    def get_sub_traitsettings(self, parent_id):
        return [ts for ts in self.traitsettings.values()
                if ts.parent_traitsetting_id == parent_id]

    def get_sub_traitsettings_for_parents(self, parent_ids):
        return {pid: self.get_sub_traitsettings(pid) for pid in parent_ids}

    def get_effective_traitsettings(self, entity_id, universes=None):
        return [ts for ts in self.traitsettings.values()
                if ts.entity_id == entity_id and ts.parent_traitsetting_id is None]


def _apply_spy():
    """A recording handler for a test-only action (the applier is not the subject)."""
    from transversal.services.effects_applier import effect_registry

    targets = []
    effect_registry.register("testimm", "noop",
                             lambda a, _eid, _u, _ctx: targets.append(a.target))
    return targets


def _fire(repo, context):
    """The `challenge_completed` moment: the event names the instance that
    finished, and carries no `source_id` (the engine binds a source only when
    the event has one, so an automatic rule resolves it by ownership instead)."""
    engine = EffectsEngine()
    engine.register(authored_sfx())
    targets = _apply_spy()
    engine.process_event_outcome(
        GameEvent(type="challenge_completed", entity_id="iron-roots",
                  universe="earth",
                  context={"trait_setting_id": "iron-roots:portent-1", **context}),
        ["sfx-activate-next-portent"], 0, repo=repo,
    )
    return targets


# ── The bug ────────────────────────────────────────────────────────────

def test_an_automatic_rule_resolves_select_source_by_ownership():
    """The container owns the rule, so `select source` is the container — and the
    path walks to the lowest-order disabled portent under it."""
    targets = _fire(PortentsRepo(), context={})

    assert targets == ["iron-roots:portent-2"], (
        "an automatic activation must resolve `select source` by ownership; "
        "otherwise the spec resolves to nobody and the effect is dropped"
    )


def test_the_explicit_source_id_still_wins():
    """The manual shape already worked, which is what hid the bug: when the event
    carries a source id the path resolves, so only the automatic triggers broke."""
    targets = _fire(PortentsRepo(), context={"source_id": "iron-roots:portents"})

    assert targets == ["iron-roots:portent-2"]


# ── The escalator: the die is the container's slot for *this* portent ──

TO_THE_CONTAINER = TargetSpec(steps=[
    {"kind": "select", "collection": "source"},
    {"kind": "navigate", "edge": "parent"},
])

CAPACITY_SLOT_FOR_MY_ORDER = TargetSpec(steps=[
    {"kind": "select", "collection": "source"},
    {"kind": "navigate", "edge": "parent"},
    {"kind": "navigate", "edge": "capacity_dice"},
    {"kind": "filter", "field": "index", "operator": "==", "value": "{order}"},
])


def escalator_sfx() -> SFX:
    return SFX(
        id="sfx-portents-escalator", name="Escalate the Agenda",
        trigger="on_challenge_completed", source_kind="trait_setting",
        effects=[Effect(timing=EffectTiming.IMMEDIATE, type="testdie",
                        action="noop", target="",
                        target_spec=TO_THE_CONTAINER,
                        result_spec=CAPACITY_SLOT_FOR_MY_ORDER)],
    )


def _fire_escalator(repo, completed: str):
    """Fire the escalator for the portent the event names, recording
    ``(target, die)`` — the container, and the slot *this* portent fills."""
    from transversal.services.effects_applier import effect_registry

    seen = []
    effect_registry.register("testdie", "noop",
                             lambda a, _e, _u, _c: seen.append((a.target, a.result)))
    engine = EffectsEngine()
    engine.register(escalator_sfx())
    engine.process_event_outcome(
        GameEvent(type="challenge_completed", entity_id="iron-roots",
                  universe="earth", context={"trait_setting_id": completed}),
        ["sfx-portents-escalator"], 0, repo=repo,
    )
    return seen


def test_the_escalator_adds_the_containers_slot_for_the_portent_that_finished():
    """The whole chain in one test: a rule on a *nested* portent, whose source is
    that portent (not the first one that happens to carry the rule), reading the
    die from the container's ordered capacity by the portent's own position."""
    # Portent 2 (order 2) fills the container's 2nd slot; portent 4 the 4th.
    assert _fire_escalator(PortentsRepo(), "iron-roots:portent-2") == [
        ("iron-roots:portents", "d6")]
    assert _fire_escalator(PortentsRepo(), "iron-roots:portent-4") == [
        ("iron-roots:portents", "d4")]


def test_the_escalator_reads_the_portent_that_finished_not_the_first_one():
    """Ownership alone returns whichever portent is walked first, so `{order}`
    would always be 1 and every completion would fill the first slot. The event
    names the instance it is about; that instance is the source."""
    seen = _fire_escalator(PortentsRepo(), "iron-roots:portent-3")

    assert seen == [("iron-roots:portents", "d8")], (
        "portent 3 must fill the container's 3rd slot (d8), not the 1st (d10)")


def test_a_rule_the_named_instance_does_not_grant_falls_back_to_ownership():
    """`sfx-activate-next-portent` lives on the container. The event names a
    portent that does not carry it, so ownership still decides — the new
    preference only applies when the named instance actually grants the rule."""
    targets = _fire(PortentsRepo(), context={})

    assert targets == ["iron-roots:portent-2"]
