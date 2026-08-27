"""Lazy migration of legacy string targets into trivial specs.

Old effects stored ``Effect.target`` as a flat string (``self``, a literal id,
or a ``{choose:kind}``/``{random:kind}`` placeholder). New effects carry a
``TargetSpec``. This module translates the *unambiguous* string forms into the
smallest spec that means the same thing; anything it can't map faithfully
(variables like ``{effect_die}``, or kinds without a collection/element type)
returns ``None`` so the caller keeps the legacy string and the author fixes it
by hand.
"""

from __future__ import annotations

from typing import Optional

from transversal.services.target_spec import (
    LiteralStep,
    SelectStep,
    TargetSpec,
)


# ``{choose:kind}`` / ``{random:kind}`` → the collection the choice seeds from.
# Cardinality (choose/random) is a *field* concern, not a spec step, so the spec
# is just the ``select``; the field declares the mode when it asks for a target.
_CHOOSE_COLLECTIONS: dict[str, str] = {
    "location": "locations",
    "occupant": "occupants",
    "entity": "entities",
    "traitsetting": "self_traitsettings",
}

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
        parsed = _parse_placeholder(t)
        # Only choose/random placeholders translate; variables ({effect_die},
        # {source_trait}, …) stay legacy.
        if parsed and parsed[0] in ("choose", "random"):
            k = parsed[1] or kind
            col = _CHOOSE_COLLECTIONS.get(k)
            if col:
                return TargetSpec(steps=[SelectStep(collection=col)])
        return None

    # Bare literal id → a single literal step (element from the target kind).
    element = _KIND_ELEMENT.get(kind)
    if element:
        return TargetSpec(steps=[LiteralStep(element=element, value=t)])

    return None
