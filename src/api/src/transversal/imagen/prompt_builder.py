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


def _build_entity_prompt(
    entity: Entity,
    trait_settings: list[TraitSetting],
    universe: str,
) -> tuple[str, str, list[str], int]:
    """Build positive prompt, negative prompt, LoRA list, and step count.

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
        prompt = f"(location background image, a humanless atmospheric image focusing on {name}, seen from above:1.2), "
        negative += ", person"
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
            if statement:
                appearance_parts.append(f"({statement}:1.4)")
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
) -> dict:
    """Build a complete image generation prompt from an entity's traits.

    Returns a dict with all the parameters needed by the ComfyUI workflow:
        prompt, negative, loras, steps, width, height
    """
    trait_settings = repository.get_effective_traitsettings(entity.id, universe)
    prompt, negative, loras, steps = _build_entity_prompt(
        entity, trait_settings, universe
    )

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
