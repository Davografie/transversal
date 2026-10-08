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
    materialise_refs,
    recipient_spec_of,
    recipient_value,
    target_spec_of,
    target_value,
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


# --- the derivation contract (registry) --------------------------------------

def test_every_derived_reference_matches_the_field_it_replaces():
    """The derivation contract: each fallback field, and the ref built from it.

    Scoped to the fields the derivation covers (`_ELEMENTS_FOR_FIELD`) on purpose.
    `hidden_when_ref` has a **second, older meaning** — the attune/suppress
    `result` fields use it to hide a field the `projection` ref supersedes
    outright, with no legacy fold and a different label. That use is a plain
    editor visibility rule; this one adds "and the field is its legacy source".
    """
    from transversal.services.effects_registry.registry import _ELEMENTS_FOR_FIELD

    covered = 0
    for meta in EFFECT_ACTION_REGISTRY:
        if meta.retired:
            continue
        for f in meta.fields:
            if f.name not in _ELEMENTS_FOR_FIELD or not f.hidden_when_ref:
                continue
            covered += 1
            ref = next((r for r in meta.refs if r.name == f.hidden_when_ref), None)
            assert ref is not None, (
                f"{meta.action_id}.{f.name} defers to {f.hidden_when_ref!r}, "
                "which no reference declares"
            )
            assert ref.label == f.label, f"{meta.action_id}: label drifted"
            assert ref.legacy_field == f.name, f"{meta.action_id}: wrong legacy source"
            assert ref.elements, (
                f"{meta.action_id}.{f.name}: a ref nothing could type-check"
            )
    assert covered >= 25, "the entity and die-family fields should all be covered"


def test_only_the_recipient_field_may_claim_the_name_recipient():
    """`recipient` is a **global** name, not just a label.

    `_effect_subject` reads `refs["recipient"]` for every action, so a ref with
    that name means *who this effect lands on*. A ref derived from a **target**
    must not take it: a transfer's target is the entity it goes to, but a handler
    resolving the subject through `_effect_subject` would then resolve the
    transfer's target as the acting entity — silently, since the write-back keeps
    the positional field correct. Caught by the recipient invariant when
    `transfer_razmerit`'s target was first named `recipient`.
    """
    for meta in EFFECT_ACTION_REGISTRY:
        if meta.retired:
            continue
        for ref in meta.refs:
            if ref.name == "recipient":
                assert ref.legacy_field == "entity", (
                    f"{meta.action_id}: {ref.name!r} is derived from "
                    f"{ref.legacy_field!r}, which is not the recipient field"
                )


def test_a_target_ref_accepts_exactly_what_the_path_already_accepted():
    """The die family's ref is a *set* — and it mirrors the action's own path.

    `reroll_die` is the control: it accepts only a pool die, so its ref accepts
    one element while its siblings' accept two. The derivation reads the action
    rather than assuming the wider set.
    """
    def ref_for(action_id):
        meta = next(m for m in EFFECT_ACTION_REGISTRY if m.action_id == action_id)
        ref = next(r for r in meta.refs if r.name == "die")
        return ref, tuple(meta.path_element)

    ref, path = ref_for("set_die")
    assert ref.elements == path == ("die", "rating_die")
    ref, path = ref_for("reroll_die")
    assert ref.elements == path == ("die",)
    assert ref.legacy_field == "target"


# --- materialising the fold into content (the migration) ---------------------

#: Actions whose *target field* is superseded by a declared reference:
#: `set_trait`'s `trait` (an instance) and `set_die`'s `die`.
SET_TRAIT = {"type": "modify_trait", "action": "set"}
SET_DIE = {"type": "modify_roll", "action": "set_die"}
GAIN = {"type": "modify_trait", "action": "gain"}


def test_materialising_moves_the_field_into_its_reference():
    """What the content migration will do: store what the fold computes in memory."""
    out = materialise_refs(Effect(**SET_TRAIT, target="ts-x"))
    assert out.refs["trait"].value == "ts-x"
    assert out.target == "" and out.target_spec is None, "the positional source is cleared"


def test_materialising_a_spec_moves_the_path_not_its_values():
    out = materialise_refs(Effect(**SET_TRAIT, target_spec=_spec("ts-x")))
    assert out.refs["trait"].spec is not None
    assert out.target_spec is None


def test_materialising_carries_every_superseded_field_at_once():
    """A gain carries a recipient *and* a trait; both move in one pass."""
    out = materialise_refs(Effect(**GAIN, entity="gmc-7", target="trait-beast"))
    assert out.refs["trait"].value == "trait-beast"
    assert out.refs["recipient"].value == "gmc-7"
    assert out.entity == "" and out.target == ""


