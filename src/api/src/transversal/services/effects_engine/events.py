"""Events — split out of src/api/src/transversal/services/effects_engine.py."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from transversal.domain import DicePoolRequest
from transversal.domain import Effect
from transversal.domain import RollResult
from typing import Optional


@dataclass
class GameEvent:
    """An event that can trigger SFXs."""
    type: str  # on_roll, on_complication, on_botch, on_success, etc.
    entity_id: str
    universe: str
    context: dict = field(default_factory=dict)
    # Optional payload depending on event type
    dice_request: Optional[DicePoolRequest] = None
    roll_result: Optional[RollResult] = None

@dataclass
class PendingSfxEffect:
    """A pending context-policy choice (``{choose_projection}``) and its SFX.

    Only a *context* value can still defer this way: a target choice is a path with
    a ``choose`` step, which travels as a structured choice instead.
    """
    effect: Effect
    sfx_name: str
    sfx_description: str = ""
    kind: str = ""                 # what the picker presents (``projection``, …)
    field_name: str = "target"     # where the answer lands (``context.projection``)
    # Immediate effects that come after this blocked effect; applied in order
    # once the choice resolves (sequential execution).
    continuation: list[Effect] = field(default_factory=list)

@dataclass
class StructuredChoice:
    """A structured ``choose`` step awaiting user resolution.

    ``element`` is the catalog element type; ``candidates`` are serialized
    display records (``id``/``name``/``subtitle``/``element``); ``count`` is how
    many to pick (1 = one, ``None`` = as many as they like); ``field`` names where
    the result lands on the effect (``target`` | ``entity`` | ``refs.<name>``).
    """
    element: str
    candidates: list
    count: int | None
    field: str
    effect: Effect
    sfx_name: str = ""
    sfx_description: str = ""
    step_index: int = 0
    source_kind: str = ""
    source_id: str = ""
    source_sfx_id: str = ""
    answers_so_far: list = field(default_factory=list)
    # Immediate effects that come after this blocked effect; applied in order
    # once the choice resolves (sequential execution).
    continuation: list[Effect] = field(default_factory=list)

@dataclass
class PendingSfxLoop:
    """A rule that would run again for the change it is already handling.

    An automated loop: the rule's own effect caused another event *of the change
    it is applying to* — a trait it steps up, a challenge it fills. Instead of
    recursing, or silently refusing, the round is offered to the table: an
    accidental loop cannot decide game state on its own, and a deliberate cascade
    can be walked one round at a time.

    Carries the event so the answer can re-run **this rule for this moment**
    (``resolveSfxLoop``); the rule's conditions and targets are re-resolved from
    live state, so a round that has become impossible simply does nothing.
    """
    sfx_id: str
    sfx_name: str
    entity_id: str
    universe: str
    event_type: str
    context: dict = field(default_factory=dict)
    sfx_description: str = ""
    #: Which round this would be. The first already ran, so the first prompt is
    #: round 2 — and it is shown to the table, because "the 4th time" reads very
    #: differently from "again".
    iteration: int = 2

@dataclass
class EventOutcome:
    """Result of processing an event through the effects engine.

    ``applied`` are immediately-applied effects. ``pending`` are immediate
    effects with a ``{choose_*}`` target that were skipped and need user
    resolution before they can be applied. ``structured`` are effects whose
    ``target_spec``/``refs`` hit a ``choose`` step and carry the pre-resolved
    candidate set for the picker. ``loops`` are rules that would re-enter the
    change they are already handling, offered to the table rather than recursed.
    """
    applied: list[Effect] = field(default_factory=list)
    pending: list[PendingSfxEffect] = field(default_factory=list)
    structured: list[StructuredChoice] = field(default_factory=list)
    loops: list[PendingSfxLoop] = field(default_factory=list)
