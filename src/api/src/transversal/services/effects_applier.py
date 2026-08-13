"""Effects applier — registry-based dispatch for Effect records.

Rather than hardcoding if/elif for each effect type, the applier
maintains a registry of handlers keyed by (type, action). New
handlers can be registered at any time — by core services, by
universe-specific modules, or by content plugins.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from transversal.domain import DieType, Effect, Entity, TraitSetting


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

    # Trait, rank, and life-path state mutations route through the shared applier.
    def _commit(a, eid, u, ctx):
        from transversal.services.effects_commit import commit_effects
        entity = em.repo.get_entity(eid)
        if entity is None:
            return
        commit_effects(entity, [a], em.repo)

    for action in ("step_up", "step_down", "set", "gain", "gain_or_step_up", "gain_complication", "gain_or_step_up_complication"):
        effect_registry.register("modify_trait", action, _commit)
    effect_registry.register("life_path", "discover", _commit)
    effect_registry.register("relationship", "create", _commit)

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


# ── Pure repo-first applier ───────────────────────────
#
# Unlike the registry above (which dispatches through the EntityManager/
# RazmeritService and persists immediately), this applier mutates in-memory
# models and returns everything the caller needs to persist and broadcast.

@dataclass
class AppliedEffect:
    """Record of one successfully applied mutation."""
    effect: Effect
    summary: str
    trait_setting_id: Optional[str] = None


@dataclass
class PendingChoice:
    """An effect whose target must be resolved by the user at runtime."""
    effect: Effect
    kind: str
    scope: Optional[str] = None


@dataclass
class EffectsResult:
    """Everything produced by apply_effects, ready for the caller to persist."""
    applied: list[AppliedEffect] = field(default_factory=list)
    new_trait_settings: list[TraitSetting] = field(default_factory=list)
    updated_trait_settings: list[TraitSetting] = field(default_factory=list)
    new_relationships: list[dict] = field(default_factory=list)
    entities_to_update: list[Entity] = field(default_factory=list)
    pending_choices: list[PendingChoice] = field(default_factory=list)
    passthrough: list[Effect] = field(default_factory=list)


def _resolve_traitset_id(trait_id: str, repo) -> str:
    trait = repo.get_trait(trait_id)
    return trait.traitset_id if trait else ""


def _trait_owner(entity: Entity, effect: Effect, repo) -> tuple[str, str]:
    """Return (from_type, owner_id) for the trait targeted by an effect.

    Defaults to the entity; if ``effect.context.relationship`` names a faction,
    target the character↔faction relationship edge instead.
    """
    rel_target = (effect.context or {}).get("relationship")
    if rel_target:
        rel = repo.get_relationship(entity.id, rel_target, "membership")
        if rel and rel.get("_key"):
            return ("relationship", rel["_key"])
    return ("entity", entity.id)


def _find_traitsetting(owner: tuple[str, str], repo, trait_id: str) -> Optional[TraitSetting]:
    from_type, owner_id = owner
    settings = (
        repo.get_relationship_traitsettings(owner_id)
        if from_type == "relationship"
        else repo.get_traitsettings_for_entity(owner_id)
    )
    for ts in settings:
        if ts.trait_id == trait_id:
            return ts
    return None


def _step_up(ts: TraitSetting) -> bool:
    """Step up the smallest die, capped at d12. Returns False if at cap/empty."""
    if not ts.dice:
        return False
    smallest = min(ts.dice, key=lambda d: d.max_value)
    if smallest == DieType.D12:
        return False
    ts.dice[ts.dice.index(smallest)] = smallest.step_up()
    return True


def _step_down(ts: TraitSetting) -> bool:
    """Step down the smallest die, floored at d4. Returns False if at floor/empty."""
    if not ts.dice:
        return False
    smallest = min(ts.dice, key=lambda d: d.max_value)
    if smallest == DieType.D4:
        return False
    ts.dice[ts.dice.index(smallest)] = smallest.step_down()
    return True


def _die(result: Optional[str]) -> DieType:
    return DieType(str(result).lower()) if result else DieType.D4


def _new_traitsetting(owner: tuple[str, str], trait_id: str, die: DieType, repo, *, negative: bool = False) -> TraitSetting:
    from_type, owner_id = owner
    traitset_id = _resolve_traitset_id(trait_id, repo)
    if not traitset_id and negative:
        traitset_id = "ts-complications"
    return TraitSetting(
        id=f"{owner_id}:{trait_id}{':complication' if negative else ''}",
        entity_id=owner_id,
        trait_id=trait_id,
        traitset_id=traitset_id,
        from_type=from_type,
        dice=[die],
        negative=negative,
        source_type="effect",
    )


def _resolve_target(entity: Entity, effect: Effect, result: EffectsResult, kind: str) -> Optional[str]:
    """Resolve a target to an id, or record a PendingChoice and return None."""
    target = effect.target or ""
    if target == "self":
        return entity.id
    if target.startswith("{choose") or target == "":
        result.pending_choices.append(PendingChoice(effect=effect, kind=effect.target_scope or kind))
        return None
    return target


# ── Mutation handlers ────────────────────────────────

def _apply_gain(entity, effect, repo, result):
    target = _resolve_target(entity, effect, result, "trait")
    if target is None:
        return
    owner = _trait_owner(entity, effect, repo)
    if _find_traitsetting(owner, repo, target):
        result.applied.append(AppliedEffect(effect, f"trait {target} already present"))
        return
    die = _die(effect.result)
    ts = _new_traitsetting(owner, target, die, repo)
    result.new_trait_settings.append(ts)
    result.applied.append(AppliedEffect(effect, f"gained {target} at {die.value}", ts.id))


def _apply_gain_or_step_up(entity, effect, repo, result):
    target = _resolve_target(entity, effect, result, "trait")
    if target is None:
        return
    owner = _trait_owner(entity, effect, repo)
    existing = _find_traitsetting(owner, repo, target)
    if existing:
        if _step_up(existing):
            result.updated_trait_settings.append(existing)
            result.applied.append(AppliedEffect(effect, f"stepped up {target}", existing.id))
        else:
            result.applied.append(AppliedEffect(effect, f"{target} already at d12"))
        return
    die = _die(effect.result)
    ts = _new_traitsetting(owner, target, die, repo)
    result.new_trait_settings.append(ts)
    result.applied.append(AppliedEffect(effect, f"gained {target} at {die.value}", ts.id))


def _apply_step_up(entity, effect, repo, result):
    target = _resolve_target(entity, effect, result, "trait")
    if target is None:
        return
    owner = _trait_owner(entity, effect, repo)
    existing = _find_traitsetting(owner, repo, target)
    if not existing:
        result.applied.append(AppliedEffect(effect, f"no trait {target} to step up"))
        return
    if _step_up(existing):
        result.updated_trait_settings.append(existing)
        result.applied.append(AppliedEffect(effect, f"stepped up {target}", existing.id))
    else:
        result.applied.append(AppliedEffect(effect, f"{target} already at d12"))


def _apply_step_down(entity, effect, repo, result):
    target = _resolve_target(entity, effect, result, "trait")
    if target is None:
        return
    owner = _trait_owner(entity, effect, repo)
    existing = _find_traitsetting(owner, repo, target)
    if not existing:
        result.applied.append(AppliedEffect(effect, f"no trait {target} to step down"))
        return
    if _step_down(existing):
        result.updated_trait_settings.append(existing)
        result.applied.append(AppliedEffect(effect, f"stepped down {target}", existing.id))
    else:
        result.applied.append(AppliedEffect(effect, f"{target} already at d4"))


def _apply_set(entity, effect, repo, result):
    target = _resolve_target(entity, effect, result, "trait")
    if target is None:
        return
    owner = _trait_owner(entity, effect, repo)
    existing = _find_traitsetting(owner, repo, target)
    if not existing:
        result.applied.append(AppliedEffect(effect, f"no trait {target} to set"))
        return
    die = _die(effect.result)
    existing.dice = [die]
    result.updated_trait_settings.append(existing)
    result.applied.append(AppliedEffect(effect, f"set {target} to {die.value}", existing.id))


def _apply_gain_complication(entity, effect, repo, result):
    target = _resolve_target(entity, effect, result, "trait")
    if target is None:
        return
    owner = _trait_owner(entity, effect, repo)
    die = _die(effect.result)
    ts = _new_traitsetting(owner, target, die, repo, negative=True)
    result.new_trait_settings.append(ts)
    result.applied.append(AppliedEffect(effect, f"gained complication {target} at {die.value}", ts.id))


def _apply_gain_or_step_up_complication(entity, effect, repo, result):
    target = _resolve_target(entity, effect, result, "trait")
    if target is None:
        return
    owner = _trait_owner(entity, effect, repo)
    existing = _find_traitsetting(owner, repo, target)
    if existing:
        if _step_up(existing):
            result.updated_trait_settings.append(existing)
            result.applied.append(AppliedEffect(effect, f"stepped up complication {target}", existing.id))
        else:
            result.applied.append(AppliedEffect(effect, f"complication {target} already at d12", existing.id))
        return
    die = _die(effect.result)
    ts = _new_traitsetting(owner, target, die, repo, negative=True)
    result.new_trait_settings.append(ts)
    result.applied.append(AppliedEffect(effect, f"gained complication {target} at {die.value}", ts.id))


def _apply_earn(entity, effect, repo, result):
    amount = int(effect.result or "0")
    entity.razmerit += amount
    result.applied.append(AppliedEffect(effect, f"earned {amount} razmerit"))


def _apply_spend(entity, effect, repo, result):
    amount = int(effect.result or "0")
    entity.razmerit -= amount
    result.applied.append(AppliedEffect(effect, f"spent {amount} razmerit"))


def _apply_transfer(entity, effect, repo, result):
    target = _resolve_target(entity, effect, result, "entity")
    if target is None:
        return
    amount = int(effect.result or "0")
    recipient = repo.get_entity(target)
    if recipient is None:
        result.applied.append(AppliedEffect(effect, f"transfer target {target} not found"))
        return
    entity.razmerit -= amount
    recipient.razmerit += amount
    result.entities_to_update.append(recipient)
    result.applied.append(AppliedEffect(effect, f"transferred {amount} razmerit to {target}"))


def _apply_discover(entity, effect, repo, result):
    target = _resolve_target(entity, effect, result, "life_path")
    if target is None:
        return
    if entity.discovered_life_paths is None:
        entity.discovered_life_paths = []
    if target not in entity.discovered_life_paths:
        entity.discovered_life_paths.append(target)
        result.applied.append(AppliedEffect(effect, f"discovered life path {target}"))
    else:
        result.applied.append(AppliedEffect(effect, f"life path {target} already discovered"))


def _apply_relationship_create(entity, effect, repo, result):
    target = _resolve_target(entity, effect, result, "entity")
    if target is None:
        return
    rel_type = effect.result or ""
    description = effect.context.get("description", "") if effect.context else ""
    result.new_relationships.append({
        "from": entity.id,
        "to": target,
        "type": rel_type,
        "description": description,
    })
    result.applied.append(AppliedEffect(effect, f"relationship {rel_type} → {target}"))


_MUTATION_HANDLERS = {
    ("modify_trait", "gain"): _apply_gain,
    ("modify_trait", "gain_or_step_up"): _apply_gain_or_step_up,
    ("modify_trait", "step_up"): _apply_step_up,
    ("modify_trait", "step_down"): _apply_step_down,
    ("modify_trait", "set"): _apply_set,
    ("modify_trait", "gain_complication"): _apply_gain_complication,
    ("modify_trait", "gain_or_step_up_complication"): _apply_gain_or_step_up_complication,
    ("transfer_razmerit", "earn"): _apply_earn,
    ("transfer_razmerit", "spend"): _apply_spend,
    ("transfer_razmerit", "transfer"): _apply_transfer,
    ("life_path", "discover"): _apply_discover,
    ("relationship", "create"): _apply_relationship_create,
}


def apply_effects(entity: Entity, effects: list[Effect], repo) -> EffectsResult:
    """Apply operational effects to an entity's in-memory state (no persistence).

    Mutates ``entity`` in place for entity-level fields (razmerit, rank, discovered
    paths) and collects new/updated TraitSetting objects, relationship edges, and
    cross-entity mutations into the returned EffectsResult. Persistence and SSE
    broadcast are the caller's responsibility.

    Unresolved targets (``{choose_*}` or empty-when-required) become PendingChoice.
    Effects without a mutation handler (resolver-context and flow effects) become
    passthrough.
    """
    result = EffectsResult()
    for effect in effects:
        handler = _MUTATION_HANDLERS.get((effect.type, effect.action))
        if handler is None:
            result.passthrough.append(effect)
            continue
        handler(entity, effect, repo, result)
    return result
