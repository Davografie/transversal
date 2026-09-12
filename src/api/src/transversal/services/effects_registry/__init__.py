"""Effects action registry — metadata for every effect action the system supports.

This is the single source of truth for:
  - Available effect actions (label, description, category)
  - Per-action field requirements (what inputs does the UI need?)
  - Valid timings (which EffectTiming values make sense for this action?)
  - Implicit defaults (what fields can the UI auto-fill and hide?)

The frontend fetches this via GraphQL to render phased effect-edit forms.

The action definitions live in the sibling ``actions_*`` modules (one per
editor section) and are assembled -- in source order -- by ``registry.py``.
This module re-exports the whole surface, so
``from transversal.services.effects_registry import X`` is unchanged.
"""

from __future__ import annotations

from transversal.services.effects_registry.action_types import (  # noqa: F401
    EffectActionMeta,
    EffectFieldDef,
    RefDef,
    _ENTITY_FIELD,
    _NOTES_CONTEXT_FIELD,
    _RELATIONSHIP_CONTEXT_FIELD,
    _STATEMENT_CONTEXT_FIELD,
    _STEPS_CONTEXT_FIELD,
)
from transversal.services.effects_registry.cards import EFFECT_ACTION_CARDS  # noqa: F401
from transversal.services.effects_registry.lookup import (  # noqa: F401
    effect_card,
    get_action_meta,
    get_actions_by_category,
    get_inverse,
    output_element_for,
)
from transversal.services.effects_registry.registry import (  # noqa: F401
    EFFECT_ACTION_REGISTRY,
    _ACTION_GROUPS,
)
