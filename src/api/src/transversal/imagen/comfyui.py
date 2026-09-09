"""ComfyUI HTTP client — submits workflows, polls for results, fetches outputs."""

from __future__ import annotations

import asyncio
import json
import os
import random
import time
from pathlib import Path
from typing import Optional
from urllib import request
from urllib.error import URLError

import aiohttp


COMFYUI_URL = os.getenv("COMFYUI_URL", "http://imagen:8188")
LORA_SERVER_URL = os.getenv("LORA_SERVER_URL", "http://imagen:8191")


# ── Synchronous helpers (for simple fire-and-forget) ──

def queue_prompt_sync(prompt: dict) -> str | None:
    """Submit a prompt to ComfyUI synchronously. Returns prompt_id."""
    try:
        data = json.dumps({"prompt": prompt}).encode("utf-8")
        req = request.Request(
            f"{COMFYUI_URL}/prompt", data=data,
            headers={"Content-Type": "application/json"},
        )
        resp = request.urlopen(req)
        result = json.loads(resp.read())
        return result.get("prompt_id")
    except URLError as e:
        raise RuntimeError(f"ComfyUI connection failed: {e}")


# ── Async client ──

class ComfyUIClient:
    """Async client for ComfyUI's REST API.

    Usage:
        client = ComfyUIClient()
        prompt_id = await client.submit_workflow(workflow_json)
        result = await client.wait_for_result(prompt_id)
        image_data = await client.get_image(result["filename"])
    """

    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or COMFYUI_URL).rstrip("/")

    async def submit_workflow(self, workflow: dict) -> str:
        """Submit a workflow JSON and return the prompt_id."""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/prompt",
                json={"prompt": workflow},
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(f"ComfyUI returned {resp.status}: {body}")
                data = await resp.json()
                prompt_id = data.get("prompt_id")
                if not prompt_id:
                    raise RuntimeError(f"No prompt_id in response: {data}")
                return prompt_id

    async def get_status(self, prompt_id: str) -> dict:
        """Check generation status. Returns full history entry if complete."""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.base_url}/history/{prompt_id}") as resp:
                if resp.status != 200:
                    return {"complete": False}
                data = await resp.json()
                return data.get(prompt_id, {"complete": False})

    async def wait_for_result(
        self, prompt_id: str, timeout_secs: int = 300, poll_interval: float = 2.0
    ) -> dict:
        """Poll until generation completes or timeout. Returns result info.

        Result dict keys: filename, subfolder, type, output_path
        """
        deadline = time.monotonic() + timeout_secs
        while time.monotonic() < deadline:
            status = await self.get_status(prompt_id)
            if not status:
                await asyncio.sleep(poll_interval)
                continue

            outputs = status.get("outputs", {})
            best_media = None
            best_node_id = None
            for node_id, node_output in outputs.items():
                # Some nodes (VHS_VideoCombine) report under "gifs" not "images"
                media = node_output.get("images", []) or node_output.get("gifs", [])
                if not media:
                    continue
                filename = media[0]["filename"]
                # Prefer animated/video outputs (webm, webp, gif) over static
                if filename.endswith((".webm", ".webp", ".gif", ".png")):
                    return {
                        "filename": filename,
                        "subfolder": media[0].get("subfolder", ""),
                        "type": media[0].get("type", "output"),
                        "node_id": node_id,
                    }
                best_media = media
                best_node_id = node_id
            if best_media:
                return {
                    "filename": best_media[0]["filename"],
                    "subfolder": best_media[0].get("subfolder", ""),
                    "type": best_media[0].get("type", "output"),
                    "node_id": best_node_id,
                }
            # Fallback: some nodes (WAS Image Save) report empty images
            # but the prompt is complete — signal completion so caller can
            # find the file by its known output path
            if outputs:
                return {
                    "filename": "",
                    "subfolder": "",
                    "type": "output",
                    "node_id": "",
                    "completed": True,
                }
            await asyncio.sleep(poll_interval)

        raise TimeoutError(f"ComfyUI generation timed out after {timeout_secs}s (prompt_id={prompt_id})")

    async def wait_for_result_images(
        self, prompt_id: str, timeout_secs: int = 300, poll_interval: float = 2.0
    ) -> list[dict]:
        """Poll until completion; return ALL output images of the run.

        Used for frame sequences (e.g. SaveImage writing a batch of frames as
        numbered PNGs). Each entry has ``filename``/``subfolder``/``type``.
        """
        deadline = time.monotonic() + timeout_secs
        while time.monotonic() < deadline:
            status = await self.get_status(prompt_id)
            if not status:
                await asyncio.sleep(poll_interval)
                continue

            outputs = status.get("outputs", {})
            best: list[dict] = []
            for node_output in outputs.values():
                media = node_output.get("images", []) or node_output.get("gifs", [])
                if len(media) > len(best):
                    best = media
            if best:
                return best
            # Prompt complete but no media reported (unlikely for SaveImage)
            if outputs:
                return []
            await asyncio.sleep(poll_interval)

        raise TimeoutError(f"ComfyUI generation timed out after {timeout_secs}s (prompt_id={prompt_id})")

    async def get_image(
        self, filename: str, subfolder: str = "", image_type: str = "output"
    ) -> bytes:
        """Download a generated image."""
        params = f"filename={filename}"
        if subfolder:
            params += f"&subfolder={subfolder}"
        if image_type:
            params += f"&type={image_type}"

        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.base_url}/view?{params}") as resp:
                if resp.status != 200:
                    raise RuntimeError(f"Failed to fetch image: {resp.status}")
                return await resp.read()

    async def interrupt(self) -> None:
        """Cancel the current job."""
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.base_url}/interrupt") as resp:
                if resp.status != 200:
                    raise RuntimeError(f"Failed to interrupt: {resp.status}")

    async def upload_image(self, image_data: bytes, filename: str) -> str:
        """Upload a file to ComfyUI's input directory. Returns the stored filename.

        Works for images and videos (VHS_LoadVideo reads videos from the same
        input dir); content-type is inferred from the filename extension.
        """
        if filename.endswith((".webm",)):
            content_type = "video/webm"
        elif filename.endswith((".mp4",)):
            content_type = "video/mp4"
        elif filename.endswith((".webp",)):
            content_type = "image/webp"
        else:
            content_type = "image/png"
        form = aiohttp.FormData()
        form.add_field("image", image_data, filename=filename, content_type=content_type)
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.base_url}/upload/image", data=form) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(f"Failed to upload image: {resp.status} — {body}")
                data = await resp.json()
                return data.get("name", filename)

    async def list_loras(self) -> list[dict]:
        """List available Flux LoRA files from the imagEN container.

        Returns [{"name": "FantasyPortraits-v3", "path": "FantasyPortraits-v3.safetensors"}, ...]
        """
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{LORA_SERVER_URL}/loras") as resp:
                if resp.status != 200:
                    return []
                return await resp.json()

    async def free_memory(self) -> None:
        """POST /free to unload models from VRAM."""
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.base_url}/free", json={}) as resp:
                pass  # best-effort


