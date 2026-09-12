"""Post-roll consequence menu assembly.

A consequence option is ``label + side + effects``. The menu is assembled
dynamically from two sources:

  - entity moves (``Entity.consequence_options`` on the acting entity's
    current location and its ancestors — lair moves)
  - SFX moves (``placement="menu"`` SFX gated by role/outcome conditions, plus
    the legacy ``trigger="on_consequence"`` SFX)

Choosing an option applies its effects through the shared effect applier
(``applyEffects``), which resolves any ``{choose_*}`` targets via the wizard.
"""

from __future__ import annotations

from transversal.domain import (
    ConditionType,
    ConsequenceOption,
    Entity,
)

from transversal.services.sfx_owner import get_available_sfx_ids
from transversal.services.conditions import evaluate_conditions


def _sfx_side(sfx) -> str:
    """Derive a menu SFX's side from its ``USER_ROLE`` condition.

    ``player`` → player, ``architect`` → gm, no role condition → either.
    """
    for c in (sfx.conditions or []):
        if c.type == ConditionType.USER_ROLE:
            return "gm" if c.target == "architect" else "player"
    return "either"


def _outcome_context(menu_context: str, role: str) -> dict:
    """Map a menu context to the outcome keys its conditions can reference."""
    ctx = {"role": role}
    if menu_context == "contest_win":
        ctx["contest_winner"] = "player"
    elif menu_context == "contest_give_in":
        ctx["gave_in"] = True
    elif menu_context == "test_success":
        ctx["tier"] = "success"
    return ctx


def assemble_consequence_menu(
    entity: Entity,
    repo,
    side: str,
    menu_context: str = "test_success",
) -> list[ConsequenceOption]:
    """Return the consequence options offered to ``side`` in ``menu_context``.

    ``menu_context`` is an outcome signal (e.g. ``contest_win``). SFX with an
    explicit ``placement="menu"`` are gated by their conditions (role/outcome);
    the legacy ``trigger="on_consequence"`` SFX still match every menu for
    backward compatibility.
    """
    options: list[ConsequenceOption] = []
    role = "architect" if side == "gm" else "player"

    # Entity moves: current location and its ancestors (nearest → root).
    location_ids: list[str] = []
    if entity.current_location:
        location_ids = [entity.current_location] + repo.get_location_ancestors(entity.current_location)
    for loc_id in location_ids:
        loc = repo.get_entity(loc_id)
        if loc is None:
            continue
        for option in loc.consequence_options:
            if option.side in (side, "either"):
                options.append(option)

    # SFX moves.
    for sfx_id in get_available_sfx_ids(entity.id, entity.current_universe, repo):
        sfx = repo.get_sfx(sfx_id)
        if sfx is None:
            continue
        # New model: menu-placed SFX, gated by role/outcome conditions. The menu
        # is a *trigger* now (`trigger="menu"`), so `effective_placement` is the
        # one read that accepts both spellings — a rule authored as
        # `trigger="manual", placement="menu"` still lands here.
        if sfx.effective_placement == "menu":
            if sfx.conditions and not evaluate_conditions(entity, sfx.conditions, repo, context=_outcome_context(menu_context, role)):
                continue
            options.append(ConsequenceOption(
                id=f"sfx:{sfx.id}", label=sfx.name, side=_sfx_side(sfx),
                effects=sfx.effects, source="sfx",
            ))
            continue
        # Legacy: trigger="on_consequence" SFX still appear in every menu.
        if sfx.trigger != "on_consequence":
            continue
        if sfx.conditions and not evaluate_conditions(entity, sfx.conditions, repo):
            continue
        options.append(ConsequenceOption(
            id=f"sfx:{sfx.id}", label=sfx.name, side="player",
            effects=sfx.effects, source="sfx",
        ))

    return options


def _hitch_side(owner_id: str, sfx) -> str:
    """Side for a hitch-menu SFX: gm bucket → gm; a character-gated table SFX → player."""
    if owner_id == "gm":
        return "gm"
    for c in (sfx.conditions or []):
        if c.type == ConditionType.ENTITY_TYPE and c.target == "character":
            return "player"
    return "either"


def assemble_hitch_menu(repo, roller_id: str = "", buyer_id: str = "") -> list[ConsequenceOption]:
    """Return the hitch/opportunity menu — ``placement="menu"`` SFX carrying a
    ``HITCH`` condition from the ``gm``/``table`` owner buckets (no base/entity
    moves).

    ``roller_id`` and ``buyer_id`` populate ``{hitch_entity}`` / ``{buying_entity}``
    so conditions can reference them; ``context["hitch"]`` marks the hitch menu
    for the ``HITCH`` condition. Side is derived from the bucket + the SFX's
    ``entity_type`` condition (character-gated = player)."""
    context = {"hitch": True, "hitch_entity": roller_id, "buying_entity": buyer_id}

    options: list[ConsequenceOption] = []
    seen: set[str] = set()
    for owner_id in ("gm", "table"):
        owner = repo.get_sfx_owner(owner_id)
        if owner is None:
            continue
        for sfx_id in owner.sfx_ids or []:
            if sfx_id in seen:
                continue
            seen.add(sfx_id)
            sfx = repo.get_sfx(sfx_id)
            if sfx is None or sfx.effective_placement != "menu":
                continue
            if not any(c.type == ConditionType.HITCH for c in (sfx.conditions or [])):
                continue
            # No default entity here — hitch conditions must reference
            # {hitch_entity} or {buying_entity} explicitly (blank subject skips).
            if sfx.conditions and not evaluate_conditions(None, sfx.conditions, repo, context):
                continue
            options.append(ConsequenceOption(
                id=f"sfx:{sfx.id}", label=sfx.name, side=_hitch_side(owner_id, sfx),
                effects=sfx.effects, source="sfx",
            ))
    return options
