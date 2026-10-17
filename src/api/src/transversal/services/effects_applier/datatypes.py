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

#: What each applied effect *did*, or why it did nothing — one
#: ``{"type", "action", "target", "note"}`` per record, accumulated on the
#: activation's context while its effects run ([[B236]]).
#:
#: The reason lives on ``AppliedEffect.summary`` and was already written for every
#: refusal; what was missing was anywhere to put it. Reaching the client mattered
#: because **a refusal is recorded exactly like a success** — `{"applied": true,
#: "effects_applied": 2}` for one real effect and one silent no-op — so a reader
#: could not tell "it worked" from "it did nothing, and here is why".
EFFECT_NOTES_CONTEXT_KEY = "_effect_notes"

#: Where a gained trait is *anchored*, when that is not the plain entity: the
#: The catalog element the ``owner_spec`` path landed on — ``relationship``,
#: ``traitsetting``, ``entity`` or ``projection``. Written by
#: :func:`effects_applier.entry.resolve_effect_owner` next to
#: :data:`OWNER_ID_CONTEXT_KEY` and read back by ``_trait_owner``, so the anchor's
#: *kind* is the type the path actually resolved to rather than an assumption
#: drawn from the action's first declared element.
OWNER_KIND_CONTEXT_KEY = "_owner_kind"

OWNER_ID_CONTEXT_KEY = "_owner_id"

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
    #: **The pool.** The option records the resolver already built — ``id`` /
    #: ``name`` / ``subtitle`` / ``rating`` / ``element`` — so the caller can
    #: present the question. Without them a choice is unanswerable: the portal fire
    #: raised one for the airport's self-portal and the four candidate cities went
    #: nowhere, so nothing could be picked and nothing happened (2026-10-17). The
    #: engine's own paths have always carried them (`StructuredChoice.candidates`);
    #: this entry point dropped them on the floor.
    #:
    #: Declared **above** ``field`` on purpose: the attribute below is *named*
    #: `field`, which shadows `dataclasses.field` for the rest of the class body.
    candidates: list = field(default_factory=list)
    #: How many to pick: ``1`` is *choose one*, ``None`` is *as many as you like*.
    count: Optional[int] = None
    field: str = "target"

@dataclass
class PendingBranch:
    """A choice node that has been reached and is waiting for an answer.

    ``options`` is ``(id, label)`` per branch, which is all a picker needs; the
    effects themselves stay on the effect, so the answer is resolved by
    ``resolve_branch_effects(effect, option_id)`` against the same authored object.
    """
    effect: Effect
    options: list[tuple[str, str]] = field(default_factory=list)


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
    #: Entities an effect **made** ([[B311]]). A report, not a write path: the
    #: handler creates the document itself, because the new id has to exist while
    #: the rest of the batch is still resolving (the same reason
    #: ``_apply_relationship_create`` mints its edge). This list is what lets a
    #: caller say what was spawned.
    new_entities: list[Entity] = field(default_factory=list)
    pending_choices: list[PendingChoice] = field(default_factory=list)
    pending_branches: list[PendingBranch] = field(default_factory=list)
    passthrough: list[Effect] = field(default_factory=list)
    revealed: list[tuple[TraitSetting, str]] = field(default_factory=list)
    #: Instances an effect *found* rather than made or changed. Only a gain with
    #: "only if missing" produces these: the trait was already there, so nothing
    #: was written, but the step still has a result worth naming — which is what
    #: lets a later step act on "the trait, however it got here".
    found_trait_settings: list[TraitSetting] = field(default_factory=list)
