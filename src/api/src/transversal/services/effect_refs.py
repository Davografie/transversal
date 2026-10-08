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

**The order is derived from the paths** (``dependency_order``): a ref that reads a
name another ref publishes resolves after it, whatever the declaration says. Only
refs that do not depend on each other keep the declared order — which is also the
order the panel asks in. Nothing about the ordering is part of the shim; it is a
fact about refs and it stays.

The shim proper is ``LEGACY_FIELDS``, ``_field_ref``, the fold inside
``effective_refs``, and the positional fallbacks in ``target_value`` /
``target_spec_of`` / ``recipient_value`` / ``recipient_spec_of``. Those — and the
``role`` markers and the positional fields themselves — go together when the
migration is done, tracked on [[B261]]. ``with_ref``, ``anchor_ref_names`` and
``dependency_order`` do not.

Not part of the shim, deliberately: ``result`` (the *string* field). It is an
operand — a die (``d6``) or a number — not a target, and folding it into refs
would be a category error. Only ``result_spec`` is a path.
"""

from __future__ import annotations

from transversal.domain import Effect, TargetRef
from transversal.services.effects_registry.action_types import EffectActionMeta
from transversal.services.effects_registry.lookup import get_action_meta_for
from transversal.services.target_spec import spec_read_names, spec_written_names

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
    """The action's declaration, or None when the object cannot name one.

    Defensive on purpose: these accessors are called from dispatch paths that
    receive whatever the caller had to hand, including test doubles and partially
    built effects. An object that cannot name its action has no declaration, so
    there is no reference to look for and the positional field answers.
    """
    if meta is not None:
        return meta
    effect_type = getattr(effect, "type", "")
    effect_action = getattr(effect, "action", "")
    if not effect_type or not effect_action:
        return None
    return get_action_meta_for(effect_type, effect_action)


def dependency_order(refs: dict[str, TargetRef]) -> list[str]:
    """The ref names in the order they *can* be resolved: a consumer after its producer.

    A ref publishes its own name (``_bind_ref_value``) and every ``output`` its
    path names; a ref consumes a name with ``{name}`` or ``select variable``.
    Reading a published name is a dependency, and a consumer resolved before its
    producer resolves against nothing and fails **closed** — no application, no
    question, no note, which is how `sfx-transverse` never fired. The engine
    derives the order from the paths, because only they know ([[B261]]).

    Refs that do not depend on each other keep the order they came in — the
    action's declaration — so this only ever corrects a real dependency, and the
    panel still asks in the declaration's order where it does not matter. A
    dependency **cycle** cannot be honoured; those refs keep their declaration
    order, which is what the engine resolved by before, rather than guessing.
    """
    names = list(refs)
    publishes: dict[str, set[str]] = {}
    for name, ref in refs.items():
        published = spec_written_names(ref.spec) if ref.spec is not None else set()
        publishes[name] = {name} | published

    producer_of: dict[str, set[str]] = {}
    for producer, published in publishes.items():
        for published_name in published:
            producer_of.setdefault(published_name, set()).add(producer)

    needed: dict[str, set[str]] = {}
    for name, ref in refs.items():
        need: set[str] = set()
        if ref.spec is not None:
            for read in spec_read_names(ref.spec):
                need |= {p for p in producer_of.get(read, ()) if p != name}
        needed[name] = need

    ordered: list[str] = []
    while len(ordered) < len(names):
        for name in names:
            if name not in ordered and needed[name] <= set(ordered):
                ordered.append(name)
                break
        else:
            # Every remaining ref waits on another — a cycle. Keep the
            # declaration order for them rather than dropping any.
            ordered.extend(n for n in names if n not in ordered)
    return ordered


def effective_refs(effect: Effect, meta: EffectActionMeta | None = None) -> dict[str, TargetRef]:
    """The effect's refs with the positional fields folded in as implicit refs.

    Ordered so that a ref comes **after** anything it reads: the resolution order
    is derived from the paths (``dependency_order``), not from the declaration, so
    a consumer cannot be authored into a silent no-op. Refs that do not depend on
    each other keep the action's **declared** order — which is also the order the
    panel asks in, so the two cannot disagree.

    A declared ref that is present but empty does not block its legacy field: an
    effect carrying ``refs={"trait": {}}`` *and* ``target="ts-x"`` still resolves.
    """
    declared = dict(effect.refs or {})
    meta = _meta_for(effect, meta)
    if meta is None or not meta.refs:
        return declared

    present: dict[str, TargetRef] = {}
    for ref_def in meta.refs:
        ref = declared.pop(ref_def.name, None)
        if ref is not None and not ref.value and ref.spec is None:
            ref = None
        if ref is None and ref_def.role:
            ref = _field_ref(effect, ref_def.role)
        if ref is not None:
            present[ref_def.name] = ref
    out = {name: present[name] for name in dependency_order(present)}
    # A stored ref the action does not declare still resolves (defensive: it is
    # content authored against an older declaration).
    out.update(declared)
    return out


def _ref_for(effect: Effect, role: str, meta: EffectActionMeta | None = None):
    """The reference an action declares for a positional field, if it declares one.

    Declaration-driven on purpose: a reader asks for *the target* or *the
    recipient*, and the action's own declared `role` says which ref holds it
    — so no reader hardcodes a ref name, and renaming one cannot leave a reader
    behind ([[B261]]).
    """
    meta = _meta_for(effect, meta)
    if meta is None:
        return None
    refs = getattr(effect, "refs", None) or {}
    for ref_def in meta.refs:
        if ref_def.role == role:
            return refs.get(ref_def.name)
    return None


def ref_value(effect: Effect, role: str, meta: EffectActionMeta | None = None) -> str:
    """A ref's resolved/literal value, or ``""`` when it holds a path instead."""
    ref = _ref_for(effect, role, meta)
    return ref.value if ref is not None and ref.value else ""


