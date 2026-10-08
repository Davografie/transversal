"""Lookup helpers over the action registry.

Split out of ``effects_registry.py``.
"""

from __future__ import annotations

from transversal.services.effects_registry.action_types import EffectActionMeta
from transversal.services.effects_registry.cards import EFFECT_ACTION_CARDS
from transversal.services.effects_registry.registry import EFFECT_ACTION_REGISTRY


def get_action_meta(action_id: str) -> EffectActionMeta | None:
    """Look up a single action by its id."""
    for meta in EFFECT_ACTION_REGISTRY:
        if meta.action_id == action_id:
            return meta
    return None


_BY_PAIR: dict[tuple[str, str], EffectActionMeta | None] = {}


def get_action_meta_for(effect_type: str, effect_action: str) -> EffectActionMeta | None:
    """Look up an action by the ``(type, action)`` an *effect* carries.

    Memoized: the resolver asks this once per effect per event, and the registry
    is immutable at runtime (``reload_action_registry`` would need this cleared,
    which no production path calls).
    """
    key = (effect_type, effect_action)
    if key not in _BY_PAIR:
        _BY_PAIR[key] = next(
            (m for m in EFFECT_ACTION_REGISTRY
             if m.effect_type == effect_type and m.effect_action == effect_action),
            None,
        )
    return _BY_PAIR[key]


def get_actions_by_category(category: str) -> list[EffectActionMeta]:
    """Return all actions matching a category ('cost', 'benefit', 'either')."""
    return [m for m in EFFECT_ACTION_REGISTRY if m.category == category]


def output_element_for(effect_type: str, effect_action: str) -> str:
    """The element an action *produces* (the type of ``Effect.output``), or "".

    The mirror of ``get_inverse``: one declaration, read by the runtime (which
    binds the produced id under the author's name) and by the editor (which offers
    that name to later steps).
    """
    for meta in EFFECT_ACTION_REGISTRY:
        if meta.effect_type == effect_type and meta.effect_action == effect_action:
            return meta.output_element
    return ""


def owner_elements_for(effect_type: str, effect_action: str) -> tuple[str, ...]:
    """The catalog elements an action's owner path may land on (empty = none).

    The handler reads this back rather than guessing a kind from the resolved
    value's shape: one declaration, so a value can never be interpreted as the
    wrong collection.
    """
    for meta in EFFECT_ACTION_REGISTRY:
        if meta.effect_type == effect_type and meta.effect_action == effect_action:
            return meta.owner_elements
    return ()


def get_inverse(effect_type: str, effect_action: str) -> tuple[tuple[str, str] | None, bool]:
    """Return ``(inverse, captures_prior)`` for an effect (type, action)."""
    for meta in EFFECT_ACTION_REGISTRY:
        if meta.effect_type == effect_type and meta.effect_action == effect_action:
            return (meta.inverse, meta.inverse_captures_prior)
    return (None, False)


def effect_card(effect_type: str, effect_action: str) -> str:
    """The card template for an effect (``{target}``/``{result}`` placeholders)."""
    templ = EFFECT_ACTION_CARDS.get((effect_type, effect_action))
    if templ:
        return templ
    meta = next((m for m in EFFECT_ACTION_REGISTRY
                 if m.effect_type == effect_type and m.effect_action == effect_action), None)
    return (meta.label if meta else f"{effect_type}/{effect_action}").lower()
