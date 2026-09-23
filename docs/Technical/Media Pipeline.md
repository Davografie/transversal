---
title: Media Pipeline
date: 2026-09-06
last-updated: 2026-09-11
tags:
  - transversal
  - technical
  - media
  - images
  - generation
aliases:
  - Media
  - Media Pipeline
  - Image Generation
  - Role Tags
status: canonical
---

# Media Pipeline

> [!note] Scope
> This document describes the **media implementation** — how images and video
> are stored, tagged, resolved, generated, and rendered. It documents the code,
> not a snapshot of live data. The September 2026 [[Data Model]] migration
> reshaped the database and media files; treat the live `media/` tree and
> ArangoDB contents as disposable, and this document (plus the source) as the
> source of truth for how media *works*.

## Overview

Media is organised around two concepts borrowed from the [[Projections and
Transversal]] model:

- **Entity = soul** — the persistent identity.
- **Projection = body** — one of possibly several per-universe incarnations.

An image belongs to **a projection (body)** via `EntityImage.projection_id`.
When `projection_id` is empty, the image is **entity-level** — the "soul
default" that any body falls back to when it has no image of its own for a
given role. One entity can have multiple projections even in the same universe
(keys are `entity:universe`, `entity:universe:2`, …).

Every image is tagged with one or more **canonical roles**:

| Role | Meaning | Static variant |
| --- | --- | --- |
| `background` | location / scene backdrop | `Large` |
| `sheet` | character-sheet portrait (small render) | `Small` |
| `navdot` | map dot / occupant marker | `Large` |

## Data model

`ImageType` (enum): `uploaded` · `imagen` · `animated` · `cutout`.

`EntityImage` (`entity_images` collection) — one record per image file:

