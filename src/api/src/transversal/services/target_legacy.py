"""Legacy flat targets → targeting specs.

An old effect stored ``Effect.target`` as a flat string — ``self``, a literal id,
or a ``{choose_kind}`` / ``{random:kind}`` placeholder — with ``target_scope`` and
``target_filter`` narrowing what the placeholder offered. A spec says the same
thing as a **path**, and the scope vocabulary is itself declared in catalog terms
(``services/target_scopes.py``), so a legacy choice compiles to the declared path
for its ``(kind, scope, filter)`` plus a terminal ``choose`` / ``random`` step.
Nothing here re-derives what a scope means — that is the point: the compiled path
*is* the one the picker's scope resolves to.

``migrate_all_sfxs`` is the one-way door. It rewrites stored effects off the flat
form and reports whether anything changed, so a startup pass over every SFX is
idempotent and a second run is a no-op.

What is deliberately *not* migrated: ``{variable}`` tokens (``{effect_die}``,
``{trait_setting}``, ``{entity_created}`` …). Those are the variables feature, not
the flat targeting form — the engine substitutes them from the activation, and
they are still live.
"""

from __future__ import annotations

from typing import Optional

from transversal.services.target_scopes import ScopeError, choice_spec
from transversal.services.target_spec import (
    LiteralStep,
    SelectStep,
    TargetSpec,
)


# ``target_kind`` (from the effect-action registry) → the element type a literal
# id resolves to.
_KIND_ELEMENT: dict[str, str] = {
    "location": "location",
    "occupant": "entity",
    "entity": "entity",
    "trait": "trait",
    "traitsetting": "traitsetting",
    "traitset": "traitset",
    "universe": "universe",
    "projection": "projection",
    "rating_die": "die",
}


def _parse_placeholder(target: str) -> tuple[str, str] | None:
    """Return ``(mode, kind)`` for a ``{mode:kind}`` / ``{mode_kind}`` target, else None."""
    body = target[1:-1]
    if ":" in body:
        mode, _, kind = body.partition(":")
    else:
        mode, _, kind = body.partition("_")
    mode = mode.strip()
    kind = kind.strip()
    return (mode, kind) if mode else None


def is_choice_placeholder(target: str) -> bool:
    """True for a ``{choose[*]}`` / ``{random[*]}`` placeholder target."""
    parsed = _parse_placeholder((target or "").strip()) if target else None
    return bool(parsed and parsed[0] in ("choose", "random"))


def from_legacy_choice(target: str, scope: Optional[str] = None,
                       filter: Optional[dict] = None) -> Optional[TargetSpec]:
    """The spec a legacy ``{choose_kind}`` / ``{random:kind}`` (+ scope/filter) meant.

    ``None`` when it cannot be expressed — an unknown kind, or a placeholder whose
    ``kind`` is not a target kind at all (``{random_starter_location}``, a
    variable-policy token that happens to parse like one).
    """
    parsed = _parse_placeholder((target or "").strip()) if target else None
    if parsed is None or parsed[0] not in ("choose", "random"):
        return None
    mode, kind = parsed
    if not kind:
        return None
    try:
        return choice_spec(kind, scope, mode, filter=filter)
    except ScopeError:
        return None


def from_legacy_target(target: str, kind: str = "") -> Optional[TargetSpec]:
    """Translate a legacy string target into a trivial spec, or None if unmappable.

    ``kind`` is the effect action's ``target_kind`` (trait/entity/location/…);
    it disambiguates bare literal ids.
    """
    t = (target or "").strip()
    if not t:
        return TargetSpec(steps=[])

    if t == "self":
        return TargetSpec(steps=[SelectStep(collection="self")])

    if t.startswith("{") and t.endswith("}"):
        # A choice compiles to the declared scope path; a *variable* token
        # ({effect_die}, {source_trait}, …) is not a target and stays as it is.
        return from_legacy_choice(t) if is_choice_placeholder(t) else None

    # Bare literal id → a single literal step (element from the target kind).
    element = _KIND_ELEMENT.get(kind)
    if element:
        return TargetSpec(steps=[LiteralStep(element=element, value=t)])

    return None


def migrate_effect(effect):
    """Rewrite one stored effect off the flat target form.

    Returns ``(effect, changed)``. Three cases:

    * its target (or subject) is a choice placeholder — compiled to the declared
      path plus a terminal ``choose`` / ``random`` step;
    * it already carries a spec — any surviving flat field is *stale*, so it is
      dropped (a spec is the target; a scope beside it narrows nothing);
    * its target is a literal with a scope that never applied to it — the inert
      narrowing is dropped.

    Anything it cannot compile is left exactly as it is: silently rewriting a
    target into something that selects differently would be worse than a stored
    legacy form the runtime still understands.
    """
    updates: dict = {}

    if effect.target_spec is None:
        spec = from_legacy_choice(effect.target, effect.target_scope, effect.target_filter)
        if spec is not None:
            updates["target_spec"] = spec
            updates["target"] = ""

    if effect.entity_spec is None:
        entity_spec = from_legacy_choice(effect.entity, effect.entity_scope)
        if entity_spec is not None:
            updates["entity_spec"] = entity_spec
            updates["entity"] = ""

    # A narrowing only ever applied to a choice target — it is either compiled
    # *into* the path above or inert, and either way it does not survive.
    if effect.target_scope:
        updates["target_scope"] = None
    if effect.target_filter:
        updates["target_filter"] = {}
    if effect.entity_scope:
        updates["entity_scope"] = None

    if not updates:
        return effect, False
    return effect.model_copy(update=updates), True


def migrate_sfx(sfx):
    """Rewrite every effect of one SFX. Returns ``(sfx, changed)``."""
    changed = False
    effects = []
    for effect in sfx.effects:
        new, did = migrate_effect(effect)
        changed = changed or did
        effects.append(new)
    if not changed:
        return sfx, False
    return sfx.model_copy(update={"effects": effects}), True


def migrate_all_sfxs(repo) -> int:
    """Move every stored SFX off the flat target form. Idempotent; returns how many
    rules changed."""
    changed_count = 0
    for sfx in repo.get_all_sfxs():
        migrated, changed = migrate_sfx(sfx)
        if changed:
            repo.update_sfx(migrated)
            changed_count += 1
    return changed_count
