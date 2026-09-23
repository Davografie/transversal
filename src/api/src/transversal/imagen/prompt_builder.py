"""Assemble text-to-image prompts from entity traits, filtered by universe.

Adapts the prompt assembly logic from the original Transversal v1 Flask app
(src/dev/transversal/flask/app.py imagegen endpoint) to the v2 Pydantic data model.
"""

import re
from typing import Optional

from transversal.db.repository import EntityRepository
from transversal.domain import Entity, EntityType, TraitSetting


# Rating weights used in the old system for emphasis in prompts
RATING_WEIGHTS = [0.4, 0.6, 0.8, 1.0, 1.2]


def clean_text(text: str) -> str:
    """Strip special chars while preserving natural text flow."""
    if not text:
        return ""
    # Remove parenthetical asides, keep the rest
    text = re.sub(r'\([^)]*\)', '', text)
    # Strip non-word chars except basic punctuation
    text = re.sub(r'[^\w\s\-.,!?:;]+', '', text)
    return text.strip()


#: How much an ancestor's description decays per level up the location chain.
#: The immediate parent describes a scene far more than its grandparent, which
#: is the behaviour the original Transversal app had.
ANCESTOR_WEIGHT_DECAY = 0.6


def _weight(value: float) -> str:
    """Format a prompt weight without float artifacts (0.216, not 0.21600000000000003)."""
    return f"{round(value, 4):g}"


def _appearance_text(repository, entity_id: str, universes: list[str]) -> str:
    """An entity's authored appearance: its `appearance` traits' statement + notes.

    v1 stored a location's description in a `description` field; v2 has no such
    field, so the equivalent content lives in the `appearance` trait — which is
    why both parts are read here.
    """
    try:
        settings = repository.get_prompt_traitsettings(entity_id, universes)
    except Exception:
        return ""
    parts: list[str] = []
    for ts in settings:
        try:
            trait = repository.get_trait(ts.trait_id)
        except Exception:
            trait = None
        if trait is None or trait.name != "appearance":
            continue
        for value in (ts.statement, ts.notes):
            cleaned = clean_text(value or "")
            if cleaned:
                parts.append(cleaned)
    return ", ".join(parts)


def _build_location_context(repository, entity: Entity, universes: list[str]) -> dict:
    """What the repository knows about a location's place in the world.

    Sub-locations are always gathered; the ancestor chain only when the location
    opts in via ``prompt_include_ancestors`` (exteriors want the surrounding
    geography, interiors usually do not).
    """
    children: list[dict] = []
    try:
        navigation = repository.navigate_from(entity.id)
    except Exception:
        navigation = {}
    for child in navigation.get("children") or []:
        child_id = child.get("_key")
        if child_id:
            children.append({
                "name": child.get("name") or "",
                "appearance": _appearance_text(repository, child_id, universes),
            })

    ancestors: list[dict] = []
    if entity.prompt_include_ancestors:
        try:
            ancestor_ids = repository.get_location_ancestors(entity.id)
        except Exception:
            ancestor_ids = []
        for ancestor_id in ancestor_ids:
            ancestor = repository.get_entity(ancestor_id)
            # A `super` parent can be a non-location (the live data has one
            # location under a character); only places describe where a place is.
            if ancestor is None or ancestor.type != EntityType.LOCATION:
                continue
            ancestors.append({
                "name": ancestor.name or "",
                "appearance": _appearance_text(repository, ancestor_id, universes),
            })

    return {"children": children, "ancestors": ancestors}


def _nested_ancestors(ancestors: list[dict], strength: float) -> str:
    """``in (parent in (grandparent:0.36):0.6)`` — nearest ancestor outermost."""
    nearest, rest = ancestors[0], ancestors[1:]
    label = nearest["name"]
    if nearest.get("appearance"):
        label += f", {nearest['appearance']}"
    weight = _weight(strength * ANCESTOR_WEIGHT_DECAY)
    if not rest:
        return f"in ({label}:{weight})"
    return f"in ({label} {_nested_ancestors(rest, strength * ANCESTOR_WEIGHT_DECAY)}:{weight})"


