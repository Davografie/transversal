"""Life-path term executor — traverse a path's steps and apply effects.

A term walks the **steps a life path declares**. A step usually wraps a roll
table, and the path's binding for the row that resolved supplies the delta and
the next step; the table itself stays pure content — it does not know it is in a
path, and the same table may appear in several paths or in none.

**A step may also wrap no table at all** ([[B314]]). An *effects-only* step has an
empty ``table_id``: it applies its own effects once and follows its own ``next``,
so a step can trigger effects directly instead of routing them through authored
rows. Where such a step needs the player to decide something, the choice is a
``choose`` step in an effect's targeting path — and it is **answered**, not
reported and dropped: the step holds still with the question pending, and the
answer re-resolves only the effects that asked.

Two flows are therefore possible, and the difference matters:

* **Wrapped** (a path with ``steps``): the edge comes from the binding
  (``LifePathBinding.next``), or the step's default when the row is unbound. Any
  ``next_step`` effect still sitting in the entry is **ignored** — the path owns
  the graph. Term verbs (``muster`` / ``force_muster`` / ``enroll`` / ``draft``)
  are ordinary effects and always run, because they are row outcomes.
* **Unwrapped / unmigrated** (a path with no steps, or a table rolled on its own):
  the legacy behaviour, where ``next_step`` effects in the entry move the term.
  This is what keeps pre-wrapper content working between the code landing and
  ``migrate_lifepath_wrapper`` running.

**A term belongs to a body** ([[B271]]). It is served by a projection, in that
projection's universe, and it grants *that* body's traits and membership — so the
checkpoint is keyed by projection (``Entity.pending_terms``) and every entry point
resolves which body is asking (``services/lifepath_scope``). Advancing a term
while playing another body is what this prevents; it was previously possible, and
the executor never checked a universe.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from transversal.domain import (
    Effect,
    EffectTiming,
    Enrollment,
    Entity,
    LifePath,
    LifePathStep,
    OutcomeTier,
    PendingTerm,
)
from transversal.services.effects_applier import apply_effects, EffectsResult
from transversal.services.lifepath_scope import (
    enrollments_for,
    pending_term_for,
    resolve_projection_id,
    UNSCOPED,
)
from transversal.services.roll_table import entry_key_for, resolve_applicable_entry
from transversal.services.effect_refs import target_value

log = logging.getLogger("transversal.lifepath")

#: The name a life path declares to say **which faction its enrolments join** ([[B41]]).
#:
#: A term begun without a faction — the case for every path no faction offers — still
#: records a cursor, because the cursor needs nothing else. But an enrolling row does
#: need somewhere to attach the membership, and the *path* is the party that knows:
#: the caller may not ([[B290]] is how it says so). One name, in one place, so the
#: executor and the panel's hint cannot drift — the panel is told to say `sect`.
ENROLLING_FACTION_VARIABLE = "sect"


class StepResolution:
    """One answered choice, echoed back to the step that raised it ([[B314]]).

    The step holds still while a ``choose`` is pending, so answering is *not* a
    second resolve of the whole step: this names the one effect that asked, its
    field and the answer — and the executor re-resolves only that effect, so an
    effect that already applied is never applied twice.
    """

    __slots__ = ("effect", "field", "answers")

    def __init__(self, effect: Effect, field: str = "target",
                 answers: Optional[dict] = None) -> None:
        self.effect = effect
        self.field = field or "target"
        #: ``{step index in the targeting path: [chosen ids]}``, the same shape the
        #: targeting resolver resumes with.
        self.answers = answers or {}


def find_step(lp: Optional[LifePath], step_id: str) -> Optional[LifePathStep]:
    """The step ``step_id`` names — by step id, or by the table it wraps.

    Two generations of checkpoint reach here and both must resolve:

    * a **step id**, which is what the wrapper writes; and
    * a bare **table id**, which is what a term stored before ``current_step_id``
      existed holds. The wrapper migration then gave every path steps, so the
      "no steps means legacy" case below stopped covering those checkpoints — and
      resolving one failed with ``step 'rt-…' not found in path 'lp-…'``. The
      bridge is the table→step mapping, not the absence of steps.

    A step id is checked first, so a table id can never shadow a step. A table
    wrapped twice is ambiguous by construction; the first step wins, which matches
    the migration that wraps each table once per path.

    An **effects-only step** has no table, so it can only be found by its step id —
    the table bridge skips it, or an empty table id would match every empty
    ``step_id`` ([[B314]]).
    """
    if lp is None or not step_id:
        return None
    for step in lp.steps:
        if step.id == step_id:
            return step
    for step in lp.steps:
        if step.table_id and step.table_id == step_id:
            return step
    if not lp.steps:
        # A path with no steps at all: pre-wrapper content whose flow still lives
        # in its entries' effects. One synthesised step, no bindings.
        return LifePathStep(id=step_id, table_id=step_id)
    return None


def entry_step(lp: LifePath) -> Optional[LifePathStep]:
    """The step a term begins at, whichever generation the path is from."""
    if lp.entry_step:
        return find_step(lp, lp.entry_step)
    if lp.steps:
        return lp.steps[0]
    if lp.entry_table_id:  # deprecated pre-wrapper field
        return LifePathStep(id=lp.entry_table_id, table_id=lp.entry_table_id)
    return None


def start_term(entity: Entity, faction_id: str, path_id: str, repo,
               projection_id: Optional[str] = None) -> PendingTerm:
    """Begin (or restart) a term in a life path, for one body.

    ``projection_id`` names the body serving it; omitted, the acting body is
    resolved (see ``services/lifepath_scope``). The term replaces any the *same*
    body already had — another body's term is untouched.

    **``faction_id`` may be empty**, and that is the point ([[B41]]): the checkpoint
    is a *cursor* — ``path_id`` + ``current_step_id`` — and a cursor needs no faction.
    The faction answers a different question, *whose sect this term serves*, and only
    one thing needs the answer: an **enrolling** row, which creates the
    ``entity → faction`` membership that rank and tenure hang off. So a path no
    faction offers can now be walked, and when its enrolling row resolves the faction
    is resolved then — the caller's if one was given, else the path's own ``{sect}``
    (see ``enrolment_faction``). With neither there is nothing to join, and the
    enrolment is skipped rather than pointed at a faction that does not exist.
    """
    lp = repo.get_lifepath(path_id)
    if lp is None:
        raise ValueError(f"LifePath '{path_id}' not found")
    step = entry_step(lp)
    if step is None:
        raise ValueError(f"LifePath '{path_id}' has no entry step")

    pid = resolve_projection_id(entity, repo, projection_id)
    pt = PendingTerm(
        faction_id=faction_id or "",
        path_id=path_id,
        projection_id=pid,
        current_step_id=step.id,
        current_table_id=step.table_id,
    )
    if getattr(entity, "pending_terms", None) is None:
        entity.pending_terms = {}
    entity.pending_terms[pid] = pt
    return pt


def resolve_step(
    entity: Entity,
    repo,
    *,
    projection_id: Optional[str] = None,
    roll: Optional[int] = None,
    tier: Optional[OutcomeTier] = None,
    index: Optional[int] = None,
    engine=None,
    resolutions: Optional[list[StepResolution]] = None,
) -> dict:
    """Resolve the current step, apply its effects, and advance.

    Immediate mutation effects apply and persist in-place; non-immediate ones
    (``end_of_beat`` / ``end_of_scene`` / ``end_of_session`` / ``after_beats`` /
    ``on_condition``) are queued into ``engine``. Flow effects are always
    immediate. Returns a summary dict with ``done``, ``pending_term``, and any
    pending target choices.

    **Two calls, one step, when the step asks a question.** A ``choose`` in an
    effect's targeting path cannot be answered in the same breath as asking it, so
    the first call applies whatever resolved fully and returns the question with
    ``done: False`` — the term **stays on this step**. The caller then answers by
    passing ``resolutions``, and *only the effects named there* are re-resolved, so
    nothing applies twice. The step advances once nothing is pending.

    An **effects-only step** (``table_id`` empty — [[B314]]) resolves the same way
    with the table half absent: no row, no binding, and its own effects are the
    whole payload.
    """
    pid = resolve_projection_id(entity, repo, projection_id)
    pt = pending_term_for(entity, pid)
    if pt is None:
        return {"done": True, "error": "no pending term"}
    step_id = pt.current_step_id or pt.current_table_id
    if not step_id:
        return {"done": True, "error": "no pending term"}

    # Adopt a pre-B271 checkpoint: it is the entity's single legacy term and this
    # body is the one playing it, so it has to be stored under a key or the flow
    # helpers — which ask whether their term is still the stored one — would treat
    # it as already ended. `migrate_lifepath_terms_to_bodies` is what assigns it to
    # the right body by path universe; this only keeps it resolvable until then.
    terms = getattr(entity, "pending_terms", None)
    if terms is None:
        entity.pending_terms = terms = {}
    if terms.get(pt.projection_id) is not pt:
        pt.projection_id = pid
        terms[pid] = pt

    lp = repo.get_lifepath(pt.path_id)
    step = find_step(lp, step_id)
    if step is None:
        return {"done": True, "error":
                f"'{step_id}' is neither a step of path '{pt.path_id}' nor a table "
                f"it wraps"}

    # Heal a pre-wrapper checkpoint on the way through: it named a table, and now
    # names the step wrapping it, so the next resolve is by identity rather than
    # by lookup. Persisted with the rest of the entity by `_persist`.
    if pt.current_step_id != step.id:
        pt.current_step_id = step.id
        pt.current_table_id = step.table_id

    # `wrapped` is what separates the two flow regimes: a path that declares steps
    # owns its graph, and the entries' own flow effects (if any are left) are then
    # ignored.
    wrapped = bool(lp is not None and lp.steps)

    # ── The step's table, or its absence ──────────────────────────────────────
    # A step with **no table** is an effects-only step ([[B314]]): the step *is*
    # the content, so there is no row to resolve, no binding to find and nothing
    # to split into row/delta effects. Everything downstream is written to work
    # with that — `table`/`entry`/`binding` stay `None` and the effect list is
    # just the step's own.
    table = None
    entry = None
    key = ""
    binding = None
    row_mutations: list[Effect] = []
    row_flow: list[Effect] = []
    delta_mutations: list[Effect] = []
    delta_flow: list[Effect] = []

    if step.table_id:
        table = repo.get_roll_table(step.table_id)
        if table is None:
            return {"done": True, "error": f"table '{step.table_id}' not found"}

        # The entry the roll picked, or the previous one whose conditions hold, or
        # nothing — see `resolve_applicable_entry` ([[B179]]). Note it may hand back a
        # *different* row than the roll named, so the binding is looked up for the row
        # that actually ran.
        entry = resolve_applicable_entry(
            table, entity, repo, roll=roll, tier=tier, index=index,
            source=table, source_element="roll_table",
            # The caller's declaration layers ([[B290]]): the row's *conditions* must see
            # the same context its effect will, or a condition could test a name the path
            # supplies and the effect after it read something else.
            path=lp, step=step,
        )
        if entry is None:
            return {"done": True, "error": "no applicable entry resolved"}

        # The path's overlay on this row, if it has one.
        key = entry_key_for(table, entry)
        binding = next((b for b in step.bindings if b.key == key), None)

        # Append the outcome to the entity's historical record (append-only event log).
        repo.add_historical_record(
            entity.id,
            "roll_table",
            {
                "life_path_id": pt.path_id,
                "life_path_name": lp.name if lp is not None else pt.path_id,
                "step_id": step.id,
                "step_label": step.label,
                "table_id": table.id,
                "table_name": table.name,
                "scheme": table.scheme.value,
                "roll_source": table.roll_source.value,
                "entry_key": key,
                "entry_label": entry.label,
                "entry_tier": entry.tier.value if entry.tier else None,
                "bound": binding is not None,
                "index": index,
            },
            universe=entity.current_universe,
        )

        row_mutations = [e for e in entry.effects if e.type != "life_path"]
        row_flow = [e for e in entry.effects if e.type == "life_path"]
        delta = list(binding.effects) if binding is not None else []
        delta_mutations = [e for e in delta if e.type != "life_path"]
        delta_flow = [e for e in delta if e.type == "life_path"]
    else:
        # The step ran no table, and the record says so rather than naming an empty
        # table — a reader that groups by `record_type` would otherwise see a roll
        # table that does not exist.
        repo.add_historical_record(
            entity.id,
            "life_path_step",
            {
                "life_path_id": pt.path_id,
                "life_path_name": lp.name if lp is not None else pt.path_id,
                "step_id": step.id,
                "step_label": step.label,
                "effects_only": True,
            },
            universe=entity.current_universe,
        )
    # The **step's** own effects: authored once for the table rather than repeated
    # on every binding, and applied after both the row's and the binding's, so one
    # may read whatever they produced or exposed. Flow is deliberately not read
    # from here — a step's destinations are `next` and its bindings, which is what
    # keeps "flow is structure, not effects" true.
    #
    # An effect whose path names a variable the resolved row never exposed resolves
    # to nothing, and `apply_effects` applies an effect once per resolved target —
    # so it is a clean no-op rather than a failure. That is exactly what lets this
    # be written once for a table whose rows expose different things.
    step_mutations = [e for e in (getattr(step, "effects", None) or [])
                      if e.type != "life_path"]
    all_mutations = row_mutations + delta_mutations + step_mutations

    old_razmerit = entity.razmerit
    scheduled = 0

    # The names these effects may use: the ambient facts (the term's faction, this
    # table's *path* faction from the enrollment, the roll) plus whatever the table
    # declares for itself — and, for an effects-only step, the **path's and the
    # step's own** declarations, which is all it has. Sealed before the effects, so
    # a condition or effect reads the same scope.
    from transversal.services.effects_applier.datatypes import BINDINGS_CONTEXT_KEY
    from transversal.services.roll_table import table_bindings

    from transversal.services.effects_applier.datatypes import (
        SOURCE_CONTEXT_KEY, SOURCE_ELEMENT_CONTEXT_KEY,
    )

    # `table_bindings` takes the table as optional by construction (`getattr`
    # throughout), so an effects-only step resolves exactly the same layers minus
    # the table's and the row's.
    bindings = table_bindings(table, entity, repo, entry=entry,
                              roll=roll, tier=tier, index=index,
                              # The caller's names ([[B290]]), so a
                              # **shared** table reads the context
                              # this path's step gives it rather than
                              # hardcoding a faction.
                              path=lp, step=step)

    effect_context = {
        BINDINGS_CONTEXT_KEY: bindings,
        # The entry's effect is applied *from* its table, so the table is the
        # source: `select source` is the table, and `navigate life_path` reaches
        # the paths that wrap it. The table is no longer owned by one path, so
        # `_source` stays the table and the *path* is named by the pending term.
        # An effects-only step has no table to be, and says so by being empty
        # rather than by pointing at something arbitrary — `select source` then
        # resolves to nobody, which is the truth.
        SOURCE_CONTEXT_KEY: table,
        SOURCE_ELEMENT_CONTEXT_KEY: "roll_table" if table is not None else "",
    }
    source_kind = "roll_table" if table is not None else ""
    source_id = table.id if table is not None else ""

    # **Resolve each effect's named references before applying it.** `apply_effects`
    # resolves the *positional* specs (entity / result / owner / target), but a
    # named reference is `resolve_refs`' job — the engine calls it and this path
    # never did, so every step effect whose target was authored as a reference
    # (which is the authored form) silently resolved to nothing and applied as a
    # no-op. That is why a step's "create a relationship" did not create one.
    #
    # **A `choose` is no longer a dead end** ([[B314]]). A spec or ref that stops at
    # one is collected as a *structured* choice — with its candidates, so the
    # player can actually be asked — rather than reported as a bare kind and
    # dropped. See the two-call contract in the docstring.
    from transversal.services.effects_engine import resolve_effect_spec_choices
    from transversal.services.effects_engine.refs import resolve_refs
    from transversal.services.target_resolver import TargetContext

    structured: list = []
    ref_ctx = TargetContext(
        subject=entity, repo=repo,
        bindings=bindings,
        # The entry's effect is applied *from* its table, matching the source the
        # `effect_context` above declares, so `select source` means the same thing
        # in a reference as it does in a field.
        source=table, source_element=source_kind,
    )

    def _with_refs(effects: list, out: list) -> list:
        resolved: list = []
        for e in effects:
            resolved.extend(resolve_refs(e, ref_ctx, out))
        return resolved

    def _one_effect(effect: Effect, field: str, answers: dict) -> list:
        """Resolve one effect's spec/ref, appending any pending choice to `structured`."""
        applied, pending = resolve_effect_spec_choices(
            effect, field, answers, entity, repo,
            # The source is the **object**, not a `source_kind`: a step's source is
            # the table it wraps, and there is no `roll_table` kind because nothing
            # attaches a rule to a table bucket. An effects-only step has no source
            # at all, and `select source` then resolves to nobody.
            source=table, source_element=source_kind,
            bindings=bindings,
        )
        structured.extend(pending)
        return applied

    if resolutions:
        # Answering a choice this step raised: only the effects the caller echoed
        # are re-resolved, so an effect that already applied is not run twice.
        to_apply: list = []
        for r in resolutions:
            to_apply.extend(_one_effect(r.effect, r.field, r.answers))
    else:
        to_apply = []
        for e in all_mutations:
            # Which spec this effect carries decides how it resolves; the engine's
            # helper walks the spec *and* the effect's named references in one go,
            # so a spec-carrying effect must not go through `_with_refs` as well.
            spec_field = ("target" if getattr(e, "target_spec", None) is not None
                          else "entity" if getattr(e, "entity_spec", None) is not None
                          else "")
            if spec_field:
                to_apply.extend(_one_effect(e, spec_field, {}))
            else:
                to_apply.extend(_with_refs([e], structured))

    # A step with a question still pending **holds still**: applying the effects
    # that resolved fully is right, but advancing would skip the answer, and
    # re-asking on the next step would ask it out of its context.
    pending_answer = bool(structured)

    if engine is not None:
        immediate = [e for e in to_apply if e.timing == EffectTiming.IMMEDIATE]
        deferred = [e for e in to_apply if e.timing != EffectTiming.IMMEDIATE]

        result: EffectsResult = apply_effects(entity, immediate, repo, effect_context)
        flow = ({"done": False} if pending_answer else
                _process_flow(entity, row_flow + delta_flow, repo, pt=pt,
                              binding=binding, step=step, wrapped=wrapped,
                              bindings=bindings))
        _persist(entity, result, repo, old_razmerit)

        from transversal.services.scheduled_events import schedule_deferred

        for e in deferred:
            schedule_deferred(repo, "entity", entity.id, e, source_sfx_id=None)
            scheduled += 1
    else:
        # No scheduler available (e.g. direct unit tests) — apply everything now.
        result: EffectsResult = apply_effects(entity, to_apply, repo, effect_context)
        flow = ({"done": False} if pending_answer else
                _process_flow(entity, row_flow + delta_flow, repo, pt=pt,
                              binding=binding, step=step, wrapped=wrapped,
                              bindings=bindings))
        _persist(entity, result, repo, old_razmerit)

    _name_cache: dict = {}

    return {
        "done": flow.get("done", False),
        "step_id": step.id,
        "table_id": table.id if table is not None else "",
        "entry_key": key,
        "entry_label": entry.label if entry is not None else "",
        "bound": binding is not None,
        # Named, not just ids ([[B303]]): a step's report is the one place a player
        # reads what their effects actually did, and `loc-6549049` says nothing.
        "applied": [named_summary(a.summary, repo, _name_cache) for a in result.applied],
        "scheduled": scheduled,
        "pending_choices": ([c.kind for c in result.pending_choices]
                            + [c.element for c in structured]
                            + flow.get("pending_choices", [])),
        # The question itself, with its candidates ([[B314]]) — a bare element name
        # cannot be answered, and the caller serializes these to the picker's wire
        # shape. The service returns domain objects; the GraphQL layer owns the wire.
        "structured_choices": structured,
        "pending_term": pending_term_for(entity, pid),
        "mustered": flow.get("mustered", False),
        "mishap_muster": flow.get("mishap_muster", False),
    }


