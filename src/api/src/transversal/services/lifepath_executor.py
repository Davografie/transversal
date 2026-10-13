"""Life-path term executor — traverse a path's steps and apply effects.

A term walks the **steps a life path declares**: each step wraps a roll table,
and the path's binding for the row that resolved supplies the delta and the next
step. The table itself stays pure content — it does not know it is in a path, and
the same table may appear in several paths or in none.

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
    """
    if lp is None or not step_id:
        return None
    for step in lp.steps:
        if step.id == step_id:
            return step
    for step in lp.steps:
        if step.table_id == step_id:
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
    """Begin (or restart) a term in a faction's life path, for one body.

    ``projection_id`` names the body serving it; omitted, the acting body is
    resolved (see ``services/lifepath_scope``). The term replaces any the *same*
    body already had — another body's term is untouched.
    """
    lp = repo.get_lifepath(path_id)
    if lp is None:
        raise ValueError(f"LifePath '{path_id}' not found")
    step = entry_step(lp)
    if step is None:
        raise ValueError(f"LifePath '{path_id}' has no entry step")

    pid = resolve_projection_id(entity, repo, projection_id)
    pt = PendingTerm(
        faction_id=faction_id,
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
) -> dict:
    """Resolve the current step, apply row + binding effects, and advance.

    Immediate mutation effects apply and persist in-place; non-immediate ones
    (``end_of_beat`` / ``end_of_scene`` / ``end_of_session`` / ``after_beats`` /
    ``on_condition``) are queued into ``engine``. Flow effects are always
    immediate. Returns a summary dict with ``done``, ``pending_term``, and any
    pending target choices.
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
    )
    if entry is None:
        return {"done": True, "error": "no applicable entry resolved"}

    # The path's overlay on this row, if it has one. `wrapped` is what separates
    # the two flow regimes: a path that declares steps owns its graph, and the
    # entries' own flow effects (if any are left) are then ignored.
    key = entry_key_for(table, entry)
    binding = next((b for b in step.bindings if b.key == key), None)
    wrapped = bool(lp is not None and lp.steps)

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

    # The names this entry's effects may use: the ambient facts (the term's
    # faction, this table's *path* faction from the enrollment, the roll) plus
    # whatever the table declares for itself. Sealed before the effects, so a
    # condition or effect reads the same scope.
    from transversal.services.effects_applier.datatypes import BINDINGS_CONTEXT_KEY
    from transversal.services.roll_table import table_bindings

    from transversal.services.effects_applier.datatypes import (
        SOURCE_CONTEXT_KEY, SOURCE_ELEMENT_CONTEXT_KEY,
    )

    effect_context = {
        BINDINGS_CONTEXT_KEY: table_bindings(table, entity, repo, entry=entry,
                                             roll=roll, tier=tier, index=index),
        # The entry's effect is applied *from* its table, so the table is the
        # source: `select source` is the table, and `navigate life_path` reaches
        # the paths that wrap it. The table is no longer owned by one path, so
        # `_source` stays the table and the *path* is named by the pending term.
        SOURCE_CONTEXT_KEY: table,
        SOURCE_ELEMENT_CONTEXT_KEY: "roll_table",
    }

    if engine is not None:
        immediate = [e for e in all_mutations if e.timing == EffectTiming.IMMEDIATE]
        deferred = [e for e in all_mutations if e.timing != EffectTiming.IMMEDIATE]

        result: EffectsResult = apply_effects(entity, immediate, repo, effect_context)
        flow = _process_flow(entity, row_flow + delta_flow, repo, pt=pt,
                             binding=binding, step=step, wrapped=wrapped)
        _persist(entity, result, repo, old_razmerit)

        from transversal.services.scheduled_events import schedule_deferred

        for e in deferred:
            schedule_deferred(repo, "entity", entity.id, e, source_sfx_id=None)
            scheduled += 1
    else:
        # No scheduler available (e.g. direct unit tests) — apply everything now.
        result: EffectsResult = apply_effects(
            entity, all_mutations, repo, effect_context)
        flow = _process_flow(entity, row_flow + delta_flow, repo, pt=pt,
                             binding=binding, step=step, wrapped=wrapped)
        _persist(entity, result, repo, old_razmerit)

    return {
        "done": flow.get("done", False),
        "step_id": step.id,
        "table_id": table.id,
        "entry_key": key,
        "entry_label": entry.label,
        "bound": binding is not None,
        "applied": [a.summary for a in result.applied],
        "scheduled": scheduled,
        "pending_choices": [c.kind for c in result.pending_choices] + flow.get("pending_choices", []),
        "pending_term": pending_term_for(entity, pid),
        "mustered": flow.get("mustered", False),
        "mishap_muster": flow.get("mishap_muster", False),
    }


def _process_flow(entity: Entity, legacy_effects: list[Effect], repo, *, pt,
                  binding=None, step=None, wrapped: bool = False) -> dict:
    """Apply the row's flow: the path's structure, or the legacy effects.

    Two regimes, and ``wrapped`` picks between them. A path that declares steps
    **owns its graph**, so the entries' own ``life_path`` effects are ignored
    entirely — two sources of truth for one edge is how a canvas and a runtime
    end up disagreeing. A path with no steps is pre-wrapper content: its flow
    still lives in those effects, and they are processed exactly as before.
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
                _ensure_enrollment(entity, pt, repo)
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
            _ensure_enrollment(entity, pt, repo)
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


def _ensure_enrollment(entity: Entity, pt: PendingTerm, repo) -> None:
    """Idempotently record the active term as an enrollment for this body.

    The enrollment is scoped to the body serving the term ([[B271]]), so the same
    character may hold the same membership through two bodies without them being
    the same fact. Also ensures the character↔faction ``membership`` edge exists
    so rank and tenure relationship traits have somewhere to attach.
    """
    for enrollment in enrollments_for(entity, pt.projection_id):
        if (enrollment.faction_id == pt.faction_id
                and enrollment.path_id == pt.path_id):
            break
    else:
        entity.life_paths.append(Enrollment(
            faction_id=pt.faction_id,
            path_id=pt.path_id,
            projection_id=pt.projection_id,
        ))

    if repo.get_relationship(entity.id, pt.faction_id, "membership") is None:
        repo.create_relationship(entity.id, pt.faction_id, "membership")


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
        repo.create_relationship(rel["from"], rel["to"], rel["type"], rel.get("description", ""))