def _location_context_clause(name: str, context: Optional[dict]) -> str:
    """Render a location's sub-locations and (optionally) its ancestor chain.

    Sub-locations keep the original app's "zones" phrasing, with every child at
    its own ``:0.4`` inside one ``:0.8`` group. The two parts are joined with the
    same ", " separator the rest of the prompt uses, and the result ends with one
    so the caller can append directly — joining them by hand is how you get
    either a doubled comma or two clauses running together.
    """
    if not context:
        return ""
    parts: list[str] = []
    zones = []
    for child in context.get("children") or []:
        label = child["name"]
        if child.get("appearance"):
            label += f", {child['appearance']}"
        zones.append(f"({label}:0.4)")
    if zones:
        parts.append(
            f"the different zones in {name} are (" + " and ".join(zones) + "):0.8)"
        )
    ancestors = context.get("ancestors") or []
    if ancestors:
        parts.append(f"located {_nested_ancestors(ancestors, 1.0)}")
    if not parts:
        return ""
    return ", ".join(parts) + ", "


def _build_entity_prompt(
    entity: Entity,
    trait_settings: list[TraitSetting],
    universe: str,
    location_context: Optional[dict] = None,
) -> tuple[str, str, list[str], int]:
    """Build positive prompt, negative prompt, LoRA list, and step count.

    ``location_context`` carries what only the repository knows about a
    location's place in the world (sub-locations, and its ancestor chain when it
    opted in). It is None for other entity types.

    Returns: (positive_prompt, negative_prompt, loras, steps)
    """
    entity_type = entity.type
    name = entity.name
    negative = ""
    loras: list[str] = []
    steps = 32

    # ── Base prompt by entity type ──

    if entity_type == EntityType.CHARACTER:
        prompt = f"(a solo upper body character portrait of {name}:1.2), "
        steps = 48
    elif entity_type == EntityType.GMC:
        prompt = f"(a solo upper body character portrait of {name}:1.2), "
        steps = 48
    elif entity_type == EntityType.ASSET:
        prompt = f"(a concept art image of {name}:1.2), "
        negative += ", person"
        steps = 48
    elif entity_type == EntityType.FACTION:
        prompt = f"(a symbol or logo or flag or shield or emblem representing the faction {name}:1.2), "
        negative += ", photo, person, environment"
        steps = 24
    elif entity_type == EntityType.LOCATION:
        prompt = f"(location background image, a humanless atmospheric image focusing on {name}:1.2), "
        negative += ", person"
        prompt += _location_context_clause(name, location_context)
    else:
        prompt = f"(a concept art image of {name}:1.2), "

    # ── Trait-based prompt enrichment ──

    appearance_parts: list[str] = []
    trait_parts: list[str] = []

    for ts in trait_settings:
        # Resolve trait info
        trait = None
        try:
            trait = EntityRepository().get_trait(ts.trait_id)
        except Exception:
            pass

        trait_name = trait.name if trait else ts.trait_id
        statement = clean_text(ts.statement) if ts.statement else ""

        if trait_name == "appearance":
            # `statement` is the short distinction ("lithe"); the longer
            # appearance description lives in the setting's freeform `notes`.
            # Both are authored appearance content, so both go in the one
            # emphasised clause — dropping `notes` silently discarded most of
            # what a GM writes about how a character looks.
            appearance = ", ".join(
                part for part in (statement, clean_text(ts.notes or "")) if part
            )
            if appearance:
                appearance_parts.append(f"({appearance}:1.4)")
        elif trait_name.startswith("LoRA"):
            if statement:
                loras.append(statement)
        elif trait_name == "negative imagen":
            if statement:
                negative += f", {statement}"
        elif trait_name == "positive imagen":
            if statement:
                prompt += f"({statement}:0.8), "
        elif ts.rating_type.value not in ("resource", "challenge"):
            # Generic trait → add to prompt with name+statement
            part = f"({trait_name}"
            if statement:
                part += f" is {statement}"
            # Rating weight
            rating_idx = max(0, min(len(ts.dice) - 1, len(RATING_WEIGHTS) - 1))
            part += f":{RATING_WEIGHTS[rating_idx]})"
            trait_parts.append(part)

    # ── Assemble ──

    if appearance_parts:
        prompt += ", ".join(appearance_parts) + ", "
    if trait_parts:
        prompt += ", ".join(trait_parts) + ", "

    # Add universe style guidance
    from transversal.imagen.models import (
        DEFAULT_NEGATIVE,
        PRIMITIVE_NEGATIVE,
        PRIMITIVE_UNIVERSES,
        UNIVERSE_STYLE_GUIDE,
    )

    if style := UNIVERSE_STYLE_GUIDE.get(universe):
        prompt += f"({style}:0.6), "

    negative += f", {DEFAULT_NEGATIVE}"

    if universe in PRIMITIVE_UNIVERSES:
        negative += f", {PRIMITIVE_NEGATIVE}"

    # Clean up: remove line breaks, collapse whitespace
    prompt = " ".join(prompt.split())
    negative = " ".join(negative.split())

    # Remove duplicate lorae while preserving order
    seen: set[str] = set()
    loras = [x for x in loras if not (x in seen or seen.add(x))]

    return prompt, negative, loras, steps


