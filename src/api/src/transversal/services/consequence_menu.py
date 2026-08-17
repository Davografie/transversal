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


# Base moves. The doom-pool step-up/down targets are intentionally generic
# ({choose_trait}); precise doom-pool scoping lands with Phase 3's challenge-pool
# work. Effect-die substitution into `result` is likewise a follow-up.
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
                action="gain_or_step_up", target="{choose_trait}", result="d6",
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
                action="gain_complication", target="{choose_trait}", result="d6",
            ),
        ],
        source="base",
    ),
    ConsequenceOption(
        id="give_asset", label="Give a GMC an asset", side="gm",
        effects=[
            Effect(
                timing=EffectTiming.IMMEDIATE, type="modify_trait",
                action="gain", target="{choose_trait}", result="d6",
            ),
        ],
        source="base",
    ),
]

BASE_CONSEQUENCE_OPTIONS: dict[str, list[ConsequenceOption]] = {
    "player": _BASE_PLAYER,
    "gm": _BASE_GM,
}


def _entity_sfx_ids(entity: Entity, repo) -> set[str]:
    """Collect SFX ids available to an entity via its trait settings.

    Includes each trait setting's explicit ``sfx_ids`` plus the trait's
    ``default_sfx_ids``. This is the pre-owner-model approximation; the SFX
    owner model (Phase 3) replaces it with owner scoping.
    """
    ids: set[str] = set()
    for ts in repo.get_traitsettings_for_entity(entity.id):
        ids.update(ts.sfx_ids)
        trait = repo.get_trait(ts.trait_id)
        if trait is not None:
            ids.update(trait.default_sfx_ids)
    return ids


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
    for sfx_id in sorted(_entity_sfx_ids(entity, repo)):
        sfx = repo.get_sfx(sfx_id)
        if sfx is None or sfx.trigger != "on_consequence":
            continue
        options.append(ConsequenceOption(
            id=f"sfx:{sfx.id}", label=sfx.name, side="player",
            effects=sfx.effects, source="sfx",
        ))

    return options
