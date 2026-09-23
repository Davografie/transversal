"""Datatypes — split out of src/api/src/transversal/services/effects_applier.py."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from transversal.domain import Effect
from transversal.domain import Entity
from transversal.domain import TraitSetting
from typing import Optional


SOURCE_CONTEXT_KEY = "_source"

SOURCE_ELEMENT_CONTEXT_KEY = "_source_element"

BINDINGS_CONTEXT_KEY = "_bindings"

#: The activation currently being applied — ``{"sfx_id": ..., "cancelable": bool}``.
#: Set by the engine around one SFX's effects so bookings are attributed to the
#: rule, and a *manual* activation's untimed undos are booked as holds.
ACTIVATION_CONTEXT_KEY = "_activation"

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
    #: Instances an effect *found* rather than made or changed. Only a gain with
    #: "only if missing" produces these: the trait was already there, so nothing
    #: was written, but the step still has a result worth naming — which is what
    #: lets a later step act on "the trait, however it got here".
    found_trait_settings: list[TraitSetting] = field(default_factory=list)
