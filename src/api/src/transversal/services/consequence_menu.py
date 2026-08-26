"""Post-roll consequence menu assembly.

A consequence option is ``label + side + effects``. The menu is assembled
dynamically from three sources:

  - base moves (always available)
  - entity moves (``Entity.consequence_options`` on the acting entity's
    current location and its ancestors — lair moves)
  - SFX moves (``on_consequence`` SFX available to the acting entity)

Choosing an option applies its effects through the shared effect applier
(``applyEffects``), which resolves any ``{choose_*}`` targets via the wizard.
"""

from __future__ import annotations

from transversal.domain import (
    ConditionType,
    ConsequenceOption,
    Effect,
    EffectTiming,
    Entity,
)


from transversal.services.sfx_owner import get_available_sfx_ids
from transversal.services.conditions import evaluate_conditions


# Base moves. The doom-pool step-up/down targets are intentionally generic
# ({choose_trait}); precise doom-pool scoping lands with Phase 3's challenge-pool
# work. ``result="{effect_die}"`` is a placeholder the frontend substitutes with
# the roll's actual effect die before applying.
_BASE_PLAYER = [
    ConsequenceOption(
        id="proceed", label="Proceed the narrative", side="player",
        effects=[], source="base",
    ),
    ConsequenceOption(
        id="create_scene_trait", label="Create a scene trait", side="player",
        effects=[
            Effect(
                timing=EffectTiming.IMMEDIATE, type="modify_trait",
                action="gain_or_step_up", target="{choose_trait}", result="{effect_die}",
            ),
        ],
        source="base",
    ),
    ConsequenceOption(
        id="decrease_doom", label="Decrease the doom pool", side="player",
        effects=[
            Effect(
                timing=EffectTiming.IMMEDIATE, type="modify_trait",
                action="step_down", target="{choose_trait}",
                target_scope="traitset:ts-complications",
            ),
        ],
        source="base",
    ),
]

_BASE_GM = [
    ConsequenceOption(
        id="increase_doom", label="Increase the doom pool", side="gm",
        effects=[
            Effect(
                timing=EffectTiming.IMMEDIATE, type="modify_trait",
                action="step_up", target="{choose_trait}",
                target_scope="traitset:ts-complications",
            ),
        ],
        source="base",
    ),
    ConsequenceOption(
        id="give_asset", label="Give a GMC an asset", side="gm",
        effects=[
            Effect(
                timing=EffectTiming.IMMEDIATE, type="modify_trait",
                action="gain", target="{choose_trait}", result="{effect_die}",
            ),
        ],
        source="base",
    ),
]

BASE_CONSEQUENCE_OPTIONS: dict[str, list[ConsequenceOption]] = {
    "player": _BASE_PLAYER,
    "gm": _BASE_GM,
}


def assemble_consequence_menu(
    entity: Entity,
    repo,
    side: str,
    menu_context: str = "test_success",
) -> list[ConsequenceOption]:
    """Return the consequence options offered to ``side`` in ``menu_context``.

    ``menu_context`` is a menu trigger value (e.g. ``test_success``). SFX are
    selected by their ``trigger``; the legacy ``on_consequence`` trigger still
    matches every consequence menu for backward compatibility.
    """
    options: list[ConsequenceOption] = list(BASE_CONSEQUENCE_OPTIONS.get(side, []))

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

    # SFX moves: selected by trigger (menu contexts are triggers now); the legacy
    # on_consequence trigger matches every consequence menu for backward compat.
    for sfx_id in get_available_sfx_ids(entity.id, entity.current_universe, repo):
        sfx = repo.get_sfx(sfx_id)
        if sfx is None:
            continue
        if sfx.trigger != menu_context and sfx.trigger != "on_consequence":
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
    """Return the hitch/opportunity menu — SFX from the ``gm``/``table``
    owner buckets whose trigger is ``hitch`` (no base or entity moves).

    ``roller_id`` and ``buyer_id`` populate ``{hitch_entity}`` / ``{buying_entity}``
    so conditions can reference them. Side is derived from the bucket + the SFX's
    ``entity_type`` condition (character-gated = player)."""
    context = {"hitch_entity": roller_id, "buying_entity": buyer_id}

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
            if sfx is None or sfx.trigger != "hitch":
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
