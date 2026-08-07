"""Ollama HTTP client — calls gemma4:12b for computer vision tasks.

Used in the animate pipeline: after generating a static image,
gemma4:12b describes the motion that should occur in the video loop.
"""

from __future__ import annotations

import base64
import os

import aiohttp


OLLAMA_URL = os.getenv("OLLAMA_URL", "http://imagen:11434")
VISION_MODEL = os.getenv("OLLAMA_VISION_MODEL", "gemma4:12b")

# System prompt template — loaded from vision_prompt.txt at startup
_VISION_SYSTEM_PROMPT: str | None = None


def _load_vision_prompt() -> str:
    """Load the vision prompt template from the imagen container filesystem."""
    global _VISION_SYSTEM_PROMPT
    if _VISION_SYSTEM_PROMPT is not None:
        return _VISION_SYSTEM_PROMPT

    paths = [
        "/app/imagen/vision_prompt.txt",
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "..", "src", "imagen", "vision_prompt.txt"),
    ]
    for p in paths:
        if os.path.exists(p):
            with open(p) as f:
                _VISION_SYSTEM_PROMPT = f.read().strip()
            return _VISION_SYSTEM_PROMPT

    # Fallback if file not found
    _VISION_SYSTEM_PROMPT = (
        "Analyze the content of this image and write a concise, single-paragraph "
        "description of your predictions around what movement takes place throughout "
        "the video sequence that follows. Use present tense. Be specific and decisive. "
        "Describe how each detail in the scene moves. One paragraph only."
    )
    return _VISION_SYSTEM_PROMPT


class OllamaClient:
    """Async client for Ollama's /api/generate endpoint."""

    def __init__(self, base_url: str | None = None, model: str | None = None):
        self.base_url = (base_url or OLLAMA_URL).rstrip("/")
        self.model = model or VISION_MODEL

    async def describe_motion(
        self,
        image_data: bytes,
        motion_hint: str = "",
        image_mime: str = "image/png",
        timeout_secs: int = 120,
    ) -> str:
        """Send an image to gemma3:12b and get a motion description back.

        Uses the vision_prompt.txt as the system prompt.
        If motion_hint is provided, it's prepended to the user prompt.
        """
        system_prompt = _load_vision_prompt()
        user_prompt = "Describe the motion in this image."
        if motion_hint:
            user_prompt = f"Hint: {motion_hint}\n\n{user_prompt}"
        # Ensure image is PNG — ollama/gemma3 may not decode webp
        try:
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(image_data))
            if img.format != "PNG":
                buf = io.BytesIO()
                img.convert("RGB").save(buf, format="PNG")
                image_data = buf.getvalue()
        except Exception:
            pass  # fall through, try raw bytes
        image_b64 = base64.b64encode(image_data).decode("utf-8")

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt, "images": [image_b64]},
            ],
            "stream": False,
            "options": {
                "temperature": 0.7,
                "num_predict": 1024,
            },
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=timeout_secs),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(f"Ollama returned {resp.status}: {body}")
                data = await resp.json()
                response_text = data.get("message", {}).get("content", "")
                if not response_text:
                    raise RuntimeError(f"Empty response from Ollama: {data}")
                return self._clean_response(response_text)

    async def unload_model(self) -> None:
        """Unload the model from VRAM by setting keep_alive to 0."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/generate",
                    json={"model": self.model, "keep_alive": 0},
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    pass  # best-effort
        except Exception:
            pass

    async def health_check(self) -> bool:
        """Check if Ollama is running and the model is available."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/api/tags",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status != 200:
                        return False
                    data = await resp.json()
                    models = [m["name"] for m in data.get("models", [])]
                    return self.model in models or any(
                        m.startswith(self.model.split(":")[0]) for m in models
                    )
        except Exception:
            return False

    @staticmethod
    def _clean_response(text: str) -> str:
        """Clean gemma output — remove quotes, prefixes, trailing artifacts."""
        text = text.strip().strip('"').strip("'")
        # Remove common prefixes
        prefixes = [
            "The image sequence depicts",
            "The image depicts",
            "The video shows",
            "The video sequence shows",
            "This image shows",
            "The scene shows",
        ]
        lower = text.lower()
        for prefix in prefixes:
            if lower.startswith(prefix.lower()):
                text = text[len(prefix):].strip(" :,")
                break
        return text.strip()
