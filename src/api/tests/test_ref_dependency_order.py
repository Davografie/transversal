"""B261 — reference order is derived from the paths, so a consumer cannot precede its producer.

A ref publishes its own name and every ``output`` its path names; a ref consumes a
name with ``{name}`` or ``select variable``. Declaring a consumer first resolved it
against nothing and the whole effect failed closed **in silence** — no
application, no question, no note. That is exactly how `sfx-transverse` never
fired: its destination path names the body, and the body reference read the name.

The order is therefore computed from the paths, not trusted to the declaration.
The declaration still decides the order of refs that do **not** depend on each
other — which is also the order the panel asks in — so it remains meaningful
without being load-bearing.
"""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace as NS

from transversal.domain import Effect, EffectTiming, TargetRef
from transversal.services.effect_refs import effective_refs
from transversal.services.effects_engine.refs import resolve_refs
from transversal.services.effects_registry.lookup import get_action_meta_for
from transversal.services.target_resolver import TargetContext
from transversal.services.target_spec import (
    AggregateStep,
    FilterStep,
    SelectStep,
    TargetSpec,
)


def _travel(refs: dict[str, TargetRef]) -> Effect:
    return Effect(timing=EffectTiming.IMMEDIATE, type="travel", action="move", refs=refs)


def _produces(output: str) -> TargetSpec:
    """A path that resolves one location and names it — travel's real destination
    shape, minus the universe it crosses."""
    return TargetSpec(steps=[
        SelectStep(collection="entities"),
        FilterStep(field="type", operator="==", value="location"),
        AggregateStep(fn="random", count=1, output=output),
    ])


def _reads_variable(name: str) -> TargetSpec:
    """Consumes a **typed** name — a step output — travel's `select variable`."""
    return TargetSpec(steps=[SelectStep(collection="variable", variable=name)])


def _reads_token(name: str) -> TargetSpec:
    """Consumes a name by comparison (``{name}``), which is how a *reference's own*
    name may be read: a ref binds its name untyped, so only this form sees it."""
    return TargetSpec(steps=[
        SelectStep(collection="entities"),
        FilterStep(field="current_universe", operator="==", value="{" + name + "}"),
    ])


# --- the order itself ---------------------------------------------------------

def test_a_consumer_is_ordered_after_the_ref_it_reads():
    effect = _travel({
        "projection": TargetRef(spec=_reads_variable("target_projection")),
        "location": TargetRef(spec=_produces("target_projection")),
        "recipient": TargetRef(value="kael"),
    })
    order = list(effective_refs(effect))
    assert order.index("location") < order.index("projection"), (
        "the destination names the body, so it has to resolve first"
    )


def test_a_literal_ref_publishes_its_name_too():
    """The dependency can reverse the declaration, and does.

    Travel declares `location` before `projection`; here the destination path reads
    the body's name, so the body must come first. Deriving the order is the only
    thing that can know that — and a literal ref publishes its name just as a
    resolved one does.
    """
    effect = _travel({
        "recipient": TargetRef(value="kael"),
        "location": TargetRef(spec=_reads_token("projection")),
        "projection": TargetRef(value="proj-1"),
    })
    order = list(effective_refs(effect))
    assert order.index("projection") < order.index("location")


def test_independent_refs_keep_the_actions_declared_order():
    effect = _travel({
        "recipient": TargetRef(value="kael"),
        "location": TargetRef(value="loc-1"),
        "projection": TargetRef(value="proj-1"),
    })
    assert list(effective_refs(effect)) == ["recipient", "location", "projection"]


def test_the_stored_dict_order_does_not_decide():
    """Order is derived from the declaration and the paths — never from however the
    JSON happened to be written, which a content migration or a dict round-trip can
    permute."""
    effect = _travel({
        "projection": TargetRef(value="proj-1"),
        "location": TargetRef(value="loc-1"),
        "recipient": TargetRef(value="kael"),
    })
    assert list(effective_refs(effect)) == ["recipient", "location", "projection"]


def test_a_dependency_cycle_keeps_the_relative_order_and_terminates():
    """Two refs reading each other cannot be ordered. Keep their relative order —
    what the engine resolved by before — rather than dropping or hanging."""
    effect = _travel({
        "recipient": TargetRef(value="kael"),
        "location": TargetRef(spec=_reads_token("projection")),
        "projection": TargetRef(spec=_reads_token("location")),
    })
    assert list(effective_refs(effect)) == ["recipient", "location", "projection"]


# --- the behaviour it exists for ---------------------------------------------

class _Repo:
    """One location, one person — enough for a path to resolve without asking."""

    def __init__(self):
        self.entities = {
            "loc-1": NS(id="loc-1", type="location", current_universe="three_realms"),
            "gmc-1": NS(id="gmc-1", type="gmc", current_location="loc-1",
                        current_universe="three_realms"),
        }

    def list_all_entities(self):
        return list(self.entities.values())

    def get_entity(self, eid):
        return self.entities.get(eid)


def test_a_consumer_declared_first_still_resolves_after_its_producer(monkeypatch):
    """The regression test for `sfx-transverse`, with the bug put back.

    Travel's declaration is reversed to the shape that cost the author a rule —
    consumer first — and the effect must still resolve, because the order no longer
    comes from the declaration. Before this change it resolved to **nothing**, in
    silence.
    """
    import transversal.services.effect_refs as effect_refs

    real_lookup = effect_refs.get_action_meta_for
    meta = real_lookup("travel", "move")
    by_name = {d.name: d for d in meta.refs}
    consumer_first = replace(
        meta, refs=[by_name["recipient"], by_name["projection"], by_name["location"]]
    )
    monkeypatch.setattr(
        effect_refs, "get_action_meta_for",
        lambda t, a: consumer_first if (t, a) == ("travel", "move") else real_lookup(t, a),
    )

    effect = _travel({
        "recipient": TargetRef(value="kael"),
        "location": TargetRef(spec=_produces("target_projection")),
        "projection": TargetRef(spec=_reads_variable("target_projection")),
    })
    resolved = resolve_refs(effect, TargetContext(repo=_Repo()))

    assert resolved, "a producer-first order is derived; the declaration cannot break it"
    assert resolved[0].refs["projection"].value == "loc-1", (
        "the body reference resolved to what the destination path named"
    )
