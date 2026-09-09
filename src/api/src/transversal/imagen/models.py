"""Imagen request/response models and workflow configuration."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class GenerationType(str, Enum):
    IMAGEN = "imagen"
    ANIMATE = "animate"
    REMOVE_BG = "remove_bg"


class GenerationStatus(str, Enum):
    PENDING = "pending"
    PROMPTING = "prompting"       # building prompt from traits
    GENERATING = "generating"     # ComfyUI running
    VISION = "vision"             # Ollama gemma3 analysing (animate only)
    ANIMATING = "animating"       # WanVideo running (animate only)
    SAVING = "saving"             # writing variants to disk
    COMPLETE = "complete"
    FAILED = "failed"


class ImagenRequest(BaseModel):
    """Parameters the frontend can override on an imagen request."""
    width: int = 832
    height: int = 1216
    steps: int = 0          # 0 = auto-detect from entity type
    seed: int = -1          # -1 = random
    lora_weights: list[float] = Field(default_factory=list)
    projection_id: str = ""  # generate for a specific body (empty = entity-level)


class AnimateRequest(BaseModel):
    """Parameters the frontend can override on an animate request."""
    width: int = 704
    height: int = 704
    steps: int = 30
    seed: int = -1
    duration_seconds: float = 3.0
    lora_strength: float = 0.95
    image_id: str = ""  # if set, skip Flux gen — animate this existing image
    motion_hint: str = ""  # user hint to guide gemma3 motion description


class RemoveBackgroundRequest(BaseModel):
    """Remove the background from an existing static image."""
    image_id: str = ""  # the static EntityImage to cut out


class GenerationProgress(BaseModel):
    """SSE progress event payload."""
    entity_id: str
    generation_type: GenerationType
    status: GenerationStatus
    message: str = ""
    percent: int = 0  # 0-100


class ImagenResponse(BaseModel):
    success: bool
    image_id: str = ""
    path: str = ""
    prompt: str = ""
    negative_prompt: str = ""
    message: str = ""


class ImageListResponse(BaseModel):
    entity_id: str
    images: list[dict] = Field(default_factory=list)


# ── Universe style guidance ──────────────────────────

UNIVERSE_STYLE_GUIDE: dict[str, str] = {
    # Add universe-specific LLM prompt modifiers
    "three_realms": "traditional Chinese ink painting style, wuxia atmosphere",
    "earth": "photorealistic, modern",
    "cyberpunk_earth": "cyberpunk, neon, high-tech, dystopian",
    "fantasy_realm": "high fantasy, painterly, epic",
}

PRIMITIVE_UNIVERSES = {"three_realms", "stone_age"}

# Additional negative prompt for primitive universes
PRIMITIVE_NEGATIVE = "technology, electronics, metal armor, guns, robots, screens, holograms, cybernetics, modern clothing, vehicles, city"

# Default negative
DEFAULT_NEGATIVE = "cgi, watermark, signature, text, low quality, blurry, deformed, disfigured"

