"""Registry — split out of src/api/src/transversal/services/effects_applier.py."""

from __future__ import annotations

from transversal.domain import Effect
from typing import Callable
from transversal.services.effects_applier.datatypes import (
    SOURCE_CONTEXT_KEY,
    SOURCE_ELEMENT_CONTEXT_KEY,
    BINDINGS_CONTEXT_KEY,
    ACTIVATION_CONTEXT_KEY,
)
from transversal.services.effects_applier.handlers_world import (
    _apply_attune_projection,
    _apply_attune_universe,
)


EffectHandler = Callable[[Effect, str, str, dict], None]

def _produced_id(result, element: str) -> str:
    """The id of the thing an applied effect produced, by its element type.

    A gain produces a new instance; a *step-up* produces the instance it changed —
    both are "what this step made", which is what the author named.
    """
    if element == "traitsetting":
        for ts in (*result.new_trait_settings, *result.updated_trait_settings,
                   *result.found_trait_settings):
            return getattr(ts, "id", "")
    elif element == "projection":
        for p in (*result.new_projections, *result.updated_projections):
            return getattr(p, "id", "")
    return ""


def publish_effect_output(effect, result, context) -> None:
    """Bind the thing this effect just produced under the author's chosen name.

    ``Effect.output`` is the author naming the step's result ("beast"), so a later
    step can `select variable {beast}` instead of re-finding what it just made.
    The element comes from the action's declared ``output_element``; the binding
    rides the *activation scope* (the same dict step outputs and refs use), which
    the engine shares with every later effect of this activation.
    """
    from transversal.services.effects_registry import output_element_for
    from transversal.services.target_resolver import Binding

    name = (getattr(effect, "output", "") or "").strip()
    if not name or result is None or not isinstance(context, dict):
        return
    element = output_element_for(effect.type, effect.action)
    if not element:
        return
    produced = _produced_id(result, element)
    if not produced:
        return
    bindings = context.get(BINDINGS_CONTEXT_KEY)
    if not isinstance(bindings, dict):
        bindings = {}
        context[BINDINGS_CONTEXT_KEY] = bindings
    bindings[name] = Binding(value=produced, values=[produced], element=element, cardinality="one")


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
        if handler is None:
            return
        activation = context.get(ACTIVATION_CONTEXT_KEY) if isinstance(context, dict) else None
        if activation:
            # Bookings made while this effect applies belong to the activation; when
            # it is a *manual* one, an effect without a duration books a hold — the
            # undo that can be applied until the activation commits.
            from transversal.services.scheduled_events import activation_booking
            with activation_booking(
                activation.get("sfx_id"), cancelable=bool(activation.get("cancelable")),
                source_id=activation.get("source_id") or "",
            ):
                self._apply_guarded(handler, action, activation, entity_id, universe, context)
        else:
            handler(action, entity_id, universe, context)

    def _apply_guarded(self, handler, action: Effect, activation: dict,
                       entity_id: str, universe: str, context: dict) -> None:
        """Apply a handler with the rule on the loop chain for its duration.

        The chain is what lets a nested state event tell *"this rule is causing
        this"* from *"this rule is being asked to cause it again"*. It is a stack,
        so the frame is alive precisely while the effects that could recurse are
        running, and per-request, so concurrent activations cannot see each other.
        A dispatch outside an activation (a life-path entry) pushes nothing: it is
        not an auto-triggered rule and has no chain to re-enter.
        """
        from transversal.services.effects_engine.shared import RULE_CHAIN

        frame = (activation.get("sfx_id"), activation.get("change"))
        token = RULE_CHAIN.set(RULE_CHAIN.get() + (frame,))
        try:
            handler(action, entity_id, universe, context)
        finally:
            RULE_CHAIN.reset(token)

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
    #
    # Each one also books its undo (the opposite operation): a cost or a gain is
    # refundable until the activation commits, so a take-back can pay it back.
    def _razmerit_op(action, a, eid):
        target = _razmerit_entity(a, eid)
        amount = int(a.result or "0")
        if action == "spend":
            raz.spend(target, amount, reason="sfx_cost")
        elif action == "earn":
            raz.earn(target, amount, reason="effect")
        else:
            raz.transfer(target, a.target, amount)
        from transversal.services.effects_applier.reverts import book_undo
        book_undo(em.repo, target, a)

    effect_registry.register("transfer_razmerit", "spend",
        lambda a, eid, u, ctx: _razmerit_op("spend", a, eid))
    effect_registry.register("transfer_razmerit", "earn",
        lambda a, eid, u, ctx: _razmerit_op("earn", a, eid))
    effect_registry.register("transfer_razmerit", "transfer",
        lambda a, eid, u, ctx: _razmerit_op("transfer", a, eid))

    # Trait, rank, and life-path state mutations route through the shared applier.
    def _commit(a, eid, u, ctx):
        from transversal.services.effects_commit import commit_effects
        entity = em.repo.get_entity(eid)
        if entity is None:
            return
        result = commit_effects(
            entity, [a], em.repo, ctx,
            source=(ctx or {}).get(SOURCE_CONTEXT_KEY),
            source_element=(ctx or {}).get(SOURCE_ELEMENT_CONTEXT_KEY),
        )
        publish_effect_output(a, result, ctx)

    for action in ("step_up", "step_down", "reduce_by_effect", "set", "gain", "gain_relationship", "gain_subtrait", "remove", "gain_or_step_up", "cortex_gain", "reveal", "disable", "enable", "toggle", "add_die", "remove_die", "copy", "move",
                   "change", "invert_polarity", "set_polarity"):
        effect_registry.register("modify_trait", action, _commit)
    effect_registry.register("life_path", "discover", _commit)
    effect_registry.register("relationship", "create", _commit)
    effect_registry.register("projection", "create", _commit)
    effect_registry.register("projection", "restore", _commit)
    effect_registry.register("modify_traitset", "set_limit", _commit)
    effect_registry.register("set_destination", "set", _commit)
    effect_registry.register("set_destination", "clear", _commit)
    effect_registry.register("modify_dice_limit", "increase", _commit)
    effect_registry.register("modify_dice_limit", "decrease", _commit)
    effect_registry.register("modify_pool", "add_dice", _commit)
    effect_registry.register("modify_pool", "add_trait_rating", _commit)
    effect_registry.register("modify_pool", "remove_added_dice", _commit)
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

    # Projection grants ([[Active Projections Design Log]]): attune *adds* a body
    # to the active set, suppress *removes* one. One handler, because the two are
    # one operation with an `op` — and because the grant lifecycle (expiry through
    # `schedule_revert`) is identical for both.
    def _projection_grant(a, eid, u, ctx):
        from transversal.domain import Attunement, AttunementOp, AttunementScope
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

        # Each action's grant shape, stated rather than derived. An attunement is
        # a *world* (an add to the active set); a suppression is a *body* (a remove
        # from it). Keeping `enable` to the universe form is deliberate — it is
        # what existing content and the derived effective-universe view expect.
        if a.action == "enable":
            op, universe, projection_id = AttunementOp.ADD, _apply_attune_universe(a, em, u), None
        elif a.action == "suppress":
            op, universe, projection_id = AttunementOp.REMOVE, None, _apply_attune_projection(a, em)
        elif a.action == "disable":
            op, universe, projection_id = AttunementOp.ADD, _apply_attune_universe(a, em, u), None
        else:  # unsuppress
            op, universe, projection_id = AttunementOp.REMOVE, None, _apply_attune_projection(a, em)

        if a.action in ("enable", "suppress"):
            # Idempotent on the whole identity, `op` included: an attunement and a
            # suppression naming the same thing are different grants, and de-duping
            # on `(universe, scope)` alone would swallow the second.
            if not any(x.op == op and x.universe == universe
                       and x.projection_id == projection_id and x.scope == scope
                       for x in entity.attunements):
                entity.attunements.append(Attunement(
                    op=op, universe=universe, projection_id=projection_id, scope=scope,
                    source_sfx_id=ctx.get("sfx_id"),
                ))
            from transversal.services.scheduled_events import schedule_revert
            schedule_revert(em.repo, "entity", entity.id, a, source_sfx_id=ctx.get("sfx_id"))
        else:
            # ⚠ Scoped by `op`, and that is the point: `disable` ends an
            # *attunement*, `unsuppress` ends a *suppression*. Matching on
            # `(universe, scope)` alone meant ending one silently stripped the
            # other — a suppressed body would come back to life when an unrelated
            # attunement expired.
            entity.attunements = [
                x for x in entity.attunements
                if not (x.op == op and x.universe == universe
                        and x.projection_id == projection_id and x.scope == scope)
            ]
        em.repo.update_entity(entity)

    effect_registry.register("attune", "enable", _projection_grant)
    effect_registry.register("attune", "disable", _projection_grant)
    effect_registry.register("attune", "suppress", _projection_grant)
    effect_registry.register("attune", "unsuppress", _projection_grant)

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

    # Changing a die is a real state change — a trait instance's rating, or the
    # scene store's pool — so these go through the mutation dispatch above rather
    # than the resolver passthrough.
    for action in ("set_die", "step_up_die", "step_down_die", "double_die",
                   "split_die", "remove_die", "restore_die", "play_as_rating", "reroll_die"):
        effect_registry.register("modify_roll", action, _commit)
    # Outcome effects are state changes too (they rewrite the committed result),
    # so they commit rather than passing through.
    for action in ("step_up_effect", "step_up_outcome"):
        effect_registry.register("modify_outcome", action, _commit)
    # The rest of the dice-pool actions are still resolver-context only.
    effect_registry.register("modify_roll", "*",
        lambda a, eid, u, ctx: None)  # passed through to resolver context
    effect_registry.register("modify_outcome", "*",
        lambda a, eid, u, ctx: None)  # passed through to resolver context