def _process_flow(entity: Entity, legacy_effects: list[Effect], repo, *, pt,
                  binding=None, step=None, wrapped: bool = False,
                  bindings: Optional[dict] = None) -> dict:
    """Apply the row's flow: the path's structure, or the legacy effects.

    Two regimes, and ``wrapped`` picks between them. A path that declares steps
    **owns its graph**, so the entries' own ``life_path`` effects are ignored
    entirely — two sources of truth for one edge is how a canvas and a runtime
    end up disagreeing. A path with no steps is pre-wrapper content: its flow
    still lives in those effects, and they are processed exactly as before.

    ``bindings`` is the activation's resolved scope, carried only so an **enrolling**
    row can find the faction the *path* supplies when the term has none ([[B41]]).
    """
    flow: dict = {"done": False, "pending_choices": []}

    if not wrapped:
        for effect in legacy_effects:
            if not _live(entity, pt):
                break

            if effect.action == "force_muster":
                _mark_mustered(entity, pt, mishap=True)
                flow["done"] = True
                flow["mustered"] = True
                flow["mishap_muster"] = True
                continue

            if effect.action == "muster":
                _mark_mustered(entity, pt, mishap=False)
                flow["done"] = True
                flow["mustered"] = True
                flow["mishap_muster"] = False
                continue

            if effect.action == "enroll":
                _ensure_enrollment(entity, pt, repo, bindings)
                continue

            if effect.action == "draft":
                _draft(entity, pt, target_value(effect), repo, flow)
                continue

            if effect.action == "next_step":
                _next_step(entity, pt, effect, flow, repo)

    if not _live(entity, pt):
        return flow

    # Structural flow — the wrapper's answer for this row.
    if binding is not None:
        if binding.enroll:
            _ensure_enrollment(entity, pt, repo, bindings)
        if binding.next:
            _advance(entity, pt, binding.next, flow, repo)
        elif binding.exit_kind:
            _exit(entity, pt, binding.exit_kind, binding.exit_path, repo, flow)
        else:
            _end_term(entity, pt, flow)  # bound, and the binding says "end here"
    elif step is not None and step.next:
        _advance(entity, pt, step.next, flow, repo)
    elif wrapped:
        # A wrapped path, a row it bound nothing, and no step default. End rather
        # than sit on the same step for ever; `validate_life_path` is what should
        # have caught it, and looping silently is the worse failure.
        _end_term(entity, pt, flow)

    return flow


