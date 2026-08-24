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
        if value in (None, ""):
            missing.append(f.name)
    return missing


def validate_sfx(sfx: SFX) -> list[str]:
    """Return authoring warnings for unknown ``{variables}`` (empty = valid).

    Context dict values are intentionally skipped — they are free-form and can
    hold mechanism tokens (projection policies, step counts) that are not
    trigger variables.
    """
    warnings: list[str] = []
    known = {v.name for v in trigger_variables(sfx.trigger)}

    for i, effect in enumerate(sfx.effects):
        for token in _effect_tokens(effect):
            if token not in known and not _reserved(token):
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

    return warnings
