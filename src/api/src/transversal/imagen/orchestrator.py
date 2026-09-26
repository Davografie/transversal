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
    inject_upscale_params,
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
from transversal.services.media_utils import (
    VARIANT_LONG_SIDES,
    has_transparency,
    trim_transparent_margins,
    wants_auto_matte,
    save_image_variants as _save_image_variants,
)

logger = logging.getLogger("transversal.imagen")
logger.setLevel(logging.INFO)
# No module-level handler: main.py's basicConfig owns root formatting, and a
# second StreamHandler here made every line print twice (bare + formatted).

# ── Paths ──────────────────────────────────────────────

WORKFLOW_DIR = Path(os.getenv(
    "WORKFLOW_DIR",
    "/app/workflows",
))

#: The upscaler. Chosen by measuring two candidates against real art at the size
#: actually served (see `inject_upscale_params`) — `4x-UltraSharp` beat
#: `RealESRGAN_x4plus` on both the illustrated and the painted-ink backgrounds.
UPSCALE_MODEL = "4x-UltraSharp.pth"

#: The model is 4x, but nothing bigger than the largest tier is ever served, so
#: the master is capped there. A 2048 resampled down from 4x is a better 2048
#: than one upscaled straight to it. Derived from the ladder, not retyped.
UPSCALE_MASTER_CAP = VARIANT_LONG_SIDES["XLarge"]

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
            flags=["ai_generated"],  # the imagen pipeline made this
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

        # 5. An occupant's picture gets a matte as part of being made ([[B214]]).
        # This is a rule about the picture, not about being *first*: every
        # generated occupant image is a subject, wherever it sits on the ladder,
        # and one that already carries a matte is left alone.
        if wants_auto_matte("entity", entity.type) and "cutout" not in entity_image.renders:
            await self._auto_cutout(entity, entity_image)

        await self._report(entity_id, gen_type, GenerationStatus.COMPLETE,
                           f"/media/imagen/{output_subpath}/{variants['large']}", 100)

        return entity_image

    async def _auto_cutout(self, entity: Entity, source: MediaImage) -> None:
        """Give a freshly made occupant picture a matte, so its small roles float.

        The generated image keeps every role auto-select gave it; the matte is a
        **render of that picture**, so ``sheet`` and ``navdot`` begin serving it the
        moment it exists. No role has to be moved onto a second record — which is
        what the old shape did, and what [[B166]]'s redistribution was really about.

        Best-effort by design: the generation that triggered this has already
        succeeded and its image is recorded, so a missing BiRefNet model or a busy
        ComfyUI must not fail the job. On failure the picture simply renders opaque,
        which is exactly what it did before the matte existed.
        """
        entity_id = entity.id
        try:
            await self._report(entity_id, GenerationType.IMAGEN,
                               GenerationStatus.SAVING, "Cutting out navdot...", 90)
            await self.run_remove_background(
                entity.id, source.id, display_name=entity.name,
                report_gen_type=GenerationType.IMAGEN,
            )
        except Exception:
            logger.exception(
                f"Auto-cutout failed for {source.id} (projection {source.projection_id}); "
                "the picture keeps rendering without a matte"
            )
            return

        logger.info(
            f"Auto-cutout for {source.projection_id or 'entity'}: "
            f"{source.id} gained a cutout render"
        )

    # ── Animate (video loop) ───────────────────────────

    async def run_animate(
        self,
        entity: Entity,
        universe: str,
        duration_seconds: float = 3.0,
        session_id: str = "",
        source_image_id: str = "",
        motion_hint: str = "",
    ) -> MediaImage:
        """Generate a video loop for an entity.

        Pipeline (fresh): Flux → gemma3 vision → WanVideo loop
        Pipeline (existing): read image from disk → gemma3 vision → WanVideo loop

        ``source_image_id`` animates an existing image instead of generating one.
        It is an **id, not a path**: the record is the single source of truth for
        where the file is and whether it is transparent, so a caller cannot hand
        in a path that disagrees with the row — and the artwork's credits travel
        with it onto the loop.
        """
        entity_id = entity.id
        gen_type = GenerationType.ANIMATE
        source = self.repo.get_image(source_image_id) if source_image_id else None
        # A loop is matted only when the picture it came from was already a cutout.
        source_transparent = bool(source.transparent) if source else False

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

            if source is not None:
                # Animating an existing picture: no still is generated and none is
                # written — the picture's own ladder *is* the still, and the loop
                # becomes one more render on it (below). Writing a second still
                # ladder here is what used to make a loop look like its own picture
                # with its own credits and flags to keep in sync.
                await self._report(entity_id, gen_type, GenerationStatus.GENERATING, "Using existing image...", 15)
                img_path = IMAGEN_DIR / (
                    f"{source.owner_id}/{source.universe}/{source.filename}_Large.{source.extension}"
                )
                if not img_path.exists():
                    raise FileNotFoundError(f"Existing image not found: {img_path}")
                static_image = img_path.read_bytes()
                short_hash = uuid.uuid4().hex[:8]
                output_subpath = f"{source.owner_id}/{source.universe}"
                output_full = IMAGEN_DIR / output_subpath
                output_full.mkdir(parents=True, exist_ok=True)
                base_name = source.filename
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
        #
        # A loop made from an existing picture is that picture **with motion**, not
        # a new picture: the render is added to the source record and nothing is
        # copied, because there is nothing to copy it to. The citation, the labels
        # and the id stay the artwork's by construction — the old shape kept three
        # copies in sync by hand, and this is the defect class [[B210]] removes.
        if source is not None:
            updated = self.repo.update_image(source.id, {
                "renders": sorted(set(source.renders) | {"animated"}),
                "animated_extension": ext.lstrip("."),
                # Only the animate pipeline's motion claim is added. It generated no
                # still here, so `ai_generated` is not its to assert: the picture
                # already said what it is, and a hand-made upload stays unlabelled.
                "flags": sorted(set(source.flags) | {"ai_animated"}),
            })
            await self._report(entity_id, gen_type, GenerationStatus.COMPLETE,
                               f"/media/animated/{output_subpath}/{base_name}{ext}", 100)
            return updated or source

        entity_image = MediaImage(
            id=image_id,
            entity_id=entity_id,
            universe=universe,
            # The still was Flux-generated by this pipeline, so the picture's
            # provenance is `imagen`; that it is also a loop lives in `renders`.
            image_type=ImageType.IMAGEN,
            renders=["animated"],
            animated_extension=ext.lstrip("."),
            # Both of the animate pipeline's own claims apply when it generated the
            # still — a fresh loop is Flux *and* WanVideo, so it is generated as
            # well as animated.
            flags=sorted({"ai_generated", "ai_animated"}),
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

    # ── Upscale (detail pass on an existing static image) ──

    async def run_upscale(
        self,
        image_id: str,
        report_gen_type: GenerationType | None = None,
    ) -> MediaImage:
        """Upscale an image's **master** in place, then re-render its tiers.

        The old master is kept as `{filename}_PreUpscale.{ext}`: upscaling is
        irreversible and this is the only copy of the art. Returns the updated
        record, whose `width`/`height` move with the master — the UI labels an
        image with those, so leaving them stale made the work look like it had
        not happened.

        Raises ``ValueError`` for a video (no variants to derive) or when the
        master is already at the cap, because then there is nothing to gain.
        """
        from datetime import datetime, timezone

        img = self.repo.get_image(image_id)
        if not img:
            raise FileNotFoundError(f"Image '{image_id}' not found")
        if "animated" in img.renders:
            raise ValueError("Upscaling works on still images; a loop has no tiers")

        out_dir = IMAGEN_DIR / img.owner_id / img.universe
        master = out_dir / f"{img.filename}_Original.{img.extension}"
        if not master.exists():
            raise FileNotFoundError(f"Master not found: {master}")

        with Image.open(master) as im:
            before = im.size
        if max(before) >= UPSCALE_MASTER_CAP:
            raise ValueError(
                f"Already at the {UPSCALE_MASTER_CAP}px ceiling ({before[0]}x{before[1]})"
            )

        gen_type = report_gen_type or GenerationType.UPSCALE
        await self._report(img.owner_id, gen_type, GenerationStatus.GENERATING,
                           "Upscaling...", 20)

        async with self._gpu_lock:
            input_filename = f"upscale_{uuid.uuid4().hex[:8]}.png"
            await self.comfyui.upload_image(master.read_bytes(), input_filename)
            workflow = _load_workflow("upscale.json")
            workflow = inject_upscale_params(
                workflow,
                input_image=input_filename,
                model_name=UPSCALE_MODEL,
                filename_prefix=f"upscaled_{img.id}",
            )
            prompt_id = await self.comfyui.submit_workflow(workflow)
            result = await self.comfyui.wait_for_result(prompt_id, timeout_secs=1800)
            if not result.get("filename"):
                raise FileNotFoundError("Upscale produced no output image")
            raw = await self.comfyui.get_image(
                result["filename"], result.get("subfolder", ""), result.get("type", "output")
            )
            await self.comfyui.free_memory()

        await self._report(img.owner_id, gen_type, GenerationStatus.SAVING, "Saving...", 85)

        upscaled = Image.open(io.BytesIO(raw))
        w, h = upscaled.size
        if max(w, h) > UPSCALE_MASTER_CAP:  # nothing larger is ever served
            scale = UPSCALE_MASTER_CAP / max(w, h)
            upscaled = upscaled.resize(
                (max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS
            )

        backup = out_dir / f"{img.filename}_PreUpscale.{img.extension}"
        if not backup.exists():
            backup.write_bytes(master.read_bytes())

        buf = io.BytesIO()
        upscaled.save(buf, format="WEBP", quality=95)  # master; tiers re-encode at 85
        master.write_bytes(buf.getvalue())
        _save_image_variants(buf.getvalue(), out_dir, img.filename)

        updated = self.repo.update_image(image_id, {"width": upscaled.size[0], "height": upscaled.size[1]})
        await self._report(img.owner_id, gen_type, GenerationStatus.COMPLETE,
                           f"{before[0]}x{before[1]} -> {upscaled.size[0]}x{upscaled.size[1]}", 100)
        logger.info(
            f"Upscaled {img.filename} ({img.owner_id}) {before[0]}x{before[1]} -> "
            f"{upscaled.size[0]}x{upscaled.size[1]}"
        )
        return updated or img

    # ── Remove background (static image cutout) ────────

    async def run_remove_background(
        self,
        owner_id: str,
        image_id: str,
        display_name: str = "",
        report_gen_type: GenerationType | None = None,
    ) -> MediaImage:
        """Add the transparent (``cutout``) render to an existing static picture.

        The matte is a **render of the picture**, not a second picture: its tiers are
        written beside the picture's own as ``{filename}_Cutout_{Tier}.webp`` and
        recorded in ``renders``. Nothing is created to copy anything to, which is how
        a cutout used to lose its credits, its flags and its id — see [[B210]].

        Which roles serve the matte is the role map's decision (``ROLE_RENDER``),
        never this method's: the old shape had to move ``navdot``/``sheet`` onto the
        new record to make it render at all.

        ``owner_id`` is the progress key and ``display_name`` names the job in the
        log; neither decides the picture — the **source image id** does, so a trait
        image is cut out under its trait with no special case.

        ``report_gen_type`` lets a caller that is already running a job of its own
        (the auto-cutout under imagen, [[B129]]) report under *that* type —
        otherwise the progress stream would flip back to a second job type
        mid-generation.
        """
        gen_type = report_gen_type or GenerationType.REMOVE_BG

        src = self.repo.get_image(image_id)
        if not src:
            raise FileNotFoundError(f"Image '{image_id}' not found")
        if "animated" in src.renders:
            raise ValueError("Background removal only works on static images")

        source_path = IMAGEN_DIR / f"{src.owner_id}/{src.universe}/{src.filename}_Large.{src.extension}"
        if not source_path.exists():
            raise FileNotFoundError(f"Source image not found: {source_path}")
        source_bytes = source_path.read_bytes()

        short_hash = uuid.uuid4().hex[:8]
        output_subpath = f"{src.owner_id}/{src.universe}"
        output_full = IMAGEN_DIR / output_subpath
        output_full.mkdir(parents=True, exist_ok=True)

        await self._report(owner_id, gen_type, GenerationStatus.GENERATING, "Removing background...", 20)

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

        await self._report(owner_id, gen_type, GenerationStatus.SAVING, "Saving cutout...", 85)

        # Trim the matte to its subject ([[B213]]). A cutout keeps the source's
        # canvas, so a subject that filled a third of the frame would be served at
        # a third of the size its tier allows — small, and floating in empty space
        # on every surface. Only transparent pixels are discarded.
        cutout_bytes, trimmed = trim_transparent_margins(cutout_bytes)
        if trimmed:
            logger.info(f"Trimmed the matte for {src.filename} ({src.owner_id}) to its subject")

        # The matte gets the picture's own base name, so it is a render *of* it —
        # the name is the whole ownership story.
        variants = _save_image_variants(cutout_bytes, output_full, f"{src.filename}_Cutout")

        # The cutter asserts nothing of its own. BiRefNet is not one of the pipelines
        # that declares AI (imagen's `ai_generated`, animate's `ai_animated`), so a
        # picture is not labelled as AI merely for having been cut out; its existing
        # flags simply stay, because removing a background does not change where the
        # picture came from. `transparent` is set because the picture now has a
        # transparent render — which is what a portrait surface asks about.
        updated = self.repo.update_image(src.id, {
            "renders": sorted(set(src.renders) | {"cutout"}),
            "transparent": src.transparent or has_transparency(cutout_bytes),
        })

        await self._report(owner_id, gen_type, GenerationStatus.COMPLETE,
                           f"/media/imagen/{output_subpath}/{variants['large']}", 100)

        return updated or src

    # ── Cleanup ─────────────────────────────────────────

    async def delete_image(self, image_id: str) -> bool:
        """Delete a picture: every file it owns, then its record.

        Every render under the base name goes — the static ladder, the matte's
        ladder, the pre-upscale backup and the loop — because a merged picture keeps
        them all under one name. Globbing the base name rather than listing suffixes
        is deliberate: the suffix list fell behind the ladder once already (`XLarge`
        was missing, so every delete leaked it), and a stray file nothing references
        is exactly the orphan class this pipeline keeps producing.
        """
        img = self.repo.get_image(image_id)
        if not img:
            return False

        imagen = IMAGEN_DIR / f"{img.owner_id}/{img.universe}"
        animated = ANIMATED_DIR / f"{img.owner_id}/{img.universe}"

        for directory in (imagen, animated):
            if not directory.exists():
                continue
            # `_*` is every tier (static, cutout, backup); `.*` is the loop, which
            # sits beside its still under the same base name.
            for pattern in (f"{img.filename}_*", f"{img.filename}.*"):
                for path in directory.glob(pattern):
                    if path.is_file():
                        path.unlink()

        # Tidy the directories the variants lived in, so a deleted image does not
        # leave an empty tree behind. `rmdir` refuses a non-empty directory, which
        # is exactly the guard wanted: another universe's or another image's files
        # keep it alive.
        for directory in (imagen, animated, imagen.parent, animated.parent):
            try:
                directory.rmdir()
            except OSError:
                pass

        return self.repo.delete_image(image_id)
