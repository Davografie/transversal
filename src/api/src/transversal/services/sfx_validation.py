"""Authoring-time SFX validation — flag unknown variables before they persist.

A single pure function the editor and the save path can both call, so a broken
SFX is caught at authoring time rather than failing silently at run time. The
rules live here — never re-implemented in the frontend.
"""

from __future__ import annotations

import re

from transversal.domain import Effect, SFX
from transversal.services.menu_contexts import trigger_variables
from transversal.services.effects_registry import EFFECT_ACTION_REGISTRY

_TOKEN = re.compile(r"\{([^{}]+)\}")

# A runtime picker placeholder — `{choose:trait}` or `{choose_trait}`. The kind
# is what a filter over the candidates has to apply to.
# Placeholders the effect system resolves itself, not trigger variables.
# choose/random/return are target/exit mechanisms; the rest are applier-internal
# context keys that happen to appear in authored fields.
_RESERVED_PREFIXES = ("choose", "random", "return")
_RESERVED_TOKENS = {"source_trait", "term_faction"}

# Roll-event timings: these effects fire at roll time, so the roll context
# (outcome scalars + the matched die's properties) is in scope.
_ROLL_TIMINGS = {"on_result", "on_set", "on_roll"}
_ROLL_CONTEXT_VARIABLES = {
    "effect_die", "total",
    "triggered_die_tier", "triggered_die_effect_die", "triggered_die_result", "triggered_die_die",
}



def _tokens(*values) -> list[str]:
    """Collect every ``{token}`` in the given string values."""
    out: list[str] = []
    for value in values:
        if isinstance(value, str):
            out.extend(_TOKEN.findall(value))
    return out


def _reserved(token: str) -> bool:
    """True for choose/random/return placeholders and applier-internal keys."""
    if token in _RESERVED_TOKENS:
        return True
    head = token.split("_", 1)[0].split(":", 1)[0]
    return head in _RESERVED_PREFIXES


def _effect_tokens(effect: Effect) -> list[str]:
    """Tokens in the effect fields that are meant to hold references/variables."""
    return _tokens(effect.target, effect.entity, effect.result)


def _action_meta(effect: Effect):
    """Return the action-registry metadata for an effect, if any."""
    for meta in EFFECT_ACTION_REGISTRY:
        if meta.effect_type == effect.type and meta.effect_action == effect.action:
            return meta
    return None


def _missing_required(effect: Effect) -> list[str]:
    """Return the names of required fields the effect leaves empty."""
    meta = _action_meta(effect)
    if meta is None:
        return []
    missing = []
    for f in meta.fields:
        if not f.required:
            continue
        value = (
            getattr(effect, f.name, None)
            if f.name in ("target", "result", "entity")
            else (effect.context or {}).get(f.name)
        )
        # A structured spec satisfies the target/entity requirement.
        if f.name == "target" and (effect.target_spec and effect.target_spec.steps):
            continue
        if f.name == "entity" and (effect.entity_spec and effect.entity_spec.steps):
            continue
        if value in (None, ""):
            missing.append(f.name)
    return missing


def _condition_meta(condition):
    """Return the vocabulary entry for a condition, if any."""
    from transversal.services.conditions import CONDITION_TYPES
    return next((m for m in CONDITION_TYPES if m.value == condition.type.name), None)


def _condition_label(condition) -> str:
    meta = _condition_meta(condition)
    return meta.label if meta else condition.type.name


def _specs_of(sfx: SFX):
    """Every targeting spec an SFX carries, labelled for warnings."""
    for i, condition in enumerate(sfx.conditions):
        if condition.spec is not None:
            yield f"Condition {i + 1}", condition.spec
    for i, effect in enumerate(sfx.effects):
        if effect.target_spec is not None:
            yield f"Effect {i + 1} target", effect.target_spec
        if effect.entity_spec is not None:
            yield f"Effect {i + 1} subject", effect.entity_spec
        for name, ref in (effect.refs or {}).items():
            if getattr(ref, "spec", None) is not None:
                yield f"Effect {i + 1} '{name}' reference", ref.spec
        for j, condition in enumerate(effect.conditions or []):
            if condition.spec is not None:
                yield f"Effect {i + 1} condition {j + 1}", condition.spec
    if sfx.listener_spec is not None:
        yield "Listener path", sfx.listener_spec
    if sfx.acquire_spec is not None:
        yield "Acquire path", sfx.acquire_spec