def _live(entity: Entity, pt: PendingTerm) -> bool:
    """Whether this term is still the one stored for its body.

    Mustering and ending *remove* the checkpoint, so a flow step has to ask rather
    than assume: the term object it holds may already be detached.
    """
    return (getattr(entity, "pending_terms", None) or {}).get(pt.projection_id) is pt


def _end_term(entity: Entity, pt: PendingTerm, flow: dict) -> None:
    """Drop the checkpoint — the term is over.

    A finished term leaves *no* checkpoint rather than an empty one: an empty
    checkpoint is a thing with no meaning that every reader would then have to
    treat as absent. Only this body's entry is removed.
    """
    terms = getattr(entity, "pending_terms", None) or {}
    if terms.get(pt.projection_id) is pt:
        del terms[pt.projection_id]
    flow["done"] = True


def _draft(entity: Entity, pt: PendingTerm, path_id: str, repo, flow: dict) -> None:
    """Hand the term to another life path — the same body keeps serving it."""
    lp = repo.get_lifepath(path_id) if path_id else None
    step = entry_step(lp) if lp else None
    if step is None:
        _end_term(entity, pt, flow)
        return
    pt.path_id = path_id
    pt.current_step_id = step.id
    pt.current_table_id = step.table_id


def _exit(entity: Entity, pt: PendingTerm, kind: str, path_id: str, repo, flow: dict) -> None:
    """Leave the path — how, is what ``kind`` says.

    ``muster`` / ``force_muster`` are *destinations* with a meaning, not effects
    that happen to end a term: every such row in the live content carries nothing
    else, which is what settled the shape. ``draft`` hands the term to another
    path; anything else simply ends it.
    """
    if kind == "draft":
        _draft(entity, pt, path_id, repo, flow)
        return
    if kind in ("muster", "force_muster"):
        mishap = kind == "force_muster"
        _mark_mustered(entity, pt, mishap=mishap)
        flow["done"] = True
        flow["mustered"] = True
        flow["mishap_muster"] = mishap
        return
    _end_term(entity, pt, flow)


