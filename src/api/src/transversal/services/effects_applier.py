"""Effects applier — registry-based dispatch for Effect records.

Rather than hardcoding if/elif for each effect type, the applier
maintains a registry of handlers keyed by (type, action). New
handlers can be registered at any time — by core services, by
universe-specific modules, or by content plugins.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable, Optional

from transversal.domain import DieType, Effect, Entity, Polarity, RatingType, TraitSetting, TraitSetSetting
from transversal.services.conditions import evaluate_conditions
from transversal.services.effect_targets import resolve_candidates
from transversal.services.trait_reveal import reveal_trait_to


# Handler signature: (action, entity_id, universe, context) -> None
EffectHandler = Callable[[Effect, str, str, dict], None]

# Reserved effect-context keys for threading a resolved activation source into
# the commit path. Written by the engine (immediate) and roll_deferral (deferred),
# read back by ``_commit`` so per-effect ``source_rating`` / ``target_path``
# conditions resolve against the trait (etc.) that owns the SFX.
SOURCE_CONTEXT_KEY = "_source"
SOURCE_ELEMENT_CONTEXT_KEY = "_source_element"
# The activation's shared variable scope (condition + effect step outputs). Carried
# in the effect context so ``entity_spec`` can resolve ``select variable``.
BINDINGS_CONTEXT_KEY = "_bindings"


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


# Global registry
effect_registry = EffectRegistry()


# ── Core handlers (registered at import time) ────────

def _register_core_handlers(em, raz):
    """Register handlers for the core service operations.

    Called during app startup with the singleton EntityManager and RazmeritService.
    """
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

    for action in ("step_up", "step_down", "reduce_by_effect", "set", "gain", "remove", "gain_or_step_up", "cortex_gain", "reveal", "disable", "enable", "toggle", "add_die", "remove_die"):
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
        scope = AttunementScope(ctx.get("scope", "self"))
        universe = a.result or u
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
    """An effect whose target must be resolved by the user at runtime.

    ``kind`` is the target kind the picker should present (``location``,
    ``occupant``, ``trait``, ``rating_die``, ``entity``, ``life_path``,
    ``roll_table``).  ``scope`` is the narrowing hint from ``Effect.target_scope``
    (e.g. a universe or "current location") used to filter candidates.
    ``field`` names the Effect field this choice resolves into (``target`` or
    ``entity``).
    """
    effect: Effect
    kind: str
    scope: Optional[str] = None
    field: str = "target"


@dataclass
class EffectsResult:
    """Everything produced by apply_effects, ready for the caller to persist."""
    applied: list[AppliedEffect] = field(default_factory=list)
    new_trait_settings: list[TraitSetting] = field(default_factory=list)
    updated_trait_settings: list[TraitSetting] = field(default_factory=list)
    removed_trait_settings: list[TraitSetting] = field(default_factory=list)
    new_relationships: list[dict] = field(default_factory=list)
    new_projections: list = field(default_factory=list)
    updated_projections: list = field(default_factory=list)
    removed_projections: list = field(default_factory=list)
    new_traitsetsettings: list = field(default_factory=list)
    updated_traitsetsettings: list = field(default_factory=list)
    entities_to_update: list[Entity] = field(default_factory=list)
    pending_choices: list[PendingChoice] = field(default_factory=list)
    passthrough: list[Effect] = field(default_factory=list)
    revealed: list[tuple[TraitSetting, str]] = field(default_factory=list)


def _resolve_traitset_id(trait_id: str, repo) -> str:
    trait = repo.get_trait(trait_id)
    return trait.traitset_id if trait else ""


def _trait_owner(entity: Entity, effect: Effect, repo) -> tuple[str, str]:
    """Return (from_type, owner_id) for the trait targeted by an effect.

    Defaults to the entity; if ``effect.context.relationship`` names a faction,
    target the character↔faction relationship edge instead.
    """
    rel_target = (effect.context or {}).get("relationship")
    if rel_target == "{term_faction}":
        # Shared tables can't hardcode a faction; resolve to the faction the
        # entity is currently in a term with.
        rel_target = entity.pending_term.faction_id if entity.pending_term else ""
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


def _find_traitsetting_by_target(subject: Entity, effect: Effect, repo, target: str) -> Optional[TraitSetting]:
    """Resolve a trait-mutation target to a TraitSetting.

    Prefers a direct *instance* lookup — the target is a traitsetting id (e.g.
    ``kael-1:trait-martial``) produced by the ``die→traitsetting`` drillthrough.
    Falls back to the legacy registry-trait + owner lookup so an authored trait
    id (``trait-martial``) still resolves to the subject's instance.
    """
    if target:
        getter = getattr(repo, "get_traitsetting", None)
        if getter is not None:
            ts = getter(target)
            if ts is not None:
                return ts
    return _find_traitsetting(_trait_owner(subject, effect, repo), repo, target)


def _step_up(ts: TraitSetting) -> bool:
    """Step up the smallest die, capped at d12. Restores an empty rating to d4."""
    if not ts.dice:
        ts.dice = [DieType.D4]
        return True
    smallest = min(ts.dice, key=lambda d: d.max_value)
    if smallest == DieType.D12:
        return False
    ts.dice[ts.dice.index(smallest)] = smallest.step_up()
    return True


def _step_down_one(ts: TraitSetting) -> str:
    """Step down the smallest die. Returns ``"stepped" | "empty"``.

    A d4 die steps down to no die (empty rating) — the trait *persists* with an
    empty rating rather than being deleted, so a temporary step-down can revert.
    """
    if not ts.dice:
        return "empty"
    smallest = min(ts.dice, key=lambda d: d.max_value)
    if smallest == DieType.D4:
        ts.dice.remove(smallest)
        return "stepped"
    ts.dice[ts.dice.index(smallest)] = smallest.step_down()
    return "stepped"


def _steps(effect: Effect) -> int:
    """Read the optional step magnitude from an effect's context (default 1)."""
    raw = (effect.context or {}).get("steps")
    try:
        return max(int(raw), 1)
    except (TypeError, ValueError):
        return 1


def _has_steps(effect: Effect) -> bool:
    """True when ``steps`` was explicitly provided in the effect's context."""
    return "steps" in (effect.context or {})


def _step_up_trait(entity: Entity, ts: TraitSetting, target: str, effect: Effect, result, repo, steps: int = 1) -> bool:
    """Step up a trait setting up to ``steps`` times.

    Returns True when the rating changed (caller persists + reverts). A negative
    trait pushed beyond d12 takes the entity out (once) and leaves the trait at
    d12.
    """
    applied = 0
    for _ in range(steps):
        if _step_up(ts):
            applied += 1
        else:
            break  # empty dice or already at d12

    if applied < steps:
        if ts.polarity == Polarity.NEGATIVE:
            entity.taken_out = True
            result.applied.append(AppliedEffect(effect, f"{target} stepped beyond d12 — taken out"))
            from transversal.domain import Effect as _Effect, EffectTiming as _ET, Timer as _Timer, TimerCombine as _TC
            from transversal.services.scheduled_events import schedule_event
            schedule_event(
                repo, "entity", entity.id,
                _Effect(timing=_ET.IMMEDIATE, type="entity", action="clear_taken_out", target="self"),
                [_Timer(event="scene", remaining=1)],
                _TC.FIRST_TO_FIRE,
            )
        elif applied == 0:
            result.applied.append(AppliedEffect(effect, f"{target} already at d12"))
    return applied > 0


def _die(result: Optional[str]) -> DieType:
    return DieType(str(result).lower()) if result else DieType.D4


def _ctx(effect: Effect, key: str) -> str:
    """Read a string context value (empty when absent)."""
    return str((effect.context or {}).get(key) or "")


def _rating_type(effect: Effect) -> RatingType:
    """Rating type authored on a trait-gain effect (default STATIC)."""
    raw = _ctx(effect, "rating_type").lower() or "static"
    try:
        return RatingType(raw)
    except ValueError:
        return RatingType.STATIC


