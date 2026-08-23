"""Orchestrator — VRAM-locked image generation and animation flows.

Coordinates: prompt builder → ComfyUI Flux (imagen) or
prompt builder → ComfyUI Flux → Ollama vision → ComfyUI WanVideo (animate).

All GPU operations serialize through a single asyncio.Lock to prevent
VRAM contention between ComfyUI and Ollama on a single RTX 4090.
"""

from __future__ import annotations

import asyncio
import json
import logging
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

logger = logging.getLogger("transversal.imagen")
logger.setLevel(logging.INFO)
if not logger.handlers:
    logger.addHandler(logging.StreamHandler())

# ── Paths ──────────────────────────────────────────────

WORKFLOW_DIR = Path(os.getenv(
    "WORKFLOW_DIR",
    "/app/workflows",
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


def _safe_filename(name: str) -> str:
    """Convert entity/universe names to safe filename components."""
    return "".join(c if c.isalnum() or c in "_-" else "_" for c in name).strip("_")


def _save_image_variants(image_data: bytes, output_dir: Path, base_name: str) -> dict[str, str]:
    """Save original + 3 variant sizes as webp. Returns dict of variant→filename.

    Files named: {base_name}_{Size}.webp (e.g. ElenaAntonova_Earth_Large_a1b2.webp)
    """
    img = Image.open(__import__("io").BytesIO(image_data))
    width, height = img.size

    variants = {
        "original": (width, height, "Original"),
        "large": (min(width, 1024), int(min(width, 1024) / width * height) if width > height else int(min(height, 1024) / height * width), "Large"),
        "small": (min(width, 240), int(min(width, 240) / width * height) if width > height else int(min(height, 240) / height * width), "Small"),
        "mini": (min(width, 48), int(min(width, 48) / width * height) if width > height else int(min(height, 48) / height * width), "Mini"),
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    filenames: dict[str, str] = {}

    for variant_key, (w, h, size_label) in variants.items():
        if variant_key == "original":
            resized = img
        else:
            if width > height:
                new_w, new_h = w, int((w / width) * height)
            else:
                new_w, new_h = int((h / height) * width), h
            resized = img.resize((new_w, new_h), Image.LANCZOS)

        # Convert RGBA → RGB for webp, strip EXIF
        if resized.mode in ("RGBA", "LA", "P"):
            resized = resized.convert("RGBA")
        else:
            resized = resized.convert("RGB")

        fname = f"{base_name}_{size_label}.webp"
        path = output_dir / fname
        resized.save(path, format="WEBP", quality=85)
        filenames[variant_key] = fname

    return filenames


class ImagenOrchestrator:
    """Orchestrate image generation with VRAM serialisation.

    Single RTX 4090 strategy:
    - All GPU operations go through `_gpu_lock`
    - Flux runs → free → Ollama runs → free → WanVideo runs → free
    - Never two GPU consumers concurrently
    """

    def __init__(
        self,
        repository: EntityRepository | None = None,
        comfyui: ComfyUIClient | None = None,
        ollama: OllamaClient | None = None,
        progress_callback: callable | None = None,
    ):
        self._gpu_lock = asyncio.Lock()
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
        projection_id: str = "",
    ) -> EntityImage:
        """Generate a static Flux image for an entity or a projection."""
        entity_id = entity.id
        gen_type = GenerationType.IMAGEN

        await self._report(entity_id, gen_type, GenerationStatus.PROMPTING, "Building prompt...", 5)

        # 1. Build prompt from traits (projection-scoped when given)
        params = build_imagen_prompt(entity, universe, self.repo, projection_id or None)
        prompt = params["prompt"]
        negative = params["negative"]
        loras = params["loras"]
        steps = params["steps"]
        width = params["width"]
        height = params["height"]
        seed = random.randint(0, 2**32 - 1)

        logger.info(f"Imagen prompt for {entity_id} ({entity.name}):\n  prompt: {prompt[:200]}...\n  negative: {negative[:200]}...\n  loras: {loras}\n  steps={steps} size={width}x{height} seed={seed}")

        # 2. Prepare Loras
        lora1 = loras[0] if len(loras) > 0 else ""
        lora1_weight = 0.8 if lora1 else 0.0
        lora2 = loras[1] if len(loras) > 1 else ""
        lora2_weight = 0.4 if lora2 else 0.0

        await self._report(entity_id, gen_type, GenerationStatus.GENERATING, "Generating image...", 20)

        async with self._gpu_lock:
            # Load workflow
            workflow = _load_workflow("imagen_flux.json")

            # Build descriptive basename: ElenaAntonova_Earth_a1b2c3d4
            short_hash = uuid.uuid4().hex[:8]
            safe_name = _safe_filename(entity.name)
            safe_universe = _safe_filename(universe)
            base_name = f"{safe_name}_{safe_universe}_{short_hash}"
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

            # Get the generated image — either download from ComfyUI or read from disk
            if result.get("filename"):
                image_data = await self.comfyui.get_image(
                    result["filename"], result.get("subfolder", ""), result.get("type", "output")
                )
            else:
                # WAS Image Save node doesn't report filenames — find the output on disk
                saved_files = sorted(output_full.glob("ComfyUI_*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
                if not saved_files:
                    raise FileNotFoundError(f"No output image found in {output_full}")
                image_data = saved_files[0].read_bytes()

            # Free VRAM
            await self.comfyui.free_memory()

        # 3. Save variants (flat files in entity/universe dir)
        await self._report(entity_id, gen_type, GenerationStatus.SAVING, "Saving images...", 80)

        variants = _save_image_variants(image_data, output_full, base_name)

        # 4. Record metadata
        owner = projection_id or None
        # Auto-select all three roles when this is the sole image for its owner
        # (entity or projection), matching upload/drop behaviour.
        existing = self.repo.get_images_for_owner(entity_id, owner)
        roles = ["background", "sheet", "navdot"] if not existing else []

        entity_image = EntityImage(
            id=short_hash,
            entity_id=entity_id,
            projection_id=owner,
            universe=universe,
            image_type=ImageType.IMAGEN,
            roles=roles,
            prompt=prompt,
            negative_prompt=negative,
            loras=loras,
            width=width,
            height=height,
            seed=seed,
            steps=steps,
            filename=base_name,
            extension="webp",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.repo.create_entity_image(entity_image)

        await self._report(entity_id, gen_type, GenerationStatus.COMPLETE,
                           f"/media/imagen/{output_subpath}/{variants['large']}", 100)

        return entity_image

    # ── Animate (video loop) ───────────────────────────

    async def run_animate(
        self,
        entity: Entity,
        universe: str,
        duration_seconds: float = 3.0,
        session_id: str = "",
        existing_image_path: str = "",
        motion_hint: str = "",
    ) -> EntityImage:
        """Generate a video loop for an entity.

        Pipeline (fresh): Flux → gemma3 vision → WanVideo loop
        Pipeline (existing): read image from disk → gemma3 vision → WanVideo loop
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
        width = params["width"]
        height = params["height"]
        # Cap resolution for WanVideo VRAM budget (RTX 4090 24GB)
        max_pixels = 1024 * 1024
        if width * height > max_pixels:
            scale = (max_pixels / (width * height)) ** 0.5
            width = int(width * scale)
            height = int(height * scale)
            # Round to nearest multiple of 64 for the VAE
            width = (width // 64) * 64
            height = (height // 64) * 64

        # Animation negative prompt
        anim_negative = f"{negative}, worst quality, low quality, bright tones, interlaced, overexposed, static, blurry, subtitles, 3D, works, paintings, lightning, images, JPEG artifacts, ugly, incomplete, deformed, disfigured, misshapen limbs, fused fingers, still picture, messy background"

        lora1 = loras[0] if len(loras) > 0 else ""
        lora1_weight = 0.8 if lora1 else 0.0
        lora2 = loras[1] if len(loras) > 1 else ""
        lora2_weight = 0.4 if lora2 else 0.0
        animate_seed = random.randint(0, 2**32 - 1)

        async with self._gpu_lock:
          try:
            # ── Step 1: Get or generate static image ──
            output_subpath = f"{entity_id}/{universe}"
            output_full = IMAGEN_DIR / output_subpath
            output_full.mkdir(parents=True, exist_ok=True)

            if existing_image_path:
                # Use existing image — skip Flux generation
                await self._report(entity_id, gen_type, GenerationStatus.GENERATING, "Using existing image...", 15)
                img_path = IMAGEN_DIR / existing_image_path
                if not img_path.exists():
                    raise FileNotFoundError(f"Existing image not found: {img_path}")
                static_image = img_path.read_bytes()
                short_hash = uuid.uuid4().hex[:8]
                safe_name = _safe_filename(entity.name)
                safe_universe = _safe_filename(universe)
                base_name = f"{safe_name}_{safe_universe}_anim_{short_hash}"
                _save_image_variants(static_image, output_full, base_name)
            else:
                # Generate new Flux image from traits
                await self._report(entity_id, gen_type, GenerationStatus.GENERATING, "Generating static image...", 15)
                short_hash = uuid.uuid4().hex[:8]
                safe_name = _safe_filename(entity.name)
                safe_universe = _safe_filename(universe)
                base_name = f"{safe_name}_{safe_universe}_{short_hash}"

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
                if flux_result.get("filename"):
                    static_image = await self.comfyui.get_image(
                        flux_result["filename"], flux_result.get("subfolder", ""), flux_result.get("type", "output")
                    )
                else:
                    saved_files = sorted(output_full.glob("ComfyUI_*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
                    if not saved_files:
                        raise FileNotFoundError(f"No output image found in {output_full}")
                    static_image = saved_files[0].read_bytes()

                _save_image_variants(static_image, output_full, base_name)
                await self.comfyui.free_memory()

            # ── Step 2: Ollama vision ──
            await self._report(entity_id, gen_type, GenerationStatus.VISION, "Analysing image with gemma3:12b...", 40)

            # Upload image to ComfyUI input dir for WanVideo
            input_filename = f"animate_{short_hash}.png"
            await self.comfyui.upload_image(static_image, input_filename)

            motion_description = await self.ollama.describe_motion(static_image, motion_hint)
            logger.info(f"Gemma3 motion description: {motion_description}")

            await self.comfyui.free_memory()
            await self.ollama.unload_model()

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

          finally:
            await self.comfyui.free_memory()
            await self.ollama.unload_model()

        # 4. Save video
        await self._report(entity_id, gen_type, GenerationStatus.SAVING, "Saving animation...", 85)

        image_id = short_hash
        video_path = ANIMATED_DIR / output_subpath
        video_path.mkdir(parents=True, exist_ok=True)

        # Determine extension
        ext = Path(wan_result["filename"]).suffix if "filename" in wan_result else ".webp"
        video_file = video_path / f"{base_name}{ext}"
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
            filename=base_name,
            extension=ext.lstrip("."),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.repo.create_entity_image(entity_image)

        await self._report(entity_id, gen_type, GenerationStatus.COMPLETE,
                           f"/media/animated/{output_subpath}/{base_name}{ext}", 100)

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

        # Remove all variants (flat files by basename)
        for suffix in ["_Original.webp", "_Large.webp", "_Small.webp", "_Mini.webp", f".{img.extension}"]:
            p = base / f"{img.filename}{suffix}"
            if p.exists():
                p.unlink()

        return self.repo.delete_entity_image(image_id)