# ── Workflow injection helpers ──

def inject_flux_params(
    workflow: dict,
    prompt: str,
    negative: str,
    width: int,
    height: int,
    steps: int,
    seed: int | None = None,
    lora1: str = "",
    lora1_weight: float = 0.0,
    lora2: str = "",
    lora2_weight: float = 0.0,
    output_path: str = "/media/imagens",
) -> dict:
    """Inject prompt parameters into a Flux workflow JSON template.

    This assumes the workflow structure from the old imagegen.py template:
    - Node 3 (XlabsSampler): steps, noise_seed
    - Node 24 (CR SDXL Aspect Ratio): width, height
    - Node 25 (Text Multiline positive): text
    - Node 26 (Text Multiline negative): text
    - Node 28 (Image Save): output_path, filename_prefix
    - Node 29 (LoraLoader lora1): lora_name, strength_model
    - Node 30 (LoraLoader lora2): lora_name, strength_model
    """
    if seed is None:
        seed = random.randint(0, 2**32 - 1)

    wf = json.loads(json.dumps(workflow))  # deep copy

    wf["3"]["inputs"]["steps"] = steps
    wf["3"]["inputs"]["noise_seed"] = seed

    wf["24"]["inputs"]["width"] = width
    wf["24"]["inputs"]["height"] = height

    wf["25"]["inputs"]["text"] = prompt
    wf["26"]["inputs"]["text"] = negative

    wf["28"]["inputs"]["output_path"] = output_path
    wf["28"]["inputs"]["filename_prefix"] = "ComfyUI"

    if lora1:
        wf["29"]["inputs"]["lora_name"] = f"flux/{lora1}.safetensors"
        wf["29"]["inputs"]["strength_model"] = lora1_weight
    else:
        wf["29"]["inputs"]["strength_model"] = 0.0

    if lora2:
        wf["30"]["inputs"]["lora_name"] = f"flux/{lora2}.safetensors"
        wf["30"]["inputs"]["strength_model"] = lora2_weight
    else:
        wf["30"]["inputs"]["strength_model"] = 0.0

    return wf