def _new_traitsetting(owner: tuple[str, str], trait_id: str, die: DieType, repo, *, negative: bool = False, statement: str = "", notes: str = "", rating_type: RatingType = RatingType.STATIC) -> TraitSetting:
    from transversal.services.polarity import default_polarity

    from_type, owner_id = owner
    traitset_id = _resolve_traitset_id(trait_id, repo)
    trait = repo.get_trait(trait_id)
    get_traitset = getattr(repo, "get_traitset_by_id", None)
    traitset = get_traitset(traitset_id) if traitset_id and get_traitset else None
    polarity = Polarity.NEGATIVE if negative else default_polarity(trait, traitset)
    if not traitset_id and polarity == Polarity.NEGATIVE:
        traitset_id = "ts-complications-a190"
    projection_id = None
    if from_type == "entity" and trait is not None and not getattr(trait, "default_ego", False):
        # Morph-by-default — anchor the grant to the entity's active projection.
        get_entity = getattr(repo, "get_entity", None)
        entity = get_entity(owner_id) if get_entity else None
        if entity is not None and entity.current_projection:
            from_type = "projection"
            projection_id = entity.current_projection
    return TraitSetting(
        id=f"{owner_id}:{trait_id}{':complication' if polarity == Polarity.NEGATIVE else ''}",
        entity_id=owner_id,
        trait_id=trait_id,
        traitset_id=traitset_id,
        from_type=from_type,
        projection_id=projection_id,
        dice=[die],
        rating_type=rating_type,
        polarity=polarity,
        statement=statement,
        notes=notes,
        source_type="effect",
    )


# Target kinds the frontend picker should present.  A bare ``{choose}`` (or an
# unknown suffix) resolves to None so the caller falls back to the handler's
# default kind.
_TARGET_KINDS = {
    "location": "location",
    "occupant": "occupant",
    "trait": "trait",
    "traitsetting": "traitsetting",
    "entity": "entity",
    "rating_die": "rating_die",
    "life_path": "life_path",
    "roll_table": "roll_table",
    "universe": "universe",
    "projection": "projection",
    "scheduled_event": "scheduled_event",
}

_PLACEHOLDER_MODES = {"choose", "random"}


def _parse_placeholder(target: str) -> Optional[tuple[str, Optional[str]]]:
    """Parse a ``{mode:kind}`` / ``{mode_kind}`` target placeholder.

    Returns ``(mode, kind)`` for a recognised mode (``choose`` / ``random``).
    ``kind`` is None for a bare ``{choose}`` / ``{random}``.  Returns None for
    non-placeholder targets or unknown modes.
    """
    if not (target.startswith("{") and target.endswith("}")):
        return None
    body = target[1:-1]
    if ":" in body:
        mode, _, kind = body.partition(":")
    else:
        mode, _, kind = body.partition("_")
    if mode not in _PLACEHOLDER_MODES:
        return None
    kind = kind.strip()
    return (mode, _TARGET_KINDS.get(kind)) if kind else (mode, None)


def is_choose_target(target: str) -> bool:
    """True if ``target`` is a ``{choose_*}`` placeholder needing user resolution."""
    parsed = _parse_placeholder(target or "")
    return parsed is not None and parsed[0] == "choose"


def choose_kind(target: str) -> Optional[str]:
    """Return the picker kind for a ``{choose_kind}`` placeholder, or None."""
    parsed = _parse_placeholder(target or "")
    if parsed is None or parsed[0] != "choose":
        return None
    return parsed[1]


def find_choose_placeholder(effect: Effect) -> Optional[tuple[str, str, Optional[str]]]:
    """Return ``(kind, field, scope)`` for the first ``{choose:*}`` in an effect.

    Checks scope values first (they narrow the subsequent target/entity/context
    choice), then ``target``/``entity``, then string ``context`` values. The
    ``field`` is the dotted Effect path the picker should resolve into
    (``"target"``, ``"entity"``, ``"target_scope"``, ``"entity_scope"``, or
    ``"context.<key>"``).
    """
    from transversal.services.effect_targets import parse_scope
    for field_name in ("target_scope", "entity_scope"):
        scope = getattr(effect, field_name, None) or ""
        _, value = parse_scope(scope)
        parsed = _parse_placeholder(value or "")
        if parsed is not None and parsed[0] == "choose":
            return (parsed[1], field_name, None)
    for field_name in ("target", "entity"):
        parsed = _parse_placeholder(getattr(effect, field_name, "") or "")
        if parsed is not None and parsed[0] == "choose":
            scope = effect.target_scope if field_name == "target" else effect.entity_scope
            return (parsed[1], field_name, scope)
    for key, value in (effect.context or {}).items():
        if isinstance(value, str):
            parsed = _parse_placeholder(value)
            if parsed is not None and parsed[0] == "choose":
                scope = effect.target_scope if key == "projection" else None
                return (parsed[1], f"context.{key}", scope)
    return None


def _scope_choice(effect: Effect) -> Optional[PendingChoice]:
    """Return a PendingChoice for a ``{choose:*}`` in the effect's scope value."""
    from transversal.services.effect_targets import parse_scope
    for field_name in ("target_scope", "entity_scope"):
        scope = getattr(effect, field_name, None) or ""
        _, value = parse_scope(scope)
        parsed = _parse_placeholder(value or "")
        if parsed is not None and parsed[0] == "choose":
            return PendingChoice(effect=effect, kind=parsed[1], scope=None, field=field_name)
    return None


def _resolve_scope_choose(scope: Optional[str], target: str) -> Optional[str]:
    """Substitute the ``{choose:*}`` placeholder in a scope value with ``target``."""
    if not scope:
        return target
    from transversal.services.effect_targets import parse_scope
    import re
    prefix, value = parse_scope(scope)
    new_value = re.sub(r"\{choose(?:_[a-z_]+|:[a-z_]+)?\}", target, value)
    return f"{prefix}:{new_value}" if prefix else new_value


def _resolve_scope(scope: Optional[str], entity: Entity, repo) -> Optional[str]:
    """Resolve a ``{random:*}`` placeholder in a scope's value position.

    ``universe:{random_universe}`` becomes ``universe:earth`` (etc.) before the
    scope reaches the candidate resolver. Literal scopes pass through untouched.
    """
    if not scope:
        return scope
    from transversal.services.effect_targets import parse_scope
    prefix, value = parse_scope(scope)
    parsed = _parse_placeholder(value or "")
    if parsed is not None and parsed[0] == "random":
        kind = parsed[1] or "universe"
        candidates = resolve_candidates(kind, None, entity, repo)
        if candidates:
            cid = random.choice([c.id for c in candidates])
            return f"{prefix}:{cid}" if prefix else cid
    return scope


def _random_candidate(kind: str, scope: Optional[str], entity: Entity, repo, action: Optional[str] = None, filter: Optional[dict] = None) -> Optional[str]:
    """Return a random in-scope candidate id for the given target kind.

    Delegates to the shared :mod:`effect_targets` resolver so the ``random``
    target mode and the frontend choose-picker see the same candidates.
    """
    scope = _resolve_scope(scope, entity, repo)
    candidates = resolve_candidates(kind, scope, entity, repo, action, filter)
    return random.choice([c.id for c in candidates]) if candidates else None


_SELF_FIELDS = {
    "location": "current_location",
    "universe": "current_universe",
    "projection": "current_projection",
}


def _parse_self_field(token: str) -> Optional[str]:
    """Return the entity attribute for a ``self.<field>`` token, else ``None``."""
    if token.startswith("self."):
        return _SELF_FIELDS.get(token[len("self."):])
    return None