def _advance(entity: Entity, pt: PendingTerm, step_id: str, flow: dict, repo) -> None:
    """Move the term to ``step_id`` within the path — or end it when empty."""
    if not step_id:
        _end_term(entity, pt, flow)
        return
    lp = repo.get_lifepath(pt.path_id)
    step = find_step(lp, step_id)
    if step is None:
        # A binding naming a step the path does not have is an authoring error.
        # End the term rather than loop on a step that cannot be resolved; the
        # validator (`validate_life_path`) is what should have caught it.
        _end_term(entity, pt, flow)
        return
    pt.current_step_id = step.id
    pt.current_table_id = step.table_id


def _next_step(entity: Entity, pt: PendingTerm, effect: Effect, flow: dict, repo) -> None:
    """Legacy effect-driven flow — used only by paths with no declared steps."""
    target = target_value(effect)

    if target.startswith("{choose"):
        flow["pending_choices"].append("table")
        return

    if not target:
        _end_term(entity, pt, flow)
        return

    _advance(entity, pt, target, flow, repo)


def _mark_mustered(entity: Entity, pt: PendingTerm, mishap: bool) -> None:
    """Muster the **body** out — its own membership, and only its own.

    Matched on the body as well as the faction and path ([[B271]]): two bodies may
    serve the same path, and mustering in one must not mark the other mustered.
    """
    for enrollment in enrollments_for(entity, pt.projection_id):
        if enrollment.faction_id == pt.faction_id and enrollment.path_id == pt.path_id:
            enrollment.mustered = True
            enrollment.mishap_muster = mishap
            break
    terms = getattr(entity, "pending_terms", None) or {}
    if terms.get(pt.projection_id) is pt:
        del terms[pt.projection_id]


