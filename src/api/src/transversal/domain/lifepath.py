"""Lifepath — split out of src/api/src/transversal/domain/__init__.py."""

from pydantic import BaseModel
from pydantic import Field
from typing import Optional
from transversal.domain.effects import Condition, Effect
from transversal.domain.enums import (
    DieType,
)
from transversal.domain.sfx import BoundVariable


class DiscoveryBlock(BaseModel):
    """Conditions for discovering a hidden life path.  Any one condition met → discovered."""
    at_location: list[str] = Field(default_factory=list)
    knows_entity: list[str] = Field(default_factory=list)
    possesses_trait: list[str] = Field(default_factory=list)
    has_trait_rating: dict[str, DieType] = Field(default_factory=dict)
    has_relationship: list[str] = Field(default_factory=list)

class LifePathBinding(BaseModel):
    """A path's overlay on **one row** of a table it wraps.

    The wrapper model, in one object. A roll table is pure content: it says what
    a row *is* and may carry its own effects. A life path wraps that table and
    superimposes meaning on chosen rows, without editing the table — so the same
    table serves many paths, and each row keeps one identity while meaning
    different things to each.

    **Flow is structure here, not effects.** What used to be ``life_path``-type
    effects on a row (``next_step`` / ``muster`` / ``enroll`` / ``draft``) is
    declared by the path instead, split by what it actually is — measured against
    the live content 2026-10-09, which decides the split rather than taste:

    * ``next`` — the **step id** in this path to advance to. An edge; ``""``
      leaves the path.
    * ``exit_kind`` — what leaving *means*, when ``next`` is empty. The content
      settled this: all 15 rows carrying ``muster``/``force_muster`` carry
      **nothing else**, and none of them carries a ``next_step``. They are not
      effects that end a term, they are the destination — a terminal with a kind.
      ``""`` = merely ended · ``"muster"`` / ``"force_muster"`` = mustered out
      honourably / dishonourably · ``"draft"`` = handed to ``exit_path``.
    * ``enroll`` — taking this row admits the character to the path. Always
      per-row, never per-path: in ``rt-verdant-qualify`` the *Accepted* rows enrol
      and the *Rejected* rows do not, so a path-level flag would enrol the
      rejected. It is also never a destination — ``enroll`` appears on a row 24
      times and **never once without a move** — which is why it is a flag on the
      edge rather than an edge of its own.
    * ``effects`` — the delta, applied *after* the row's own effects. Ordinary
      effects only; flow verbs do not appear here.
    """
    key: str
    next: str = ""  # step id within this path; "" leaves the path
    exit_kind: str = ""  # "" | "muster" | "force_muster" | "draft"
    exit_path: str = ""  # the destination when exit_kind == "draft"
    enroll: bool = False
    effects: list[Effect] = Field(default_factory=list)

class LifePathStep(BaseModel):
    """One position in a path — a wrapped table, or effects and nothing else.

    ``id`` is the step's identity, not the table's — which is what lets a path
    wrap the same table twice (two steps, one table), and lets a step live on
    after its table being re-pointed.

    **``table_id`` may be empty, and that is a different kind of step** ([[B314]]):
    an **effects-only step**. Instead of rolling a table and hanging meaning on
    its rows, the step applies its own ``effects`` once and follows its own
    ``next``. That is what makes a step able to *trigger effects* — and the
    player's choice, where there is one, comes from a ``choose`` step in an
    effect's targeting path rather than from pre-authored rows.

    It is empty rather than ``None`` because that is the convention the rest of
    this model already uses for "absent" (``LifePath.entry_step``,
    ``LifePathStep.next``, ``LifePathBinding.next``) — and a step with no table is
    still a step: it has an ``id``, a ``next`` and a place in the graph.
    """
    id: str
    #: The roll table this step wraps. ``""`` = no table: an effects-only step.
    table_id: str = ""
    label: str = ""
    #: Where a row with no binding of its own goes. ``""`` = the term ends.
    next: str = ""
    bindings: list[LifePathBinding] = Field(default_factory=list)
    #: Effects that apply to **this step whatever row resolved** — once per
    #: activation, after the row's own effects and the binding's delta, in the same
    #: scope. The counterpart of ``next``: that is the step's default *flow*, this
    #: is its default *behaviour*, so a path does not have to repeat an identical
    #: effect on every binding.
    #:
    #: It reads the whole scope, so it may consume a name the resolved row exposed.
    #: **Consume it as a targeting path** — ``target_spec``/``owner_spec`` with a
    #: ``select variable <name>`` step — because that form resolves to *zero
    #: targets* when no row exposed the name, and ``_apply_spec_effect`` then applies
    #: the effect zero times: a clean no-op. Author it once; it runs where it applies.
    #:
    #: A flat ``{name}`` in ``target``/``result`` is safe now, but only because the
    #: engine refuses it: `_substitute_effect_context` reports the names it could
    #: not fill and the dispatch **skips** such an effect, logging it and noting it
    #: on the outcome ([[B282]]). It used to run against the literal string
    #: ``"{name}"`` — a junk target, silently. Prefer the path: a skip is a visible
    #: failure, which is better than a wrong write but worse than a clean no-op.
    effects: list[Effect] = Field(default_factory=list)
    #: Names this **step** supplies to the tables it wraps ([[B290]]), resolved
    #: before the table's own declarations so a *shared* table can read the context
    #: its caller gives it. Same shape as a roll table's ``bound_variables``; a step
    #: is the specific caller, the table is the shared content.
    #:
    #: **Declarations only**, deliberately: a step does not reserve a typed slot for
    #: its rows to fill in v1 (that shape is identical and can follow), so a
    #: pathless declaration here is half-typed input and is dropped.
    bound_variables: list[BoundVariable] = Field(default_factory=list)