def _resolve_target(entity: Entity, effect: Effect, result: EffectsResult, kind: str, repo) -> Optional[str]:
    """Resolve a target to an id, record a PendingChoice, or pick a random candidate.

    - ``self`` → the entity's own id.
    - ``{choose_*}`` / empty → a PendingChoice the caller resolves later.
    - ``{random:*}`` → a random in-scope candidate (no PendingChoice).
    - anything else → returned as a literal target id.
    """
    target = effect.target or ""
    if target == "self":
        return entity.id
    attr = _parse_self_field(target)
    if attr is not None:
        return getattr(entity, attr, None)
    parsed = _parse_placeholder(target)
    if parsed is not None:
        mode, choose_kind = parsed
        resolved_kind = choose_kind or kind
        if mode == "random":
            return _random_candidate(resolved_kind, effect.target_scope, entity, repo, effect.action, effect.target_filter)
        result.pending_choices.append(
            PendingChoice(effect=effect, kind=resolved_kind, scope=effect.target_scope)
        )
        return None
    if target == "":
        result.pending_choices.append(
            PendingChoice(effect=effect, kind=kind, scope=effect.target_scope)
        )
        return None
    return target


def _effect_subject(entity: Entity, effect: Effect, result: EffectsResult, repo):
    """Resolve the entity an effect acts on (``effect.entity``).

    Blank or ``"self"`` means the applyEffects entity. A ``{choose_entity}`` /
    ``{random:entity}`` placeholder resolves through the same candidate machinery
    as ``target``; anything else is treated as a literal entity id.
    """
    if effect.entity_spec is not None:
        from transversal.services.target_resolver import TargetContext, resolve

        resolution = resolve(effect.entity_spec, TargetContext(subject=entity, repo=repo))
        if resolution.values:
            return resolution.values[0]
        result.applied.append(AppliedEffect(effect, "entity spec resolved to nothing"))
        return None
    subject = (effect.entity or "").strip()
    if subject in ("", "self") or subject == entity.id:
        return entity
    attr = _parse_self_field(subject)
    if attr is not None:
        ref_id = getattr(entity, attr, None)
        return repo.get_entity(ref_id) if ref_id else None
    parsed = _parse_placeholder(subject)
    if parsed is not None:
        mode, kind = parsed
        resolved_kind = kind or "entity"
        if mode == "random":
            cid = _random_candidate(resolved_kind, effect.entity_scope, entity, repo, effect.action, effect.target_filter)
            return repo.get_entity(cid) if cid else None
        result.pending_choices.append(
            PendingChoice(effect=effect, kind=resolved_kind, scope=effect.entity_scope, field="entity")
        )
        return None
    subject_entity = repo.get_entity(subject)
    if subject_entity is None:
        result.applied.append(AppliedEffect(effect, f"entity {subject} not found"))
        return None
    return subject_entity


def _track_subject(result: EffectsResult, primary: Entity, subject: Entity) -> None:
    """Record a cross-entity subject so commit_effects persists it."""
    if subject is not None and subject is not primary and subject not in result.entities_to_update:
        result.entities_to_update.append(subject)


def resolve_choice(choice: PendingChoice, target: str) -> Effect:
    """Resolve a pending choice to a concrete target, returning a re-appliable effect.

    The returned effect has the pending field (``target``, ``entity``, or a
    ``context.*`` sub-field) set to the chosen id and can be passed back to
    :func:`apply_effects` (or ``commit_effects``) to complete the mutation.
    """
    field = choice.field
    if field in ("target_scope", "entity_scope"):
        return choice.effect.model_copy(update={field: _resolve_scope_choose(getattr(choice.effect, field), target)})
    if "." in field:
        top, _, sub = field.partition(".")
        ctx = dict(choice.effect.context or {})
        ctx[sub] = target
        return choice.effect.model_copy(update={top: ctx})
    return choice.effect.model_copy(update={field: target})


# ── Mutation handlers ────────────────────────────────

def _apply_gain(entity, effect, repo, result):
    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)
    target = _resolve_target(subject, effect, result, "trait", repo)
    if target is None:
        return
    owner = _trait_owner(subject, effect, repo)
    if _find_traitsetting_by_target(subject, effect, repo, target):
        result.applied.append(AppliedEffect(effect, f"trait {target} already present"))
        return
    die = _die(effect.result)
    ts = _new_traitsetting(owner, target, die, repo, negative=bool(effect.negative),
                           rating_type=_rating_type(effect), statement=_ctx(effect, "statement"), notes=_ctx(effect, "notes"))
    result.new_trait_settings.append(ts)
    result.applied.append(AppliedEffect(effect, f"gained {target} at {die.value}", ts.id))
    _queue_entity_revert(repo, subject, effect, target=target)


def _apply_gain_or_step_up(entity, effect, repo, result):
    """Create at ``result`` if absent, then step up; or step up an existing trait.

    Without an explicit ``steps`` this preserves the historical behavior (create
    at ``result``, or step up once). With ``steps`` set, both paths step up that
    many times — ``result`` is then the base die (e.g. d4 + ``steps``).
    """
    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)
    target = _resolve_target(subject, effect, result, "trait", repo)
    if target is None:
        return
    owner = _trait_owner(subject, effect, repo)
    existing = _find_traitsetting_by_target(subject, effect, repo, target)
    steps = _steps(effect)
    if existing:
        if _step_up_trait(subject, existing, target, effect, result, repo, steps=steps):
            result.updated_trait_settings.append(existing)
            result.applied.append(AppliedEffect(effect, f"stepped up {target}", existing.id))
            _queue_explicit(repo, existing, effect, "step_down", target)
            _maybe_complete_challenge(existing, subject)
        return
    die = _die(effect.result)
    ts = _new_traitsetting(owner, target, die, repo, negative=bool(effect.negative),
                           rating_type=_rating_type(effect), statement=_ctx(effect, "statement"), notes=_ctx(effect, "notes"))
    if _has_steps(effect):
        _step_up_trait(subject, ts, target, effect, result, repo, steps=steps)
    result.new_trait_settings.append(ts)
    final_die = ts.dice[0] if ts.dice else die
    result.applied.append(AppliedEffect(effect, f"gained {target} at {final_die.value}", ts.id))
    _queue_explicit(repo, subject, effect, "remove", target)


def _apply_cortex_gain(entity, effect, repo, result):
    """Cortex-style trait application: create at the effect die if absent.

    If the trait already exists, compare the effect die against the current
    rating: a higher effect die jumps the rating straight up to it (d8→d12 is
    legal); otherwise step up one step.  Polarity comes from ``effect.negative``
    (only used when the trait is first created).
    """
    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)
    target = _resolve_target(subject, effect, result, "trait", repo)
    if target is None:
        return
    owner = _trait_owner(subject, effect, repo)
    die = _die(effect.result)
    negative = bool(effect.negative)
    existing = _find_traitsetting_by_target(subject, effect, repo, target)
    if existing:
        if not existing.dice:
            existing.dice = [die]
            result.updated_trait_settings.append(existing)
            result.applied.append(AppliedEffect(effect, f"gained {target} at {die.value}", existing.id))
            return
        # Single-die rating assumption (Cortex traits/complications); choosing
        # one die from a multi-die rating is deferred.
        rating = existing.dice[0]
        if die.max_value > rating.max_value:
            existing.dice = [die]
            result.updated_trait_settings.append(existing)
            result.applied.append(AppliedEffect(effect, f"{target} jumped to {die.value}", existing.id))
        elif _step_up_trait(subject, existing, target, effect, result, repo):
            result.updated_trait_settings.append(existing)
            result.applied.append(AppliedEffect(effect, f"stepped up {target}", existing.id))
        return
    ts = _new_traitsetting(owner, target, die, repo, negative=negative,
                           rating_type=_rating_type(effect), statement=_ctx(effect, "statement"), notes=_ctx(effect, "notes"))
    result.new_trait_settings.append(ts)
    result.applied.append(AppliedEffect(effect, f"gained {target} at {die.value}", ts.id))


