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
from transversal.services.roll_table import entry_key_for, resolve_applicable_entry
from transversal.services.effect_refs import target_value


def find_step(lp: Optional[LifePath], step_id: str) -> Optional[LifePathStep]:
    """The step named by ``step_id``, or a synthesised one for pre-wrapper content.

    A path that has not been migrated carries no steps and checkpoints itself by
    bare *table* id (the flow lived in the entries' ``next_step`` effects). Rather
    than refuse it, treat the id as a one-table step with no bindings — the
    executor then behaves exactly as it did before the wrapper existed.
    """
    if lp is None or not step_id:
        return None
    for step in lp.steps:
        if step.id == step_id:
            return step
    if not lp.steps:
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


def start_term(entity: Entity, faction_id: str, path_id: str, repo) -> PendingTerm:
    """Begin (or restart) a term in a faction's life path."""
    lp = repo.get_lifepath(path_id)
    if lp is None:
        raise ValueError(f"LifePath '{path_id}' not found")
    step = entry_step(lp)
    if step is None:
        raise ValueError(f"LifePath '{path_id}' has no entry step")

    pt = PendingTerm(
        faction_id=faction_id,
        path_id=path_id,
        current_step_id=step.id,
        current_table_id=step.table_id,
    )
    entity.pending_term = pt
    return pt


