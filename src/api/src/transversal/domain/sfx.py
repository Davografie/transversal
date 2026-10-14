"""Sfx — split out of src/api/src/transversal/domain/__init__.py."""

from enum import Enum

from pydantic import BaseModel
from pydantic import Field
from pydantic import model_validator
from transversal.services.target_spec import TargetSpec
from typing import Optional
from transversal.domain.effects import (
    Condition,
    Effect,
    EffectDuration,
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

    ``element``/``cardinality`` are the author's **declared type**, and they exist
    for one job: a roll table may **reserve** a name — a type and no path — so every
    row assigning that name is checked against it rather than trusted. Without a
    declared type a name's type is whatever path was written for it, so the same
    name can be ``location/one`` on one row and ``location/many`` on another and
    nothing objects ([[B285]]). Empty on both means "trace the path", which is what
    every SFX declaration does — a rule has no layer that could check it.
    """

    name: str
    spec: Optional[TargetSpec] = None
    #: The type the author states for this name: an element from the target catalog
    #: (``location``, ``entity``, …) and the cardinality it resolves to. Set on a
    #: **reservation** (a table's typed slot) and, optionally, beside a path to
    #: have the trace checked against what was intended.
    #:
    #: Read through ``services.roll_table.is_reservation`` / ``declared_type_of``,
    #: which is the one definition of what the two fields mean — a second reader
    #: here would be a second opinion.
    element: str = ""
    cardinality: str = ""


class ReachFlavour(str, Enum):
    """How a reach declaration relates the owners its path yields to the rule.

    ``GRANTED`` — they simply *have* it: available from them, no learn-chip.
    ``OFFERED`` — they are *offered* it as a chip and may take it.
    """
    GRANTED = "granted"
    OFFERED = "offered"


class ReachDeclaration(BaseModel):
    """One way this rule reaches owners: a targeting path plus the relationship.

    The path **yields the owners** — it is a *selector*, not a gate, so there is
    no per-candidate question left to ask. ``Source`` declares the element every
    path must land on, and stays the seed the rule's other fields start from.

    Declarations combine with **OR** (the union is the reach), and where an owner
    is both granted and offered, **granted wins** — they simply have it. The
    hand-picked lists stay as the static form of the same two relationships
    (``Trait.possible_sfx_ids`` = offered, ``default_sfx_ids`` = granted).
    See [[Dynamic SFX Reach]].
    """

    spec: TargetSpec
    flavour: ReachFlavour = ReachFlavour.OFFERED


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
    # How this rule **reaches owners**, beyond the hand-picked lists a trait
    # declares. Each declaration is a targeting path plus a flavour; the path
    # yields the owners, so it is a *selector* and not a gate — the old
    # per-candidate acquire path is gone ([[Dynamic SFX Reach]]). Resolved
    # read-only at read time; nothing is written onto anyone.
    #
    # ``Source`` above declares the element *every* path must land on, which is
    # what keeps a path that ends somewhere else from being a reach declaration.
    reach: list["ReachDeclaration"] = Field(default_factory=list)
    # Named values resolved from the world **before the condition gate**, in
    # declaration order — so a condition may read them, a later binding may start
    # from an earlier one, and a flat `{name}` field means the same thing
    # everywhere. Resolution lives in
    # `services.effects_engine.firing.bind_declared`; this is only the
    # declaration. (The runtime scope it fills is called `bindings`.)
    bound_variables: list["BoundVariable"] = Field(default_factory=list)
    effects: list[Effect] = Field(default_factory=list)
    conditions: list["Condition"] = Field(default_factory=list)
    # How long the SFX stays armed once triggered. **Nothing is authored by
    # default** — this used to default to one roll, which the editor then wrote
    # back on every save, so 42 of 46 rules carried a value nobody had set and
    # could not see (`sfx-gift` showed "Duration 1 roll" in the Active rail for a
    # rule whose effects are both immediate, where the duration does nothing).
    #
    # Its only reader is the arming of **roll-timing** effects: `_split_duration`
    # takes a ``rolls`` timer as the roll budget and any other timer
    # (``beat``/``scene``/``session``/a state-change event) as a boundary that
    # drops the rule. With no duration there is therefore **no roll limit** — the
    # rule stays armed until something else drops it — which is the honest meaning
    # of "the author set nothing", and the panel now says so.
    duration: Optional["EffectDuration"] = None

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