def _apply_step_up(entity, effect, repo, result):
    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)
    target = _resolve_target(subject, effect, result, "trait", repo)
    if target is None:
        return
    existing = _find_traitsetting_by_target(subject, effect, repo, target)
    if not existing:
        result.applied.append(AppliedEffect(effect, f"no trait {target} to step up"))
        return
    if _step_up_trait(subject, existing, target, effect, result, repo, steps=_steps(effect)):
        result.updated_trait_settings.append(existing)
        result.applied.append(AppliedEffect(effect, f"stepped up {target}", existing.id))
        _queue_trait_revert(repo, existing, effect)
        _maybe_complete_challenge(existing, subject)


def _apply_step_down(entity, effect, repo, result):
    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)
    target = _resolve_target(subject, effect, result, "trait", repo)
    if target is None:
        return
    existing = _find_traitsetting_by_target(subject, effect, repo, target)
    if not existing:
        result.applied.append(AppliedEffect(effect, f"no trait {target} to step down"))
        return
    for _ in range(_steps(effect)):
        status = _step_down_one(existing)
        if status == "stepped":
            continue
        result.applied.append(AppliedEffect(effect, f"{target} has no dice to step down"))
        return
    result.updated_trait_settings.append(existing)
    result.applied.append(AppliedEffect(effect, f"stepped down {target}", existing.id))
    _queue_trait_revert(repo, existing, effect)


def _maybe_complete_challenge(ts: TraitSetting, subject: Entity) -> None:
    """Fire the completion event when a positive challenge reaches capacity."""
    from transversal.services.challenge_pools import fire_challenge_completed
    universe = subject.current_universe if subject else ""
    fire_challenge_completed(ts, universe)


def _apply_add_die(entity, effect, repo, result):
    """Add a die to a trait setting's rating (any rating type).

    Appends ``effect.result`` (a die size, e.g. ``d6``) to the trait setting's
    ``dice`` list. Static/resource/challenge ratings are all a ``dice`` list, so
    this is type-agnostic; the duration revert removes the same die. A positive
    challenge pool is bounded by its ``capacity`` (the completion target).
    """
    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)
    target = _resolve_target(subject, effect, result, "trait", repo)
    if target is None:
        return
    existing = _find_traitsetting_by_target(subject, effect, repo, target)
    if not existing:
        result.applied.append(AppliedEffect(effect, f"no trait {target} to add a die to"))
        return
    if (
        existing.rating_type == RatingType.CHALLENGE
        and existing.polarity == Polarity.POSITIVE
        and existing.capacity
        and len(existing.dice) >= len(existing.capacity)
    ):
        result.applied.append(AppliedEffect(effect, f"{target} is already at capacity"))
        return
    die = _die(effect.result)
    existing.dice.append(die)
    result.updated_trait_settings.append(existing)
    result.applied.append(AppliedEffect(effect, f"added {die.value} to {target}", existing.id))
    _queue_trait_revert(repo, existing, effect)
    _maybe_complete_challenge(existing, subject)


def _apply_remove_die(entity, effect, repo, result):
    """Remove a die from a trait setting's rating (any rating type).

    Removes the first die matching ``effect.result`` from the trait setting's
    ``dice`` list. The duration revert re-adds the same die.
    """
    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)
    target = _resolve_target(subject, effect, result, "trait", repo)
    if target is None:
        return
    existing = _find_traitsetting_by_target(subject, effect, repo, target)
    if not existing or not existing.dice:
        result.applied.append(AppliedEffect(effect, f"no trait {target} to remove a die from"))
        return
    die = _die(effect.result)
    for i, d in enumerate(existing.dice):
        if d == die:
            existing.dice.pop(i)
            break
    else:
        result.applied.append(AppliedEffect(effect, f"{target} has no {die.value} to remove"))
        return
    result.updated_trait_settings.append(existing)
    result.applied.append(AppliedEffect(effect, f"removed {die.value} from {target}", existing.id))
    _queue_trait_revert(repo, existing, effect)


def _apply_reduce_by_effect(entity, effect, repo, result):
    """Reduce a trait by the effect-die-vs-rating comparison.

    ``effect.context.effect_die`` is the winning effect die (``{effect_die}``
    substituted at fire time). If it is strictly larger than the trait's rating
    die the trait is removed; otherwise it steps down one step. Shared
    comparison via ``dice_resolver.compare_effect_die``.
    """
    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)
    target = _resolve_target(subject, effect, result, "trait", repo)
    if target is None:
        return
    existing = _find_traitsetting_by_target(subject, effect, repo, target)
    if not existing or not existing.dice:
        result.applied.append(AppliedEffect(effect, f"no trait {target} to reduce"))
        return

    raw_die = (effect.context or {}).get("effect_die")
    try:
        effect_die = DieType(str(raw_die).lower()) if raw_die else None
    except ValueError:
        effect_die = None
    if effect_die is None:
        result.applied.append(AppliedEffect(effect, "no effect die to compare"))
        return

    target_die = existing.dice[0]
    from transversal.services.dice_resolver import compare_effect_die
    if compare_effect_die(effect_die, target_die) == "remove":
        result.removed_trait_settings.append(existing)
        result.applied.append(
            AppliedEffect(effect, f"removed {target} (effect die {effect_die.value} beats {target_die.value})", existing.id)
        )
    else:
        status = _step_down_one(existing)
        if status != "stepped":
            result.applied.append(AppliedEffect(effect, f"{target} has no dice to step down"))
            return
        result.updated_trait_settings.append(existing)
        result.applied.append(
            AppliedEffect(effect, f"stepped down {target} (effect die {effect_die.value} ≤ {target_die.value})", existing.id)
        )
        _queue_trait_revert(repo, existing, effect)


def _apply_set(entity, effect, repo, result):
    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)
    target = _resolve_target(subject, effect, result, "trait", repo)
    if target is None:
        return
    existing = _find_traitsetting_by_target(subject, effect, repo, target)
    if not existing:
        result.applied.append(AppliedEffect(effect, f"no trait {target} to set"))
        return
    die = _die(effect.result)
    prior = existing.dice[0].value if existing.dice else None
    existing.dice = [die]
    result.updated_trait_settings.append(existing)
    result.applied.append(AppliedEffect(effect, f"set {target} to {die.value}", existing.id))
    _queue_trait_revert(repo, existing, effect, prior_result=prior)


def _apply_disable(entity, effect, repo, result):
    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)
    target = _resolve_target(subject, effect, result, "trait", repo)
    if target is None:
        return
    ts = _find_traitsetting_by_target(subject, effect, repo, target)
    if ts is None:
        result.applied.append(AppliedEffect(effect, f"no trait {target} to disable"))
        return
    if not ts.enabled:
        result.applied.append(AppliedEffect(effect, f"{target} already disabled"))
        return
    ts.enabled = False
    result.updated_trait_settings.append(ts)
    result.applied.append(AppliedEffect(effect, f"disabled {target}", ts.id))
    _queue_trait_revert(repo, ts, effect)


def _apply_enable(entity, effect, repo, result):
    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)
    target = _resolve_target(subject, effect, result, "trait", repo)
    if target is None:
        return
    ts = _find_traitsetting_by_target(subject, effect, repo, target)
    if ts is None:
        result.applied.append(AppliedEffect(effect, f"no trait {target} to enable"))
        return
    if ts.enabled:
        result.applied.append(AppliedEffect(effect, f"{target} already enabled"))
        return
    ts.enabled = True
    result.updated_trait_settings.append(ts)
    result.applied.append(AppliedEffect(effect, f"enabled {target}", ts.id))


def _apply_toggle(entity, effect, repo, result):
    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)
    target = _resolve_target(subject, effect, result, "trait", repo)
    if target is None:
        return
    ts = _find_traitsetting_by_target(subject, effect, repo, target)
    if ts is None:
        result.applied.append(AppliedEffect(effect, f"no trait {target} to toggle"))
        return
    ts.enabled = not ts.enabled
    result.updated_trait_settings.append(ts)
    state = "enabled" if ts.enabled else "disabled"
    result.applied.append(AppliedEffect(effect, f"toggled {target} → {state}", ts.id))
    _queue_trait_revert(repo, ts, effect)


