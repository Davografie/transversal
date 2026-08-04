"""Orchestrator — VRAM-locked image generation and animation flows.

Coordinates: prompt builder → ComfyUI Flux (imagen) or
prompt builder → ComfyUI Flux → Ollama vision → ComfyUI WanVideo (animate).

All GPU operations serialize through a single asyncio.Lock to prevent
VRAM contention between ComfyUI and Ollama on a single RTX 4090.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import uuid
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from transversal.db.repository import EntityRepository
from transversal.domain import Entity, EntityImage, EntityType, ImageType
from transversal.imagen.comfyui import (
    ComfyUIClient,
    inject_flux_params,
    inject_wan_params,
)
from transversal.imagen.models import (
    DEFAULT_NEGATIVE,
    PRIMITIVE_NEGATIVE,
    PRIMITIVE_UNIVERSES,
    GenerationStatus,
    GenerationType,
)
from transversal.imagen.ollama import OllamaClient
from transversal.imagen.prompt_builder import build_imagen_prompt


# ── Paths ──────────────────────────────────────────────

WORKFLOW_DIR = Path(os.getenv(
    "WORKFLOW_DIR",
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "..", "src", "imagen", "workflows"),
))

MEDIA_DIR = Path(os.getenv("MEDIA_DIR", "/app/media"))
IMAGEN_DIR = MEDIA_DIR / "imagen"
ANIMATED_DIR = MEDIA_DIR / "animated"
COMFY_INPUT_DIR = Path(os.getenv("COMFY_INPUT_DIR", "/app/ComfyUI/input"))


# ── Helpers ────────────────────────────────────────────

def _load_workflow(name: str) -> dict:
    """Load a ComfyUI workflow JSON template."""
    path = WORKFLOW_DIR / name
    if not path.exists():
        # Try alternate paths
        alt = Path(__file__).parent.parent.parent.parent.parent.parent.parent / "src" / "imagen" / "workflows" / name
        if alt.exists():
            path = alt
        else:
            raise FileNotFoundError(f"Workflow not found: {name} (tried {path}, {alt})")
    with open(path) as f:
        return json.load(f)


def _save_image_variants(image_data: bytes, base_path: Path, base_name: str) -> dict[str, Path]:
    """Save original + 3 variant sizes. Returns dict of variant→path."""
    img = Image.open(__import__("io").BytesIO(image_data))
    width, height = img.size

    variants = {
        "original": (width, height),
        "large": (min(width, 1024), int(min(width, 1024) / width * height) if width > height else int(min(height, 1024) / height * width)),
        "small": (min(width, 240), int(min(width, 240) / width * height) if width > height else int(min(height, 240) / height * width)),
        "mini": (min(width, 48), int(min(width, 48) / width * height) if width > height else int(min(height, 48) / height * width)),
    }

    # Ensure width is the larger dimension for resizing
    for name, (w, h) in variants.items():
        if name == "original":
            resized = img
        else:
            if width > height:
                new_w = w
                new_h = int((w / width) * height)
            else:
                new_h = h
                new_w = int((h / height) * width)
            resized = img.resize((new_w, new_h), Image.LANCZOS)

        # Strip EXIF
        data = list(resized.getdata())
        clean = Image.new(resized.mode, resized.size)
        clean.putdata(data)

        path = base_path / f"{base_name}_{name}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        clean.save(path)

    # Return paths relative to MEDIA_DIR for URL use
    return {v: p for v, p in variants.items()}


class ImagenOrchestrator:
    """Orchestrate image generation with VRAM serialisation.

    Single RTX 4090 strategy:
    - All GPU operations go through `_gpu_lock`
    - Flux runs → free → Ollama runs → free → WanVideo runs → free
    - Never two GPU consumers concurrently
    """

    _gpu_lock = asyncio.Lock()

    def __init__(
        self,
        repository: EntityRepository | None = None,
        comfyui: ComfyUIClient | None = None,
        ollama: OllamaClient | None = None,
        progress_callback: callable | None = None,
    ):
        self.repo = repository or EntityRepository()
        self.comfyui = comfyui or ComfyUIClient()
        self.ollama = ollama or OllamaClient()
        self._progress = progress_callback

    async def _report(self, entity_id: str, gen_type: GenerationType, status: GenerationStatus, message: str = "", percent: int = 0):
        if self._progress:
            await self._progress(entity_id, gen_type, status, message, percent)

    # ── Imagen (static image) ──────────────────────────

    async def run_imagen(
        self,
        entity: Entity,
        universe: str,
        session_id: str = "",
    ) -> EntityImage:
        """Generate a static Flux image for an entity."""
        entity_id = entity.id
        gen_type = GenerationType.IMAGEN

        await self._report(entity_id, gen_type, GenerationStatus.PROMPTING, "Building prompt...", 5)

        # 1. Build prompt from traits
        params = build_imagen_prompt(entity, universe, self.repo)
        prompt = params["prompt"]
        negative = params["negative"]
        loras = params["loras"]
        steps = params["steps"]
        width = params["width"]
        height = params["height"]
        seed = random.randint(0, 2**32 - 1)

        # 2. Prepare Loras
        lora1 = loras[0] if len(loras) > 0 else ""
        lora1_weight = 0.8 if lora1 else 0.0
        lora2 = loras[1] if len(loras) > 1 else ""
        lora2_weight = 0.4 if lora2 else 0.0

        await self._report(entity_id, gen_type, GenerationStatus.GENERATING, "Generating image...", 20)

        async with self._gpu_lock:
            # Load workflow
            workflow = _load_workflow("imagen_flux.json")

            # Prepare output path
            image_id = uuid.uuid4().hex[:12]
            output_subpath = f"{entity_id}/{universe}"
            output_full = IMAGEN_DIR / output_subpath
            output_full.mkdir(parents=True, exist_ok=True)

            # Inject params
            wf = inject_flux_params(
                workflow,
                prompt=prompt,
                negative=negative,
                width=width,
                height=height,
                steps=steps,
                seed=seed,
                lora1=lora1,
                lora1_weight=lora1_weight,
                lora2=lora2,
                lora2_weight=lora2_weight,
                output_path=str(output_full),
            )

            # Submit and wait
            prompt_id = await self.comfyui.submit_workflow(wf)
            result = await self.comfyui.wait_for_result(prompt_id, timeout_secs=600)

            # Download generated image
            image_data = await self.comfyui.get_image(
                result["filename"], result.get("subfolder", ""), result.get("type", "output")
            )

            # Free VRAM
            await self.comfyui.free_memory()

        # 3. Save variants
        await self._report(entity_id, gen_type, GenerationStatus.SAVING, "Saving images...", 80)

        base_path = IMAGEN_DIR / output_subpath / image_id
        variants = _save_image_variants(image_data, base_path, "imagen")

        # 4. Record metadata
        entity_image = EntityImage(
            id=image_id,
            entity_id=entity_id,
            universe=universe,
            image_type=ImageType.IMAGEN,
            prompt=prompt,
            negative_prompt=negative,
            loras=loras,
            width=width,
            height=height,
            seed=seed,
            steps=steps,
            filename=f"{output_subpath}/{image_id}",
            extension="png",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.repo.create_entity_image(entity_image)

        await self._report(entity_id, gen_type, GenerationStatus.COMPLETE,
                           f"/media/imagen/{output_subpath}/{image_id}_large.png", 100)

        return entity_image

    # ── Animate (video loop) ───────────────────────────

    async def run_animate(
        self,
        entity: Entity,
        universe: str,
        duration_seconds: float = 3.0,
        session_id: str = "",
    ) -> EntityImage:
        """Generate a video loop for an entity.

        Pipeline:
        1. Generate static image (Flux)
        2. Ollama gemma3:12b vision → motion description
        3. WanVideo image-to-video with interpolation/looping
        """
        entity_id = entity.id
        gen_type = GenerationType.ANIMATE

        # 1. Static image first
        await self._report(entity_id, gen_type, GenerationStatus.PROMPTING, "Building prompt...", 5)

        params = build_imagen_prompt(entity, universe, self.repo)
        prompt = params["prompt"]
        negative = params["negative"]
        loras = params["loras"]
        steps_flux = params["steps"]
        width = 704
        height = 704

        # Animation negative prompt
        anim_negative = f"{negative}, worst quality, low quality, bright tones, interlaced, overexposed, static, blurry, subtitles, 3D, works, paintings, lightning, images, JPEG artifacts, ugly, incomplete, deformed, disfigured, misshapen limbs, fused fingers, still picture, messy background"

        lora1 = loras[0] if len(loras) > 0 else ""
        lora1_weight = 0.8 if lora1 else 0.0
        lora2 = loras[1] if len(loras) > 1 else ""
        lora2_weight = 0.4 if lora2 else 0.0
        animate_seed = random.randint(0, 2**32 - 1)

        async with self._gpu_lock:
            # ── Step 1: Generate static image ──
            await self._report(entity_id, gen_type, GenerationStatus.GENERATING, "Generating static image...", 15)

            image_id = uuid.uuid4().hex[:12]
            output_subpath = f"{entity_id}/{universe}"
            output_full = IMAGEN_DIR / output_subpath
            output_full.mkdir(parents=True, exist_ok=True)

            flux_wf = _load_workflow("imagen_flux.json")
            flux_wf = inject_flux_params(
                flux_wf,
                prompt=prompt,
                negative=negative,
                width=width,
                height=height,
                steps=steps_flux,
                seed=animate_seed,
                lora1=lora1,
                lora1_weight=lora1_weight,
                lora2=lora2,
                lora2_weight=lora2_weight,
                output_path=str(output_full),
            )

            flux_prompt_id = await self.comfyui.submit_workflow(flux_wf)
            flux_result = await self.comfyui.wait_for_result(flux_prompt_id, timeout_secs=600)
            static_image = await self.comfyui.get_image(
                flux_result["filename"], flux_result.get("subfolder", ""), flux_result.get("type", "output")
            )

            # Save static image
            static_path = IMAGEN_DIR / output_subpath / image_id
            _save_image_variants(static_image, static_path, "imagen")

            # Free Flux from VRAM
            await self.comfyui.free_memory()

            # ── Step 2: Ollama vision ──
            await self._report(entity_id, gen_type, GenerationStatus.VISION, "Analysing image with gemma3:12b...", 40)

            # Copy image to ComfyUI input dir for WanVideo
            input_filename = f"animate_{image_id}.png"
            input_path = COMFY_INPUT_DIR / input_filename
            input_path.parent.mkdir(parents=True, exist_ok=True)
            input_path.write_bytes(static_image)

            motion_description = await self.ollama.describe_motion(static_image)

            await self.comfyui.free_memory()

            # ── Step 3: WanVideo generation ──
            await self._report(entity_id, gen_type, GenerationStatus.ANIMATING,
                               f"Generating video loop...", 60)

            wan_wf = _load_workflow("animate_wan.json")
            wan_wf = inject_wan_params(
                wan_wf,
                motion_prompt=motion_description,
                negative=anim_negative,
                input_image=input_filename,
                width=width,
                height=height,
                steps=30,
                seed=animate_seed,
                duration_seconds=duration_seconds,
                lora_strength=0.95,
                lora_activation_word="",
            )

            wan_prompt_id = await self.comfyui.submit_workflow(wan_wf)
            wan_result = await self.comfyui.wait_for_result(wan_prompt_id, timeout_secs=1200)

            # Download video
            video_data = await self.comfyui.get_image(
                wan_result["filename"], wan_result.get("subfolder", ""), wan_result.get("type", "output")
            )

            await self.comfyui.free_memory()

        # 4. Save video
        await self._report(entity_id, gen_type, GenerationStatus.SAVING, "Saving animation...", 85)

        video_path = ANIMATED_DIR / output_subpath
        video_path.mkdir(parents=True, exist_ok=True)

        # Determine extension
        ext = Path(wan_result["filename"]).suffix if "filename" in wan_result else ".webp"
        video_file = video_path / f"{image_id}{ext}"
        video_file.write_bytes(video_data)

        # 5. Record metadata
        entity_image = EntityImage(
            id=image_id,
            entity_id=entity_id,
            universe=universe,
            image_type=ImageType.ANIMATED,
            prompt=prompt,
            negative_prompt=anim_negative,
            loras=loras,
            width=width,
            height=height,
            seed=animate_seed,
            steps=steps_flux,
            filename=f"{output_subpath}/{image_id}",
            extension=ext.lstrip("."),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.repo.create_entity_image(entity_image)

        await self._report(entity_id, gen_type, GenerationStatus.COMPLETE,
                           f"/media/animated/{output_subpath}/{image_id}{ext}", 100)

        return entity_image

    # ── Cleanup ─────────────────────────────────────────

    async def delete_image(self, image_id: str) -> bool:
        """Delete an image and its variants from disk and DB."""
        img = self.repo.get_entity_image(image_id)
        if not img:
            return False

        if img.image_type == ImageType.ANIMATED:
            base = ANIMATED_DIR / f"{img.entity_id}/{img.universe}"
        else:
            base = IMAGEN_DIR / f"{img.entity_id}/{img.universe}"

        # Remove all variants
        for suffix in ["_original.png", "_large.png", "_small.png", "_mini.png", f".{img.extension}"]:
            p = base / f"{image_id}{suffix}"
            if p.exists():
                p.unlink()

        # Remove directory if empty
        try:
            base.rmdir()
            # Also try parent
            base.parent.rmdir()
        except OSError:
            pass

        return self.repo.delete_entity_image(image_id)
