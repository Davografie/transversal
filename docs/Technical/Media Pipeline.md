---
title: Media Pipeline
date: 2026-09-06
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

`ImageType` (enum): `uploaded` · `imagen` · `animated`.

`EntityImage` (`entity_images` collection) — one record per image file:

- `id` — uuid (`_key`).
- `entity_id` — owning entity (soul).
- `projection_id` — owning body; empty = entity-level default.
- `universe` — the universe the image was generated/uploaded in.
- `image_type` — see above.
- `roles` — subset of `background` / `sheet` / `navdot`.
- `prompt`, `negative_prompt`, `loras` — generation provenance.
- `width`, `height`, `seed`, `steps` — generation params.
- `filename` — base name without variant suffix or extension.
- `extension` — file extension (e.g. `webp`, `webm`, `mp4`).
- `created_at` — ISO 8601.

## Storage layout

Static images are saved as WebP in several size variants:

```
media/imagen/{entity_id}/{universe}/{filename}_{variant}.{ext}
    variant ∈ Original · Large (≤1024) · Small (≤240) · Mini (≤48)
```

Animated loops live separately:

```
media/animated/{entity_id}/{universe}/{filename}.{ext}   # .webm / .mp4
```

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

### GraphQL surface

- `Entity.image(role, projectionId?)` — the canonical resolver. When
  `projectionId` is omitted it resolves through the entity's `current_projection`
  (active body), falling back to entity level. This is what most callers use.
- `Entity.background_image` — entity-level `background` (Large); falls back to
  the legacy denormalized `_background_image` string.
- `Entity.sheet_portrait` — entity-level `sheet` (Small); falls back to
  `background_image`.
- `Projection.sheet_image` — that body's `sheet` (Small), with entity fallback.

There is deliberately **no** fallback to the legacy `background_image` field
from the role-based `image()` resolver — callers that want a role image use the
role tags.

### Batch resolution

`_role_urls` / `_navdot_urls` / `get_role_images` / `get_navdot_images` resolve
many entities at once, each through its active projection. `get_navdot_images`
is used by the location navigate endpoint for occupants, children, transversal
destinations, and the parent.

## REST API

- `POST /media/upload` — upload a file; convert to WebP, save variants, register
  an `EntityImage`, auto-select roles when it is the sole entity-level image.
- `POST /imagen/{entity_id}` — trigger async static generation (optional
  `projection_id` in body → per-projection generation).
- `POST /animate/{entity_id}` — trigger async video-loop generation.
- `POST /imagen/{entity_id}/cancel` — interrupt the active job.
- `GET /imagen/jobs` — active generation/animation jobs + queue position.
- `GET /imagen/loras` — available Flux LoRAs.
- `GET /entities/images?role=&ids=` — batch role-image resolution (used by the
  peers bar to avoid loading images for the whole entity list).
- `GET /imagen/{entity_id}` — list images (with `projection_id`, `roles`,
  `path_large`, `path_animated`).
- `PATCH /imagen/{image_id}` — update `roles`, `universe`, and/or
  `projection_id` (ownership reassignment).
- `DELETE /imagen/{image_id}` — delete an image and its variants.

## Generation pipeline

`ImagenOrchestrator` runs the async jobs; `prompt_builder` assembles prompts.

### Prompt building

`build_imagen_prompt(entity, universe, repository, projection_id)`:

- Starts from a per-entity-type base prompt (character/GMC portrait, asset
  concept, faction emblem, location backdrop).
- Enriches from trait settings:
  - `appearance` trait → weighted appearance clause.
  - `LoRA*` traits → LoRA list.
  - `negative imagen` / `positive imagen` traits → negative/positive additions.
  - generic traits → `(trait is statement:rating_weight)` clauses.
- Adds universe style guidance and the universe's per-entity-type LoRA config.

For a **projection** generation, trait selection is scoped by
`get_prompt_traitsettings(entity_id, universes, projection_id)`: entity traits
(`from_type == 'entity'`) plus that projection's morph traits
(`from_type == 'projection'` and matching `projection_id`). Entity-level
generation uses entity traits only.

### Imagen (static)

`run_imagen` → ComfyUI Flux → `_save_image_variants` (Original/Large/Small/Mini
WebP) → `EntityImage`. If the result is the sole image for its owner, all three
roles are auto-selected.

### Animate (video)

`run_animate` produces a static Flux image (or reuses an existing one), runs it
through Ollama (gemma3 vision) to derive a motion description, then feeds that
to ComfyUI WanVideo. Output is the `.webm`/`.mp4` loop.

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
  animate, delete.

## Upload & format handling

`ALLOWED_EXTENSIONS = png, jpg, jpeg, gif, webp, svg, heic, heif`. HEIC/HEIF
(iOS camera photos) are decoded via `pillow-heif`, then converted to WebP;
SVG and GIF pass through unchanged. Size cap is 10 MB.
