"""Effects — split out of src/api/src/transversal/domain/__init__.py."""

from pydantic import BaseModel
from pydantic import Field
from transversal.services.target_spec import TargetSpec
from typing import Optional
from transversal.domain.enums import (
    ConditionType,
    EffectTiming,
    TimerCombine,
)


class TargetRef(BaseModel):
    """One named reference an effect resolves against game state.

    ``value`` is the concrete id after resolution — or, before resolution, a
    literal id / ``self`` / ``{choose_*}`` / ``{random:*}`` token. ``spec`` is
    the structured targeting pipeline that resolves ``value`` at fire time
    (None = literal). ``scope`` narrows runtime choice for ``{choose_*}`` /
    ``{random:*}``. The ref's element type is declared by the action's
    ``EffectActionMeta.refs`` entry, not stored per effect.
    """
    value: str = ""
    spec: Optional[TargetSpec] = None
    scope: Optional[str] = None

class Effect(BaseModel):
    """A single operational effect — shared by SFX and life-path consequences.

    Sign (cost vs benefit) is derived from (type, action); it is not stored.
    """
    timing: EffectTiming = EffectTiming.IMMEDIATE
    type: str
    action: str
    target: str = ""
    entity: str = ""  # explicit subject entity; "" or "self" = the applyEffects entity
    result: Optional[str] = None
    target_scope: Optional[str] = None  # narrowing hint for runtime target choice
    entity_scope: Optional[str] = None  # narrowing hint for runtime entity choice
    target_filter: dict = Field(default_factory=dict)  # candidate field predicates, e.g. {"starter_location": True}
    die_filter: dict = Field(default_factory=dict)  # roll-die predicates for roll-deferred effects, e.g. {"role": None}
    conditions: list["Condition"] = Field(default_factory=list)  # per-effect gate (reuses the SFX condition model)
    negative: bool = False  # polarity of trait-grant effects: true = negative trait (opponent uses it)
    context: dict = Field(default_factory=dict)  # e.g. relationship description
    duration: Optional["EffectDuration"] = None  # when set, schedules the inverse effect on expiry
    # Structured targeting pipeline (the new model). None means the effect still
    # uses the legacy ``target`` string and is lazily migrated on read.
    target_spec: Optional[TargetSpec] = None
    # Structured subject resolution (who the effect applies to). None means the
    # effect still uses the legacy ``entity`` string.
    entity_spec: Optional[TargetSpec] = None
    # Named references — the multi-target model. Each key is a declared ref name
    # (see ``EffectActionMeta.refs``); ``target``/``entity`` remain as the
    # legacy single-reference fallback until the Step-3 migration removes them.
    refs: dict[str, TargetRef] = Field(default_factory=dict)
    #: The author's name for *this step's result* ("beast"), bound into the
    #: activation scope so a later effect can `select variable {beast}` — when the
    #: action declares an ``output_element`` (what it produces). Empty = unnamed.
    output: Optional[str] = None

class Timer(BaseModel):
    """One countdown within an effect duration.

    ``event`` names the advancement signal that decrements it: ``"beat"``,
    ``"scene"``, ``"session"``, or any state-change event (e.g.
    ``"location_changed"``). ``remaining`` is the countdown; ``0`` (or event
    ``"immediate"``) fires on the next advancement pass.
    """
    event: str = "scene"
    remaining: int = 0

class EffectDuration(BaseModel):
    """Timers + combine that turn a forward effect into a temporary one."""
    timers: list["Timer"] = Field(default_factory=list)
    combine: TimerCombine = TimerCombine.FIRST_TO_FIRE

class ScheduledEvent(BaseModel):
    """A persisted row in the central timer store.

    ``target_type`` + ``target_id`` identify the owner (entity or trait setting)
    the effect applies against; resolved at fire time so a deleted target is a
    no-op.

    ``kind`` says what the row is for:

    - ``"revert"`` — an undo timer: applies its effect when the timers expire.
    - ``"pending"`` — a deferred forward effect: applies when the timers expire.
    - ``"hold"`` — the undo of an effect that had no timer. It never fires on its
      own: it is applied when the activation is **ended** early, and dissolved
      when the activation *commits* — a delayed part of it fires, or the dice are
      rolled. Until then the whole activation can be taken back.
    """
    id: str
    target_type: str = "entity"           # "entity" | "trait_setting"
    target_id: str = ""                   # entity id or trait-setting id
    effect: "Effect"                     # the revert (or deferred) effect
    timers: list["Timer"] = Field(default_factory=list)
    combine: TimerCombine = TimerCombine.FIRST_TO_FIRE
    source_sfx_id: Optional[str] = None
    kind: str = "revert"                  # "revert" | "pending" | "hold"
    created_at: str = ""                  # ISO timestamp; orders a cancel's reverts

class ConsequenceOption(BaseModel):
    """A selectable entry in the post-roll consequence menu.

    Authored directly on entities (location moves), registered as base moves,
    or derived from ``on_consequence`` SFX. Choosing one applies its effects.
    """
    id: str
    label: str
    side: str = "player"  # "player" | "gm" | "either"
    effects: list[Effect] = Field(default_factory=list)
    source: str = "base"  # "base" | "entity" | "sfx"

class Condition(BaseModel):
    """A configurable, automatically-evaluated gate or limit.

    Parallel to Effect: authored once, evaluated against an entity's state.
    """
    type: ConditionType = ConditionType.ALWAYS
    subject: str = ""                # "" = current entity; else literal id or {variable}
    target: str = ""                  # trait / location / entity id (or {variable})
    # Enum filters take *several* values (any-of). `target` stays for one, and for
    # everything already authored; readers use `target_values()` so the two can
    # never be read inconsistently.
    targets: list[str] = Field(default_factory=list)
    value: Optional[str] = None       # threshold, e.g. rank number
    operator: str = ">="              # numeric comparator for HAS_RAZMERIT ("<", "<=", "==", "!=", ">=", ">")
    narrative: str = ""               # human-readable fallback text
    spec: Optional[TargetSpec] = None  # TARGET_PATH: a targeting path (seeded by `select source`) resolved non-empty

    def target_values(self) -> list[str]:
        """Every value this condition matches on, one or several.

        The single `target` and the list `targets` are one idea: an enum filter
        accepts one value or several, and several means *any of*.
        """
        values = [v.strip() for v in (self.targets or []) if str(v).strip()]
        if not values and self.target:
            values = [self.target.strip()]
        return values
