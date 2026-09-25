"""Upscale the **background** masters with an ESRGAN model ([[B207]]).

Delivery was fixed by the variant ladder; this is the other half — putting more
detail into the masters themselves. Scope is the `background` role only: those are
the images drawn full-bleed at viewport size, and the ones big screens expose.
Portraits and map dots render small and gain little.

**Why the master is capped at 2048.** The model is 4×, so an 832×1216 master comes
back 3328×4864 (16 MP). Storing that would cost ~1 MB per image and slow every
tier re-render, for pixels nothing ever serves — `XLarge` (2048) is the largest
tier that exists. So the 4× result is resampled **down** to 2048, which is a
better 2048 than upscaling straight to it: there is more information to resample
from.

**The pre-upscale master is kept** as `{filename}_PreUpscale.{ext}`. Upscaling is
irreversible and this is the only copy of the art; the backup is ~150 KB per
image and can be deleted whenever the result is trusted.

Idempotent: an image whose master is already at the cap is skipped, so a re-run
costs nothing. `--force` re-does them anyway (e.g. to try another model).

Usage::

    docker compose exec api python -m transversal.upscale_backgrounds --limit 3 --apply
    docker compose exec api python -m transversal.upscale_backgrounds --apply
"""

from __future__ import annotations

import asyncio
import io
import sys
import time
from pathlib import Path

from PIL import Image

from transversal.db.arango import IMAGES, get_db
from transversal.imagen.comfyui import ComfyUIClient, inject_upscale_params
from transversal.imagen.orchestrator import _load_workflow, _safe_filename
from transversal.services.media_utils import ROLE_VARIANT, save_image_variants

IMAGEN_DIR = Path("/app/media/imagen")

#: `XLarge` is the largest tier that exists, so nothing bigger is worth storing.
MASTER_CAP = 2048

#: Chosen by measuring both against real art, not by reputation — see
#: `inject_upscale_params`. The alternatives on disk are RealESRGAN_x4plus
#: (smooth, and it smears illustrated line work) and RealESRGAN_x4plus_anime_6B.
MODEL = "4x-UltraSharp.pth"


def _cap(img: Image.Image, long_side: int = MASTER_CAP) -> Image.Image:
    w, h = img.size
    if max(w, h) <= long_side:
        return img
    s = long_side / max(w, h)
    return img.resize((max(1, round(w * s)), max(1, round(h * s))), Image.LANCZOS)


async def _wait_for_idle_gpu(client: ComfyUIClient, poll: float = 10.0) -> None:
    """Yield while ComfyUI has anyone else's work queued.

    This script drives ComfyUI directly, so it does NOT hold the orchestrator's
    `_gpu_lock` — that lock is per-process and this is a separate one. A batch of
    849 upscales would otherwise sit on the same 4090 as a user's generation and
    two jobs would fight for VRAM. ComfyUI's own queue is the honest signal, and
    it covers every submitter rather than just this app's.
    """
    import aiohttp

    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{client.base_url}/queue") as resp:
                    if resp.status != 200:
                        return
                    q = await resp.json()
        except Exception:
            return  # can't tell — better to proceed than to hang the batch
        busy = len(q.get("queue_running") or []) or len(q.get("queue_pending") or [])
        if not busy:
            return
        print(f"    (GPU busy with {busy} job(s) — waiting)", flush=True)
        await asyncio.sleep(poll)


async def _upscale(client: ComfyUIClient, data: bytes, tag: str) -> bytes:
    uploaded = await client.upload_image(data, f"upscale_{tag}.png")
    wf = inject_upscale_params(_load_workflow("upscale.json"), uploaded, MODEL, f"upscaled_{tag}")
    prompt_id = await client.submit_workflow(wf)
    result = await client.wait_for_result(prompt_id, timeout_secs=1800)
    if not result.get("filename"):
        raise RuntimeError(f"upscale produced no output: {result}")
    return await client.get_image(
        result["filename"], result.get("subfolder", ""), result.get("type", "output")
    )


async def main(apply: bool = False, limit: int = 0, force: bool = False) -> int:
    db = get_db()
    rows = [
        d for d in db.aql.execute('FOR d IN images FILTER "background" IN d.roles RETURN d')
        if (d.get("image_type") or "") != "animated"
    ]
    print(f"background images: {len(rows)}  (model {MODEL}, cap {MASTER_CAP})")

    client = ComfyUIClient()
    done = skipped = missing = failed = 0
    started = time.time()

    for doc in sorted(rows, key=lambda d: d.get("_key") or ""):
        owner, universe = doc.get("owner_id") or "", doc.get("universe") or ""
        filename, ext = doc.get("filename") or "", doc.get("extension") or "webp"
        out_dir = IMAGEN_DIR / owner / universe
        original = out_dir / f"{filename}_Original.{ext}"
        if not (filename and original.exists()):
            missing += 1
            continue

        with Image.open(original) as im:
            before = im.size
            master_long = max(before)
        if master_long >= MASTER_CAP and not force:
            skipped += 1
            continue
        if limit and done >= limit:
            break
        if not apply:
            print(f"WOULD upscale {filename} ({owner}) {before[0]}x{before[1]}")
            done += 1
            continue

        t0 = time.time()
        try:
            await _wait_for_idle_gpu(client)
            raw = await _upscale(client, original.read_bytes(), _safe_filename(filename)[:40])
            await client.free_memory()
            up = _cap(Image.open(io.BytesIO(raw)))
            backup = out_dir / f"{filename}_PreUpscale.{ext}"
            if not backup.exists():
                backup.write_bytes(original.read_bytes())
            buf = io.BytesIO()
            up.save(buf, format="WEBP", quality=95)  # master quality; tiers re-encode at 85
            original.write_bytes(buf.getvalue())
            save_image_variants(buf.getvalue(), out_dir, filename)
        except Exception as exc:  # one bad image must not stop the batch
            failed += 1
            print(f"  FAILED {filename}: {type(exc).__name__}: {exc}", flush=True)
            continue

        done += 1
        secs = time.time() - t0
        elapsed = time.time() - started
        print(f"  [{done}] {before[0]}x{before[1]} -> {up.size[0]}x{up.size[1]} "
              f"in {secs:.1f}s  (elapsed {elapsed/60:.1f}m)", flush=True)

    print()
    print("=== BACKGROUND UPSCALE ===")
    print(f"apply={apply}")
    print(f"  upscaled:            {done}")
    print(f"  already at the cap:  {skipped}")
    print(f"  missing master:      {missing}")
    print(f"  failed:              {failed}")
    if done and apply:
        total = time.time() - started
        print(f"  {total/60:.1f} min total, {total/max(done,1):.1f}s per image")
        remaining = len(rows) - done - skipped - missing
        if remaining > 0:
            print(f"  ~{remaining * total / max(done,1) / 60:.0f} min for the remaining {remaining}")
    if not apply:
        print("  (dry run — nothing written; re-run with --apply)")
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    limit = 0
    if "--limit" in args:
        limit = int(args[args.index("--limit") + 1])
    sys.exit(asyncio.run(main(apply="--apply" in args, limit=limit, force="--force" in args)))
