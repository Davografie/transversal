"""Datatypes — split out of src/api/src/transversal/services/effects_applier.py."""

from dataclasses import dataclass
from dataclasses import field
from transversal.domain import Effect
from transversal.domain import Entity
from transversal.domain import TraitSetting
from typing import Optional


SOURCE_CONTEXT_KEY = "_source"

SOURCE_ELEMENT_CONTEXT_KEY = "_source_element"

BINDINGS_CONTEXT_KEY = "_bindings"

@dataclass
class AppliedEffect:
    """Record of one successfully applied mutation."""
    effect: Effect
    summary: str
    trait_setting_id: Optional[str] = None

@dataclass
class PendingChoice:
    """An effect whose target must be resolved by the user at runtime.

    ``kind`` is the target kind the picker should present (``location``,
    ``occupant``, ``trait``, ``rating_die``, ``entity``, ``life_path``,
    ``roll_table``).  ``scope`` is the narrowing hint from ``Effect.target_scope``
    (e.g. a universe or "current location") used to filter candidates.
    ``field`` names the Effect field this choice resolves into (``target`` or
    ``entity``).
    """
    effect: Effect
    kind: str
    scope: Optional[str] = None
    field: str = "target"

@dataclass
class EffectsResult:
    """Everything produced by apply_effects, ready for the caller to persist."""
    applied: list[AppliedEffect] = field(default_factory=list)
    new_trait_settings: list[TraitSetting] = field(default_factory=list)
    updated_trait_settings: list[TraitSetting] = field(default_factory=list)
    removed_trait_settings: list[TraitSetting] = field(default_factory=list)
    new_relationships: list[dict] = field(default_factory=list)
    new_projections: list = field(default_factory=list)
    updated_projections: list = field(default_factory=list)
    removed_projections: list = field(default_factory=list)
    new_traitsetsettings: list = field(default_factory=list)
    updated_traitsetsettings: list = field(default_factory=list)
    entities_to_update: list[Entity] = field(default_factory=list)
    pending_choices: list[PendingChoice] = field(default_factory=list)
    passthrough: list[Effect] = field(default_factory=list)
    revealed: list[tuple[TraitSetting, str]] = field(default_factory=list)
