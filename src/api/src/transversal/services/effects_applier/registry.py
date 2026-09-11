"""Registry — split out of src/api/src/transversal/services/effects_applier.py."""

from __future__ import annotations

from transversal.domain import Effect
from typing import Callable
from transversal.services.effects_applier.datatypes import (
    SOURCE_CONTEXT_KEY,
    SOURCE_ELEMENT_CONTEXT_KEY,
)
from transversal.services.effects_applier.handlers_world import (
    _apply_attune_universe,
)


EffectHandler = Callable[[Effect, str, str, dict], None]

def _razmerit_entity(effect: Effect, acting_entity_id: str) -> str:
    """Who a razmerit effect acts on.

    The engine resolves an authored ``entity_spec`` into ``effect.entity`` before
    dispatch, and a substituted ``{variable}`` (e.g. ``{buying_entity}``) lands
    there too — so a concrete value means "this entity", while blank / ``self`` /
    an unresolved placeholder means the acting entity.
    """
    subject = (effect.entity or "").strip()
    if not subject or subject == "self" or subject.startswith("{"):
        return acting_entity_id
    return subject

class EffectRegistry:
    """Registry of effect handlers.

    Handlers are keyed by (type, action). A handler for ("*", action)
    matches any type for that action. A handler for (type, "*") matches
    any action for that type.

    The registry is global — any module can register handlers.
    """

    def __init__(self):
        self._handlers: dict[tuple[str, str], EffectHandler] = {}

    def register(self, effect_type: str, action: str, handler: EffectHandler) -> None:
        """Register a handler for a specific (type, action) pair."""
        self._handlers[(effect_type, action)] = handler

    def apply(self, action: Effect, entity_id: str, universe: str, context: dict) -> None:
        """Dispatch an effect action to its registered handler.

        Tries: (type, action) → (*, action) → (type, *) → (*, *) → no-op.
        """
        key = (action.type, action.action)
        handler = (
            self._handlers.get(key)
            or self._handlers.get(("*", action.action))
            or self._handlers.get((action.type, "*"))
            or self._handlers.get(("*", "*"))
        )
        if handler:
            handler(action, entity_id, universe, context)

