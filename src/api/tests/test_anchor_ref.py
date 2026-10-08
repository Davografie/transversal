"""The owner is an **anchor**, not another reference ([[B261]]).

`release_effect_owner` settles where the thing an effect *makes* lives, and it
settles it **once**: it returns on the first landing. Every other reference
multiplies the application — a `target` resolving to three dice applies the
effect three times. Folding the owner into that machinery would turn "create one
thing, anchored here" into "create one thing per anchor".

So an anchor is authored as a reference (one vocabulary in the panel, one order
rule) and declared `anchor=True`, which tells the reference resolver to leave it
alone. These tests pin both halves: the declaration, and the fact that it does
not multiply.
"""

from __future__ import annotations

from types import SimpleNamespace as NS

import pytest

from transversal.domain import Effect, TargetRef
from transversal.services.effect_refs import anchor_ref_names
from transversal.services.effects_applier.datatypes import OWNER_ID_CONTEXT_KEY
from transversal.services.effects_applier.entry import resolve_effect_owner
from transversal.services.effects_engine.refs import resolve_refs
from transversal.services.effects_registry.lookup import get_action_meta_for
from transversal.services.target_resolver import TargetContext
from transversal.services.target_spec import SelectStep, TargetSpec

OWNER_ACTIONS = ("gain_trait", "gain_subtrait", "gain_or_step_up_trait",
                 "cortex_gain_trait", "copy_trait", "move_trait")


class _Repo:
    def __init__(self):
        self.entities = {
            i: NS(id=i, current_location="loc-1", current_universe="earth")
            for i in ("kael", "gmc-1", "gmc-2")
        }

    def get_entity(self, eid):
        return self.entities.get(eid)

    def list_entities_by_location(self, _loc):
        return list(self.entities.values())


def _occupants() -> TargetSpec:
    return TargetSpec(steps=[SelectStep(collection="occupants")])


# --- the declaration ---------------------------------------------------------

def test_an_action_with_owner_elements_declares_an_anchor_ref():
    checked = 0
    for action_id in OWNER_ACTIONS:
        meta = next(m for m in _all() if m.action_id == action_id)
        if not meta.owner_elements:
            continue
        checked += 1
        ref = next(r for r in meta.refs if r.name == "owner")
        assert ref.anchor is True, action_id
        assert ref.elements == tuple(meta.owner_elements), action_id
        assert ref.role == "owner", action_id
        assert ref.label == "Anchored to", action_id
    assert checked, "expected the gain/copy/move family to declare an owner path"


def test_no_other_reference_is_an_anchor():
    """Exactly one concept is anchored; anything else must keep multiplying."""
    for meta in _all():
        for ref in meta.refs:
            if ref.anchor:
                assert ref.name == "owner", f"{meta.action_id}: {ref.name} is anchored"


def _all():
    from transversal.services.effects_registry.registry import EFFECT_ACTION_REGISTRY
    return [m for m in EFFECT_ACTION_REGISTRY if not m.retired]


# --- it does not multiply ----------------------------------------------------

def test_an_anchor_reference_does_not_fan_the_effect_out():
    """The owner path resolves to three occupants — and still makes *one* thing."""
    repo = _Repo()
    effect = Effect(type="modify_trait", action="gain", target="trait-x",
                    refs={"owner": TargetRef(spec=_occupants())})
    assert anchor_ref_names(effect) == {"owner"}
    out = resolve_refs(effect, TargetContext(subject=repo.entities["kael"], repo=repo))
    assert len(out) == 1, "an anchor is settled elsewhere; it must not multiply"


def test_the_contrast_a_normal_reference_does_fan_out():
    """The same spec, as a `trait` reference, applies three times — that is the
    behaviour the anchor exists to *not* have."""
    repo = _Repo()
    effect = Effect(type="modify_roll", action="step_up_die", target="d6",
                    refs={"die": TargetRef(spec=_occupants())})
    assert anchor_ref_names(effect) == set()
    out = resolve_refs(effect, TargetContext(subject=repo.entities["kael"], repo=repo))
    assert len(out) == 3


def test_a_positional_owner_spec_still_resolves():
    """Content authored before the reference keeps working."""
    repo = _Repo()
    effect = Effect(type="modify_trait", action="gain", target="trait-x",
                    owner_spec=_occupants())
    out = resolve_effect_owner(effect, "kael", repo, {})
    assert out.context[OWNER_ID_CONTEXT_KEY] == "kael"
    assert out.owner_spec is None
    assert out.refs["owner"].value == "kael", "the answer is published under the ref"


def test_the_owner_resolver_reads_the_anchor_reference():
    repo = _Repo()
    effect = Effect(type="modify_trait", action="gain", target="trait-x",
                    refs={"owner": TargetRef(spec=_occupants())})
    out = resolve_effect_owner(effect, "kael", repo, {})
    assert out.context[OWNER_ID_CONTEXT_KEY] == "kael"
    assert out.refs["owner"].value == "kael"


def test_no_owner_path_leaves_the_effect_untouched():
    """`owner_spec` naming nothing and not being authored are the same state."""
    repo = _Repo()
    effect = Effect(type="modify_trait", action="gain", target="trait-x")
    assert resolve_effect_owner(effect, "kael", repo, {}) is effect
