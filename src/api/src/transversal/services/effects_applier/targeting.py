"""Targeting — split out of src/api/src/transversal/services/effects_applier.py."""

import random

from dataclasses import field
from transversal.domain import Effect
from transversal.domain import Entity
from transversal.services.effect_targets import resolve_candidates
from typing import Optional
from transversal.services.effects_applier.datatypes import (
    AppliedEffect,
    EffectsResult,
    PendingChoice,
)


_TARGET_KINDS = {
    "location": "location",
    "occupant": "occupant",
    "trait": "trait",
    "traitsetting": "traitsetting",
    "entity": "entity",
    "rating_die": "rating_die",
    "life_path": "life_path",
    "roll_table": "roll_table",
    "universe": "universe",
    "projection": "projection",
    "scheduled_event": "scheduled_event",
}

_PLACEHOLDER_MODES = {"choose", "random"}

def _parse_placeholder(target: str) -> Optional[tuple[str, Optional[str]]]:
    """Parse a ``{mode:kind}`` / ``{mode_kind}`` target placeholder.

    Returns ``(mode, kind)`` for a recognised mode (``choose`` / ``random``).
    ``kind`` is None for a bare ``{choose}`` / ``{random}``.  Returns None for
    non-placeholder targets or unknown modes.
    """
    if not (target.startswith("{") and target.endswith("}")):
        return None
    body = target[1:-1]
    if ":" in body:
        mode, _, kind = body.partition(":")
    else:
        mode, _, kind = body.partition("_")
    if mode not in _PLACEHOLDER_MODES:
        return None
    kind = kind.strip()
    return (mode, _TARGET_KINDS.get(kind)) if kind else (mode, None)

def is_choose_target(target: str) -> bool:
    """True if ``target`` is a ``{choose_*}`` placeholder needing user resolution."""
    parsed = _parse_placeholder(target or "")
    return parsed is not None and parsed[0] == "choose"

def choose_kind(target: str) -> Optional[str]:
    """Return the picker kind for a ``{choose_kind}`` placeholder, or None."""
    parsed = _parse_placeholder(target or "")
    if parsed is None or parsed[0] != "choose":
        return None
    return parsed[1]

def find_choose_placeholder(effect: Effect) -> Optional[tuple[str, str, Optional[str]]]:
    """Return ``(kind, field, scope)`` for the first ``{choose:*}`` in an effect.

    Checks scope values first (they narrow the subsequent target/entity/context
    choice), then ``target``/``entity``, then string ``context`` values. The
    ``field`` is the dotted Effect path the picker should resolve into
    (``"target"``, ``"entity"``, ``"target_scope"``, ``"entity_scope"``, or
    ``"context.<key>"``).
    """
    from transversal.services.effect_targets import parse_scope
    for field_name in ("target_scope", "entity_scope"):
        scope = getattr(effect, field_name, None) or ""
        _, value = parse_scope(scope)
        parsed = _parse_placeholder(value or "")
        if parsed is not None and parsed[0] == "choose":
            return (parsed[1], field_name, None)
    for field_name in ("target", "entity"):
        parsed = _parse_placeholder(getattr(effect, field_name, "") or "")
        if parsed is not None and parsed[0] == "choose":
            scope = effect.target_scope if field_name == "target" else effect.entity_scope
            return (parsed[1], field_name, scope)
    for key, value in (effect.context or {}).items():
        if isinstance(value, str):
            parsed = _parse_placeholder(value)
            if parsed is not None and parsed[0] == "choose":
                scope = effect.target_scope if key == "projection" else None
                return (parsed[1], f"context.{key}", scope)
    return None

def _scope_choice(effect: Effect) -> Optional[PendingChoice]:
    """Return a PendingChoice for a ``{choose:*}`` in the effect's scope value."""
    from transversal.services.effect_targets import parse_scope
    for field_name in ("target_scope", "entity_scope"):
        scope = getattr(effect, field_name, None) or ""
        _, value = parse_scope(scope)
        parsed = _parse_placeholder(value or "")
        if parsed is not None and parsed[0] == "choose":
            return PendingChoice(effect=effect, kind=parsed[1], scope=None, field=field_name)
    return None

def _resolve_scope_choose(scope: Optional[str], target: str) -> Optional[str]:
    """Substitute the ``{choose:*}`` placeholder in a scope value with ``target``."""
    if not scope:
        return target
    from transversal.services.effect_targets import parse_scope
    import re
    prefix, value = parse_scope(scope)
    new_value = re.sub(r"\{choose(?:_[a-z_]+|:[a-z_]+)?\}", target, value)
    return f"{prefix}:{new_value}" if prefix else new_value

def _resolve_scope(scope: Optional[str], entity: Entity, repo) -> Optional[str]:
    """Resolve a ``{random:*}`` placeholder in a scope's value position.

    ``universe:{random_universe}`` becomes ``universe:earth`` (etc.) before the
    scope reaches the candidate resolver. Literal scopes pass through untouched.
    """
    if not scope:
        return scope
    from transversal.services.effect_targets import parse_scope
    prefix, value = parse_scope(scope)
    parsed = _parse_placeholder(value or "")
    if parsed is not None and parsed[0] == "random":
        kind = parsed[1] or "universe"
        candidates = resolve_candidates(kind, None, entity, repo)
        if candidates:
            cid = random.choice([c.id for c in candidates])
            return f"{prefix}:{cid}" if prefix else cid
    return scope