def _apply_cancel_scheduled_event(entity, effect, repo, result):
    """Cancel a specific pending timer (target = a scheduled-event id)."""
    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)
    target = _resolve_target(subject, effect, result, "scheduled_event", repo)
    if target is None:
        return  # pending choice (or no candidate)
    if repo.delete_scheduled_event(target):
        result.applied.append(AppliedEffect(effect, f"ended active effect {target}", target))
    else:
        result.applied.append(AppliedEffect(effect, f"no active effect {target} to end"))


def _apply_create_projection(entity, effect, repo, result):
    """Create + activate a temporary alternate body (disguise) in the current
    universe/location; schedule a restore of the prior body on expiry."""
    from transversal.domain import Projection, TransversalType
    from transversal.services.entity_manager import touch_projection

    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)

    ctx = effect.context or {}
    name = (effect.target or "").strip() or (ctx.get("name") or "").strip() or "disguise"
    prior = subject.current_projection
    proj = Projection(
        id=_next_projection_id(subject.id, subject.current_universe, repo),
        entity_id=subject.id,
        origin_universe=subject.current_universe,
        universe=subject.current_universe,
        name=name,
        current_location=subject.current_location,
        transversal_type=TransversalType.NATIVE,
    )
    touch_projection(proj)
    result.new_projections.append(proj)
    subject.current_projection = proj.id
    result.applied.append(AppliedEffect(effect, f"disguised as {name} ({proj.id})", proj.id))
    _queue_entity_revert(repo, subject, effect, prior_result=prior)


def _apply_restore_projection(entity, effect, repo, result):
    """Revert a temporary projection: re-activate the prior body at the current
    location and delete the temporary (disguise) body."""
    from transversal.services.entity_manager import touch_projection

    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)

    prior_id = (effect.result or "").strip()
    if not prior_id:
        return
    prior = repo.get_projection(prior_id)
    if prior is None:
        result.applied.append(AppliedEffect(effect, f"prior body {prior_id} not found"))
        return
    disguise_id = subject.current_projection
    if disguise_id and disguise_id != prior_id:
        disguise = repo.get_projection(disguise_id)
        if disguise is not None:
            result.removed_projections.append(disguise)
    prior.current_location = subject.current_location
    touch_projection(prior)
    result.updated_projections.append(prior)
    subject.current_projection = prior.id
    result.applied.append(AppliedEffect(effect, f"restored body {prior.id}"))


def _find_traitsetsetting(entity_id: str, traitset_id: str, repo) -> Optional[TraitSetSetting]:
    for tss in repo.get_traitsetsettings_for_entity(entity_id):
        if tss.traitset_id == traitset_id and tss.from_type == "entity":
            return tss
    return None


def _apply_set_traitset_limit(entity, effect, repo, result):
    """Override how many traits this entity can hold in a trait set.

    ``result`` is the new limit (integer). Empty result clears the override.
    Duration-driven reverts restore the prior limit (or clear).
    """
    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)
    target = _resolve_target(subject, effect, result, "traitset", repo)
    if target is None:
        return
    raw = (effect.result or "").strip()
    existing = _find_traitsetsetting(subject.id, target, repo)

    if raw == "":
        if existing is not None and existing.limit is not None:
            existing.limit = None
            result.updated_traitsetsettings.append(existing)
            result.applied.append(AppliedEffect(effect, f"cleared {target} limit override", existing.id))
        return

    try:
        new_limit = max(int(raw), 0)
    except (TypeError, ValueError):
        new_limit = 1

    prior = existing.limit if existing is not None else None
    if existing is None:
        tss = TraitSetSetting(
            id=f"{subject.id}:{target}", entity_id=subject.id, traitset_id=target,
            from_type="entity", limit=new_limit,
        )
        result.new_traitsetsettings.append(tss)
        result.applied.append(AppliedEffect(effect, f"set {target} limit to {new_limit}", tss.id))
        _queue_entity_revert(repo, subject, effect, prior_result="")
    else:
        existing.limit = new_limit
        result.updated_traitsetsettings.append(existing)
        result.applied.append(AppliedEffect(effect, f"set {target} limit to {new_limit}", existing.id))
        _queue_entity_revert(repo, subject, effect, prior_result=str(prior) if prior is not None else "")


def _apply_dice_limit(entity, effect, repo, result):
    """Increase/decrease the dice-pool selection limits (total vs effect dice).

    ``effect.result`` is the delta magnitude (default 1); ``effect.context.limit``
    selects ``total`` (base 2) or ``effect`` (base 1). The delta is applied to
    ``Entity.total_dice_bonus`` / ``Entity.effect_dice_bonus``; a duration on the
    effect schedules the inverse (opposite sign, same magnitude) on expiry.
    """
    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)

    which = (effect.context or {}).get("limit") or "total"
    raw = (effect.result or "").strip()
    try:
        amount = int(raw)
    except (TypeError, ValueError):
        amount = 1
    delta = amount if effect.action == "increase" else -amount

    if which == "effect":
        subject.effect_dice_bonus = (subject.effect_dice_bonus or 0) + delta
    else:
        subject.total_dice_bonus = (subject.total_dice_bonus or 0) + delta

    result.applied.append(AppliedEffect(effect, f"{effect.action}d {which} dice limit by {amount}"))
    _queue_entity_revert(repo, subject, effect)


def _resolve_pool(target: str, entity, repo) -> tuple[str, str]:
    """Map a resolved pool target id to ``(location_id, owner_id)``.

    Accepts the composite ids the targeting resolver produces
    (``difficulty:<location>``, ``pool:<entity>``) plus a bare entity/location id
    as a fallback (a location id implies the GM difficulty pool).
    """
    t = (target or "").strip()
    if not t:
        return ("", "")
    if t.startswith("difficulty:"):
        loc = t[len("difficulty:"):]
        return (loc, loc)
    if t.startswith("pool:"):
        owner_id = t[len("pool:"):]
        owner = repo.get_entity(owner_id)
        return (owner.current_location if owner else "", owner_id)
    owner = repo.get_entity(t)
    if owner is not None:
        loc = owner.id if owner.type == "location" else owner.current_location
        return (loc or "", owner.id)
    return ("", "")


def _apply_add_dice(entity, effect, repo, result):
    """Add dice to a targeted dice pool (the GM difficulty pool or an entity's).

    ``effect.target`` is a resolved pool id (``difficulty:<loc>`` or
    ``pool:<entity>``); ``effect.context.dice`` is the list of die sizes to add.
    """
    from transversal.services.contest_tracker import broadcast_pool_change
    from transversal.services.scene_state import get_scene_store

    dice = (effect.context or {}).get("dice") or []
    if isinstance(dice, str):
        dice = [d.strip() for d in dice.split(",") if d.strip()]
    if not dice:
        result.applied.append(AppliedEffect(effect, "no dice to add"))
        return

    location_id, owner_id = _resolve_pool(effect.target, entity, repo)
    if not location_id or not owner_id:
        result.applied.append(AppliedEffect(effect, f"pool target not found: {effect.target}"))
        return

    store = get_scene_store()
    pool = store.get_pool(location_id, owner_id)
    for die in dice:
        pool.append({"die": die, "source_kind": "sfx", "source_id": "", "label": die, "ts_id": None})
    store.save_pool(location_id, owner_id, pool)
    broadcast_pool_change(location_id, owner_id, dice=pool, phase="adding")
    result.applied.append(AppliedEffect(effect, f"added {len(dice)} dice to {owner_id} pool"))


