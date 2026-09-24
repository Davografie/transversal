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


def _join_parts(*values: str | None) -> str:
    """Join non-empty prompt fragments with ', '."""
    return ", ".join(part for part in values if part)


def _effective_projection(entity: Entity) -> str | None:
    """The body to read traits from when the caller names no projection.

    Mirrors ``Entity.image()``, which resolves ``projection_id or
    current_projection``. Creating a trait setting through the API anchors it to
    the active body (``from_type='projection'``), so an entity's appearance
    normally lives on ``current_projection`` rather than on the entity — reading
    entity-level traits alone silently drops everything authored through the API.
    That is how 19 locations' appearances, and the 27 entities [[mcp-architect]]
    wrote, went missing from the prompt while the images resolved fine.
    """
    return entity.current_projection or None


def _appearance_text(
    repository,
    entity_id: str,
    universes: list[str],
    projection_id: str | None = None,
) -> str:
    """An entity's authored appearance: its `appearance` traits' statement + notes.

    v1 stored a location's description in a `description` field; v2 has no such
    field, so the equivalent content lives in the `appearance` trait — which is
    why both parts are read here.

    ``projection_id`` must be the *owning* entity's active body: a sub-location
    or ancestor carries its own projection, not the root location's.
    """
    try:
        settings = repository.get_prompt_traitsettings(entity_id, universes, projection_id)
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
        cleaned = _join_parts(clean_text(ts.statement or ""), clean_text(ts.notes or ""))
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
                "appearance": _appearance_text(
                    repository, child_id, universes, child.get("current_projection")
                ),
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
                "appearance": _appearance_text(
                    repository, ancestor_id, universes, ancestor.current_projection
                ),
            })

    return {"children": children, "ancestors": ancestors}


def _occupant_location_id(entity: Entity, projection_id: str | None, repository) -> str | None:
    """Where an occupant is standing, for its own prompt.

    The **body's** location wins when there is one: a projection can be
    somewhere its entity is not (four live entities are, e.g. a body in one
    place while the soul sits in another), and describing a body as standing
    where its soul happens to be would be wrong.
    """
    if projection_id:
        try:
            projection = repository.get_projection(projection_id)
        except Exception:
            projection = None
        if projection is not None and projection.current_location:
            return projection.current_location
    return entity.current_location or None


def _build_occupant_location_context(
    repository, entity: Entity, projection_id: str | None, universes: list[str]
) -> dict:
    """Where an occupant is, for its prompt: the containing location + ancestors.

    v1 gave npc and asset prompts this chain ("located in …", decaying 0.6 per
    level); v2 dropped it. Gated by the entity's own ``prompt_include_ancestors``
    toggle — a GMC with **Surroundings** off builds exactly the prompt it did
    before.

    **No sub-locations.** Those describe what a place *contains*, which is the
    right thing for a location's own backdrop and the wrong thing for someone
    standing in it.
    """
    if not entity.prompt_include_ancestors:
        return {"children": [], "ancestors": []}

    location_id = _occupant_location_id(entity, projection_id, repository)
    if not location_id:
        return {"children": [], "ancestors": []}

    # Nearest first: the place they are in, then up the chain.
    try:
        chain = [location_id] + list(repository.get_location_ancestors(location_id))
    except Exception:
        chain = [location_id]

    ancestors: list[dict] = []
    for place_id in chain:
        place = repository.get_entity(place_id)
        # A `super` parent can be a non-location (the live data has one location
        # under a character); only places describe where someone is.
        if place is None or place.type != EntityType.LOCATION:
            continue
        ancestors.append({
            "name": place.name or "",
            "appearance": _appearance_text(
                repository, place_id, universes, place.current_projection
            ),
        })

    return {"children": [], "ancestors": ancestors}


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
        prompt += _location_context_clause(name, location_context)
    elif entity_type == EntityType.ASSET:
        prompt = f"(a concept art image of {name}:1.2), "
        negative += ", person"
        steps = 48
        prompt += _location_context_clause(name, location_context)
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
        notes = clean_text(ts.notes) if ts.notes else ""
        # Most live settings hold their content in ONE of the two fields, not
        # both: 231 of 423 `negative imagen` settings are notes-only, so gating
        # on `statement` alone dropped the majority of them.
        details = _join_parts(statement, notes)

        if trait_name == "appearance":
            # `statement` is the short distinction ("lithe"); the longer
            # appearance description lives in the setting's freeform `notes`.
            # Both are authored appearance content, so both go in the one
            # emphasised clause — dropping `notes` silently discarded most of
            # what a GM writes about how a character looks.
            if details:
                appearance_parts.append(f"({details}:1.4)")
        elif trait_name.startswith("LoRA"):
            # Deliberately `statement` only, and NOT merged with `notes`: the
            # value is fed to ComfyUI as a LoRA filename
            # (`flux/{name}.safetensors`), so free text would corrupt the path.
            # Every live LoRA setting already carries the name in `statement`.
            if statement:
                loras.append(statement)
        elif trait_name == "negative imagen":
            if details:
                negative += f", {details}"
        elif trait_name == "positive imagen":
            if details:
                prompt += f"({details}:0.8), "
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
    morph traits plus the entity's ego traits drive the prompt. **When it is
    omitted the entity's active body is used** (``current_projection``), the same
    rule ``Entity.image()`` applies — the API anchors new trait settings to the
    active body, so without this fallback a prompt silently loses every
    appearance authored through the API. Only genuinely body-less entities fall
    through to entity traits alone. ``universe`` is the generation universe
    (style guide + LoRA config).

    Returns a dict with all the parameters needed by the ComfyUI workflow:
        prompt, negative, loras, steps, width, height
    """
    projection_id = projection_id or _effective_projection(entity)
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
    elif entity.type in (EntityType.GMC, EntityType.ASSET):
        # v1 gave npc/asset prompts the containing location and its ancestors.
        # Characters are deliberately excluded: a PC is generated wherever the
        # player wants, not pinned to wherever the soul currently sits.
        location_context = _build_occupant_location_context(
            repository, entity, projection_id, trait_universes
        )
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