def resolve_step(
    entity: Entity,
    repo,
    *,
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
    pt = entity.pending_term
    if pt is None:
        return {"done": True, "error": "no pending term"}
    step_id = pt.current_step_id or pt.current_table_id
    if not step_id:
        return {"done": True, "error": "no pending term"}

    lp = repo.get_lifepath(pt.path_id)
    step = find_step(lp, step_id)
    if step is None:
        return {"done": True, "error": f"step '{step_id}' not found in path '{pt.path_id}'"}

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
        immediate = [e for e in row_mutations + delta_mutations
                     if e.timing == EffectTiming.IMMEDIATE]
        deferred = [e for e in row_mutations + delta_mutations
                    if e.timing != EffectTiming.IMMEDIATE]

        result: EffectsResult = apply_effects(entity, immediate, repo, effect_context)
        flow = _process_flow(entity, row_flow + delta_flow, repo,
                             binding=binding, step=step, wrapped=wrapped)
        _persist(entity, result, repo, old_razmerit)

        from transversal.services.scheduled_events import schedule_deferred

        for e in deferred:
            schedule_deferred(repo, "entity", entity.id, e, source_sfx_id=None)
            scheduled += 1
    else:
        # No scheduler available (e.g. direct unit tests) — apply everything now.
        result: EffectsResult = apply_effects(
            entity, row_mutations + delta_mutations, repo, effect_context)
        flow = _process_flow(entity, row_flow + delta_flow, repo,
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
        "pending_term": entity.pending_term,
        "mustered": flow.get("mustered", False),
        "mishap_muster": flow.get("mishap_muster", False),
    }


def _process_flow(entity: Entity, legacy_effects: list[Effect], repo, *,
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
            if entity.pending_term is None:
                break

            if effect.action == "force_muster":
                _mark_mustered(entity, mishap=True)
                flow["done"] = True
                flow["mustered"] = True
                flow["mishap_muster"] = True
                continue

            if effect.action == "muster":
                _mark_mustered(entity, mishap=False)
                flow["done"] = True
                flow["mustered"] = True
                flow["mishap_muster"] = False
                continue

            if effect.action == "enroll":
                _ensure_enrollment(entity, repo)
                continue

            if effect.action == "draft":
                _draft(entity, target_value(effect), repo, flow)
                continue

            if effect.action == "next_step":
                _next_step(entity, effect, flow, repo)

    if entity.pending_term is None:
        return flow

    # Structural flow — the wrapper's answer for this row.
    if binding is not None:
        if binding.enroll:
            _ensure_enrollment(entity, repo)
        if binding.next:
            _advance(entity, binding.next, flow, repo)
        elif binding.exit_kind:
            _exit(entity, binding.exit_kind, binding.exit_path, repo, flow)
        else:
            _end_term(entity, flow)  # bound, and the binding says "end here"
    elif step is not None and step.next:
        _advance(entity, step.next, flow, repo)
    elif wrapped:
        # A wrapped path, a row it bound nothing, and no step default. End rather
        # than sit on the same step for ever; `validate_life_path` is what should
        # have caught it, and looping silently is the worse failure.
        _end_term(entity, flow)

    return flow


def _end_term(entity: Entity, flow: dict) -> None:
    """Clear the checkpoint — the term is over."""
    pt = entity.pending_term
    if pt is None:
        return
    pt.current_step_id = ""
    pt.current_table_id = ""
    flow["done"] = True


def _draft(entity: Entity, path_id: str, repo, flow: dict) -> None:
    """Hand the term to another life path."""
    pt = entity.pending_term
    lp = repo.get_lifepath(path_id) if path_id else None
    step = entry_step(lp) if lp else None
    if pt is None:
        return
    if step is None:
        _end_term(entity, flow)
        return
    pt.path_id = path_id
    pt.current_step_id = step.id
    pt.current_table_id = step.table_id


def _exit(entity: Entity, kind: str, path_id: str, repo, flow: dict) -> None:
    """Leave the path — how, is what ``kind`` says.

    ``muster`` / ``force_muster`` are *destinations* with a meaning, not effects
    that happen to end a term: every such row in the live content carries nothing
    else, which is what settled the shape. ``draft`` hands the term to another
    path; anything else simply ends it.
    """
    if kind == "draft":
        _draft(entity, path_id, repo, flow)
        return
    if kind in ("muster", "force_muster"):
        mishap = kind == "force_muster"
        _mark_mustered(entity, mishap=mishap)
        flow["done"] = True
        flow["mustered"] = True
        flow["mishap_muster"] = mishap
        return
    _end_term(entity, flow)


def _advance(entity: Entity, step_id: str, flow: dict, repo) -> None:
    """Move the term to ``step_id`` within the path — or end it when empty."""
    pt = entity.pending_term
    if pt is None:
        return
    if not step_id:
        _end_term(entity, flow)
        return
    lp = repo.get_lifepath(pt.path_id)
    step = find_step(lp, step_id)
    if step is None:
        # A binding naming a step the path does not have is an authoring error.
        # End the term rather than loop on a step that cannot be resolved; the
        # validator (`validate_life_path`) is what should have caught it.
        _end_term(entity, flow)
        return
    pt.current_step_id = step.id
    pt.current_table_id = step.table_id


def _next_step(entity: Entity, effect: Effect, flow: dict, repo) -> None:
    """Legacy effect-driven flow — used only by paths with no declared steps."""
    pt = entity.pending_term
    if pt is None:
        return

    target = target_value(effect)

    if target.startswith("{choose"):
        flow["pending_choices"].append("table")
        return

    if not target:
        _end_term(entity, flow)
        return

    _advance(entity, target, flow, repo)


def _mark_mustered(entity: Entity, mishap: bool) -> None:
    pt = entity.pending_term
    if pt is not None:
        for enrollment in entity.life_paths:
            if enrollment.faction_id == pt.faction_id and enrollment.path_id == pt.path_id:
                enrollment.mustered = True
                enrollment.mishap_muster = mishap
                break
    entity.pending_term = None


def _ensure_enrollment(entity: Entity, repo) -> None:
    """Idempotently record the active term as an enrollment.

    Also ensures the character↔faction ``membership`` edge exists so rank and
    tenure relationship traits have somewhere to attach.
    """
    pt = entity.pending_term
    if pt is None:
        return
    for enrollment in entity.life_paths:
        if enrollment.faction_id == pt.faction_id and enrollment.path_id == pt.path_id:
            break
    else:
        entity.life_paths.append(Enrollment(faction_id=pt.faction_id, path_id=pt.path_id))

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
