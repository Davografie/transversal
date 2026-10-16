"""A life-path step's effects, applied through the executor's own path ([[B303]]).

The path from a rule to a *step* of a life path is not the engine's path, and three
things it needed were missing — each one silent, each one only visible as "the
effect did nothing":

1. **Named references were never resolved.** `apply_effects` resolves the
   positional specs; a named reference is `resolve_refs`' job, and the executor
   did not call it. Every step effect whose target was authored as a reference —
   which is the authored form — resolved to nothing and applied as a no-op.
2. **`Effect.output` was never published**, so a later effect could not reference
   what an earlier one made ("gain a trait *on the relationship I just created*"),
   and the trait landed on the character instead.
3. **`resolve_refs` dropped anchor refs** when it wrote an effect back, so the
   `owner` anchor's spec was gone before `resolve_effect_owner` looked for it —
   the same mis-anchoring, from the other end.

These pin the pieces that can be checked without a database; the end-to-end
appearance of the trait *on the edge* was verified against the live world.
"""

from types import SimpleNamespace as NS

from transversal.domain import Effect, EffectTiming, TargetRef, TargetSpec
from transversal.services.effects_applier.entry import _publish_output, _result_counts
from transversal.services.effects_applier.datatypes import BINDINGS_CONTEXT_KEY, EffectsResult
from transversal.services.effects_engine.refs import resolve_refs
from transversal.services.lifepath_executor import named_summary
from transversal.services.target_resolver import Binding, TargetContext

PATH_REF = "lp-24f963a8"


class Repo:
    """Only what a `literal` step needs: fetch the element by id.

    `_lookup_literal` returns nothing without a repo, so a spec-bearing ref would
    resolve to no values at all and `resolve_refs` would return an empty list —
    which would make these tests pass for the wrong reason.
    """

    def get_trait(self, tid):
        return NS(id=tid)

    def get_entity(self, eid):
        return NS(id=eid, type="character")


# ── 3. an anchor ref survives resolution ──────────────────────────────────────

def test_resolve_refs_keeps_the_anchor_it_deliberately_does_not_resolve():
    """The anchor is excluded from *resolution*, not from the effect. Rebuilding
    the refs from the resolved names alone dropped it, so the anchor's spec was
    gone by the time `resolve_effect_owner` looked for it."""
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_trait", action="gain",
        refs={
            "trait": TargetRef(spec=TargetSpec(steps=[
                {"kind": "literal", "element": "trait", "value": "trait-1"}])),
            "owner": TargetRef(spec=TargetSpec(steps=[
                {"kind": "select", "collection": "variable", "variable": "origin_relation"}])),
        },
    )
    ctx = TargetContext(
        subject=NS(id="char-1", type="character"), repo=Repo(),
        bindings={"origin_relation": Binding(
            value="edge-1", values=["edge-1"], element="relationship", cardinality="one")},
    )

    out = resolve_refs(effect, ctx)

    assert out, "the effect vanished"
    owner = (out[0].refs or {}).get("owner")
    assert owner is not None, "the anchor ref was dropped from the resolved effect"
    assert owner.spec is not None, "the anchor lost its spec, so it can never resolve"


def test_a_resolved_ref_is_still_written_back_as_a_value():
    """The complement: the refs that *were* resolved keep their resolved value."""
    effect = Effect(
        timing=EffectTiming.IMMEDIATE, type="modify_trait", action="gain",
        refs={"trait": TargetRef(spec=TargetSpec(steps=[
            {"kind": "literal", "element": "trait", "value": "trait-9"}]))},
    )
    ctx = TargetContext(subject=NS(id="char-1", type="character"), repo=Repo())
    out = resolve_refs(effect, ctx)
    assert out[0].refs["trait"].value == "trait-9"


# ── 2. an output binds what *this* effect produced ────────────────────────────

def test_an_output_binds_the_relationship_edge_key():
    effect = Effect(timing=EffectTiming.IMMEDIATE, type="relationship", action="create",
                    output="origin_relation", result="relation")
    result = EffectsResult()
    result.new_relationships.append(
        {"from": "char-1", "to": "loc-1", "type": "relation", "key": "edge-7"})
    context: dict = {}

    _publish_output(effect, result, context, _result_counts(EffectsResult()))

    bound = context[BINDINGS_CONTEXT_KEY]["origin_relation"]
    assert bound.value == "edge-7"
    assert bound.element == "relationship"


def test_an_effect_that_produced_nothing_does_not_bind_an_earlier_effects_output():
    """A batch accumulates every effect's products, and `_produced_id` returns the
    *first* of the declared element — so publishing against the whole result would
    bind an earlier effect's tie to this one's name."""
    result = EffectsResult()
    result.new_relationships.append(
        {"from": "char-1", "to": "loc-1", "type": "relation", "key": "edge-first"})
    before = _result_counts(result)          # snapshot *after* the earlier effect

    later = Effect(timing=EffectTiming.IMMEDIATE, type="relationship", action="create",
                   output="second_relation", result="relation")
    context: dict = {}
    _publish_output(later, result, context, before)   # produced nothing itself

    assert "second_relation" not in (context.get(BINDINGS_CONTEXT_KEY) or {})


def test_an_unnamed_effect_publishes_nothing():
    effect = Effect(timing=EffectTiming.IMMEDIATE, type="relationship", action="create")
    result = EffectsResult()
    result.new_relationships.append(
        {"from": "char-1", "to": "loc-1", "type": "relation", "key": "edge-1"})
    context: dict = {}
    _publish_output(effect, result, context, {})
    assert not (context.get(BINDINGS_CONTEXT_KEY) or {})


# ── 4. the report names things ────────────────────────────────────────────────

class NamingRepo:
    """Only the readers `named_summary` walks, so a miss is a miss."""

    def __init__(self):
        self.calls = []

    def get_entity(self, eid):
        self.calls.append(("entity", eid))
        return NS(id=eid, name="Antarctica") if eid == "loc-1" else None

    def get_trait(self, tid):
        self.calls.append(("trait", tid))
        return NS(id=tid, name="origin") if tid == "trait-1" else None


def test_a_summary_names_the_ids_it_can_and_leaves_the_rest_alone():
    """The matcher is deliberately a fixed prefix list: a summary is prose, and a
    loose matcher would rewrite "d8" or "no-owner" into names nobody asked for."""
    repo = NamingRepo()
    assert named_summary("relationship relation → loc-1", repo) == "relationship relation → Antarctica"
    assert named_summary("gained trait-1 at d8", repo) == "gained origin at d8"
    # Unknown to the readers, prose, a die, a dashed word, a bare key: untouched.
    for untouched in ("placed at loc-9999", "no owner path resolved",
                      "d8 and no-owner note", "3 of them", "111981129"):
        assert named_summary(untouched, repo) == untouched, untouched


def test_the_same_id_is_looked_up_once():
    repo = NamingRepo()
    cache: dict = {}
    named_summary("placed at loc-1", repo, cache)
    before = len(repo.calls)
    named_summary("and again at loc-1", repo, cache)
    assert len(repo.calls) == before, "the cache did not hold"


def test_a_repo_that_cannot_answer_leaves_the_summary_intact():
    assert named_summary("placed at loc-1", object()) == "placed at loc-1"
    assert named_summary("placed at loc-1", None) == "placed at loc-1"
    assert named_summary("", NamingRepo()) == ""
