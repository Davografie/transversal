"""Authoring-time SFX validation — flag unknown variables before they persist.

A single pure function the editor and the save path can both call, so a broken
SFX is caught at authoring time rather than failing silently at run time. The
rules live here — never re-implemented in the frontend.
"""

from __future__ import annotations

import re

from transversal.domain import Effect, SFX
from transversal.services.menu_contexts import trigger_variables
from transversal.services.effect_targets import FILTER_FIELDS
from transversal.services.effects_registry import EFFECT_ACTION_REGISTRY

_TOKEN = re.compile(r"\{([^{}]+)\}")

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

_FILTER_KINDS = {f.field: f.kinds for f in FILTER_FIELDS}


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
    return _tokens(effect.target, effect.entity, effect.result, effect.target_scope, effect.entity_scope)


def _action_meta(effect: Effect):
    """Return the action-registry metadata for an effect, if any."""
    for meta in EFFECT_ACTION_REGISTRY:
        if meta.effect_type == effect.type and meta.effect_action == effect.action:
            return meta
    return None


def _target_kind(effect: Effect):
    meta = _action_meta(effect)
    return meta.target_kind if meta else None


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
    # Menu SFX (placement="menu") can reference any consequence-menu variable
    # (effect_die, hitch/buying/opponent …), regardless of which menu they gate.
    if sfx.placement == "menu":
        from transversal.services.menu_contexts import MENU_CONTEXT_VARIABLES
        known |= {v.name for vs in MENU_CONTEXT_VARIABLES.values() for v in vs}
    # The declared source kind exposes its typed variable, so the author can
    # reference it in effects/conditions without a false "unknown variable".
    from transversal.services.target_catalog import source_variable
    src_var = source_variable(sfx.source_kind or "")
    if src_var:
        known.add(src_var)

    for i, effect in enumerate(sfx.effects):
        known_here = known
        if effect.timing.value in _ROLL_TIMINGS:
            known_here = known | _ROLL_CONTEXT_VARIABLES
        for token in _effect_tokens(effect):
            if token not in known_here and not _reserved(token):
                warnings.append(f"Effect {i + 1}: unknown variable {{{token}}}")

        target_kind = _target_kind(effect)
        for field in (effect.target_filter or {}):
            kinds = _FILTER_KINDS.get(field)
            if kinds and target_kind and target_kind not in kinds:
                warnings.append(f"Effect {i + 1}: filter '{field}' does not apply to {target_kind} targets")

        for name in _missing_required(effect):
            warnings.append(f"Effect {i + 1}: missing required field '{name}'")

    for i, condition in enumerate(sfx.conditions):
        for token in _tokens(condition.subject, condition.target):
            if token not in known and not _reserved(token):
                warnings.append(f"Condition {i + 1}: unknown variable {{{token}}}")

    # Arming scope consistency: a listener_spec scope needs a resolvable path.
    if sfx.arming_scope == "listener_spec" and not (sfx.listener_spec and sfx.listener_spec.steps):
        warnings.append("Arming scope is 'listener_spec' but no listener path is set")

    # source_kind ↔ ownership: a declared source that no surface actually owns
    # makes ``select source`` / ``source_rating`` resolve to nothing at fire time.
    if repo is not None and sfx.id and sfx.source_kind:
        from transversal.services.target_catalog import source_kind as source_kind_def
        sk = source_kind_def(sfx.source_kind)
        if sk is not None and sk.owner_surface:
            from transversal.services.sfx_owner import owned_surfaces
            surfaces = owned_surfaces(repo, sfx.id)
            if surfaces and sk.owner_surface not in surfaces:
                owned = ", ".join(sorted(surfaces))
                warnings.append(
                    f"Source is '{sfx.source_kind}' but this SFX is owned by {owned}, "
                    f"not '{sk.owner_surface}' — select source / source rating will resolve to nothing"
                )

    # A condition that reads the source can only pass when the SFX has that kind
    # of source — "source rating" on an entity SFX is the same silent no-op class.
    from transversal.services.conditions import CONDITION_TYPES
    from transversal.services.target_catalog import source_kind as source_kind_def
    kind = source_kind_def(sfx.source_kind or "")
    element = getattr(kind, "element", "") or ""
    every_condition = list(sfx.conditions) + [
        c for e in sfx.effects for c in (e.conditions or [])
    ]
    for cond in every_condition:
        meta = next((m for m in CONDITION_TYPES if m.value == cond.type.name), None)
        if meta and meta.requires_source_elements and element not in meta.requires_source_elements:
            warnings.append(
                f"'{meta.label}' can never pass here: it reads the SFX's source, and this "
                f"SFX's source is '{sfx.source_kind or 'unset'}'"
            )

    return warnings