def _random_candidate(kind: str, scope: Optional[str], entity: Entity, repo, action: Optional[str] = None, filter: Optional[dict] = None) -> Optional[str]:
    """Return a random in-scope candidate id for the given target kind.

    Delegates to the shared :mod:`effect_targets` resolver so the ``random``
    target mode and the frontend choose-picker see the same candidates.
    """
    scope = _resolve_scope(scope, entity, repo)
    candidates = resolve_candidates(kind, scope, entity, repo, action, filter)
    return random.choice([c.id for c in candidates]) if candidates else None

_SELF_FIELDS = {
    "location": "current_location",
    "universe": "current_universe",
    "projection": "current_projection",
}

def _parse_self_field(token: str) -> Optional[str]:
    """Return the entity attribute for a ``self.<field>`` token, else ``None``."""
    if token.startswith("self."):
        return _SELF_FIELDS.get(token[len("self."):])
    return None

def _resolve_target(entity: Entity, effect: Effect, result: EffectsResult, kind: str, repo) -> Optional[str]:
    """Resolve a target to an id, record a PendingChoice, or pick a random candidate.

    - ``self`` → the entity's own id.
    - ``{choose_*}`` / empty → a PendingChoice the caller resolves later.
    - ``{random:*}`` → a random in-scope candidate (no PendingChoice).
    - anything else → returned as a literal target id.
    """
    target = effect.target or ""
    if target == "self":
        return entity.id
    attr = _parse_self_field(target)
    if attr is not None:
        return getattr(entity, attr, None)
    parsed = _parse_placeholder(target)
    if parsed is not None:
        mode, choose_kind = parsed
        resolved_kind = choose_kind or kind
        if mode == "random":
            return _random_candidate(resolved_kind, effect.target_scope, entity, repo, effect.action, effect.target_filter)
        result.pending_choices.append(
            PendingChoice(effect=effect, kind=resolved_kind, scope=effect.target_scope)
        )
        return None
    if target == "":
        result.pending_choices.append(
            PendingChoice(effect=effect, kind=kind, scope=effect.target_scope)
        )
        return None
    return target

def _effect_subject(entity: Entity, effect: Effect, result: EffectsResult, repo):
    """Resolve the entity an effect acts on (``effect.entity``).

    Blank or ``"self"`` means the applyEffects entity. A ``{choose_entity}`` /
    ``{random:entity}`` placeholder resolves through the same candidate machinery
    as ``target``; anything else is treated as a literal entity id.
    """
    if effect.entity_spec is not None:
        from transversal.services.target_resolver import TargetContext, resolve

        resolution = resolve(effect.entity_spec, TargetContext(subject=entity, repo=repo))
        if resolution.values:
            return resolution.values[0]
        result.applied.append(AppliedEffect(effect, "entity spec resolved to nothing"))
        return None
    subject = (effect.entity or "").strip()
    if subject in ("", "self") or subject == entity.id:
        return entity
    attr = _parse_self_field(subject)
    if attr is not None:
        ref_id = getattr(entity, attr, None)
        return repo.get_entity(ref_id) if ref_id else None
    parsed = _parse_placeholder(subject)
    if parsed is not None:
        mode, kind = parsed
        resolved_kind = kind or "entity"
        if mode == "random":
            cid = _random_candidate(resolved_kind, effect.entity_scope, entity, repo, effect.action, effect.target_filter)
            return repo.get_entity(cid) if cid else None
        result.pending_choices.append(
            PendingChoice(effect=effect, kind=resolved_kind, scope=effect.entity_scope, field="entity")
        )
        return None
    subject_entity = repo.get_entity(subject)
    if subject_entity is None:
        result.applied.append(AppliedEffect(effect, f"entity {subject} not found"))
        return None
    return subject_entity

def _track_subject(result: EffectsResult, primary: Entity, subject: Entity) -> None:
    """Record a cross-entity subject so commit_effects persists it."""
    if subject is not None and subject is not primary and subject not in result.entities_to_update:
        result.entities_to_update.append(subject)

def resolve_choice(choice: PendingChoice, target: str) -> Effect:
    """Resolve a pending choice to a concrete target, returning a re-appliable effect.

    The returned effect has the pending field (``target``, ``entity``, or a
    ``context.*`` sub-field) set to the chosen id and can be passed back to
    :func:`apply_effects` (or ``commit_effects``) to complete the mutation.
    """
    field = choice.field
    if field in ("target_scope", "entity_scope"):
        return choice.effect.model_copy(update={field: _resolve_scope_choose(getattr(choice.effect, field), target)})
    if "." in field:
        top, _, sub = field.partition(".")
        ctx = dict(choice.effect.context or {})
        ctx[sub] = target
        return choice.effect.model_copy(update={top: ctx})
    return choice.effect.model_copy(update={field: target})
