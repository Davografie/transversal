"""Refs — split out of src/api/src/transversal/services/effects_engine.py."""

from __future__ import annotations

from dataclasses import field
from transversal.domain import Effect
from transversal.domain import SFX
from typing import Optional
from transversal.services.effect_refs import (
    LEGACY_FIELDS,
    anchor_ref_names,
    effective_refs,
    legacy_field_by_ref,
)
from transversal.services.effects_engine.events import (
    StructuredChoice,
)


def _substitute_effect_context(effect: Effect, context: dict, bindings: dict | None = None) -> Effect:
    """Replace ``{context_key}`` placeholders across an effect's string fields.

    Covers ``result`` (the original behaviour), plus ``target``, ``entity``, and
    string ``context`` values so entity/string trigger variables can drive where
    an effect points, not just a numeric/string result. ``bindings`` (per-
    activation output variables) override the event context on name collision.
    """
    source: dict = {}
    if context:
        source.update(context)
    if bindings:
        # Only scalar ("one") bindings substitute into string fields; a "many"
        # binding must be re-used via `select variable` (never stringified).
        source.update({
            name: b.value
            for name, b in bindings.items()
            if getattr(b, "cardinality", "one") != "many"
        })
    if not source:
        return effect

    def _sub(s: Optional[str]) -> Optional[str]:
        if not s:
            return s
        out = s
        for key, value in source.items():
            placeholder = "{" + key + "}"
            if placeholder in out:
                out = out.replace(placeholder, str(value) if value is not None else "")
        return out

    updates: dict = {}
    for field in ("result", "target", "entity"):
        old = getattr(effect, field)
        new = _sub(old)
        if new != old:
            updates[field] = new

    if effect.refs:
        new_refs = {}
        refs_changed = False
        for name, ref in effect.refs.items():
            nv = _sub(ref.value)
            if nv != ref.value:
                new_refs[name] = ref.model_copy(update={"value": nv})
                refs_changed = True
            else:
                new_refs[name] = ref
        if refs_changed:
            updates["refs"] = new_refs

    new_context = {}
    context_changed = False
    for k, v in (effect.context or {}).items():
        if isinstance(v, str):
            nv = _sub(v)
            if nv != v:
                context_changed = True
                new_context[k] = nv
            else:
                new_context[k] = v
        else:
            new_context[k] = v
    if context_changed:
        updates["context"] = new_context

    # And the dice a per-die effect runs for. `die_filter` names the dice by their
    # own fields, and the one an author most needs is *whose* die it is — "for each
    # unchosen die **from this rule's source**" is `{"role": null, "ts_id":
    # "{trait_setting}"}`, and leaving the token literal matched nothing (a rule
    # that creates a hazard from its own die instead created one for every
    # unchosen die in the pool). Only string values can carry a token; a `null`
    # is the whole point of "not chosen", so non-strings pass through untouched.
    if effect.die_filter:
        new_filter = {}
        filter_changed = False
        for k, v in effect.die_filter.items():
            nv = _sub(v) if isinstance(v, str) else v
            if nv != v:
                filter_changed = True
            new_filter[k] = nv
        if filter_changed:
            updates["die_filter"] = new_filter

    if not updates:
        return effect
    return effect.model_copy(update=updates)

# The shared implementation lives in `target_resolver` (this module is inside
# the `effects_engine` package, which imports `roll_deferral` — so importing it
# from here would be a cycle). Re-exported under the name the callers here use.
from transversal.services.target_resolver import resolved_id as _resolved_id  # noqa: E402


def _structured_choice(pc, effect: Effect, field: str, sfx: Optional[SFX] = None,
                       source_kind: str = "", source_id: str = "",
                       source_sfx_id: str = "",
                       answers_so_far: list | None = None,
                       repo=None) -> StructuredChoice:
    """Serialize a resolver pending ``choose`` (``PendingTargetChoice``) into a
    ``StructuredChoice`` whose candidates are ready for the picker."""
    from transversal.services.target_resolver import serialize_candidates

    candidates = [
        {"id": c.id, "name": c.name, "subtitle": c.subtitle, "rating": c.rating, "element": c.element}
        for c in serialize_candidates(pc.element, pc.candidates, repo=repo)
    ]
    return StructuredChoice(
        element=pc.element,
        candidates=candidates,
        count=pc.count,
        field=field,
        effect=effect,
        sfx_name=sfx.name if sfx else "",
        sfx_description=sfx.description if sfx else "",
        step_index=pc.step_index,
        source_kind=source_kind,
        source_id=source_id,
        source_sfx_id=source_sfx_id,
        answers_so_far=list(answers_so_far or []),
    )

