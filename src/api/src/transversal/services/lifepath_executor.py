"""Life-path term executor — traverse linked roll tables and apply effects.

A term is a sequence of RollTable resolutions driven by flow effects:
``next_step`` (literal / return-address / player choice), ``draft``, and
``force_muster``. Non-flow effects resolve through the shared applier.
"""

from __future__ import annotations

from typing import Optional

from transversal.domain import (
    Effect,
    EffectTiming,
    Enrollment,
    Entity,
    OutcomeTier,
    PendingTerm,
)
from transversal.services.effects_applier import apply_effects, EffectsResult
from transversal.services.roll_table import resolve_table


def start_term(entity: Entity, faction_id: str, path_id: str, repo) -> PendingTerm:
    """Begin (or restart) a term in a faction's life path."""
    lp = repo.get_lifepath(path_id)
    if lp is None:
        raise ValueError(f"LifePath '{path_id}' not found")
    if not lp.entry_table_id:
        raise ValueError(f"LifePath '{path_id}' has no entry table")

    pt = PendingTerm(
        faction_id=faction_id,
        path_id=path_id,
        current_table_id=lp.entry_table_id,
        continuation=[],
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
    """Resolve the current pending table, apply effects, and advance the flow.

    Immediate mutation effects apply and persist in-place; non-immediate ones
    (``end_of_beat`` / ``end_of_scene`` / ``end_of_session`` / ``after_beats``
    / ``on_condition``) are queued into ``engine``. Flow effects are always
    immediate. Returns a summary dict with ``done``, ``pending_term``, and any
    pending target choices.
    """
    pt = entity.pending_term
    if pt is None or not pt.current_table_id:
        return {"done": True, "error": "no pending term"}

    table = repo.get_roll_table(pt.current_table_id)
    if table is None:
        return {"done": True, "error": f"table '{pt.current_table_id}' not found"}

    entry = resolve_table(table, roll=roll, tier=tier, index=index)
    if entry is None:
        return {"done": True, "error": "no entry resolved"}

    # Append the outcome to the entity's historical record (append-only event log).
    lp = repo.get_lifepath(pt.path_id)
    repo.add_historical_record(
        entity.id,
        "roll_table",
        {
            "life_path_id": pt.path_id,
            "life_path_name": lp.name if lp is not None else pt.path_id,
            "table_id": table.id,
            "table_name": table.name,
            "scheme": table.scheme.value,
            "roll_source": table.roll_source.value,
            "entry_label": entry.label,
            "entry_tier": entry.tier.value if entry.tier else None,
            "index": index,
        },
        universe=entity.current_universe,
    )

    mutation_effects = [e for e in entry.effects if e.type != "life_path"]
    flow_effects = [e for e in entry.effects if e.type == "life_path"]

    old_razmerit = entity.razmerit
    scheduled = 0

    # The names this entry's effects may use: the ambient facts (the term's
    # faction, this table's *path* faction from the enrollment, the roll) plus
    # whatever the table declares for itself. Sealed before the effects, so a
    # condition or effect reads the same scope.
    from transversal.services.effects_applier.datatypes import BINDINGS_CONTEXT_KEY
    from transversal.services.roll_table import table_bindings

    effect_context = {
        BINDINGS_CONTEXT_KEY: table_bindings(table, entity, repo, roll=roll, tier=tier, index=index)
    }

    if engine is not None:
        immediate = [e for e in mutation_effects if e.timing == EffectTiming.IMMEDIATE]
        deferred = [e for e in mutation_effects if e.timing != EffectTiming.IMMEDIATE]

        result: EffectsResult = apply_effects(entity, immediate, repo, effect_context)
        flow = _process_flow(entity, flow_effects, repo)
        _persist(entity, result, repo, old_razmerit)

        from transversal.services.scheduled_events import schedule_deferred

        for e in deferred:
            schedule_deferred(repo, "entity", entity.id, e, source_sfx_id=None)
            scheduled += 1
    else:
        # No scheduler available (e.g. direct unit tests) — apply everything now.
        result: EffectsResult = apply_effects(entity, mutation_effects, repo, effect_context)
        flow = _process_flow(entity, flow_effects, repo)
        _persist(entity, result, repo, old_razmerit)

    return {
        "done": flow.get("done", False),
        "table_id": table.id,
        "entry_label": entry.label,
        "applied": [a.summary for a in result.applied],
        "scheduled": scheduled,
        "pending_choices": [c.kind for c in result.pending_choices] + flow.get("pending_choices", []),
        "pending_term": entity.pending_term,
        "mustered": flow.get("mustered", False),
        "mishap_muster": flow.get("mishap_muster", False),
    }


def _process_flow(entity: Entity, effects: list[Effect], repo) -> dict:
    """Apply flow effects to the entity's pending term / enrollment."""
    flow: dict = {"done": False, "pending_choices": []}
    pt = entity.pending_term

    for effect in effects:
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
            target_path = effect.target
            lp = repo.get_lifepath(target_path) if target_path else None
            if pt is not None and lp and lp.entry_table_id:
                pt.path_id = target_path
                pt.current_table_id = lp.entry_table_id
                pt.continuation = []
                pt.return_map = {}
            continue

        if effect.action == "next_step":
            _next_step(entity, effect, flow, repo)

    return flow


def _next_step(entity: Entity, effect: Effect, flow: dict, repo) -> None:
    pt = entity.pending_term
    if pt is None:
        return

    target = effect.target or ""
    return_to = (effect.context or {}).get("return_to")

    if target.startswith("{choose"):
        flow["pending_choices"].append("table")
        return

    # Named exit: "{return:<name>}" resolves against the caller's return map.
    if target.startswith("{return:") and target.endswith("}"):
        name = target[len("{return:"):-1]
        target = pt.return_map.get(name, "")
        pt.return_map = {}
        if not target:
            pt.current_table_id = ""
            flow["done"] = True
            return
        pt.current_table_id = target
        return

    # Entering a shared table: store the named-exit map (single map, no nesting).
    if isinstance(return_to, dict) and return_to:
        pt.return_map = dict(return_to)

    # Legacy single-exit string return (backward compatible with the stack).
    if isinstance(return_to, str) and return_to and return_to != target:
        pt.continuation.append(return_to)

    if target in ("", "{continue}"):
        if pt.continuation:
            target = pt.continuation.pop()
        else:
            pt.current_table_id = ""
            flow["done"] = True
            return

    pt.current_table_id = target


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
