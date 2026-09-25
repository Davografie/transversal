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
    MATTING = "matting"           # per-frame bg removal (transparent animations)
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
    image_id: str = ""  # the static MediaImage to cut out


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

# Default negative.
#
# The caption/inscription vocabulary is here because `watermark, signature, text`
# alone was NOT enough to stop a style LoRA from writing on the image: a
# `ChineseScrollPainting` LoRA (applied automatically to `three_realms`
# locations) is trained on scroll paintings, which carry calligraphic
# inscriptions and red seal stamps, and it reproduced them over an explicit
# "text, watermark, signature" negative. Adding the vocabulary below removed
# them for the same prompt, seed and LoRA weight.
#
# Do NOT move any of this into the positive prompt. Tested: a positive clause
# reading "no text, no calligraphy, no seal stamps" produced *more* calligraphy
# than the baseline — Flux/T5 does not negate, so naming the thing summons it.
DEFAULT_NEGATIVE = (
    "cgi, watermark, signature, text, low quality, blurry, deformed, disfigured, "
    "caption, captions, lettering, writing, calligraphy, inscription, "
    "seal, seal stamp, red seal, stamp, logo, title, subtitle, signage, "
    "chinese characters, kanji, border, frame, ui"
)

