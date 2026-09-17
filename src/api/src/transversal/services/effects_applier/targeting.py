"""Targeting — resolving an effect's ``target``/``entity`` string to an id.

A target is normally resolved *before* the applier sees it: an action that names
one carries a targeting **spec**, and the engine fans the effect out per resolved
id (see ``effects_engine.firing``). What is left here is the small set of string
forms that are not paths at all:

* ``self`` — the applyEffects entity;
* ``self.<field>`` — one of its own id fields (``location``, ``universe``,
  ``projection``);
* a literal id.

The flat ``{choose_kind}`` / ``{random:kind}`` placeholders and the
``target_scope`` narrowing that fed them are gone: both are paths now, and a path
is resolved before this point. An id that resolves to nothing leaves the effect
unapplied — fail closed, which is what a path that resolved nothing means too.
"""

from __future__ import annotations

from typing import Optional

from transversal.domain import Effect
from transversal.domain import Entity
from transversal.services.effects_applier.datatypes import (
    AppliedEffect,
    EffectsResult,
)


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


def context_choice(effect: Effect) -> Optional[tuple[str, str]]:
    """``(kind, field)`` for a ``{choose_*}`` in a context value, else ``None``.

    A *context policy* — ``context.projection = "{choose_projection}"`` — asks the
    user to pick when the effect fires, and the effect is deferred until they do.
    This is the variables feature, not a target placeholder: a *target* choice is
    a path with a ``choose`` step, which the engine resolves as a structured
    choice and never as a context token.
    """
    for key, value in (effect.context or {}).items():
        if not isinstance(value, str):
            continue
        token = value.strip()
        if not (token.startswith("{") and token.endswith("}")):
            continue
        body = token[1:-1]
        mode, _, kind = body.partition(":") if ":" in body else body.partition("_")
        if mode == "choose" and kind:
            return kind, f"context.{key}"
    return None


def _resolve_target(entity: Entity, effect: Effect, result: EffectsResult, repo) -> Optional[str]:
    """The effect's target as a concrete id, or ``None`` when it names nothing."""
    target = (effect.target or "").strip()
    if target == "self":
        return entity.id
    attr = _parse_self_field(target)
    if attr is not None:
        return getattr(entity, attr, None)
    return target or None


def _effect_subject(entity: Entity, effect: Effect, result: EffectsResult, repo):
    """Resolve the entity an effect acts on (``effect.entity``).

    A spec (``entity_spec``) wins; otherwise blank or ``"self"`` means the
    applyEffects entity, ``self.<field>`` reads one of its own id fields, and
    anything else is a literal entity id.
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
    subject_entity = repo.get_entity(subject)
    if subject_entity is None:
        result.applied.append(AppliedEffect(effect, f"entity {subject} not found"))
        return None
    return subject_entity


def _track_subject(result: EffectsResult, primary: Entity, subject: Entity) -> None:
    """Record a cross-entity subject so commit_effects persists it."""
    if subject is not None and subject is not primary and subject not in result.entities_to_update:
        result.entities_to_update.append(subject)


def resolve_choice(choice, target: str) -> Effect:
    """Resolve a pending choice to a concrete target, returning a re-appliable effect.

    The returned effect has the pending field (``target``, ``entity``, or a
    ``context.*`` sub-field) set to the chosen id and can be passed back to
    :func:`apply_effects` (or ``commit_effects``) to complete the mutation.
    """
    field = choice.field
    if "." in field:
        top, _, sub = field.partition(".")
        ctx = dict(choice.effect.context or {})
        ctx[sub] = target
        return choice.effect.model_copy(update={top: ctx})
    return choice.effect.model_copy(update={field: target})