- `id` — uuid (`_key`).
- `entity_id` — owning entity (soul).
- `projection_id` — owning body; empty = entity-level default.
- `universe` — the universe the image was generated/uploaded in.
- `image_type` — see above.
- `roles` — subset of `background` / `sheet` / `navdot`.
- `transparent` — the file has a transparent background (an alpha channel with
  non-opaque pixels). Detected at ingestion, never hand-set. See
  [[#Transparency]].
- `prompt`, `negative_prompt`, `loras` — generation provenance.
- `width`, `height`, `seed`, `steps` — generation params.
- `filename` — base name without variant suffix or extension.
- `extension` — file extension (e.g. `webp`, `webm`, `mp4`).
- `created_at` — ISO 8601.

## Transparency

`EntityImage.transparent` marks images whose background has been cut out. It is
**orthogonal to `roles`** — an image can be both `navdot`-tagged and transparent
— and it is what lets the UI render a cutout differently from a full-bleed
image (floating portrait instead of a cropped circle).

Detection is `has_transparency(image_bytes)` in `services/media_utils.py`: true
when the decoded image has an alpha channel with any pixel below full opacity.
It is applied at every ingestion point — `POST /media/upload`, `run_imagen`,
`run_remove_background`, and `migrate_media` — so the flag is never out of sync
with the file.

Existing rows are backfilled by a one-off, idempotent script (dry-run by
default):

```bash
docker compose exec api python -m transversal.backfill_transparency          # report
docker compose exec api python -m transversal.backfill_transparency --apply  # write
```

Animated images are skipped (video has no alpha to detect); transparent loops
get the flag from the matting stage instead (see [[#Transparent animations]]).

## Storage layout

Static images are saved as WebP in several size variants:

```
media/imagen/{entity_id}/{universe}/{filename}_{variant}.{ext}
    variant ∈ Original · Large (≤1024) · Small (≤240) · Mini (≤48)
```

Alpha survives the variant pass: sources with an alpha channel are converted
RGBA→RGBA, so cutouts stay transparent in every variant.

> [!warning] Variant quirk
> For **portrait** sources the `Large` variant is derived on the width axis, so
> its long side collapses to the source's *short* side (478×700 → 326×478).
> Landscape sources scale as expected. Treat `Original` as the native copy and
> `Large` as an upper bound, not a guarantee.

Animated loops live separately:

```
media/animated/{entity_id}/{universe}/{filename}.{ext}   # .webm / .mp4 / .webp
```

Transparent loops are **VP9-alpha WebM** (`yuva420p`) written by the matting
stage — see [[#Transparent animations]].

A legacy flat-file path `media/{flat_filename}` exists for backward
compatibility on upload, but the canonical form is the per-entity directory
above.

## Resolution

The single resolution primitive is `EntityRepository.resolve_role_image(entity_id,
role, projection_id, variant)`. Order of precedence:

1. The projection's own image carrying `role` (newest first).
2. Entity-level image carrying `role` whose `universe` matches the projection's
   **current**, then **origin**, universe.
3. Any entity-level image carrying `role`.

With no `projection_id`, only entity-level images are considered.

`resolve_role_image_entry(entity_id, role, projection_id)` runs the same
resolution but returns the `EntityImage` record instead of a URL;
`resolve_role_image` is a thin URL wrapper over it. Reach for the entry form
whenever you need image metadata — `transparent` being the reason it exists.

### GraphQL surface

- `Entity.image(role, projectionId?)` — the canonical resolver. When
  `projectionId` is omitted it resolves through the entity's `current_projection`
  (active body), falling back to entity level. This is what most callers use.
- `Entity.background_image` — entity-level `background` (Large); falls back to
  the legacy denormalized `_background_image` string.
- `Entity.sheet_portrait` — entity-level `sheet` (Small); falls back to
  `background_image`.
- `Projection.sheet_image` — that body's `sheet` (Small), with entity fallback.
- `Entity.sheet_portrait_transparent` / `Projection.sheet_image_transparent` —
  booleans mirroring the sheet resolution above, so the sheet can render a
  cutout portrait differently. The legacy denormalized background fallback has
  no alpha information and reports `false` (opaque).

There is deliberately **no** fallback to the legacy `background_image` field
from the role-based `image()` resolver — callers that want a role image use the
role tags.

### Batch resolution

`_role_urls` / `_navdot_urls` / `get_role_images` / `get_navdot_images` resolve
many entities at once, each through its active projection. `get_navdot_images`
is used by the location navigate endpoint for occupants, children, transversal
destinations, and the parent.

`get_navdot_transparency(entity_ids)` is the same batch resolution returning
`{entity_id: bool}` (whether the resolved navdot image is transparent), and the
navigate endpoint surfaces it as `image_transparent` on occupants and
`navdot_image_transparent` on children / transversal destinations / the parent.
Those two flags are what the map uses to float a cutout navdot instead of
cropping it into a filled dot.

## REST API

- `POST /media/upload` — upload a file; convert to WebP, save variants, register
  an `EntityImage`, auto-select roles when it is the sole entity-level image.
- `POST /imagen/{entity_id}` — trigger async static generation (optional
  `projection_id` in body → per-projection generation).
- `POST /animate/{entity_id}` — trigger async video-loop generation. Body may
  carry `image_id` to animate an existing image; when that image is
  `transparent`, the finished loop is matted (see below).
- `POST /remove-background/{entity_id}` — body `{image_id}`; async, static
  images only. Produces a new transparent cutout image (see below).
- `POST /imagen/{entity_id}/cancel` — interrupt the active job.
- `GET /imagen/jobs` — active generation/animation jobs + queue position.
- `GET /imagen/loras` — available Flux LoRAs.
- `GET /entities/images?role=&ids=` — batch role-image resolution (used by the
  peers bar to avoid loading images for the whole entity list).
- `GET /imagen/{entity_id}` — list images (with `projection_id`, `roles`,
  `transparent`, `path_large`, `path_animated`).
- `PATCH /imagen/{image_id}` — update `roles`, `universe`, and/or
  `projection_id` (ownership reassignment).
- `DELETE /imagen/{image_id}` — delete an image and its variants.

All three generation endpoints return `202` immediately and publish progress on
the `imagen_progress` SSE event. Statuses are `prompting` → `generating` →
`saving` → `complete`/`failed`, plus `vision` and `animating` for animate and
`matting` for transparent animations; background removal reports under
`generating` / `saving`.

## Generation pipeline

`ImagenOrchestrator` runs the async jobs; `prompt_builder` assembles prompts.

### Prompt building

`build_imagen_prompt(entity, universe, repository, projection_id)`:

- Starts from a per-entity-type base prompt (character/GMC portrait, asset
  concept, faction emblem, location backdrop).
- Enriches from trait settings:
  - `appearance` trait → weighted appearance clause. The clause carries the
    setting's `statement` **and** its freeform `notes` (both run through
    `clean_text`), joined into one `:1.4` clause — the appearance description
    lives in `notes` far more often than in `statement` (of the live appearance
    settings, 438/455 carry notes and 434 have no statement at all).
  - `LoRA*` traits → LoRA list.
  - `negative imagen` / `positive imagen` traits → negative/positive additions.
  - generic traits → `(trait is statement:rating_weight)` clauses.
- Adds universe style guidance, the universe's per-entity-type LoRA config, and
  the universe's free-text **prompt steering** sentence
  (`Entity.prompt_steering`, authored per universe in the GM LoRA panel and
  appended last as `(sentence:0.9)` so it reads as the final style direction).

For a **projection** generation, trait selection is scoped by
`get_prompt_traitsettings(entity_id, universes, projection_id)`: entity traits
(`from_type == 'entity'`) plus that projection's morph traits
(`from_type == 'projection'` and matching `projection_id`). Entity-level
generation uses entity traits only.

### Imagen (static)

`run_imagen` → ComfyUI Flux → `_save_image_variants` (Original/Large/Small/Mini
WebP) → `EntityImage`. If the result is the sole image for its owner, all three
roles are auto-selected.

### Remove background (static cutout)

`run_remove_background` turns an existing static image into a transparent
cutout. It is **non-destructive**: the source is untouched and the result is a
new `EntityImage` of type `cutout`, owned by the same entity *or projection* as
the source, with `transparent=true` and no role tags (tag it `navdot` /`sheet`
as needed).

Pipeline: read the source's `Large` variant → upload to ComfyUI →
`bg_remove.json` → BiRefNet → alpha composite → RGBA PNG →
`_save_image_variants` → record.

The workflow is `LoadImage → LoadBackgroundRemovalModel → RemoveBackground →
InvertMask → JoinImageWithAlpha → SaveImage`.

> [!warning] Two traps in that node graph
> **1. The model must be BiRefNet.** ComfyUI's built-in
> `LoadBackgroundRemovalModel` reads `models/background_removal/` and only
> loads BiRefNet checkpoints; a BEN2 file is rejected at run time with
> *"background model file is invalid and does not contain a valid background
> removal model"*. The installed model is `BiRefNet_HR.safetensors`; keep
> incompatible files out of that folder (an unusable file still shows up in the
> node's dropdown — rename it to `.disabled`).
> **2. `BiRefNet_HR` emits a *background* mask.** `RemoveBackground`'s output
> feeds `JoinImageWithAlpha` as alpha, so without `InvertMask` the composite
> keeps the background and punches the subject out into a silhouette.
> Verify the direction by probing the corners (should be transparent) and the
> subject (opaque).

### Animate (video)

`run_animate` produces a static Flux image (or reuses an existing one), runs it
through Ollama (gemma3 vision) to derive a motion description, then feeds that
to ComfyUI WanVideo. Output is the `.webm`/`.mp4` loop.

#### Transparent animations

WanVideo generates opaque RGB frames — it paints its own background — so alpha
cannot be carried through generation. When the **source image is
`transparent`**, the opaque loop is matted after generation instead:

1. `bg_remove_video.json` — `VHS_LoadVideo` (frames) → BiRefNet `RemoveBackground`
   over the whole frame batch → `InvertMask` → `JoinImageWithAlpha` → RGBA PNG
   frame sequence.
2. The orchestrator downloads the frames and applies a **3-frame temporal
   median to the alpha channel only** — BiRefNet has no temporal consistency, so
   edges flicker frame to frame without it.
3. `ffmpeg -c:v libvpx-vp9 -pix_fmt yuva420p -crf 32 -b:v 0` encodes the loop to
   **VP9-alpha WebM**. VP9/VP8-alpha WebM is the cross-browser alpha format;
   alpha **MP4** is HEVC-alpha and plays on Apple devices only, so it is not
   used here.

Requirements and gotchas:

- **`ffmpeg` must exist in the API image** (it runs in the orchestrator, not in
  the ComfyUI container). It is in `src/api/Dockerfile`.
- The stage runs inside the existing `_gpu_lock`; animations report a `matting`
  status between `animating` and `saving`. Budget ~30–60 s extra GPU for a 3 s
  loop (~72 frames).
- Per-frame BiRefNet is used for now; a temporal video-matting model
  (e.g. RMBG-2.0-video) is the upgrade path if edges wobble.
- The finished loop is stored as `.webm` with `transparent=true`.

> [!warning] `ffprobe` lies about these files
> `ffprobe` (and ffmpeg's own VP9 decoder) report the matted output as
> `yuv420p`, i.e. *without* alpha. That is a decode-side quirk, not a bad
> encode: the container carries `alpha_mode: 1` and the alpha plane is in the
> bitstream (visible as a byte-size delta against an opaque encode of the same
> frames). Verified in Chrome with a canvas alpha probe — the background is
> genuinely transparent. Don't "fix" the encode based on `ffprobe`.

## Role assignment & auto-select

Roles are **unique per (owner, role)**, where owner = `projection_id` when set,
else `entity_id`. Assigning a role strips it from sibling images with the same
owner.

Auto-select of all three roles happens whenever an image becomes the **sole**
image in its owner scope:

- **upload** — sole entity-level image.
- **generation** — sole image for the entity or projection.
- **drop** — dragging an image onto an empty entity/projection gallery.

## Frontend

- `MediaImage.vue` — unified renderer: `<video>` for `.webm`/`.mp4`, `<img>`
  otherwise. Accepts a known `src`, or `entity-id` + `role` to query.
- `composables/media.js` — `isVideoUrl` (`.webm`/`.mp4`) and `panAxis`
  (background panning direction).
- `composables/useEntityMedia.js` — resolves `Entity.image(role)` and applies
  the quality/cache resolution.
- `composables/useMediaQuality.js` — quality preference (`auto`/`low`/`high`
  in localStorage), Network Information API slow-connection detection, static
  variant rewriting, animated→static `_Small` fallback, and cache-aware
  resolution (prefer a cached original over a downgraded fetch).
- `gm/GmEntityEditPanel.vue` — entity gallery + per-projection galleries;
  drag between them reassigns ownership; per-projection [imagen] button.
- `gm/ImageViewer.vue` — role checkboxes (BG/Sheet/Nav), universe selector,
  animate, **Remove BG**, delete. Remove BG is offered for static images only
  (hidden for animated loops and for images that are already cutouts).

### Consuming `transparent`

The flag reaches renderers by whichever road that surface already uses:

- **Map navdots** — the location navigate payload (`image_transparent`,
  `navdot_image_transparent`).
- **Sheet portrait** — GraphQL (`Entity.sheetPortraitTransparent`,
  `Projection.sheetImageTransparent`).
- **Galleries / image viewer** — `transparent` on `GET /imagen/{entity_id}`.

The rendering treatment itself (floating cutout vs. cropped circle) lives with
the owning sessions: [[navigation]] for navdots, [[character-sheet]] for sheet
portraits.

## Upload & format handling

`ALLOWED_EXTENSIONS = png, jpg, jpeg, gif, webp, heic, heif`. HEIC/HEIF
(iOS camera photos) are decoded via `pillow-heif`, then converted to WebP. GIF —
and any other source Pillow reports as animated — passes through unchanged;
everything else is re-encoded to WebP. Size cap is 10 MB.

> [!warning] `.svg` is not accepted (SEC-4)
> SVG used to be allowed and passed through un-re-encoded. It is served from the
> app's own origin and can carry script — i.e. stored XSS — so the extension is
> now rejected at upload. The removal is deliberate; don't re-add it without a
> sanitizer.

`entity_id` and `universe` become filesystem path components, so both are
validated against `_SAFE_COMPONENT`
(`^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`) before anything touches disk — no
separators, no `..`, no leading dot. The *stored* `current_universe` is
validated on the same path, so a bad value already in the data cannot traverse
either. A failure is a 400.
