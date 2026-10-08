"""The B261 compatibility shim — `services/effect_refs.py`.

`effective_refs` folds an effect's positional path fields into its named `refs`,
so the resolver reads one vocabulary while the fields are migrated away. These
tests pin the two properties that make the shim safe to land:

- **it is inert** for any action that declares no `legacy_field` marker, and
- when an action *does* opt in, the positional field is read as the named ref —
  and a resolved value is written back into the field so an unmigrated handler
  still sees it.
"""

from __future__ import annotations

import pytest

from transversal.domain import Effect, TargetRef
from transversal.domain.effects import TargetSpec
from transversal.services.effect_refs import (
    LEGACY_FIELDS,
    effective_refs,
    legacy_field_by_ref,
)
from transversal.services.effects_engine.refs import resolve_refs
from transversal.services.effects_registry.action_types import EffectActionMeta, RefDef
from transversal.services.effects_registry.registry import EFFECT_ACTION_REGISTRY


def _meta(*refs: RefDef) -> EffectActionMeta:
    return EffectActionMeta(
        action_id="t", label="T", description="", category="benefit",
        effect_type="trait", effect_action="t", refs=list(refs),
    )


def _spec(value: str) -> TargetSpec:
    return TargetSpec.model_validate({"steps": [{"kind": "literal", "value": value}]})


# --- inertness ---------------------------------------------------------------

def test_an_action_with_no_marker_reads_exactly_its_stored_refs():
    effect = Effect(type="modify_pool", action="add_trait_rating",
                    refs={"trait": TargetRef(value="ts-x"), "pool": TargetRef(value="p-1")})
    meta = _meta(RefDef("trait", "Trait", "traitsetting"), RefDef("pool", "Pool", "pool"))
    assert effective_refs(effect, meta) == effect.refs


def test_no_action_in_the_registry_has_a_marker_yet_so_nothing_folds():
    """The shim's inertness, asserted against the live registry.

    This is the *general* form: whenever every declared marker is absent, an
    effect's positional fields are left alone. When markers are added this test
    keeps passing; it fails only if a marker is added without its ref being
    honoured.
    """
    unchecked = []
    for m in EFFECT_ACTION_REGISTRY:
        if any(d.legacy_field for d in m.refs):
            continue
        unchecked.append(m)
        effect = Effect(type=m.effect_type, action=m.effect_action,
                        target="trait-anything", entity="gmc-anything",
                        refs={"pool": TargetRef(value="p-1")})
        assert effective_refs(effect, m) == effect.refs
    assert unchecked, "expected the registry to still be un-migrated at this point"


def test_an_effect_with_no_refs_and_no_markers_returns_unchanged():
    effect = Effect(type="trait", action="t", target="loc-1")
    assert resolve_refs(effect, None) == [effect]


# --- folding the positional fields -------------------------------------------

def test_a_marked_ref_reads_the_legacy_target_string():
    effect = Effect(type="trait", action="t", target="ts-x")
    meta = _meta(RefDef("trait", "Trait", "traitsetting", legacy_field="target"))
    refs = effective_refs(effect, meta)
    assert refs["trait"].value == "ts-x" and refs["trait"].spec is None


def test_a_marked_ref_prefers_the_legacy_spec_over_the_string():
    effect = Effect(type="trait", action="t", target="ts-stale", target_spec=_spec("ts-x"))
    meta = _meta(RefDef("trait", "Trait", "traitsetting", legacy_field="target"))
    assert effective_refs(effect, meta)["trait"].spec is not None


def test_a_stored_ref_wins_over_the_legacy_field():
    effect = Effect(type="trait", action="t", target="ts-old",
                    refs={"trait": TargetRef(value="ts-new")})
    meta = _meta(RefDef("trait", "Trait", "traitsetting", legacy_field="target"))
    assert effective_refs(effect, meta)["trait"].value == "ts-new"


def test_an_empty_stored_ref_does_not_block_the_legacy_field():
    """`refs={"trait": {}}` beside `target="ts-x"` must still resolve."""
    effect = Effect(type="trait", action="t", target="ts-x", refs={"trait": TargetRef()})
    meta = _meta(RefDef("trait", "Trait", "traitsetting", legacy_field="target"))
    assert effective_refs(effect, meta)["trait"].value == "ts-x"


def test_the_entity_field_folds():
    effect = Effect(type="trait", action="t", entity="gmc-7")
    meta = _meta(RefDef("recipient", "Give To", "entity", legacy_field="entity"))
    assert effective_refs(effect, meta)["recipient"].value == "gmc-7"