def _add_trait_rating_to_pool(ts_id: str, pool_id: str, entity, repo):
    """Add a trait setting's rating dice to a pool; return ``(location_id, owner_id)``.

    Returns ``(None, None)`` when the trait is missing/has no rating, or the pool
    target is unresolvable.
    """
    from transversal.services.contest_tracker import broadcast_pool_change
    from transversal.services.scene_state import get_scene_store

    ts = repo.get_traitsetting(ts_id) if ts_id else None
    if ts is None or not ts.dice:
        return (None, None)
    location_id, owner_id = _resolve_pool(pool_id, entity, repo)
    if not location_id or not owner_id:
        return (None, None)

    trait = repo.get_trait(ts.trait_id)
    label = trait.name if trait else ts.trait_id
    dice = [d.value for d in ts.dice]
    store = get_scene_store()
    pool = store.get_pool(location_id, owner_id)
    for die in dice:
        pool.append({"die": die, "source_kind": "trait", "source_id": ts.id, "label": label, "ts_id": ts.id})
    store.save_pool(location_id, owner_id, pool)
    broadcast_pool_change(location_id, owner_id, dice=pool, phase="adding")
    return (location_id, owner_id)


def _apply_add_trait_rating(entity, effect, repo, result):
    """Add a trait instance's rating dice to a targeted dice pool.

    ``refs["trait"]`` is a resolved ``traitsetting`` id (the complication to
    heal); ``refs["pool"]`` is a resolved pool id (``difficulty:<loc>`` or
    ``pool:<entity>``). Both are authored through the targeting wizard.
    """
    trait_ref = (effect.refs or {}).get("trait")
    pool_ref = (effect.refs or {}).get("pool")
    ts_id = trait_ref.value if trait_ref else ""
    pool_id = pool_ref.value if pool_ref else ""

    ts = repo.get_traitsetting(ts_id) if ts_id else None
    if ts is None:
        result.applied.append(AppliedEffect(effect, f"trait {ts_id or '(unset)'} not found"))
        return
    if not ts.dice:
        result.applied.append(AppliedEffect(effect, f"trait {ts_id} has no rating"))
        return

    loc = _add_trait_rating_to_pool(ts_id, pool_id, entity, repo)
    if loc == (None, None):
        result.applied.append(AppliedEffect(effect, f"pool target not found: {pool_id or '(unset)'}"))
        return
    trait = repo.get_trait(ts.trait_id)
    label = trait.name if trait else ts.trait_id
    result.applied.append(AppliedEffect(effect, f"added {label} rating {[d.value for d in ts.dice]} to pool"))


def _resolve_pool_ref(effect):
    """Return the resolved pool id from ``refs["pool"]`` or the literal ``target``."""
    pool_ref = (effect.refs or {}).get("pool")
    return (pool_ref.value if pool_ref else "") or (effect.target or "")


def _roll_stored_pool(location_id: str, owner_id: str):
    """Roll a stored pool in place; return the enriched dice, or None if empty.

    Mirrors the REST ``difficulty-roll`` (no hitches reported): rolls every die,
    saves the enriched result, and broadcasts ``pool_updated`` phase="rolled".
    """
    from transversal.services.contest_tracker import broadcast_pool_change
    from transversal.services.scene_state import get_scene_store
    from transversal.services.dice_resolver import roll_dice
    from transversal.domain import DieSpec

    store = get_scene_store()
    dice = store.get_pool(location_id, owner_id)
    if not dice:
        return None

    specs = [
        DieSpec(
            die=DieType(d["die"]),
            source_kind=d.get("source_kind", "manual"),
            source_id=d.get("source_id", ""),
            label=d.get("label", ""),
            ts_id=d.get("ts_id"),
            resource=d.get("resource", False),
        )
        for d in dice
    ]
    rolls = roll_dice(specs)
    enriched = [
        {**d, "result": r.result, "hitch": r.result == 1, "role": None, "bought": False,
         "tier": r.tier.value if r.tier else None,
         "effect_die": r.tier.effect_die.value if r.tier and r.tier.effect_die else None}
        for d, r in zip(dice, rolls)
    ]
    store.save_pool(location_id, owner_id, enriched)
    broadcast_pool_change(location_id, owner_id, dice=enriched, phase="rolled")
    return enriched


def _apply_roll_pool(entity, effect, repo, result):
    """Roll a target dice pool in place and broadcast the result.

    The pool is resolved from ``refs["pool"]`` (or ``effect.target``); every die
    is rolled and the enriched result is broadcast — no difficulty is set.
    """
    pool_id = _resolve_pool_ref(effect)
    location_id, owner_id = _resolve_pool(pool_id, entity, repo)
    if not location_id or not owner_id:
        result.applied.append(AppliedEffect(effect, f"pool target not found: {pool_id or '(unset)'}"))
        return

    enriched = _roll_stored_pool(location_id, owner_id)
    if enriched is None:
        result.applied.append(AppliedEffect(effect, f"pool {owner_id} is empty"))
        return
    result.applied.append(AppliedEffect(effect, f"rolled {owner_id} pool ({len(enriched)} dice)"))


def _apply_resolve_pool(entity, effect, repo, result):
    """Auto-resolve a target dice pool: roll it, auto-pick the total, set difficulty.

    Rolls the pool (see ``_apply_roll_pool``), then sums the two highest dice
    (the standard keep-2 opposition total) and sets the location's difficulty,
    broadcasting ``difficulty_set`` — the GM's manual total-pick step is gone.
    """
    pool_id = _resolve_pool_ref(effect)
    location_id, owner_id = _resolve_pool(pool_id, entity, repo)
    if not location_id or not owner_id:
        result.applied.append(AppliedEffect(effect, f"pool target not found: {pool_id or '(unset)'}"))
        return

    enriched = _roll_stored_pool(location_id, owner_id)
    if enriched is None:
        result.applied.append(AppliedEffect(effect, f"pool {owner_id} is empty"))
        return

    # Auto-select the two highest as the total (the keep-2 opposition total),
    # marking their role so the difficulty tab renders the resolved selection
    # rather than empty slots.
    order = sorted(range(len(enriched)), key=lambda i: (enriched[i].get("result") or 0), reverse=True)
    for i in order[:2]:
        enriched[i]["role"] = "total"
    total = sum((enriched[i].get("result") or 0) for i in order[:2])

    from transversal.services.scene_state import get_scene_store
    from transversal.services.contest_tracker import broadcast_pool_change
    from transversal.api.sse.bus import StreamEvent, event_bus
    from transversal.services.session_manager import session_manager

    store = get_scene_store()
    store.save_pool(location_id, owner_id, enriched)
    broadcast_pool_change(location_id, owner_id, dice=enriched, phase="resolved")

    store.set_difficulty(location_id, total)
    for s in session_manager.list_active():
        event_bus.publish(StreamEvent(
            event="difficulty_set",
            session_id=s.id,
            data={"difficulty": total, "location_id": location_id},
        ))

    result.applied.append(AppliedEffect(effect, f"resolved {owner_id} pool → difficulty {total}"))


def _apply_earn(entity, effect, repo, result):
    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)
    amount = int(effect.result or "0")
    subject.razmerit += amount
    result.applied.append(AppliedEffect(effect, f"earned {amount} razmerit"))


def _apply_spend(entity, effect, repo, result):
    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)
    amount = int(effect.result or "0")
    subject.razmerit -= amount
    result.applied.append(AppliedEffect(effect, f"spent {amount} razmerit"))


def _apply_transfer(entity, effect, repo, result):
    target = _resolve_target(entity, effect, result, "entity", repo)
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
    target = _resolve_target(entity, effect, result, "life_path", repo)
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
    target = _resolve_target(entity, effect, result, "entity", repo)
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


def _apply_remove(entity, effect, repo, result):
    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)
    target = _resolve_target(subject, effect, result, "trait", repo)
    if target is None:
        return
    existing = _find_traitsetting_by_target(subject, effect, repo, target)
    if not existing:
        result.applied.append(AppliedEffect(effect, f"no trait {target} to remove"))
        return
    result.removed_trait_settings.append(existing)
    result.applied.append(AppliedEffect(effect, f"removed {target}", existing.id))