def enrolment_faction(pt: PendingTerm, bindings: Optional[dict] = None) -> str:
    """The faction an enrolling row admits this body to: the term's, else the path's.

    The **term's faction wins**, which is the caller-over-shared-content precedence
    the whole wrapper uses: a caller that named a faction meant it. A path no faction
    offers has no term faction, so it states its own by declaring
    ``{ENROLLING_FACTION_VARIABLE}`` ([[B290]]'s layer), and the resolved scope is
    where that arrives.

    Returns ``""`` when neither says — there is then nothing to join, and the caller
    decides what to do about it (``_ensure_enrollment`` skips rather than inventing
    an edge to a faction that does not exist).
    """
    if getattr(pt, "faction_id", ""):
        return pt.faction_id
    binding = (bindings or {}).get(ENROLLING_FACTION_VARIABLE)
    return getattr(binding, "value", "") or ""


def _ensure_enrollment(entity: Entity, pt: PendingTerm, repo,
                       bindings: Optional[dict] = None) -> None:
    """Idempotently record the active term as an enrollment for this body.

    The enrollment is scoped to the body serving the term ([[B271]]), so the same
    character may hold the same membership through two bodies without them being
    the same fact. Also ensures the character↔faction ``membership`` edge exists
    so rank and tenure relationship traits have somewhere to attach.

    ``bindings`` is the activation's resolved scope, which is where a faction-less
    term finds the **path's own** faction (see ``enrolment_faction``). When neither
    the term nor the path names one, nothing is enrolled and that is **said in the
    log**: an enrolling row that silently admitted nobody is exactly the failure this
    role keeps meeting, and a `membership` edge to the empty string would be worse.
    """
    faction_id = enrolment_faction(pt, bindings)
    if not faction_id:
        log.warning(
            "[lifepath] path %s enrols on a resolved row, but neither the term nor the "
            "path's `{%s}` names a faction — no membership was created",
            pt.path_id, ENROLLING_FACTION_VARIABLE)
        return

    for enrollment in enrollments_for(entity, pt.projection_id):
        if (enrollment.faction_id == faction_id
                and enrollment.path_id == pt.path_id):
            break
    else:
        entity.life_paths.append(Enrollment(
            faction_id=faction_id,
            path_id=pt.path_id,
            projection_id=pt.projection_id,
        ))

    if repo.get_relationship(entity.id, faction_id, "membership") is None:
        repo.create_relationship(entity.id, faction_id, "membership")