def test_the_owner_and_result_specs_fold_but_the_result_string_does_not():
    """`result` is an operand (a die), not a target — only `result_spec` is a path."""
    effect = Effect(type="trait", action="t", result="d6", owner_spec=_spec("rel-1"),
                    result_spec=_spec("rating:0:ts-x"))
    meta = _meta(RefDef("anchor", "Anchor", "relationship", legacy_field="owner"),
                 RefDef("die", "Die", "rating_die", legacy_field="result"))
    refs = effective_refs(effect, meta)
    assert refs["anchor"].spec is not None
    assert refs["die"].spec is not None
    # The die *value* is not a ref and never becomes one.
    assert "d6" not in [r.value for r in refs.values()]


def test_an_unknown_legacy_field_is_a_declaration_bug_not_a_silent_no_op():
    effect = Effect(type="trait", action="t", target="ts-x")
    meta = _meta(RefDef("trait", "Trait", "traitsetting", legacy_field="targt"))
    with pytest.raises(ValueError, match="unknown legacy field"):
        effective_refs(effect, meta)


# --- order is the declaration's, not the dict's ------------------------------

def test_order_follows_the_declaration_not_the_stored_dict():
    effect = Effect(type="trait", action="t",
                    refs={"pool": TargetRef(value="p-1"), "trait": TargetRef(value="ts-x")})
    meta = _meta(RefDef("trait", "Trait", "traitsetting"), RefDef("pool", "Pool", "pool"))
    assert list(effective_refs(effect, meta)) == ["trait", "pool"]


def test_a_stored_ref_the_action_does_not_declare_still_resolves():
    effect = Effect(type="trait", action="t", refs={"ghost": TargetRef(value="x")})
    meta = _meta(RefDef("trait", "Trait", "traitsetting"))
    assert effective_refs(effect, meta)["ghost"].value == "x"


def test_a_declared_ref_that_says_nothing_is_absent():
    effect = Effect(type="trait", action="t")
    meta = _meta(RefDef("trait", "Trait", "traitsetting", legacy_field="target"))
    assert effective_refs(effect, meta) == {}


# --- write-back, so an unmigrated handler still works ------------------------

def test_a_resolved_implicit_ref_is_written_back_into_its_field(monkeypatch):
    """The point of the shim: migrate the resolver first, the handlers later."""
    import transversal.services.effect_refs as shim

    meta = _meta(RefDef("trait", "Trait", "traitsetting", legacy_field="target"))
    monkeypatch.setattr(shim, "get_action_meta_for", lambda *a, **k: meta)
    assert legacy_field_by_ref(Effect(type="t", action="t"), meta) == {"trait": "target"}

    class _Ts:
        id = "ts-x"

    class _Repo:
        def get_traitsetting(self, _value):
            return _Ts()

        def get_entity(self, _value):
            return None

    from transversal.services.target_resolver import TargetContext

    effect = Effect(type="t", action="t", target="ts-stale",
                    target_spec=TargetSpec.model_validate(
                        {"steps": [{"kind": "literal", "element": "traitsetting", "value": "ts-x"}]}))

    out = resolve_refs(effect, TargetContext(subject=None, repo=_Repo()))
    assert len(out) == 1
    resolved = out[0]
    assert resolved.refs["trait"].value == "ts-x"
    assert resolved.target == "ts-x"        # written back for the old reader
    assert resolved.target_spec is None


def test_a_literal_ref_still_surfaces_under_its_declared_name(monkeypatch):
    """A string legacy target needs no repo: it *is* the resolved value."""
    import transversal.services.effect_refs as shim

    meta = _meta(RefDef("trait", "Trait", "traitsetting", legacy_field="target"))
    monkeypatch.setattr(shim, "get_action_meta_for", lambda *a, **k: meta)
    effect = Effect(type="t", action="t", target="ts-x")
    out = resolve_refs(effect, None)
    assert [e.refs["trait"].value for e in out] == ["ts-x"]
    assert out[0].target == "ts-x"


def test_the_legacy_field_map_covers_exactly_the_four_positional_fields():
    assert set(LEGACY_FIELDS) == {"target", "entity", "owner", "result"}
    assert LEGACY_FIELDS["owner"][0] == ""   # an owner is only ever a path
    assert LEGACY_FIELDS["result"][0] == ""  # a result string is an operand
