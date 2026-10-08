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
    for i, declaration in enumerate(getattr(sfx, "reach", None) or []):
        if getattr(declaration, "spec", None) is not None:
            yield f"Reach path {i + 1}", declaration.spec


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

    # The rule's **declared** bound variables are bound before the condition gate
    # (`effects_engine.firing.bind_declared`), so a condition's path and every
    # effect may name them, and a later declaration may start from an earlier one.
    # A name the activation already owns is *refused* by the engine rather than
    # overwritten, so say it here instead of letting a declaration look effective.
    declared_names: list[str] = []
    for i, bv in enumerate(getattr(sfx, "bound_variables", None) or []):
        name = (getattr(bv, "name", "") or "").strip()
        spec = getattr(bv, "spec", None)
        if not name:
            warnings.append(f"Bound variable {i + 1} has no name — nothing can refer to it")
            continue
        if not (spec is not None and getattr(spec, "steps", None)):
            warnings.append(f"Bound variable '{name}' has no path — it will never bind")
            continue
        if name in declared_names:
            warnings.append(f"Bound variable {i + 1} '{name}' is already declared above")
            continue
        if name in known:
            warnings.append(
                f"Bound variable '{name}' is already a name this activation binds — "
                f"the earlier one wins"
            )
            continue
        declared_names.append(name)
        known.add(name)

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
    reserved = set(scope_seed_names(sfx.trigger, sfx.source_kind)) | set(declared_names)
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

    # Directions that cannot be followed from the place this rule lives on. Shown
    # here as well as refused at the attach, because the editor only knows the
    # owner once it is attached — and a rule can be re-pointed afterwards.
    if repo is not None and sfx.id:
        warnings.extend(unreachable_directions(sfx, repo))

    # Targets that name nothing. The rules live in `effect_validation` because a
    # roll-table entry's effects need the same answer ([[B156]]); this only names
    # the carrier. A dead target applies *silently* — no error, no log, just a
    # dangling setting on the sheet — so authoring time is the only cheap place to
    # catch it.
    if repo is not None:
        from transversal.services.effect_validation import find_missing_targets
        from transversal.services.target_catalog import source_element as _src_el

        for finding in find_missing_targets(
            sfx.effects, repo,
            source_element=_src_el(sfx.source_kind) if sfx.source_kind else None,
        ):
            warnings.append(f"Effect {finding.effect_index + 1}: {finding.message}")

    # ── Half a mechanism is a silent no-op ────────────────────────
    #
    # Two shapes read as finished and do nothing at all. Neither shows up at fire
    # time, so authoring is the only cheap place to say so.

    # 1. A `select` seed that names no collection resolves to nothing, so every path
    #    through it is dead: a gate that never holds, a condition that never passes,
    #    an effect that never lands. Live content has one (`sfx-expose-trait`).
    path_specs: list[tuple[str, object]] = list(_specs_of(sfx))
    for bv in (getattr(sfx, "bound_variables", None) or []):
        if getattr(bv, "spec", None) is not None:
            path_specs.append((f"Bound variable '{getattr(bv, 'name', '') or '?'}'", bv.spec))
    for path_label, path_spec in path_specs:
        for path_step in (getattr(path_spec, "steps", None) or []):
            if (getattr(path_step, "kind", "") == "select"
                    and not str(getattr(path_step, "collection", "") or "").strip()):
                warnings.append(
                    f"{path_label}: the 'select' step names no collection — "
                    f"that path resolves to nothing"
                )
                break

    # 2. A rule that **reaches nobody**. Reach has two forms: the static one, a
    #    trait declaring the rule in its `possibleSfxIds` (offered) or
    #    `defaultSfxIds` (granted), and the dynamic one, a reach declaration on the
    #    rule itself. With neither, no learn-chip can appear anywhere and no one
    #    simply has it — the silent reading the author hit on 2026-09-26, when an
    #    acquire path was authored on the belief that it *granted* reach. A warning
    #    rather than an error, because a rule may legitimately be attached or
    #    granted directly and never learned at all (and a fresh draft reaches
    #    nobody until something declares it). [[Dynamic SFX Reach]]
    if repo is not None and sfx.id and not (getattr(sfx, "reach", None) or []):
        list_declaring = getattr(repo, "list_traits_declaring_sfx", None)
        declaring = list_declaring(sfx.id) if list_declaring is not None else []
        # Being attached is *also* reaching someone (`entity.sfx_ids`, the table
        # bucket), so ownership has to be checked too — and an ownership read that
        # cannot answer must not invent a warning.
        try:
            from transversal.services.sfx_owner import owned_surfaces
            unowned = not owned_surfaces(repo, sfx.id)
        except Exception:
            unowned = False
        if not declaring and unowned:
            warnings.append(
                "Reach: no trait lists this rule as possible, it declares no reach "
                "path, and nothing owns it — so it reaches nobody: no learn-chip "
                "can appear anywhere and no one simply has it"
            )

    # 3. A reach path that starts from `select source` — which can **never** work.
    #    A declaration is resolved with no subject and **no source**: it says who
    #    the rule reaches *world-wide*, rather than what is asking (that was the
    #    retired acquire gate's reading — see `sfx_owner._resolve_reach_spec`). So
    #    the step errors, the path yields nobody, and the author gets no feedback
    #    at all: the declaration *is* present, so the warning above stays quiet.
    #    The human authored exactly this (`sfx-transverse`, 2026-09-29) and saw a
    #    rule that simply did nothing. Unambiguous, so it is reported per path —
    #    unlike "this path resolves to nobody", which is data-dependent (a faction
    #    with no members yet is legitimately empty) and is not warned about.
    for i, declaration in enumerate(getattr(sfx, "reach", None) or []):
        steps = getattr(getattr(declaration, "spec", None), "steps", None) or []
        if any(getattr(s, "kind", "") == "select"
               and getattr(s, "collection", "") == "source" for s in steps):
            warnings.append(
                f"Reach path {i + 1}: 'select source' cannot resolve — a reach "
                "declaration has no source of its own (it is resolved for the whole "
                "world, with no activation), so this path reaches nobody. Start from "
                "a collection instead: `traits`, `entities`, `traitsets`, …"
            )

    return warnings


# ── Directions that lead nowhere ──────────────────────────────
#
# The predicate lives in `guided_route` because the *attach* refusal needs it too:
# a rule granting directions is measured from the place that owns it, and that is
# only known when it is attached (or read back from ownership). See that module
# for why a location owner is the only origin this refuses on.


def unreachable_directions(sfx: SFX, repo) -> list[str]:
    """Directions on this rule that cannot be followed from the place it lives on."""
    if repo is None or not sfx.id:
        return []
    from transversal.services.guided_route import (
        declares_literal_directions,
        describe_unreachable,
        find_unreachable_directions,
    )
    from transversal.services.sfx_owner import list_owner_refs

    # Guarded *before* the ownership read: that read walks every entity, and the
    # overwhelming majority of rules grant no directions at all.
    if not declares_literal_directions(sfx):
        return []
    origins = [r["owner_id"] for r in list_owner_refs(repo, "location")
               if sfx.id in (r.get("sfx_ids") or [])]
    return [describe_unreachable(f, repo) for f in find_unreachable_directions(sfx, repo, origins)]