def inject_wan_params(
    workflow: dict,
    motion_prompt: str,
    negative: str,
    input_image: str,  # filename in ComfyUI input dir
    width: int,
    height: int,
    steps: int,
    seed: int | None = None,
    duration_seconds: float = 3.0,
    lora_strength: float = 0.95,
    lora_activation_word: str = "",
    framerate: int = 24,
) -> dict:
    """Inject parameters into the WhiteRabbitInterpLoop WanVideo workflow.

    Key nodes (from WhiteRabbitInterpLoop1.json):
    - Node 58 (LoadImage): image filename
    - Node 99 (Positive Prompt): motion description text
    - Node 110 (Negative Prompt): negative prompt
    - Node 118 (Duration Hint): seconds
    - Node 168 (Working Size): longest side
    - Node 170 (LoRA Activation Word): trigger
    - Node 176 (Sample Framerate): target
    - Node 217 (Steps): steps
    - Node 512 (Seed): seed
    - Node 562 (LoRA Strength): strength
    """
    if seed is None:
        seed = random.randint(0, 2**32 - 1)

    wf = json.loads(json.dumps(workflow))  # deep copy

    wf["58"]["inputs"]["image"] = input_image

    wf["99"]["inputs"]["value"] = motion_prompt
    wf["110"]["inputs"]["value"] = negative

    wf["118"]["inputs"]["Xi"] = duration_seconds
    wf["118"]["inputs"]["Xf"] = duration_seconds

    wf["168"]["inputs"]["Xi"] = max(width, height)
    wf["168"]["inputs"]["Xf"] = max(width, height)

    wf["170"]["inputs"]["value"] = lora_activation_word

    wf["176"]["inputs"]["Xi"] = framerate
    wf["176"]["inputs"]["Xf"] = framerate

    wf["217"]["inputs"]["Xi"] = steps
    wf["217"]["inputs"]["Xf"] = steps

    wf["512"]["inputs"]["seed"] = seed

    wf["562"]["inputs"]["Xi"] = lora_strength
    wf["562"]["inputs"]["Xf"] = lora_strength

    return wf


def inject_bg_removal_params(
    workflow: dict,
    input_image: str,  # filename already uploaded to ComfyUI's input dir
    filename_prefix: str = "bgremoved",
) -> dict:
    """Inject the input filename into the BiRefNet background-removal workflow.

    Node 1 (LoadImage): image filename
    Node 6 (SaveImage): filename_prefix
    """
    wf = json.loads(json.dumps(workflow))  # deep copy

    wf["1"]["inputs"]["image"] = input_image
    wf["6"]["inputs"]["filename_prefix"] = filename_prefix

    return wf


def inject_bg_removal_video_params(
    workflow: dict,
    input_video: str,  # filename already uploaded to ComfyUI's input dir
    filename_prefix: str = "bgremoved_video",
) -> dict:
    """Inject the video filename into the per-frame BiRefNet matting workflow.

    Node 1 (VHS_LoadVideo): video filename
    Node 6 (SaveImage): filename_prefix (PNG frame sequence)
    """
    wf = json.loads(json.dumps(workflow))  # deep copy

    wf["1"]["inputs"]["video"] = input_video
    wf["6"]["inputs"]["filename_prefix"] = filename_prefix

    return wf
