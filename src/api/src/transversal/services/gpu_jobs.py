"""Whether this deployment may spend the GPU (B88).

The GPU is in the machine that serves the app, and since 2026-10-16 that app is on
the public internet. A public surface that can start Flux, a video loop, a matte or
an upscale spends the owner's own graphics card, so `GPU_JOBS` is the switch:

- **off** refuses the GPU endpoints *and* stops uploads from queuing an automatic
  matte, so nothing reaches ComfyUI at all — an upload must not be the back door.
- **unset means on**, which keeps the single-user default and makes disabling the
  deliberate act rather than something that happens by forgetting a variable.

Reading is never affected: the gallery, the images and the media were never the GPU.
"""

from __future__ import annotations

import os

#: The variable, named in `docker-compose.yaml` because compose only passes what a
#: service lists — the trap this repo has already been bitten by twice.
ENV = "GPU_JOBS"

_OFF = {"0", "off", "false", "no", "disabled", "none"}

#: What a refused request says. One string, so the API and its tests cannot drift.
REFUSAL = (
    "image generation is disabled on this deployment: it spends the host's GPU, "
    "which is reserved for the owner's own use"
)


def enabled() -> bool:
    """May this deployment spend the GPU?"""
    return (os.getenv(ENV, "") or "").strip().lower() not in _OFF