#: The id prefixes the world uses. A **fixed list** rather than "anything with a
#: dash", because a summary is prose: a loose matcher would rewrite words
#: ("non-player", a range, a count) into names nobody asked for.
_ID_PREFIXES = (
    "loc", "location", "character", "char", "gmc", "asset", "faction", "universe",
    "trait", "traitsetting", "ts", "traitset", "rt", "lp", "sfx", "projection", "proj",
)

_ID_TOKEN_RE = re.compile(r"\b(?:" + "|".join(_ID_PREFIXES) + r")-[A-Za-z0-9][A-Za-z0-9_-]*")

#: Readers that can turn an id into a name, in the order they are tried.
_NAME_READERS = ("get_entity", "get_trait", "get_lifepath", "get_roll_table",
                 "get_traitset_by_id", "get_projection")


def named_summary(summary: str, repo, cache: Optional[dict] = None) -> str:
    """Replace the ids in an applied-effect summary with the names they stand for.

    The summaries are written by the **handlers**, which know the id they resolved
    and nothing else — ``AppliedEffect.summary`` is a plain string — so a step's
    report read *"relationship relation → loc-6549049"*. Names live in the
    readers, so this is the pass that puts them back: the same job
    ``sfx_text.repo_name_resolver`` does for card text, for the one surface that
    says what an effect **did** ([[B303]]).

    A token nobody answers for is left **exactly as it was**. A summary that gains
    a name is an improvement; one that loses a fact is a regression, and a miss is
    far more likely to be an id this does not know than a nameable thing.
    """
    if not summary or repo is None:
        return summary or ""
    cache = {} if cache is None else cache

    def name_for(token: str) -> str:
        if token in cache:
            return cache[token]
        found = token
        for reader in _NAME_READERS:
            fn = getattr(repo, reader, None)
            if fn is None:
                continue
            try:
                obj = fn(token)
            except Exception:
                obj = None
            name = getattr(obj, "name", "") if obj is not None else ""
            if name:
                found = str(name)
                break
        cache[token] = found
        return found

    return _ID_TOKEN_RE.sub(lambda m: name_for(m.group(0)), summary)