def test_materialising_changes_nothing_that_has_nothing_to_fold():
    effect = Effect(**SET_TRAIT)
    assert materialise_refs(effect) is effect, "identity, so a sweep can skip it"


def test_materialising_is_equivalent_to_the_fold():
    """The property that makes the migration safe: what is stored decides the same.

    `effective_refs` is what the resolver sees. Before the migration it computes
    the fold from the field; after it, the fold is already in `refs`. The two must
    agree, or content migration would change what an effect does.
    """
    for effect in (
        Effect(**SET_TRAIT, target="ts-x"),
        Effect(**SET_TRAIT, target_spec=_spec("ts-x")),
        Effect(**GAIN, entity="gmc-7", target="trait-beast"),
        Effect(**SET_DIE, target="d6"),
        Effect(type="modify_trait", action="move", target="ts-x"),   # no legacy ref
    ):
        before = effective_refs(effect)
        after = effective_refs(materialise_refs(effect))
        assert before == after, f"{effect.action}: the fold must survive being stored"


def test_materialising_leaves_the_result_operand_alone():
    """`result` is a value, not a path — there is no reference for it to move into."""
    out = materialise_refs(Effect(**SET_TRAIT, target="ts-x", result="d8"))
    assert out.result == "d8"


# --- the accessor a migrated reader uses -------------------------------------

def test_target_value_reads_the_reference_first():
    effect = Effect(type="modify_trait", action="set", target="ts-stale",
                    refs={"trait": TargetRef(value="ts-fresh")})
    assert target_value(effect) == "ts-fresh"


def test_target_value_falls_back_to_the_field():
    effect = Effect(type="modify_trait", action="set", target="ts-x")
    assert target_value(effect) == "ts-x"


def test_target_value_is_declaration_driven_not_name_driven():
    """Whatever the action calls its target ref, the reader finds it the same way.

    `set` names it `trait`, `set_die` names it `die`, `change` names it `instance`,
    `set_location` names it `location` — a reader asks for *the target*, and the
    action's own `legacy_field` marker answers.
    """
    cases = [
        ({"type": "modify_trait", "action": "set"}, "trait", "ts-x"),
        ({"type": "modify_roll", "action": "set_die"}, "die", "die:pool:kael:0"),
        ({"type": "modify_trait", "action": "change"}, "instance", "ts-y"),
        ({"type": "location", "action": "set"}, "location", "loc-1"),
    ]
    for action_kwargs, ref_name, value in cases:
        effect = Effect(**action_kwargs, refs={ref_name: TargetRef(value=value)})
        assert target_value(effect) == value, action_kwargs["action"]


def test_target_value_ignores_a_ref_that_is_not_the_target():
    """An anchor or a secondary ref must not be mistaken for the target."""
    effect = Effect(type="modify_trait", action="gain", target="trait-beast",
                    refs={"recipient": TargetRef(value="gmc-7"),
                          "owner": TargetRef(value="rel-1")})
    assert target_value(effect) == "trait-beast", "neither ref supersedes `target`"


def test_target_value_treats_an_empty_ref_as_no_answer():
    effect = Effect(type="modify_trait", action="set", target="ts-x",
                    refs={"trait": TargetRef()})
    assert target_value(effect) == "ts-x"


def test_target_value_on_an_action_with_no_target_ref_is_the_field():
    effect = Effect(type="modify_trait", action="move", target="ts-x")
    assert target_value(effect) == "ts-x"


def test_target_spec_of_reads_the_path_from_either_home():
    """The renderer's accessor: the path, whether it is positional or in the ref."""
    positional = Effect(type="modify_trait", action="set", target_spec=_spec("ts-x"))
    assert target_spec_of(positional) is positional.target_spec

    migrated = materialise_refs(positional)
    assert migrated.target_spec is None
    assert target_spec_of(migrated) is not None, (
        "a renderer reading only `target_spec` would lose the path after migration"
    )
    assert target_spec_of(migrated) == positional.target_spec


def test_target_spec_of_is_none_when_the_target_is_a_literal():
    effect = Effect(type="modify_trait", action="set", target="ts-x")
    assert target_spec_of(effect) is None


def test_the_accessors_survive_an_object_that_cannot_name_its_action():
    """Dispatch paths hand these whatever the caller had — including test doubles.

    An object with no `type`/`action`/`refs` has no declaration, so there is no
    reference to find and the positional field answers. Without this the accessor
    raised `AttributeError` from inside a razmerit reader that had always been
    handed a light stub.
    """
    class _Stub:
        entity = "gmc-7"
        target = "ts-x"

    assert recipient_value(_Stub()) == "gmc-7"
    assert target_value(_Stub()) == "ts-x"
    assert recipient_spec_of(_Stub()) is None
    assert target_spec_of(_Stub()) is None