def _bind_ref_value(context, name: str, value: str) -> None:
    """Publish a resolved reference value into the activation scope.

    A step's comparison value may be a ``{name}`` reference (see the resolver's
    ``_bound_value``), so binding each ref as it resolves is what lets one path
    join to a choice made in another — *the who's projection whose universe is
    the one just chosen*. ``resolve_refs`` resolves producer-first (the order comes
    from the paths, not the declaration), so a ref that another consumes is bound
    before its consumer runs ([[B261]]).

    A universe resolves to its *entity*, but content identifies a world by its
    handle (``three_realms``, not ``universe-three_realms``) — and a projection's
    ``universe`` field holds the handle. So a universe-valued binding stores the
    handle, which is what makes ``filter universe == {universe}`` line up.
    """
    from transversal.services.target_resolver import Binding

    bindings = getattr(context, "bindings", None)
    if bindings is None or not value:
        return
    handle = value
    repo = getattr(context, "repo", None)
    entity = repo.get_entity(value) if repo is not None else None
    if entity is not None and getattr(entity, "type", "") == "universe":
        handle = getattr(entity, "current_universe", "") or value
    bindings[name] = Binding(value=handle, element="", cardinality="one")

def resolve_refs(effect: Effect, context, structured: Optional[list] = None,
                 answers: dict[int, list[str]] | None = None,
                 source_kind: str = "", source_id: str = "",
                 source_sfx_id: str = "") -> list[Effect]:
    """Resolve each named ref and fan the effect out over multi-value refs.

    Returns the concrete effects to apply — one per combination of resolved ref
    values (the cartesian product across refs). A ref whose ``spec`` resolves to
    ``N`` values fans the effect out ``N`` ways; literal / token refs (``self``,
    ``{choose_*}``, raw ids) contribute one fixed value and do not fan out. If
    any ref resolves to zero values, nothing matches and an empty list is
    returned. An effect with no refs returns ``[effect]`` unchanged.

    When a ref's spec hits a ``choose`` step, the ref is left unresolved, a
    ``StructuredChoice`` is appended to ``structured`` (if provided), and an
    empty list is returned. ``answers`` resumes mid-path ``choose`` steps already
    answered by the user.

    The refs are the action's *effective* ones ([[B261]]): a positional field a
    ``RefDef`` marks as its legacy home is read as that named ref, and the
    resolved value is written back into the field so handlers that still read
    ``effect.target``/``effect.entity`` keep working while they are migrated.
    """
    refs_in = effective_refs(effect)
    # An anchor is authored as a reference but settled by its own resolver, so it
    # is not resolved (or multiplied) here. An effect whose only ref is an anchor
    # resolves to itself, exactly as one with no refs does.
    _anchors = anchor_ref_names(effect)
    if _anchors:
        refs_in = {n: r for n, r in refs_in.items() if n not in _anchors}
    if not refs_in:
        return [effect]
    from itertools import product
    from transversal.services.target_resolver import resolve

    legacy_by_ref = legacy_field_by_ref(effect)
    answers_so_far = [{"stepIndex": k, "ids": list(v)} for k, v in sorted((answers or {}).items())]

    resolved_values: dict[str, list[str]] = {}
    for name, ref in refs_in.items():
        if ref.spec is None:
            resolved_values[name] = [ref.value]
            _bind_ref_value(context, name, ref.value)
            continue
        resolution = resolve(ref.spec, context, answers=answers)
        if resolution.pending_choices:
            if structured is not None:
                for pc in resolution.pending_choices:
                    structured.append(_structured_choice(
                        pc, effect, f"refs.{name}",
                        # What a resume rebuilds the source from. Prefer the
                        # caller's, fall back to the context's, so an emit site
                        # cannot silently drop it and leave every `select source`
                        # in the answered path resolving to nobody ([[B262]]).
                        source_kind=source_kind or getattr(context, "source_kind", "") or "",
                        source_id=source_id or getattr(context, "source_id", "") or "",
                        source_sfx_id=source_sfx_id, answers_so_far=answers_so_far,
                        repo=getattr(context, "repo", None),
                    ))
            return []
        ids = []
        for value in resolution.values:
            rid = _resolved_id(value)
            if rid is not None:
                ids.append(rid)
        resolved_values[name] = ids
        # Publish the ref so a *later* ref's path can compare against it. The
        # declaration order defines the dependency: an Attune declares its
        # chosen universe before the projection path that filters on it.
        if len(ids) == 1:
            _bind_ref_value(context, name, ids[0])

    names = list(refs_in.keys())
    out: list[Effect] = []
    for combo in product(*(resolved_values[n] for n in names)):
        refs = {}
        updates: dict = {}
        for name, value in zip(names, combo):
            ref = refs_in[name]
            refs[name] = (
                ref if ref.spec is None
                else ref.model_copy(update={"value": value, "spec": None})
            )
            # A ref that stands in for a positional field writes its answer back
            # into it, so a handler that has not been migrated yet is unaffected.
            field_name = legacy_by_ref.get(name)
            if field_name:
                string_field, spec_field = LEGACY_FIELDS[field_name]
                if string_field:
                    updates[string_field] = value
                updates[spec_field] = None
        out.append(effect.model_copy(update={"refs": refs, **updates}))
    return out