def ref_spec(effect: Effect, role: str, meta: EffectActionMeta | None = None):
    """A ref's path, or ``None`` when it holds a literal value instead."""
    ref = _ref_for(effect, role, meta)
    return ref.spec if ref is not None and ref.spec is not None else None


def target_value(effect: Effect, meta: EffectActionMeta | None = None) -> str:
    """The effect's target, from its reference or the positional field.

    This is the accessor the migration needs. Once content carries references
    instead of positional fields, every reader of `effect.target` must come
    through here, or it reads an empty string: a card renders "travels to", a
    validator checks nothing, a guided route has no destination. The positional
    field is still the fallback, so both forms work while content is migrated.
    """
    return ref_value(effect, "target", meta) or (getattr(effect, "target", "") or "")


def target_spec_of(effect: Effect, meta: EffectActionMeta | None = None):
    """The effect's target **path**, wherever it is authored.

    The companion of `target_value`: that one reads a resolved/literal target,
    this one reads the path form. A renderer needs the path to describe *what
    kind of thing* is targeted ("the trait instance you rolled"), and after the
    migration the path lives in the reference — reading only `target_spec` would
    silently render no target at all.
    """
    return ref_spec(effect, "target", meta) or getattr(effect, "target_spec", None)


def recipient_value(effect: Effect, meta: EffectActionMeta | None = None) -> str:
    """Who the effect lands on, from its reference or the positional field."""
    return ref_value(effect, "entity", meta) or (getattr(effect, "entity", "") or "")


def recipient_spec_of(effect: Effect, meta: EffectActionMeta | None = None):
    """The recipient **path**, wherever it is authored."""
    return ref_spec(effect, "entity", meta) or getattr(effect, "entity_spec", None)


def legacy_field_by_ref(effect: Effect, meta: EffectActionMeta | None = None) -> dict[str, str]:
    """Ref name -> the positional field it supersedes, for the declared markers."""
    meta = _meta_for(effect, meta)
    if meta is None:
        return {}
    return {d.name: d.role for d in meta.refs if d.role}


def with_ref(effect: Effect, role: str, value: str = "", spec=None,
             meta: EffectActionMeta | None = None) -> Effect:
    """A copy of ``effect`` with the reference its action declares for ``role`` set.

    The **builder's** half of the migration. A builder used to hand an effect a
    positional field — `target="self"`, `entity="{hitch_entity}"` — and let the
    resolver fold it. It now points the effect at the reference instead, by role,
    so the construction says what it means and no caller hardcodes a ref name.

    Asking for a role the action does not declare is a **bug in the caller**, not a
    no-op: it would silently build an effect that names nobody, so it raises.
    """
    meta = _meta_for(effect, meta)
    if meta is None:
        raise ValueError(
            f"{getattr(effect, 'type', '?')}/{getattr(effect, 'action', '?')} "
            "declares no references"
        )
    for ref_def in meta.refs:
        if ref_def.role == role:
            refs = dict(effect.refs or {})
            refs[ref_def.name] = TargetRef(value=value, spec=spec)
            return effect.model_copy(update={"refs": refs})
    raise ValueError(
        f"{meta.action_id} declares no {role!r} reference "
        f"(has: {[d.name for d in meta.refs]})"
    )


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
