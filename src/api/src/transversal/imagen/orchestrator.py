"""Orchestrator — VRAM-locked image generation and animation flows.

Coordinates: prompt builder → ComfyUI Flux (imagen) or
prompt builder → ComfyUI Flux → Ollama vision → ComfyUI WanVideo (animate).

All GPU operations serialize through a single asyncio.Lock to prevent
VRAM contention between ComfyUI and Ollama on a single RTX 4090.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import random
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageChops

from transversal.db.repository import EntityRepository
from transversal.domain import Entity, MediaImage, EntityType, ImageType
from transversal.imagen.comfyui import (
    ComfyUIClient,
    inject_bg_removal_params,
    inject_bg_removal_video_params,
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
from transversal.services.media_utils import has_transparency

logger = logging.getLogger("transversal.imagen")
logger.setLevel(logging.INFO)
# No module-level handler: main.py's basicConfig owns root formatting, and a
# second StreamHandler here made every line print twice (bare + formatted).

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
    ) -> MediaImage:
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

        # 2. Prepare Loras
        lora1 = loras[0] if len(loras) > 0 else ""
        lora1_weight = 0.8 if lora1 else 0.0
        lora2 = loras[1] if len(loras) > 1 else ""
        lora2_weight = 0.4 if lora2 else 0.0

        # Full, untruncated generation log — mirrors the old app's format so the
        # exact prompt, negative, and applied LoRAs (with weights) are inspectable
        # after the fact. Only the first two LoRAs are injected into the workflow.
        lora_note = ""
        if len(loras) > 2:
            lora_note = f"loras configured (only the first two apply): {loras}\n"
        logger.info(
            f"generating image\n"
            f"entity: {entity_id} ({entity.name})\n"
            f"universe: {universe}\n"
            f"projection: {projection_id or '(none)'}\n"
            f"steps: {steps}\n"
            f"width: {width}\n"
            f"height: {height}\n"
            f"seed: {seed}\n"
            f"lora 1: {lora1 or '(none)'}\n"
            f"weight 1: {lora1_weight}\n"
            f"lora 2: {lora2 or '(none)'}\n"
            f"weight 2: {lora2_weight}\n"
            f"{lora_note}"
            f"prompt: {prompt}\n"
            f"negative: {negative}"
        )

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

        entity_image = MediaImage(
            id=short_hash,
            entity_id=entity_id,
            projection_id=owner,
            universe=universe,
            image_type=ImageType.IMAGEN,
            roles=roles,
            transparent=has_transparency(image_data),
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
        self.repo.create_image(entity_image)

        # 5. First image for a projection → also cut it out (B129). A cutout
        # needs a source, so this hangs off the first *generated image* rather
        # than off entity creation, which has no image yet.
        if owner and not existing:
            await self._auto_cutout_for_projection(entity, entity_image)

        await self._report(entity_id, gen_type, GenerationStatus.COMPLETE,
                           f"/media/imagen/{output_subpath}/{variants['large']}", 100)

        return entity_image

    async def _auto_cutout_for_projection(self, entity: Entity, source: MediaImage) -> None:
        """Cut out a projection's first image and tag the pair background/cutout.

        The generated image becomes the ``background``; the transparent cutout
        becomes both the ``navdot`` and the ``sheet`` portrait, which is what
        lets a body show a floating cutout rather than a cropped circle.

        Best-effort by design: the generation that triggered this has already
        succeeded and its image is recorded, so a missing BiRefNet model or a
        busy ComfyUI must not fail the job. On failure the source keeps the
        roles auto-select gave it (all three), so the body still has an image
        for every role — strictly better than stripping them with no cutout to
        put in their place.

        No sibling cleanup is needed: this only runs when the owner had no
        images at all, so there is nothing holding ``background``/``sheet``/
        ``navdot`` to strip.
        """
        entity_id = entity.id
        try:
            await self._report(entity_id, GenerationType.IMAGEN,
                               GenerationStatus.SAVING, "Cutting out navdot...", 90)
            cutout = await self.run_remove_background(
                entity, source.id, report_gen_type=GenerationType.IMAGEN
            )
        except Exception:
            logger.exception(
                f"Auto-cutout failed for {source.id} (projection {source.projection_id}); "
                "keeping the generated image with all three roles"
            )
            return

        self.repo.update_image(source.id, {"roles": ["background"]})
        self.repo.update_image(cutout.id, {"roles": ["navdot", "sheet"]})
        source.roles = ["background"]
        logger.info(
            f"Auto-cutout for projection {source.projection_id}: "
            f"{source.id} → background, {cutout.id} → navdot+sheet"
        )

    # ── Animate (video loop) ───────────────────────────

    async def run_animate(
        self,
        entity: Entity,
        universe: str,
        duration_seconds: float = 3.0,
        session_id: str = "",
        existing_image_path: str = "",
        motion_hint: str = "",
        source_transparent: bool = False,
    ) -> MediaImage:
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

            if source_transparent:
                await self._report(entity_id, gen_type, GenerationStatus.MATTING,
                                   "Removing background from frames...", 70)
                video_data = await self._matte_video(video_data, short_hash)

          finally:
            await self.comfyui.free_memory()
            await self.ollama.unload_model()

        # 4. Save video
        await self._report(entity_id, gen_type, GenerationStatus.SAVING, "Saving animation...", 85)

        image_id = short_hash
        video_path = ANIMATED_DIR / output_subpath
        video_path.mkdir(parents=True, exist_ok=True)

        # Transparent animations are re-encoded as VP9-alpha webm by the
        # matting stage; opaque ones keep the WanVideo output container.
        if source_transparent:
            ext = ".webm"
        else:
            ext = Path(wan_result["filename"]).suffix if "filename" in wan_result else ".webp"
        video_file = video_path / f"{base_name}{ext}"
        video_file.write_bytes(video_data)

        # 5. Record metadata
        entity_image = MediaImage(
            id=image_id,
            entity_id=entity_id,
            universe=universe,
            image_type=ImageType.ANIMATED,
            transparent=source_transparent,
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
        self.repo.create_image(entity_image)

        await self._report(entity_id, gen_type, GenerationStatus.COMPLETE,
                           f"/media/animated/{output_subpath}/{base_name}{ext}", 100)

        return entity_image

    # ── Video matting (transparent animations) ─────────

    async def _matte_video(self, video_bytes: bytes, tag: str, framerate: float = 24.0) -> bytes:
        """Per-frame BiRefNet background removal on an opaque video loop.

        VHS_LoadVideo frames → BiRefNet → invert mask → alpha composite →
        RGBA PNG sequence → download → 3-frame temporal median on the alpha
        channel (anti-flicker) → VP9 alpha webm via ffmpeg.

        Must be called while holding ``_gpu_lock`` (it submits GPU work).
        """
        input_filename = f"matte_{tag}.webm"
        await self.comfyui.upload_image(video_bytes, input_filename)

        workflow = _load_workflow("bg_remove_video.json")
        workflow = inject_bg_removal_video_params(
            workflow,
            input_video=input_filename,
            filename_prefix=f"matte_{tag}",
        )

        prompt_id = await self.comfyui.submit_workflow(workflow)
        frames = await self.comfyui.wait_for_result_images(prompt_id, timeout_secs=1200)
        if not frames:
            raise FileNotFoundError("Frame matting produced no output frames")
        await self.comfyui.free_memory()

        frames = sorted(frames, key=lambda f: f["filename"])
        images: list[Image.Image] = []
        for f in frames:
            data = await self.comfyui.get_image(
                f["filename"], f.get("subfolder", ""), f.get("type", "output")
            )
            images.append(Image.open(io.BytesIO(data)).convert("RGBA"))

        with tempfile.TemporaryDirectory(prefix="matte_") as tmp:
            tmp_path = Path(tmp)
            n = len(images)
            for i, img in enumerate(images):
                # Temporal median (radius 1) over the alpha channel only —
                # BiRefNet has no temporal consistency, so edges can flicker.
                a0 = images[max(0, i - 1)].getchannel("A")
                a1 = img.getchannel("A")
                a2 = images[min(n - 1, i + 1)].getchannel("A")
                med = ImageChops.lighter(
                    ImageChops.darker(a0, a1),
                    ImageChops.darker(ImageChops.lighter(a0, a1), a2),
                )
                rgb = img.convert("RGB").split()
                Image.merge("RGBA", (*rgb, med)).save(tmp_path / f"frame_{i:05d}.png")

            out_path = tmp_path / "out.webm"
            cmd = [
                "ffmpeg", "-y", "-loglevel", "error",
                "-framerate", str(framerate),
                "-i", str(tmp_path / "frame_%05d.png"),
                "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p",
                "-crf", "32", "-b:v", "0",
                str(out_path),
            ]
            subprocess.run(cmd, check=True, timeout=600)
            return out_path.read_bytes()

    # ── Remove background (static image cutout) ────────

    async def run_remove_background(
        self,
        entity: Entity,
        image_id: str,
        report_gen_type: GenerationType | None = None,
    ) -> MediaImage:
        """Remove the background from an existing static image via BiRefNet.

        Produces a new transparent cutout image owned by the same entity or
        projection as the source. Non-destructive: the source is untouched.

        ``report_gen_type`` lets a caller that is already running a job of its
        own (the auto-cutout under imagen, B129) report under *that* type —
        otherwise the progress stream would flip back to a second job type
        mid-generation.
        """
        entity_id = entity.id
        gen_type = report_gen_type or GenerationType.REMOVE_BG

        src = self.repo.get_image(image_id)
        if not src:
            raise FileNotFoundError(f"Image '{image_id}' not found")
        if src.image_type == ImageType.ANIMATED:
            raise ValueError("Background removal only works on static images")

        source_path = IMAGEN_DIR / f"{src.owner_id}/{src.universe}/{src.filename}_Large.{src.extension}"
        if not source_path.exists():
            raise FileNotFoundError(f"Source image not found: {source_path}")
        source_bytes = source_path.read_bytes()

        short_hash = uuid.uuid4().hex[:8]
        safe_name = _safe_filename(entity.name)
        safe_universe = _safe_filename(src.universe)
        base_name = f"{safe_name}_{safe_universe}_cut_{short_hash}"
        output_subpath = f"{src.owner_id}/{src.universe}"
        output_full = IMAGEN_DIR / output_subpath
        output_full.mkdir(parents=True, exist_ok=True)

        await self._report(entity_id, gen_type, GenerationStatus.GENERATING, "Removing background...", 20)

        async with self._gpu_lock:
            input_filename = f"bgrem_{short_hash}.png"
            await self.comfyui.upload_image(source_bytes, input_filename)

            workflow = _load_workflow("bg_remove.json")
            workflow = inject_bg_removal_params(
                workflow,
                input_image=input_filename,
                filename_prefix=f"bgremoved_{short_hash}",
            )

            prompt_id = await self.comfyui.submit_workflow(workflow)
            result = await self.comfyui.wait_for_result(prompt_id, timeout_secs=600)
            if not result.get("filename"):
                raise FileNotFoundError("Background removal produced no output image")
            cutout_bytes = await self.comfyui.get_image(
                result["filename"], result.get("subfolder", ""), result.get("type", "output")
            )
            await self.comfyui.free_memory()

        await self._report(entity_id, gen_type, GenerationStatus.SAVING, "Saving cutout...", 85)

        variants = _save_image_variants(cutout_bytes, output_full, base_name)
        with Image.open(output_full / variants["original"]) as _im:
            width, height = _im.size

        entity_image = MediaImage(
            id=short_hash,
            # The cutout belongs to the same owner and the same tier as its
            # source, whatever kind that owner is — never assumed to be an
            # entity with a projection.
            owner_kind=src.owner_kind,
            owner_id=src.owner_id,
            variant_id=src.variant_id,
            universe=src.universe,
            image_type=ImageType.CUTOUT,
            roles=[],
            transparent=has_transparency(cutout_bytes),
            prompt=f"background removed from {src.filename}",
            negative_prompt="",
            loras=[],
            width=width,
            height=height,
            seed=0,
            steps=0,
            filename=base_name,
            extension="webp",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.repo.create_image(entity_image)

        await self._report(entity_id, gen_type, GenerationStatus.COMPLETE,
                           f"/media/imagen/{output_subpath}/{variants['large']}", 100)

        return entity_image

    # ── Cleanup ─────────────────────────────────────────

    async def delete_image(self, image_id: str) -> bool:
        """Delete an image and its variants from disk and DB."""
        img = self.repo.get_image(image_id)
        if not img:
            return False

        if img.image_type == ImageType.ANIMATED:
            base = ANIMATED_DIR / f"{img.owner_id}/{img.universe}"
        else:
            base = IMAGEN_DIR / f"{img.owner_id}/{img.universe}"

        # Remove all variants (flat files by basename)
        for suffix in ["_Original.webp", "_Large.webp", "_Small.webp", "_Mini.webp", f".{img.extension}"]:
            p = base / f"{img.filename}{suffix}"
            if p.exists():
                p.unlink()

        # Tidy the directories the variants lived in, so a deleted image does not
        # leave an empty tree behind. `rmdir` refuses a non-empty directory, which
        # is exactly the guard wanted: another universe's or another image's files
        # keep it alive.
        for directory in (base, base.parent):
            try:
                directory.rmdir()
            except OSError:
                pass

        return self.repo.delete_image(image_id)
