"""Sfx — split out of src/api/src/transversal/domain/__init__.py."""

from pydantic import BaseModel
from pydantic import Field
from pydantic import model_validator
from transversal.services.target_spec import TargetSpec
from typing import Optional
from transversal.domain.effects import (
    Condition,
    Effect,
    EffectDuration,
    Timer,
)
from transversal.domain.enums import (
    ConditionType,
)
from transversal.domain.traits import (
    derive_arming_scope,
    derive_placement,
)


class BoundVariable(BaseModel):
    """A named value the rule resolves from the world *before it does anything*.

    The author names a thing once ("their cultivation stage") with the target
    builder, and every later reader — a condition's path, an effect's path, or a
    flat ``{name}`` field — reads the same name. Distinct from a step's inline
    ``output`` (the 💡 on a path): that binds as a *side effect* of a path
    authored for another purpose, so it cannot exist before the conditions and
    cannot be read by them.

    ``name`` is the author's; ``spec`` resolves against the resolved activation
    source, so ``select source`` is the usual seed.
    """

    name: str
    spec: TargetSpec


class SFX(BaseModel):
    """SFX registry entry.

    Stored in the `sfxs` collection. ``trigger`` names the single activation
    axis — an auto-fire event, ``manual``, or a consequence menu; ``conditions``
    filter which instance of that activation applies (target/threshold/narrative).
    """
    id: str
    name: str
    description: str = ""
    trigger: str
    # Declarative owner type — what kind of thing carries this SFX (its
    # activation source). One of the ``SOURCE_KINDS`` keys in
    # ``target_catalog`` (``trait_setting``/``traitset_setting``/``entity``/
    # ``projection``); ``None`` = bucket/passive (no meaningful origin).
    source_kind: Optional[str] = None
    # Activation surface: ``auto`` (event-driven), ``sheet`` (owner card),
    # ``menu`` (post-roll consequence menu). ``None`` = derive from ``trigger``.
    placement: Optional[str] = None
    # Listener scope: who the armed SFX listens to — ``self`` (the triggering
    # entity), ``global`` (every entity's rolls), or ``listener_spec`` (a set
    # resolved from ``listener_spec``). ``None`` = derive from ``trigger``
    # (``on_session_start`` → global, else self).
    arming_scope: Optional[str] = None
    # Targeting path resolving the listener *set* when ``arming_scope`` is
    # ``listener_spec`` (e.g. ``select self → navigate relationships → filter
    # type == curse_bind → navigate target``).
    listener_spec: Optional[TargetSpec] = None
    # A **gate on acquiring** this rule, not on using it: a path seeded at the
    # thing being unlocked (`select source` = the trait instance), resolved when
    # someone tries to take it. Passes iff it resolves non-empty and error-free —
    # the same reading a `TARGET_PATH` condition gets. `None` = acquirable
    # anywhere, which is the common case.
    #
    # Deliberately not a condition: conditions are evaluated when the rule *fires*
    # as well as when it is offered, so gating with one would take the rule away
    # again the moment its bearer left the place they learned it.
    acquire_spec: Optional[TargetSpec] = None
    # Whether the rule applies to the surfaces its acquisition path targets
    # **without being learned first** ([[B131]]).
    #
    # `Trait.possible_sfx_ids` is the declaration: it says which trait offers the
    # rule, and with this flag set every *instance* of that trait simply has it —
    # no learn-chip, no `sfx_ids` entry on the instance. Unset (the default, and
    # what every existing rule means) it must be taken before it can be used.
    #
    # The acquire gate still bounds *where* it applies when one is declared: "only
    # in the Verdant Steps" is a fact about the rule's reach, not about learning,
    # and going implicit must not quietly make it universal.
    implicit: bool = False
    # Named values resolved from the world **before the condition gate**, in
    # declaration order — so a condition may read them, a later binding may start
    # from an earlier one, and a flat `{name}` field means the same thing
    # everywhere. Resolution lives in
    # `services.effects_engine.firing.bind_declared`; this is only the
    # declaration. (The runtime scope it fills is called `bindings`.)
    bound_variables: list["BoundVariable"] = Field(default_factory=list)
    effects: list[Effect] = Field(default_factory=list)
    conditions: list["Condition"] = Field(default_factory=list)
    # How long the SFX stays in effect once triggered (the in-memory effective
    # tracker). Default = one roll. ``rolls``/``beat``/``scene``/``session`` or
    # a state-change event (``location_changed``/``trait_updated``) timer
    # extends it; ``None`` = indefinite (until cleared).
    duration: Optional["EffectDuration"] = Field(
        default_factory=lambda: EffectDuration(timers=[Timer(event="rolls", remaining=1)])
    )

    @model_validator(mode="before")
    @classmethod
    def _fold_legacy_menu_context(cls, data):
        """Migrate ``menu_context`` into ``trigger`` (single activation axis)."""
        if isinstance(data, dict) and data.get("menu_context"):
            data = {**data}
            data["trigger"] = data["menu_context"]
            data.pop("menu_context", None)
        return data

    @model_validator(mode="before")
    @classmethod
    def _fold_legacy_limit(cls, data):
        """Migrate the old ``limit`` string into a NARRATIVE condition."""
        if isinstance(data, dict) and data.get("limit"):
            limit = data["limit"]
            data = {**data}
            data.pop("limit", None)
            if not data.get("conditions"):
                data["conditions"] = [
                    Condition(type=ConditionType.NARRATIVE, narrative=limit)
                ]
        return data

    @property
    def limit(self) -> str:
        """Backward-compatible read of the narrative limit."""
        for c in self.conditions:
            if c.type == ConditionType.NARRATIVE and c.narrative:
                return c.narrative
        return ""

    @property
    def effective_placement(self) -> str:
        """The activation surface, derived from ``trigger`` when unset."""
        return self.placement or derive_placement(self.trigger)

    @property
    def effective_arming_scope(self) -> str:
        """The listener scope, derived from ``trigger`` when unset."""
        return self.arming_scope or derive_arming_scope(self.trigger)

class SfxOwner(BaseModel):
    """A named SFX owner bucket.

    Stored in the `sfx_owners` collection. Ownership lives on the owner side:
    these buckets collect SFX ids that are available by category rather than by
    a single entity/trait/projection. Seeded with `table` (everyone) and `gm`
    (GM-context only).
    """
    id: str
    sfx_ids: list[str] = Field(default_factory=list)