def build_imagen_prompt(
    entity: Entity,
    universe: str,
    repository: EntityRepository,
    projection_id: str | None = None,
) -> dict:
    """Build a complete image generation prompt from an entity's traits.

    ``projection_id`` scopes the prompt to a specific body: that projection's
    morph traits plus the entity's ego traits drive the prompt. With no
    projection, only entity traits are used. ``universe`` is the generation
    universe (style guide + LoRA config).

    Returns a dict with all the parameters needed by the ComfyUI workflow:
        prompt, negative, loras, steps, width, height
    """
    trait_universes = [universe]
    if projection_id:
        proj = repository.get_projection(projection_id)
        if proj is not None:
            trait_universes = sorted(
                {u for u in (universe, proj.origin_universe, proj.universe) if u}
            )
    trait_settings = repository.get_prompt_traitsettings(
        entity.id, trait_universes, projection_id
    )
    location_context = None
    if entity.type == EntityType.LOCATION:
        location_context = _build_location_context(repository, entity, trait_universes)
    prompt, negative, loras, steps = _build_entity_prompt(
        entity, trait_settings, universe, location_context
    )

    # Merge universe-level LoRA config + prompt steering for this entity type
    try:
        universe_docs = list(repository._entities.find({"type": "universe", "current_universe": universe}))
        if universe_docs:
            universe_entity = Entity.model_validate({**universe_docs[0], "id": universe_docs[0]["_key"]})
            if universe_entity.lora_config:
                entity_type_key = entity.type.value.upper()
                universe_loras = universe_entity.lora_config.get(entity_type_key, [])
                for lora_name in universe_loras:
                    if lora_name not in loras:
                        loras.append(lora_name)
            # Free-text steering sentence authored on the universe (GM panel).
            # Appended last so it reads as the final style direction.
            steering = clean_text(universe_entity.prompt_steering or "").strip()
            if steering:
                prompt = f"{prompt} ({steering}:0.9), "
    except Exception:
        pass  # Don't fail imagen if universe lookup fails

    width = 832
    height = 1216

    if entity.type == EntityType.FACTION:
        width = 1024
        height = 1024
    elif entity.type == EntityType.LOCATION:
        width = 1024
        height = 1024
    elif entity.type == EntityType.ASSET:
        width = 1216
        height = 832

    return {
        "prompt": prompt,
        "negative": negative,
        "loras": loras,
        "steps": steps,
        "width": width,
        "height": height,
    }