def _register_core_handlers(em, raz):
    """Register handlers for the core service operations.

    Called during app startup with the singleton EntityManager and RazmitService.
    """
    # Read the registry *from the package module*, not from a local global: the
    # handler registry is module-level state at ``effects_applier.effect_registry``
    # and callers (and tests) swap it by rebinding that attribute. Reading it here
    # keeps those swaps effective for registration too.
    from transversal.services import effects_applier as _applier
    effect_registry = _applier.effect_registry

    from transversal.services.entity_manager import EntityManager
    from transversal.services.razmerit import RazmeritService

    # Razmerit operations. Who it acts on is explicit: the effect's ``entity``
    # (already resolved from any ``entity_spec`` by the engine), falling back to
    # the acting entity only when the field is blank/``self``.
    effect_registry.register("transfer_razmerit", "spend",
        lambda a, eid, u, ctx: raz.spend(_razmerit_entity(a, eid), int(a.result or "0"), reason="sfx_cost"))
    effect_registry.register("transfer_razmerit", "earn",
        lambda a, eid, u, ctx: raz.earn(_razmerit_entity(a, eid), int(a.result or "0"), reason="effect"))
    effect_registry.register("transfer_razmerit", "transfer",
        lambda a, eid, u, ctx: raz.transfer(_razmerit_entity(a, eid), a.target, int(a.result or "0")))

    # Trait, rank, and life-path state mutations route through the shared applier.
    def _commit(a, eid, u, ctx):
        from transversal.services.effects_commit import commit_effects
        entity = em.repo.get_entity(eid)
        if entity is None:
            return
        commit_effects(
            entity, [a], em.repo, ctx,
            source=(ctx or {}).get(SOURCE_CONTEXT_KEY),
            source_element=(ctx or {}).get(SOURCE_ELEMENT_CONTEXT_KEY),
        )

    for action in ("step_up", "step_down", "reduce_by_effect", "set", "gain", "remove", "gain_or_step_up", "cortex_gain", "reveal", "disable", "enable", "toggle", "add_die", "remove_die", "copy", "move"):
        effect_registry.register("modify_trait", action, _commit)
    effect_registry.register("life_path", "discover", _commit)
    effect_registry.register("relationship", "create", _commit)
    effect_registry.register("projection", "create", _commit)
    effect_registry.register("projection", "restore", _commit)
    effect_registry.register("modify_traitset", "set_limit", _commit)
    effect_registry.register("modify_dice_limit", "increase", _commit)
    effect_registry.register("modify_dice_limit", "decrease", _commit)
    effect_registry.register("modify_pool", "add_dice", _commit)
    effect_registry.register("modify_pool", "add_trait_rating", _commit)
    effect_registry.register("modify_pool", "roll", _commit)
    effect_registry.register("modify_pool", "resolve", _commit)

    # Entity operations
    def _create_asset(a, eid, u, ctx):
        created = em.create(
            name=ctx.get("name", a.target or "Created Asset"),
            entity_type="gmc" if a.target == "npc" else "asset",
            universe=u,
            location=ctx.get("location"),
            razmerit=ctx.get("razmerit", 0),
        )
        from transversal.services.scheduled_events import schedule_revert
        schedule_revert(em.repo, "entity", created.id, a, target=created.id, source_sfx_id=ctx.get("sfx_id"))
        return created

    def _delete_entity(a, eid, u, ctx):
        target = a.target or ""
        if target and target != "self":
            em.repo.delete_entity(target)

    effect_registry.register("create_entity", "create_asset", _create_asset)
    effect_registry.register("entity", "delete_entity", _delete_entity)

    # Attunement (temporary effective-universe additions)
    def _attune(a, eid, u, ctx):
        from transversal.domain import Attunement, AttunementScope
        raw = (a.target or "").strip()
        target_id = eid if raw in ("", "self", "wielder") else raw
        entity = em.repo.get_entity(target_id)
        if entity is None:
            return
        # Scope is authored on the effect ("self" = only the carrier, "domain" =
        # everyone in its location subtree); fall back to the event context so
        # callers that set scope at fire time keep working.
        raw_scope = (a.context or {}).get("scope") or ctx.get("scope") or "self"
        try:
            scope = AttunementScope(raw_scope)
        except ValueError:
            scope = AttunementScope.SELF
        universe = _apply_attune_universe(a, em, u)
        if a.action == "enable":
            if not any(x.universe == universe and x.scope == scope for x in entity.attunements):
                entity.attunements.append(Attunement(
                    universe=universe, scope=scope,
                    source_sfx_id=ctx.get("sfx_id"),
                ))
            from transversal.services.scheduled_events import schedule_revert
            schedule_revert(em.repo, "entity", entity.id, a, source_sfx_id=ctx.get("sfx_id"))
        else:  # disable
            entity.attunements = [
                x for x in entity.attunements
                if not (x.universe == universe and x.scope == scope)
            ]
        em.repo.update_entity(entity)

    effect_registry.register("attune", "enable", _attune)
    effect_registry.register("attune", "disable", _attune)

    # Targeting ban (directional, scene-counted): the owner may not target the
    # resolved opponent again until the ban expires.
    def _targeting_ban(a, eid, u, ctx):
        from transversal.services.targeting_bans import apply_targeting_ban
        entity = em.repo.get_entity(eid)
        if entity is None:
            return
        target = ctx.get("contest_entity_opponent") or (a.target or "")
        if not target or target == "self":
            return
        apply_targeting_ban(entity, target)
        from transversal.services.scheduled_events import schedule_revert
        schedule_revert(em.repo, "entity", entity.id, a, target=target, source_sfx_id=ctx.get("sfx_id"))
        em.repo.update_entity(entity)

    def _remove_targeting_ban(a, eid, u, ctx):
        from transversal.services.targeting_bans import remove_targeting_ban
        entity = em.repo.get_entity(eid)
        if entity is None:
            return
        remove_targeting_ban(entity, a.target or "")
        em.repo.update_entity(entity)

    def _clear_taken_out(a, eid, u, ctx):
        entity = em.repo.get_entity(eid)
        if entity is None:
            return
        entity.taken_out = False
        em.repo.update_entity(entity)

    effect_registry.register("entity", "targeting_ban", _targeting_ban)
    effect_registry.register("entity", "remove_targeting_ban", _remove_targeting_ban)
    effect_registry.register("entity", "clear_taken_out", _clear_taken_out)

    # Travel — move the entity across a universal boundary.
    #
    # Delegates to the shared repo-first applier (``apply_effects``) so the
    # subject, destination location, universe scope, and body policy resolve
    # through the same choose/random machinery as every other effect.
    def _travel(a, eid, u, ctx):
        entity = em.repo.get_entity(eid)
        if entity is None:
            return
        from transversal.services.effects_commit import commit_effects
        commit_effects(entity, [a], em.repo, ctx)

    effect_registry.register("travel", "move", _travel)
    effect_registry.register("location", "set", _commit)

    # Dice pool operations (handled by resolver, not state changes)
    effect_registry.register("modify_roll", "*",
        lambda a, eid, u, ctx: None)  # passed through to resolver context
    effect_registry.register("modify_outcome", "*",
        lambda a, eid, u, ctx: None)  # passed through to resolver context
