"""Bulk variant of the upscale pass: every `background` master below the ceiling.

**The primary way to upscale is the button** in the image viewer ([[B207]]) — it
spends the GPU only on pictures that need it, from the surface where you are
already looking at the picture, and it is the same code path as this script.
This exists for when a whole-role sweep is wanted.

The pipeline itself lives in `ImagenOrchestrator.run_upscale`: the model, the cap,
the `_PreUpscale` backup, the tier re-render and the dimension update are all
there. This only decides *which* images and in what order, so there is exactly one
implementation of the upscale — the two copies of the variant writer are the
cautionary tale.

It drives ComfyUI through that method, which takes the orchestrator's own
`_gpu_lock`, but that lock is per-process and this is a separate process from the
API. So before each image it also waits while ComfyUI's queue holds anyone else's
work: otherwise a sweep and a user's generation fight over the one 4090.

Idempotent — the orchestrator refuses a master already at the cap, and that
refusal is counted, not printed as a failure.

Usage::

    docker compose exec api python -m transversal.upscale_backgrounds --limit 5 --apply
    docker compose exec api python -m transversal.upscale_backgrounds --apply
"""

from __future__ import annotations

import asyncio
import sys
import time

from transversal.db.arango import get_db
from transversal.imagen.comfyui import ComfyUIClient
from transversal.imagen.models import GenerationType
from transversal.imagen.orchestrator import (
    UPSCALE_MASTER_CAP,
    UPSCALE_MODEL,
    ImagenOrchestrator,
)
from transversal.services.media_utils import ROLE_VARIANT


async def _wait_for_idle_gpu(client: ComfyUIClient, poll: float = 10.0) -> None:
    """Yield while ComfyUI has anyone else's work queued — see the docstring."""
    import aiohttp

    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{client.base_url}/queue") as resp:
                    if resp.status != 200:
                        return
                    q = await resp.json()
        except Exception:
            return  # can't tell — better to proceed than to hang the sweep
        busy = len(q.get("queue_running") or []) or len(q.get("queue_pending") or [])
        if not busy:
            return
        print(f"    (GPU busy with {busy} job(s) — waiting)", flush=True)
        await asyncio.sleep(poll)


async def main(apply: bool = False, limit: int = 0) -> int:
    db = get_db()
    rows = [
        d for d in db.aql.execute('FOR d IN images FILTER "background" IN d.roles RETURN d')
        if (d.get("image_type") or "") != "animated"
    ]
    print(f"background images: {len(rows)}  (model {UPSCALE_MODEL}, ceiling {UPSCALE_MASTER_CAP})")

    client = ComfyUIClient()
    orchestrator = ImagenOrchestrator(comfyui=client)
    done = at_cap = failed = 0
    started = time.time()

    for doc in sorted(rows, key=lambda d: d.get("_key") or ""):
        if limit and done >= limit:
            break
        if not apply:
            print(f"WOULD upscale {doc.get('filename')} ({doc.get('owner_id')})")
            done += 1
            continue

        await _wait_for_idle_gpu(client)
        t0 = time.time()
        try:
            image = await orchestrator.run_upscale(doc["_key"])
        except ValueError as exc:
            # Expected: already at the ceiling, or a loop.
            at_cap += 1
            print(f"  skip {doc.get('filename')}: {exc}", flush=True)
            continue
        except Exception as exc:
            failed += 1
            print(f"  FAILED {doc.get('filename')}: {type(exc).__name__}: {exc}", flush=True)
            continue

        done += 1
        print(f"  [{done}] {image.filename} -> {image.width}x{image.height} "
              f"in {time.time() - t0:.1f}s", flush=True)

    print()
    print("=== BACKGROUND UPSCALE (bulk) ===")
    print(f"apply={apply}")
    print(f"  upscaled:           {done}")
    print(f"  already at ceiling: {at_cap}")
    print(f"  failed:             {failed}")
    if apply and done:
        total = time.time() - started
        print(f"  {total/60:.1f} min, {total/done:.1f}s per image")
    if not apply:
        print("  (dry run — nothing written; re-run with --apply)")
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    limit = int(args[args.index("--limit") + 1]) if "--limit" in args else 0
    sys.exit(asyncio.run(main(apply="--apply" in args, limit=limit)))