class LifePath(BaseModel):
    """A life path — **a layer over roll tables**, not an owner of them.

    A path names the tables it wraps (``steps``) and what each of their rows means
    *to this path* (``LifePathBinding``). The tables stay reusable content: this
    reverses the old direction, where ``RollTable.life_path`` said which path a
    table belonged to and the flow lived in the entries' ``next_step`` effects.

    Scope is now derived rather than declared — a table wrapped by no path is
    shared/fundamental, one wrapped by a path is that path's — so the same table
    can serve several paths at once.

    Two gates, deliberately separate (the human, 2026-09-23):

    * ``discovery`` — has the character found out this path **exists**? A one-time
      reveal, ORed across its conditions.
    * ``conditions`` — may the character **walk** it *now*? An entity-scoped gate
      evaluated with the effects condition model ([[B194]]), all-of, reusing
      ``services/lifepath_walkability.py``. Empty → always walkable.
    """
    id: str
    name: str
    universe: str
    description: str = ""
    #: Step id the term begins at. Empty on a path that has not been migrated yet.
    entry_step: str = ""
    steps: list[LifePathStep] = Field(default_factory=list)
    #: Names the **path** supplies to the tables its steps wrap ([[B290]]), resolved
    #: before the step's and the table's declarations — outermost first, because a
    #: shared table may be wrapped by several paths and must read whatever context
    #: *this* term gives it. A path-level value therefore wins over a shared table's
    #: declaration of the same name; mark a declaration ``override`` to replace the
    #: table's outright rather than merely shadow it.
    #:
    #: Declarations only in v1 — see ``LifePathStep.bound_variables``.
    bound_variables: list[BoundVariable] = Field(default_factory=list)
    discovery: Optional[DiscoveryBlock] = None  # null → always visible
    conditions: list[Condition] = Field(default_factory=list)  # empty → always walkable
    #: **Deprecated** — the pre-wrapper entry table. Read only as a fallback while
    #: content migrates, and only to synthesise a single-table step. Replaced by
    #: ``entry_step`` + ``steps``.
    entry_table_id: str = ""

class Enrollment(BaseModel):
    """A character's membership in a faction's life path — **held by a body**.

    ``projection_id`` is the body that served the term ([[B271]]). Membership is a
    fact about a life lived in a universe, not about the character across all of
    them: two bodies may serve the same path without colliding, and mustering in
    one must not mark the other mustered. Empty means the membership predates
    per-body scoping and is read as belonging to whichever body is asking.
    """
    faction_id: str
    path_id: str
    projection_id: str = ""
    mustered: bool = False
    mishap_muster: bool = False

class PendingTerm(BaseModel):
    """In-progress life path term checkpoint.

    Holds where the entity is in the path's steps so a term can be resumed
    mid-way (reload / another device).

    ``current_step_id`` is the checkpoint. ``current_table_id`` is **derived** —
    the table that step wraps — and is kept because the surfaces read it to know
    what to display; it is not independent state.

    ``continuation`` / ``return_map`` are vestigial: they existed so a *shared*
    table could return to whichever path called it, which the wrapper makes
    unnecessary (a path declares its own ``next``). No live content ever used
    them — measured 2026-10-09: 0 of 103 ``next_step`` targets are tokens — so
    the executor no longer reads them. Kept as empty fields for now because
    ``LifePathWizard``'s queries still select them; remove with [[ui-ux]] when
    that wizard is retired.
    """
    faction_id: str = ""
    path_id: str = ""
    #: The body serving this term ([[B271]]). The term is *lived* by a projection
    #: in a universe, so this is what keys it on the entity and what decides which
    #: enrollments and mustering it owns.
    projection_id: str = ""
    current_step_id: str = ""
    current_table_id: str = ""  # derived from current_step_id
    continuation: list[str] = Field(default_factory=list)  # vestigial
    return_map: dict[str, str] = Field(default_factory=dict)  # vestigial
