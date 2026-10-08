"""One vocabulary for the paths an effect names — the B261 compatibility shim.

An effect names paths two ways today:

- **positionally** — ``target``/``target_spec`` (the thing acted on),
  ``entity``/``entity_spec`` (who it lands on), ``owner_spec`` (the edge an
  anchored trait hangs from) and ``result_spec`` (a die read from a path);
- **by name** — ``refs``, declared per action by ``RefDef``.

Two vocabularies with two order rules is what let the panel ask "what" while the
engine asked "who". This module folds them into one ordered set of refs, so the
resolver, the engine and the handlers can read a single vocabulary while the
positional fields are migrated away.

A ``RefDef`` opts in by declaring ``legacy_field`` — the positional field it
supersedes. An action that declares no marker, and an effect that carries no
marked ref, behave exactly as before: the shim is **inert** until an action opts
in, which is what lets it land without touching 352 stored effects.

Not part of the shim, deliberately: ``result`` (the *string* field). It is an
operand — a die (``d6``) or a number — not a target, and folding it into refs
would be a category error. Only ``result_spec`` is a path.

Delete this module, the ``legacy_field`` markers and the positional fields
together when the migration is done — tracked on [[B261]].
"""

from __future__ import annotations

from transversal.domain import Effect, TargetRef
from transversal.services.effects_registry.action_types import EffectActionMeta
from transversal.services.effects_registry.lookup import get_action_meta_for

#: Legacy field name -> (its string field, its spec field). ``owner`` and
#: ``result`` have no string form: an owner is only ever a path, and a result
#: string is an operand rather than a target.
LEGACY_FIELDS: dict[str, tuple[str, str]] = {
    "target": ("target", "target_spec"),
    "entity": ("entity", "entity_spec"),
    "owner": ("", "owner_spec"),
    "result": ("", "result_spec"),
}


def _field_ref(effect: Effect, field: str) -> TargetRef | None:
    """The ref a positional field stands for, or None when the field says nothing."""
    try:
        string_field, spec_field = LEGACY_FIELDS[field]
    except KeyError:  # a marker that names nothing real is a declaration bug
        raise ValueError(f"unknown legacy field {field!r}") from None
    spec = getattr(effect, spec_field, None)
    if spec is not None:
        return TargetRef(spec=spec)
    value = getattr(effect, string_field, "") if string_field else ""
    return TargetRef(value=value) if value else None


def _meta_for(effect: Effect, meta: EffectActionMeta | None) -> EffectActionMeta | None:
    if meta is not None:
        return meta
    return get_action_meta_for(effect.type, effect.action)


def effective_refs(effect: Effect, meta: EffectActionMeta | None = None) -> dict[str, TargetRef]:
    """The effect's refs, in the action's **declared** order, with the positional
    fields folded in as implicit refs.

    Order is the declaration's, not the stored dict's. Two reasons, and the second
    is the point of the whole migration: a ref declared before another is resolved
    first so the later one can compare against it (Attune decides the world, then
    the projection that filters on it), and the panel renders the same order the
    engine resolves in — so the two cannot disagree.

    A declared ref that is present but empty does not block its legacy field: an
    effect carrying ``refs={"trait": {}}`` *and* ``target="ts-x"`` still resolves.
    """
    declared = dict(effect.refs or {})
    meta = _meta_for(effect, meta)
    if meta is None or not meta.refs:
        return declared

    out: dict[str, TargetRef] = {}
    for ref_def in meta.refs:
        ref = declared.pop(ref_def.name, None)
        if ref is not None and not ref.value and ref.spec is None:
            ref = None
        if ref is None and ref_def.legacy_field:
            ref = _field_ref(effect, ref_def.legacy_field)
        if ref is not None:
            out[ref_def.name] = ref
    # A stored ref the action does not declare still resolves (defensive: it is
    # content authored against an older declaration).
    out.update(declared)
    return out


def legacy_field_by_ref(effect: Effect, meta: EffectActionMeta | None = None) -> dict[str, str]:
    """Ref name -> the positional field it supersedes, for the declared markers."""
    meta = _meta_for(effect, meta)
    if meta is None:
        return {}
    return {d.name: d.legacy_field for d in meta.refs if d.legacy_field}


def anchor_ref_names(effect: Effect, meta: EffectActionMeta | None = None) -> set[str]:
    """The ref names that are **anchors** — authored, but not resolved here.

    An anchor says where the thing the effect makes lives, and its own resolver
    settles it once. `resolve_refs` must leave it alone: every other reference
    multiplies the application, and an anchor that resolved to three edges would
    make three things instead of one thing anchored three ways.
    """
    meta = _meta_for(effect, meta)
    if meta is None:
        return set()
    return {d.name for d in meta.refs if d.anchor}


def materialise_refs(effect: Effect, meta: EffectActionMeta | None = None) -> Effect:
    """Rewrite an effect so its positional paths live in ``refs`` — the fold, stored.

    The shim folds a positional field into its declared reference every time the
    effect resolves (``effective_refs``). This does it **once**, into the content,
    so the positional fields can eventually be deleted.

    It is deliberately the *same* fold, not a second implementation: whatever
    `effective_refs` returns is exactly what gets written, and the fields it
    superseded are cleared in the same move. An effect with nothing to fold is
    returned unchanged (identity, so a caller can skip it cheaply).

    Only the fields a ref declares are touched — `result` is an operand, not a
    path, and never has a reference to move into.
    """
    folded = effective_refs(effect, meta)
    if folded == (effect.refs or {}):
        return effect
    updates: dict = {"refs": folded}
    for field_name in set(legacy_field_by_ref(effect, meta).values()):
        string_field, spec_field = LEGACY_FIELDS[field_name]
        if string_field:
            updates[string_field] = ""
        updates[spec_field] = None
    return effect.model_copy(update=updates)