def resolve_effect_spec_choices(
    effect: Effect,
    field: str,
    answers: dict[int, list[str]],
    entity,
    repo,
    source_kind: str = "",
    source_id: str = "",
    source_sfx_id: str = "",
    bindings: dict | None = None,
) -> tuple[list[Effect], list[StructuredChoice]]:
    """Re-resolve an effect's spec/ref with partial ``choose`` answers.

    Returns ``(resolved_effects, pending)``. ``resolved_effects`` are concrete
    effects with the spec/ref resolved (ready to commit); ``pending`` carries the
    next ``choose`` step(s) as structured choices when the path is not yet fully
    answered. Used by the resume mutation after the user answers a mid-path
    ``choose``.
    """
    from transversal.services.target_resolver import TargetContext, resolve, resolve_source

    source, source_element = (
        resolve_source(source_kind, source_id, repo)
        if source_kind and source_id and repo is not None
        else (None, None)
    )
    ctx = TargetContext(subject=entity, repo=repo, source=source, source_element=source_element,
                        bindings=bindings if bindings is not None else {},
                        source_kind=source_kind or "", source_id=source_id or "")
    answers_so_far = [{"stepIndex": k, "ids": list(v)} for k, v in sorted((answers or {}).items())]

    if field.startswith("refs."):
        structured_choices: list = []
        resolved_list = resolve_refs(
            effect, ctx, structured=structured_choices, answers=answers,
            source_kind=source_kind, source_id=source_id, source_sfx_id=source_sfx_id,
        )
        if structured_choices:
            return [], structured_choices
        # ``resolve_refs`` already cleared the resolved specs and set the
        # concrete values, fanning out one effect per value combination.
        return resolved_list, []

    spec = effect.target_spec if field == "target" else effect.entity_spec
    if spec is None:
        return [], []
    resolution = resolve(spec, ctx, answers=answers)
    if resolution.pending_choices:
        return [], [_structured_choice(pc, effect, field, source_kind=source_kind, source_id=source_id, source_sfx_id=source_sfx_id, answers_so_far=answers_so_far, repo=repo) for pc in resolution.pending_choices]

    out: list[Effect] = []
    for value in resolution.values:
        rid = _resolved_id(value)
        if rid is None:
            continue
        if field == "target":
            out.append(effect.model_copy(update={"target": rid, "target_spec": None}))
        else:
            out.append(effect.model_copy(update={"entity": rid, "entity_spec": None}))

    # …and walk the effect's named **references** on the way out. A choice raised for
    # the subject is answered before the refs are resolved — the effect has to stay
    # whole for the answer to re-resolve it — so the effect handed back here still
    # carries them as *paths*, and every handler reads `refs.<name>.value`. Without
    # this, Gift moved the trait to nobody: the recipient arrived, the trait did not.
    if out and effect.refs:
        ref_choices: list = []
        fanned: list[Effect] = []
        for concrete in out:
            fanned.extend(resolve_refs(
                concrete, ctx, ref_choices, answers=answers,
                source_kind=source_kind, source_id=source_id,
                source_sfx_id=source_sfx_id,
            ))
        if ref_choices:
            return [], ref_choices
        return fanned, []
    return out, []