def _resolve_learner(entity: Entity, effect: Effect, result: EffectsResult) -> Optional[str]:
    """Resolve who learns a revealed trait.

    ``effect.context.learner`` defaults to ``"self"`` (the entity the effect
    is applied to — the activating entity for a manual SFX).  A literal entity
    id passes through.  ``{choose_*}` / ``{random:*}` placeholders are not yet
    supported here (the owner entity is the intended dynamic piece for spying).
    """
    learner = (effect.context or {}).get("learner") or "self"
    learner = (learner or "").strip()
    if learner in ("", "self"):
        return entity.id
    if _parse_placeholder(learner) is not None:
        result.applied.append(AppliedEffect(effect, f"learner placeholder not supported: {learner}"))
        return None
    return learner


def _apply_reveal(entity, effect, repo, result):
    """Add the learner to a trait setting's ``known_to`` (fog of war)."""
    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)
    target = _resolve_target(subject, effect, result, "trait", repo)
    if target is None:
        return
    ts = _find_traitsetting_by_target(subject, effect, repo, target)
    if ts is None:
        result.applied.append(AppliedEffect(effect, f"no trait {target} to reveal"))
        return
    learner = _resolve_learner(entity, effect, result)
    if learner is None:
        return
    if reveal_trait_to(ts, learner):
        result.revealed.append((ts, learner))
        result.applied.append(AppliedEffect(effect, f"revealed {target} to {learner}", ts.id))
    else:
        result.applied.append(AppliedEffect(effect, f"{learner} already knows {target}"))


def _queue_trait_revert(repo, ts, effect, prior_result=None):
    """Schedule the inverse of ``effect`` on a trait setting in the central store."""
    from transversal.services.scheduled_events import schedule_revert

    schedule_revert(repo, "trait_setting", ts.id, effect, prior_result=prior_result)


def _queue_entity_revert(repo, entity, effect, target=None, prior_result=None):
    """Schedule the inverse of ``effect`` on an entity in the central store."""
    from transversal.services.scheduled_events import schedule_revert

    schedule_revert(repo, "entity", entity.id, effect, target=target, prior_result=prior_result)


def _queue_explicit(repo, owner, effect, action, target):
    """Schedule an explicit inverse action (for compound actions like gain_or_step_up)."""
    if not effect.duration or not effect.duration.timers:
        return
    from transversal.domain import Effect as _Effect, EffectTiming as _ET
    from transversal.services.scheduled_events import schedule_event

    target_type = "trait_setting" if hasattr(owner, "trait_id") else "entity"
    schedule_event(
        repo, target_type, owner.id,
        _Effect(timing=_ET.IMMEDIATE, type="modify_trait", action=action, target=target),
        effect.duration.timers,
        effect.duration.combine,
    )


def _next_projection_id(entity_id: str, universe: str, repo) -> str:
    """Generate a unique projection key (first body keeps the legacy key)."""
    base = f"{entity_id}:{universe}"
    existing = {p.id for p in repo.get_projections_for_entity(entity_id)}
    if base not in existing:
        return base
    n = 2
    while f"{base}:{n}" in existing:
        n += 1
    return f"{base}:{n}"


def _scope_universe(scope: Optional[str]) -> Optional[str]:
    """Return a literal universe from a ``universe:X`` scope, else None."""
    from transversal.services.effect_targets import parse_scope
    if not scope:
        return None
    prefix, value = parse_scope(scope)
    if prefix == "universe" and value and not value.startswith("{"):
        return value
    return None


def _apply_set_location(entity, effect, repo, result):
    """Place an entity at a location without crossing a universal boundary.

    Sets the entity's ``current_location`` (and its active body's location).
    The destination location's universe, when known, is authoritative — matching
    the REST ``move`` endpoint. Unlike ``travel``, no body/transversal policy
    applies: the active body simply relocates.

    If the subject has no active body, a fresh native body is created — mirroring
    ``EntityManager.move_to`` — so an unplaced character is never left bodiless.
    """
    from transversal.domain import Projection, TransversalType
    from transversal.services.entity_manager import touch_projection

    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)

    location_id = _resolve_target(subject, effect, result, "location", repo)
    if location_id is None:
        return  # pending choice recorded

    loc = repo.get_entity(location_id)
    dest_universe = loc.current_universe if loc is not None and loc.current_universe else subject.current_universe

    subject.current_location = location_id
    subject.current_universe = dest_universe

    proj = repo.get_projection(subject.current_projection) if subject.current_projection else None
    if proj is not None:
        proj.current_location = location_id
        proj.universe = dest_universe
        touch_projection(proj)
        result.updated_projections.append(proj)
    else:
        proj = Projection(
            id=_next_projection_id(subject.id, dest_universe, repo),
            entity_id=subject.id,
            origin_universe=dest_universe,
            universe=dest_universe,
            current_location=location_id,
            transversal_type=TransversalType.NATIVE,
        )
        touch_projection(proj)
        result.new_projections.append(proj)
        subject.current_projection = proj.id

    result.applied.append(AppliedEffect(effect, f"placed at {location_id}"))


def _apply_travel(entity, effect, repo, result):
    """Cross a universal boundary, honoring subject/location/mechanism/body/universe.

    Subject = ``effect.entity``. Destination location = ``effect.target`` (literal,
    ``{choose_location}``, or ``{random:location}``). Universe = ``effect.target_scope``
    (``universe:X``) or, for a location scope, the target location's universe.
    Mechanism = ``context.transversal_type``. Body policy = ``context.projection``.

    Inapposite always uses the active body (it travels). Consciousness picks a
    body via ``{last_projection}`` / ``{random_projection}`` / ``{choose_projection}``
    (reuse an existing body in the destination universe, falling back to a fresh
    body when there is none) or ``{new_projection}`` (always spawn).
    """
    from transversal.domain import Projection, TransversalType
    from transversal.services.entity_manager import touch_projection

    subject = _effect_subject(entity, effect, result, repo)
    if subject is None:
        return
    _track_subject(result, entity, subject)

    ctx = effect.context or {}
    travel_type = ctx.get("transversal_type") or "inapposite"
    projection_policy = (ctx.get("projection") or "active").strip()

    def _spawn_body(dest_universe: str, location_id: str, trans_type: TransversalType) -> None:
        proj = Projection(
            id=_next_projection_id(subject.id, dest_universe, repo),
            entity_id=subject.id,
            origin_universe=dest_universe,
            universe=dest_universe,
            current_location=location_id,
            transversal_type=trans_type,
        )
        touch_projection(proj)
        result.new_projections.append(proj)
        subject.current_projection = proj.id
        subject.current_universe = dest_universe
        subject.current_location = location_id
        result.applied.append(AppliedEffect(effect, f"spawned body {proj.id}"))

    def _dest_universe() -> str:
        uni = _scope_universe(effect.target_scope)
        if uni:
            return uni
        target = (effect.target or "").strip()
        if target and not target.startswith("{"):
            loc = repo.get_entity(target)
            if loc and loc.current_universe:
                return loc.current_universe
        return subject.current_universe

    # ── Inapposite — the active body itself travels. ──
    if travel_type != "consciousness":
        location_id = _resolve_target(subject, effect, result, "location", repo)
        if location_id is None:
            return  # pending choice recorded
        dest_universe = _dest_universe()
        proj = repo.get_projection(subject.current_projection) if subject.current_projection else None
        if proj is None:
            _spawn_body(dest_universe, location_id, TransversalType.NATIVE)
        else:
            proj.universe = dest_universe
            proj.current_location = location_id
            proj.transversal_type = (
                TransversalType.NATIVE if dest_universe == proj.origin_universe else TransversalType.INAPPOSITE
            )
            touch_projection(proj)
            result.updated_projections.append(proj)
            subject.current_projection = proj.id
            subject.current_universe = dest_universe
            subject.current_location = location_id
            result.applied.append(AppliedEffect(effect, f"relocated to {location_id}"))
        return

    # ── Consciousness — pick/reuse/spawn a body in the destination universe. ──
    if projection_policy == "active":
        projection_policy = "{last_projection}"  # legacy alias

    dest_universe = _dest_universe()

    def _arrive_in_body(proj) -> None:
        touch_projection(proj)
        result.updated_projections.append(proj)
        subject.current_projection = proj.id
        subject.current_universe = proj.universe
        subject.current_location = proj.current_location
        result.applied.append(AppliedEffect(effect, f"arrived in body {proj.id}"))

    def _spawn_new() -> None:
        location_id = _resolve_target(subject, effect, result, "location", repo)
        if location_id is None:
            return
        _spawn_body(dest_universe, location_id, TransversalType.CONSCIOUSNESS)

    # A literal projection id is a resolved ``{choose_projection}``.
    if projection_policy not in ("{last_projection}", "{new_projection}", "{random_projection}", "{choose_projection}"):
        proj = repo.get_projection(projection_policy)
        if proj is not None:
            _arrive_in_body(proj)
            return
        projection_policy = "{new_projection}"

    if projection_policy in ("{last_projection}", "{random_projection}", "{choose_projection}"):
        scope = effect.target_scope or (f"universe:{dest_universe}" if dest_universe else None)
        candidates = resolve_candidates("projection", scope, subject, repo)
        if candidates:
            if projection_policy == "{choose_projection}":
                result.pending_choices.append(PendingChoice(
                    effect=effect, kind="projection",
                    scope=scope,
                    field="context.projection",
                ))
                return
            if projection_policy == "{last_projection}":
                projs = [repo.get_projection(c.id) for c in candidates]
                projs = [p for p in projs if p is not None]
                projs.sort(key=lambda p: p.last_used_at or "", reverse=True)
                proj = projs[0] if projs else None
            else:
                proj = repo.get_projection(random.choice([c.id for c in candidates]))
            if proj is not None:
                _arrive_in_body(proj)
                return
        projection_policy = "{new_projection}"  # no existing body → spawn a fresh one

    _spawn_new()


