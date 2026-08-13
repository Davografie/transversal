"""Effects applier — registry-based dispatch for Effect records.

Rather than hardcoding if/elif for each effect type, the applier
maintains a registry of handlers keyed by (type, action). New
handlers can be registered at any time — by core services, by
universe-specific modules, or by content plugins.
"""

from __future__ import annotations

from typing import Callable

from transversal.domain import Effect


# Handler signature: (action, entity_id, universe, context) -> None
EffectHandler = Callable[[Effect, str, str, dict], None]


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


# Global registry
effect_registry = EffectRegistry()


# ── Core handlers (registered at import time) ────────

def _register_core_handlers(em, raz):
    """Register handlers for the core service operations.

    Called during app startup with the singleton EntityManager and RazmeritService.
    """
    from transversal.services.entity_manager import EntityManager
    from transversal.services.razmerit import RazmeritService

    # Razmerit operations
    effect_registry.register("transfer_razmerit", "spend",
        lambda a, eid, u, ctx: raz.spend(eid, int(a.result or "0"), reason="sfx_cost"))
    effect_registry.register("transfer_razmerit", "earn",
        lambda a, eid, u, ctx: raz.earn(eid, int(a.result or "0"), reason="effect"))
    effect_registry.register("transfer_razmerit", "transfer",
        lambda a, eid, u, ctx: raz.transfer(eid, a.target, int(a.result or "0")))

    # Trait operations
    def _modify_trait(a, eid, u, ctx):
        settings = em.get_traitsettings(eid)
        target = a.target

        # Resolve {source_trait} placeholder: find the trait that has the triggering SFX
        if target == "{source_trait}":
            sfx_name = ctx.get("sfx_name", "")
            for ts in settings:
                if sfx_name in (ts.sfx_ids or []):
                    target = ts.id
                    break

        for ts in settings:
            if ts.trait_id == target or ts.id == target:
                if a.action == "step_up":
                    em.step_up_trait(ts)
                elif a.action == "step_down":
                    em.step_down_trait(ts)
                elif a.action == "set":
                    from transversal.domain import DieType
                    ts.dice = [DieType(a.result)] if a.result else ts.dice
                    em.update_traitsetting(ts)
                break

    effect_registry.register("modify_trait", "step_up", _modify_trait)
    effect_registry.register("modify_trait", "step_down", _modify_trait)
    effect_registry.register("modify_trait", "set", _modify_trait)

    # Entity operations
    effect_registry.register("create_entity", "create_asset",
        lambda a, eid, u, ctx: em.create(
            name=ctx.get("name", a.target or "Created Asset"),
            entity_type="gmc" if a.target == "npc" else "asset",
            universe=u,
            location=ctx.get("location"),
            razmerit=ctx.get("razmerit", 0),
        ))

    # Location operations
    effect_registry.register("spoof_location", "enable",
        lambda a, eid, u, ctx: None)  # handled by resolver reading effective traits
    effect_registry.register("spoof_location", "disable",
        lambda a, eid, u, ctx: None)

    # Dice pool operations (handled by resolver, not state changes)
    effect_registry.register("modify_roll", "*",
        lambda a, eid, u, ctx: None)  # passed through to resolver context
    effect_registry.register("modify_outcome", "*",
        lambda a, eid, u, ctx: None)  # passed through to resolver context