def _persist(entity: Entity, result: EffectsResult, repo, old_razmerit: Optional[int] = None) -> None:
    """Persist in-memory mutations and broadcast SSE for live updates.

    Mirrors ``effects_commit.commit_effects``, but the primary entity is always
    persisted so the ``pending_term`` checkpoint survives a mid-term resume.
    """
    from transversal.api.sse.bus import StreamEvent, event_bus
    from transversal.services.session_manager import session_manager

    def publish(event: str, data: dict) -> None:
        for s in session_manager.list_active():
            event_bus.publish(StreamEvent(event=event, session_id=s.id, data=data))

    for other in result.entities_to_update:
        repo.update_entity(other)
        publish("entity_updated", {
            "entity_id": other.id,
            "name": other.name,
            "current_universe": other.current_universe,
            "current_location": other.current_location,
        })

    # The primary entity (always — pending_term checkpoint must persist).
    repo.update_entity(entity)
    publish("entity_updated", {
        "entity_id": entity.id,
        "name": entity.name,
        "current_universe": entity.current_universe,
        "current_location": entity.current_location,
    })
    if old_razmerit is not None and entity.razmerit != old_razmerit:
        publish("razmerit_changed", {
            "entity_id": entity.id,
            "old_balance": old_razmerit,
            "new_balance": entity.razmerit,
            "reason": "life_path",
        })

    for ts in result.new_trait_settings:
        repo.create_traitsetting(ts)
        publish("trait_updated", {"entity_id": ts.entity_id, "trait_id": ts.trait_id})
    for ts in result.updated_trait_settings:
        repo.update_traitsetting(ts)
        publish("trait_updated", {"entity_id": ts.entity_id, "trait_id": ts.trait_id})

    for rel in result.new_relationships:
        # The handler mints the edge (so `output` can name it); only an edge that
        # somehow arrived without a key is created here.
        if rel.get("created"):
            continue
        created = repo.create_relationship(rel["from"], rel["to"], rel["type"], rel.get("description", ""))
        if isinstance(created, dict):
            rel["key"] = created.get("_key", "")