def _condition_specs(sfx: SFX):
    """The specs that are *gates*. A condition is evaluated, never answered."""
    for i, condition in enumerate(sfx.conditions):
        if condition.spec is not None:
            yield f"Condition {i + 1}", condition.spec
    for i, effect in enumerate(sfx.effects):
        for j, condition in enumerate(effect.conditions or []):
            if condition.spec is not None:
                yield f"Effect {i + 1} condition {j + 1}", condition.spec


def _source_kinds_for(elements: tuple[str, ...]) -> set[str]:
    """The source kinds whose element is one of ``elements`` (see ``SOURCE_KINDS``)."""
    from transversal.services.target_catalog import SOURCE_KINDS

    return {s.value for s in SOURCE_KINDS if s.element in elements}


def validate_sfx(sfx: SFX, repo=None) -> list[str]:
    """Return authoring warnings for unknown ``{variables}`` (empty = valid).

    Context dict values are intentionally skipped — they are free-form and can
    hold mechanism tokens (projection policies, step counts) that are not
    trigger variables.

    When ``repo`` is provided and the SFX is already persisted, also warns on a
    declared ``source_kind`` that matches no actual owner (a silent no-op at
    fire time) and on a ``listener_spec`` arming scope without a listener path.
    """
    warnings: list[str] = []
    known = {v.name for v in trigger_variables(sfx.trigger)}
    # Menu SFX can reference any consequence-menu variable
    # (effect_die, hitch/buying/opponent …), regardless of which menu they gate.
    # Read through `effective_placement` so both spellings count: `trigger="menu"`
    # (the model today) and a legacy `placement="menu"` override.
    if sfx.effective_placement == "menu":
        from transversal.services.menu_contexts import MENU_CONTEXT_VARIABLES
        known |= {v.name for vs in MENU_CONTEXT_VARIABLES.values() for v in vs}
    # The declared source kind exposes its typed variable, so the author can
    # reference it in effects/conditions without a false "unknown variable".
    from transversal.services.target_catalog import scope_seed_names, source_variable
    src_var = source_variable(sfx.source_kind or "")
    if src_var:
        known.add(src_var)
    # ...and so does its **scalar** fields, declared beside it in
    # ``SOURCE_SCALAR_SEEDS`` (`{order}`). The editor offers those
    # (`effectVariables` reads `scope_seed_names`), so a validator that did not
    # would warn about a name it is itself advertising — which it did, for every
    # source scalar, until this line. One declaration, both readers.
    known |= set(scope_seed_names(sfx.trigger, sfx.source_kind))

    # A trigger that is *about its source* can never pass for a source kind that
    # has no such thing: "when this trait is added" needs a trait instance to be
    # about. Named here rather than left to a log line at fire time.
    from transversal.services.menu_contexts import TRIGGERS
    _trigger = next((t for t in TRIGGERS if t.value == sfx.trigger), None)
    if _trigger is not None and _trigger.requires_source_elements:
        if (sfx.source_kind or "") not in _source_kinds_for(_trigger.requires_source_elements):
            # The author-facing word ("Trait setting"), not the catalog element.
            from transversal.services.target_catalog import SOURCE_KINDS
            need = " / ".join(
                s.label for s in SOURCE_KINDS if s.element in _trigger.requires_source_elements
            ) or " / ".join(_trigger.requires_source_elements)
            warnings.append(
                f"'{_trigger.label}' fires when this rule's own source is added, so it needs a "
                f"{need} source — with {sfx.source_kind or 'no source'} it can never pass"
            )

    # A name an earlier effect bound is in scope for everything after it: an
    # ``Effect.output`` on a *producing* action is bound at fire time
    # (``effects_applier.publish_effect_output``), so `{beast}` in a later step is
    # known, not unknown.
    from transversal.services.effects_registry import output_element_for as _output_element_for
    named_outputs: set[str] = set()
    for i, effect in enumerate(sfx.effects):
        known_here = known | named_outputs
        if effect.timing.value in _ROLL_TIMINGS:
            known_here = known | named_outputs | _ROLL_CONTEXT_VARIABLES
        for token in _effect_tokens(effect):
            if token not in known_here and not _reserved(token):
                warnings.append(f"Effect {i + 1}: unknown variable {{{token}}}")
        name = (getattr(effect, "output", "") or "").strip()
        if name and _output_element_for(effect.type, effect.action):
            named_outputs.add(name)

        for name in _missing_required(effect):
            warnings.append(f"Effect {i + 1}: missing required field '{name}'")

    for i, condition in enumerate(sfx.conditions):
        for token in _tokens(condition.subject, condition.target):
            if token not in known and not _reserved(token):
                warnings.append(f"Condition {i + 1}: unknown variable {{{token}}}")

    # What a take-back would leave behind. A manual rule can be ended early (until
    # it commits), and the effects it cannot undo are the ones the registry
    # declares no inverse for. Named only where the mixture exists: a rule that is
    # entirely irreversible is not a take-back rule at all, and one that is
    # entirely reversible needs no note.
    if sfx.trigger in ("manual", "on_activate"):
        from transversal.services.effects_registry import get_inverse
        has_undoable = any(get_inverse(e.type, e.action)[0] for e in sfx.effects)
        if has_undoable:
            for i, effect in enumerate(sfx.effects):
                if not get_inverse(effect.type, effect.action)[0]:
                    warnings.append(
                        f"Effect {i + 1} cannot be undone: pressing the rule again before it "
                        f"commits leaves it in place (no inverse for {effect.type}/{effect.action})"
                    )

    # An effect's output name must not shadow a name the activation already binds,
    # and two steps cannot share one name — the later binding would silently win.
    from transversal.services.target_catalog import scope_seed_names
    reserved = set(scope_seed_names(sfx.trigger, sfx.source_kind))
    seen_names: set[str] = set()
    for i, effect in enumerate(sfx.effects):
        name = (getattr(effect, "output", "") or "").strip()
        if not name:
            continue
        if name in reserved:
            warnings.append(
                f"Effect {i + 1}: output name '{name}' shadows the rule's own '{name}' — pick another"
            )
        elif name in seen_names:
            warnings.append(f"Effect {i + 1}: output name '{name}' is already used by an earlier effect")
        seen_names.add(name)

    # Arming scope consistency: a listener_spec scope needs a resolvable path.
    if sfx.arming_scope == "listener_spec" and not (sfx.listener_spec and sfx.listener_spec.steps):
        warnings.append("Arming scope is 'listener_spec' but no listener path is set")

    # source_kind ↔ ownership: a declared source that no surface actually owns
    # makes ``select source`` / ``source_rating`` resolve to nothing at fire time.
    if repo is not None and sfx.id and sfx.source_kind:
        from transversal.services.target_catalog import source_kind as source_kind_def
        sk = source_kind_def(sfx.source_kind)
        if sk is not None and sk.owner_surfaces:
            from transversal.services.sfx_owner import owned_surfaces
            surfaces = owned_surfaces(repo, sfx.id)
            if surfaces and not (set(sk.owner_surfaces) & surfaces):
                owned = ", ".join(sorted(surfaces))
                wanted = " or ".join(f"'{s}'" for s in sk.owner_surfaces)
                warnings.append(
                    f"Source is '{sfx.source_kind}' but this SFX is owned by {owned}, "
                    f"not {wanted} — select source / source rating will resolve to nothing"
                )

    # A condition that reads the source can only pass when the SFX has that kind
    # of source — "source rating" on an entity SFX is the same silent no-op class.
    from transversal.services.target_catalog import source_kind as source_kind_def
    kind = source_kind_def(sfx.source_kind or "")
    element = getattr(kind, "element", "") or ""
    every_condition = list(sfx.conditions) + [
        c for e in sfx.effects for c in (e.conditions or [])
    ]
    for cond in every_condition:
        meta = _condition_meta(cond)
        if meta and meta.requires_source_elements and element not in meta.requires_source_elements:
            warnings.append(
                f"'{meta.label}' can never pass here: it reads the SFX's source, and this "
                f"SFX's source is '{sfx.source_kind or 'unset'}'"
            )

    # `select source` resolves only when the SFX declares a source that resolves:
    # an unset source, or a `table`/`gm` bucket, exposes none. The editor refuses
    # to offer the seed there; this catches a draft authored any other way (MCP,
    # the API, or content written before the seed was hidden).
    if not element:
        for label, spec in _specs_of(sfx):
            if any(step.kind == "select" and step.collection == "source" for step in spec.steps):
                warnings.append(
                    f"{label}: 'select source' resolves to nothing — this SFX's "
                    f"source is '{sfx.source_kind or 'unset'}'"
                )

    # A step value may name a value bound earlier in the activation
    # (`filter universe == {chosen_universe}`). A name nothing binds matches
    # nothing, so the path resolves empty and the card reads vaguely — which is
    # exactly how "the universe" ended up on law-bridge's card.
    bound = set(known) | named_outputs
    for label, spec in _specs_of(sfx):
        for step in spec.steps:
            value = getattr(step, "value", None)
            if isinstance(value, str):
                for token in _TOKEN.findall(value):
                    if token not in bound and not _reserved(token):
                        warnings.append(
                            f"{label}: '{{{token}}}' is not bound by anything — that step "
                            f"can never match"
                        )
        bound |= {s.output for s in spec.steps if getattr(s, "output", None)}

    # A condition is a filter, and `choose` is a question. A gate has nobody to
    # ask, so the step resolves to nothing and the condition silently never
    # passes — the editor refuses to author it, and this catches content that
    # predates that (or was authored elsewhere).
    for label, spec in _condition_specs(sfx):
        if any(step.kind == "choose" for step in spec.steps):
            warnings.append(
                f"{label}: a 'choose' step needs an answer, and a condition is "
                f"evaluated without one — it can never pass"
            )

    # Fire-time context, from the capability map: a condition that reads a key the
    # evaluation point never supplies can never pass. One rule for every context
    # condition and every fire site, so neither needs a special case here.
    from transversal.services.conditions import (
        BOUNDARY_TIMINGS, BOUNDARY_TRIGGERS, condition_context_keys, context_keys_for,
    )

    def _gap(condition, available) -> str:
        """What this condition reads that the evaluation point lacks ("" = fine)."""
        if available is None:
            return ""
        missing = sorted(condition_context_keys(condition) - available)
        if not missing:
            return ""
        keys = ", ".join(f"'{k}'" for k in missing)
        if not available:
            return f"it reads {keys}, and a boundary supplies no context"
        return f"it reads {keys}, and there is no context at this moment"

    for i, condition in enumerate(sfx.conditions):
        gap = _gap(condition, context_keys_for(sfx.trigger, "", sfx.placement))
        if gap:
            warnings.append(
                f"Condition {i + 1}: '{_condition_label(condition)}' can never pass — {gap}"
            )
    for i, effect in enumerate(sfx.effects):
        available = context_keys_for(sfx.trigger, effect.timing.value, sfx.placement)
        for condition in (effect.conditions or []):
            gap = _gap(condition, available)
            if gap:
                warnings.append(
                    f"Effect {i + 1}: '{_condition_label(condition)}' can never pass — {gap}"
                )

    return warnings