_MUTATION_HANDLERS = {
    ("modify_trait", "gain"): _apply_gain,
    ("modify_trait", "remove"): _apply_remove,
    ("modify_trait", "gain_or_step_up"): _apply_gain_or_step_up,
    ("modify_trait", "cortex_gain"): _apply_cortex_gain,
    ("modify_trait", "step_up"): _apply_step_up,
    ("modify_trait", "step_down"): _apply_step_down,
    ("modify_trait", "add_die"): _apply_add_die,
    ("modify_trait", "remove_die"): _apply_remove_die,
    ("modify_trait", "reduce_by_effect"): _apply_reduce_by_effect,
    ("modify_trait", "set"): _apply_set,
    ("modify_trait", "disable"): _apply_disable,
    ("modify_trait", "enable"): _apply_enable,
    ("modify_trait", "toggle"): _apply_toggle,
    ("entity", "cancel_scheduled_event"): _apply_cancel_scheduled_event,
    ("projection", "create"): _apply_create_projection,
    ("projection", "restore"): _apply_restore_projection,
    ("modify_traitset", "set_limit"): _apply_set_traitset_limit,
    ("modify_dice_limit", "increase"): _apply_dice_limit,
    ("modify_dice_limit", "decrease"): _apply_dice_limit,
    ("modify_pool", "add_dice"): _apply_add_dice,
    ("modify_pool", "add_trait_rating"): _apply_add_trait_rating,
    ("modify_pool", "roll"): _apply_roll_pool,
    ("modify_pool", "resolve"): _apply_resolve_pool,
    ("modify_trait", "reveal"): _apply_reveal,
    ("transfer_razmerit", "earn"): _apply_earn,
    ("transfer_razmerit", "spend"): _apply_spend,
    ("transfer_razmerit", "transfer"): _apply_transfer,
    ("life_path", "discover"): _apply_discover,
    ("relationship", "create"): _apply_relationship_create,
    ("travel", "move"): _apply_travel,
    ("location", "set"): _apply_set_location,
}


def apply_effects(entity: Entity, effects: list[Effect], repo, context: dict | None = None, source=None, source_element: str | None = None) -> EffectsResult:
    """Apply operational effects to an entity's in-memory state (no persistence).

    Mutates ``entity`` in place for entity-level fields (razmerit, rank, discovered
    paths) and collects new/updated TraitSetting objects, relationship edges, and
    cross-entity mutations into the returned EffectsResult. Persistence and SSE
    broadcast are the caller's responsibility.

    Unresolved targets (``{choose_*}` or empty-when-required) become PendingChoice.
    Effects without a mutation handler (resolver-context and flow effects) become
    passthrough. An effect whose ``conditions`` fail against ``context`` is skipped.
    """
    result = EffectsResult()
    bindings = (context or {}).get(BINDINGS_CONTEXT_KEY) or {}
    for raw_effect in effects:
        effect = raw_effect
        if effect.conditions and not evaluate_conditions(entity, effect.conditions, repo, context, source=source, source_element=source_element):
            continue
        # Resolve an ``entity_spec`` here too when this list was applied directly
        # (the engine resolves first on its own path); handlers then see a
        # concrete ``entity`` id, matching the engine's ``target_spec`` rewrite.
        effect = resolve_effect_entity(effect, entity.id, repo, context)
        scope_choice = _scope_choice(effect)
        if scope_choice is not None:
            result.pending_choices.append(scope_choice)
            continue
        handler = _MUTATION_HANDLERS.get((effect.type, effect.action))
        if handler is None:
            result.passthrough.append(effect)
            continue
        handler(entity, effect, repo, result)
    return result


def resolve_effect_entity(effect: Effect, entity_id: str, repo, context: dict | None = None,
                          collections: dict | None = None) -> Effect:
    """Rewrite ``effect`` so its entity is a concrete id, resolving ``entity_spec``.

    ``entity_spec`` is resolved against the activation's variable scope (carried
    in ``context`` under :data:`BINDINGS_CONTEXT_KEY`), so an authored path can
    pick up a variable a condition bound — e.g. "the d4 traits this roll matched,"
    navigated on to their owning entities. Effects without a spec pass through
    untouched, and a spec that resolves to nothing leaves the effect as authored
    so the existing "resolved to nothing" report still fires.

    ``collections`` seeds the path's event-scoped collections. Callers that are
    already iterating one die should pass ``{"rolled_dice": [die]}`` — inside a
    per-die effect, the die being processed *is* the roll the path should read.
    """
    if effect.entity_spec is None or not effect.entity_spec.steps:
        return effect
    entity = repo.get_entity(entity_id) if repo is not None else None
    if entity is None:
        return effect
    bindings = (context or {}).get(BINDINGS_CONTEXT_KEY) or {}
    resolved = _resolve_entity_spec(effect, entity, repo, bindings, collections)
    return resolved if resolved is not None else effect


def _resolve_entity_spec(effect: Effect, entity: Entity, repo, bindings: dict,
                         collections: dict | None = None) -> Effect | None:
    """Resolve ``effect.entity_spec`` to a concrete id, or None if it resolves nothing.

    ``bindings`` is the activation scope (condition + earlier-effect outputs), so a
    path can pick up a variable a condition named — e.g. the d4 traits this roll
    matched, navigated on to their owning entities.
    """
    from transversal.services.target_resolver import TargetContext, resolve

    resolution = resolve(
        effect.entity_spec,
        TargetContext(subject=entity, repo=repo, bindings=bindings,
                      collections=dict(collections or {})),
    )
    for value in resolution.values:
        rid = getattr(value, "id", None)
        if rid is None and isinstance(value, dict):
            rid = value.get("id") or value.get("ts_id")
        if rid:
            return effect.model_copy(update={"entity": rid, "entity_spec": None})
    return None
