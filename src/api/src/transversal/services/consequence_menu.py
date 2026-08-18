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
    ConsequenceOption,
    Effect,
    EffectTiming,
    Entity,
)


from transversal.services.sfx_owner import get_available_sfx_ids


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
        id="apply_complication", label="Apply a complication", side="gm",
        effects=[
            Effect(
                timing=EffectTiming.IMMEDIATE, type="modify_trait",
                action="gain_complication", target="{choose_trait}", result="{effect_die}",
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


def assemble_consequence_menu(entity: Entity, repo, side: str) -> list[ConsequenceOption]:
    """Return the consequence options offered to ``side`` in this context."""
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

    # SFX moves: on_consequence SFX available to the acting entity (player side).
    for sfx_id in get_available_sfx_ids(entity.id, entity.current_universe, repo):
        sfx = repo.get_sfx(sfx_id)
        if sfx is None or sfx.trigger != "on_consequence":
            continue
        options.append(ConsequenceOption(
            id=f"sfx:{sfx.id}", label=sfx.name, side="player",
            effects=sfx.effects, source="sfx",
        ))

    return options
