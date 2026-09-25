---
title: Media Pipeline
date: 2026-09-06
last-updated: 2026-09-25
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

An image belongs to an **owner** — an entity or a trait — and may sit one tier
below it via `MediaImage.variant_id`: a **projection (body)** for an entity, a
**traitsetting** for a trait. An empty `variant_id` is the owner-level
**definition** image — the "soul default" that any body falls back to when it
has no image of its own for a given role (and, for a trait, the canonical
picture). One entity can have multiple projections even in the same universe
(keys are `entity:universe`, `entity:universe:2`, …).

Every image is tagged with one or more **canonical roles**:

| Role | Meaning | Static variant |
| --- | --- | --- |
| `background` | location / scene backdrop | `Large` |
| `sheet` | character-sheet portrait (small render) | `Small` |
| `navdot` | map dot / occupant marker | `Large` |

## Data model

> [!info] The owner model (`B200`, landed 2026-09-25)
> An image is owned by an **entity** or a **trait**, and may sit one tier below
> its owner. The same change renamed the collection `entity_images` → `images`
> and the class `EntityImage` → `MediaImage` (and the constant `ENTITY_IMAGES` →
> `IMAGES`). [[Trait Images Design Log]] carries the decisions and the reasoning.

`ImageType` (enum): `uploaded` · `imagen` · `animated` · `cutout`.

`MediaImage` (`images` collection) — one record per image file:

- `id` — uuid (`_key`).
- `owner_kind` — `entity` or `trait`.
- `owner_id` — the owning record: an entity id (soul) or a registry trait id.
  Ids are type-prefixed, which is why resolution needs no kind parameter.
- `variant_id` — the tier below the owner; empty = the owner-level **definition**
  image. A projection for an entity, a traitsetting for a trait.
- `universe` — the universe the image was generated/uploaded in.
- `image_type` — see above.
- `roles` — subset of `background` / `sheet` / `navdot`.
- `flags` — provenance labels (`ai`, `ai_generated`, `ai_animated`). **Not roles**
  — see [[#Provenance flags (AI)]].
- `transparent` — the file has a transparent background (an alpha channel with
  non-opaque pixels). Detected at ingestion, never hand-set. See
  [[#Transparency]].
- `prompt`, `negative_prompt`, `loras` — generation provenance.
- `width`, `height`, `seed`, `steps` — generation params.
- `filename` — base name without variant suffix or extension.
- `extension` — file extension (e.g. `webp`, `webm`, `mp4`).
- `created_at` — ISO 8601.
- `entity_id` / `projection_id` — **transitional mirrors** of `owner_id` /
  `variant_id`. Rows written before the backfill carry only these, and the older
  code still running against the shared database reads them, so they are kept in
  sync in both directions. `update_image` normalises every write back through the
  model, because a raw dict merge that updates one representation and not the
  other is exactly how resolution ends up reading a stale owner. Dropped in a
  later commit.

## Transparency

`MediaImage.transparent` marks images whose background has been cut out. It is
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
media/imagen/{owner_id}/{universe}/{filename}_{variant}.{ext}
    variant ∈ Original · Large (≤1024) · Small (≤240) · Mini (≤48)
```

`owner_id` is the directory key, and it does not change when an entity gains a
trait image: existing files stayed exactly where they were through the `B200`
backfill. Trait images land under `media/imagen/trait-…/`, which cannot collide
with entity keys because the ids are type-prefixed.

Alpha survives the variant pass: sources with an alpha channel are converted
RGBA→RGBA, so cutouts stay transparent in every variant.

> [!warning] Variant quirk
> For **portrait** sources the `Large` variant is derived on the width axis, so
> its long side collapses to the source's *short* side (478×700 → 326×478).
> Landscape sources scale as expected. Treat `Original` as the native copy and
> `Large` as an upper bound, not a guarantee.

Animated loops live separately:

```
media/animated/{owner_id}/{universe}/{filename}.{ext}   # .webm / .mp4 / .webp
```

Transparent loops are **VP9-alpha WebM** (`yuva420p`) written by the matting
stage — see [[#Transparent animations]].

A legacy flat-file path `media/{flat_filename}` exists for backward
compatibility on upload, but the canonical form is the per-entity directory
above.

## Resolution

The single resolution primitive is
`EntityRepository.resolve_role_image(owner_id, role, variant_id, variant)`.
Order of precedence:

1. The variant's own image carrying `role` (newest first) — a projection's, or a
   traitsetting's.
2. The owner-level image carrying `role` whose `universe` matches the variant's
   **current**, then **origin**, universe.
3. Any owner-level image carrying `role`.

With no `variant_id`, only owner-level images are considered.

**The kind of owner never enters resolution.** Ids are type-prefixed
(`character-…`, `loc-…`, `trait-…`), so the ladder is the same for an entity and
a trait. The one rung that behaves differently is the universe match: it needs a
projection to supply a universe to match against, and a trait has none, so it is
simply skipped — which is what lets **one canonical trait image serve every
universe the trait belongs to** (663 of the 802 live traits span more than one,
up to 15 each). Trait images are stored in a universe for provenance, not as a
filter.

`resolve_role_image_entry(owner_id, role, variant_id)` runs the same resolution
but returns the `MediaImage` record instead of a URL; `resolve_role_image` is a
thin URL wrapper over it. Reach for the entry form whenever you need image
metadata — `transparent` being the reason it exists.

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
- `Trait.image(role)` / `Trait.imageTransparent(role)` — the trait's picture for
  a role, using the same role→variant map (`sheet` → `Small`), so a trait image
  and an entity portrait follow one size convention. Resolved at the trait's
  definition tier: role-filtered, universe-ignoring (`B200`).

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

### Traits as image owners

A **trait** is an owner on the same ladder (`B200`). Its definition image is the
trait's canonical picture; slice 2 lets a **traitsetting** override it per
instance, exactly as a projection overrides an entity.

**Roles are not ignored for traits** — the human's decision, 2026-09-25 — and
each has a real surface, so they are not decorative:

| role | trait surface | surface owner |
| --- | --- | --- |
| `sheet` | the trait's picture in the sheet row and the trait detail panel | [[character-sheet]] |
| `background` | the trait detail panel's backdrop | [[character-sheet]] |
| `navdot` | the trait's marker in the location-viewer scene (the chip) | [[navigation]] |

The **sole-image rule applies here too**, so a trait's first image takes all
three roles and renders in all three places without its author thinking about
roles at all.

A trait's images are **cascaded on deletion**: `delete_trait` removes the rows
and the files, because an owner that can own images has to clean them up —
without that, deleting a trait seeds exactly the orphan class
[[data-migration]] is already carrying 25 rows of.

> [!note] Built so far
> Slice 1's media half has **landed**: the owner model, the collection rename and
> backfill, owner-aware resolution and upload, GraphQL `Trait.image(role)`, and
> the registry editor's Image section — upload, remove, and **cut out**. Nothing
> else in slice 1 is media's.
>
> Not built: the trait-shaped **generation** entry point, slice 2's traitsetting
> override, and the three partner surfaces above. Nothing *auto*-cuts a trait
> image, because that rule hangs off a first *generated* image and trait
> generation does not exist yet.

### Migrating the collection (`B200`)

```bash
docker compose exec api python -m transversal.migrate_images_owner          # dry run
docker compose exec api python -m transversal.migrate_images_owner --apply  # write
```

One idempotent pass that both renames `entity_images` → `images` and stamps the
owner fields, because the two touch the same documents. It preserves `_key`
(image ids are referenced by stored rows), never overwrites a key already
present, and is safe to re-run — which is how it picks up images the *older* code
writes during the transition, since the containers at `:3000` keep running
`release-build` until the branch merges. `entity_images` is **left in place** as
the rollback.

## REST API

- `POST /media/upload` — upload a file; convert to WebP, save variants, register
  a `MediaImage`, auto-select all three roles when it is the sole image on its
  rung. Takes `owner_kind` (`entity` | `trait`), `owner_id`, `variant_id`,
  `universe` and `flags` (comma-separated provenance labels — send `ai` for art
  you know involved AI); `entity_id` / `projection_id` are still accepted as
  aliases because two frontend callers send them. Registration is
  **best-effort**: if
  the owner does not exist, or a trait belongs to no universe and none was
  named, the file is still written and `image_id` comes back null rather than
  failing an upload whose file already landed.
- `POST /imagen/{entity_id}` — trigger async static generation (optional
  `projection_id` in body → per-projection generation).
- `POST /animate/{entity_id}` — trigger async video-loop generation. Body may
  carry `image_id` to animate an existing image; when that image is
  `transparent`, the finished loop is matted (see below).
- `POST /remove-background/{owner_id}` — body `{image_id}`; async, static
  images only. Any owner: `?owner_kind=entity` (default) or `trait`. Produces a
  new transparent cutout image (see below).
- `POST /imagen/{entity_id}/cancel` — interrupt the active job.
- `GET /imagen/jobs` — active generation/animation jobs + queue position.
- `GET /imagen/loras` — available Flux LoRAs.
- `GET /entities/images?role=&ids=` — batch role-image resolution (used by the
  peers bar to avoid loading images for the whole entity list).
- `GET /imagen/{entity_id}` — list images (with `projection_id`, `roles`, `flags`,
  `transparent`, `path_large`, `path_animated`). Any owner id works — a trait's
  gallery reads through the same endpoint.
- `PATCH /imagen/{image_id}` — update `roles`, `flags`, `universe`, and/or
  `projection_id` (ownership reassignment). Roles strip siblings; `flags` do not.
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
  - `LoRA*` traits → LoRA list. **`statement` only, never merged with `notes`**:
    the value becomes a filename (`flux/{name}.safetensors`), so free text would
    corrupt the path. All live LoRA settings already use `statement`.
  - `negative imagen` / `positive imagen` traits → negative/positive additions,
    each carrying `statement` **and** `notes`. Most live settings use one field
    or the other, not both: 231 of 423 `negative imagen` settings are notes-only,
    so gating on `statement` alone (`B167`) dropped the majority of them.
  - generic traits → `(trait is statement:rating_weight)` clauses. This branch
    still ignores `notes`, unlike the three above.
- Adds universe style guidance, the universe's per-entity-type LoRA config, and
  the universe's free-text **prompt steering** sentence
  (`Entity.prompt_steering`, authored per universe in the GM LoRA panel and
  appended last as `(sentence:0.9)` so it reads as the final style direction).

Every prompt's negative ends with **`DEFAULT_NEGATIVE`** (`imagen/models.py`),
which suppresses the stock-image and *inscription* artefacts: `watermark,
signature, text`, plus `caption(s)`, `lettering`, `writing`, `calligraphy`,
`inscription`, `seal` / `seal stamp` / `red seal`, `logo`, `title`, `subtitle`,
`signage`, `chinese characters`, `kanji`, `border`, `frame`, `ui`.

> [!warning] Suppression goes in the negative — never in the positive
> A style LoRA can write on the image: `ChineseScrollPainting`, applied
> automatically to `three_realms` locations from the universe's `LOCATION` lora
> config, reproduces the calligraphic inscriptions and red seals that scroll
> paintings carry, over an explicit `text, watermark, signature` negative. The
> widened negative above removes them (`B175`).
>
> What did **not** work: a *positive* clause reading "no text, no calligraphy, no
> seal stamps" produced **more** calligraphy than the baseline. Flux/T5 does not
> negate, so naming the thing summons it. A test guards the positive prompt
> against that phrasing.
>
> When this reappears, remember the LoRA is at weight 0.8
> (`inject_flux_params` defaults `lora1_weight = 0.8`) — checking the weight is
> the first move, and the second is whether the prompt *asked* for writing (the
> injected zone prose can, e.g. "bamboo slips with assignments in chinese
> writing").

For a **projection** generation, trait selection is scoped by
`get_prompt_traitsettings(entity_id, universes, projection_id)`: entity traits
(`from_type == 'entity'`) plus that projection's morph traits
(`from_type == 'projection'` and matching `projection_id`).

> [!warning] Never read a prompt without a projection
> Creating a trait setting through the API **anchors it to the active body**
> (`from_type='projection'`), so an entity's appearance normally lives on its
> `current_projection`, not on the entity. `build_imagen_prompt` therefore
> resolves `projection_id or entity.current_projection` — the same rule
> `Entity.image()` already applied — and only genuinely body-less entities fall
> through to entity traits alone. Without that fallback a prompt silently loses
> every morph trait: the gallery's main Imagen button sends `projection_id=''`,
> so it was the *common* case, and 19 locations' appearances plus every
> appearance authored through the API ([[mcp-architect]]'s 27 entities) never
> reached the generator while their images resolved fine (`B167`).
>
> The same applies per-entity inside the location context: a sub-location or
> ancestor is read with **its own** `current_projection`, not the root
> location's.

### Location prompts

A `location` opens with
`(location background image, a humanless atmospheric image focusing on {name}:1.2), `
— deliberately **no** "seen from above": not every location is viewed from
above. Two place-aware clauses can follow, both restored from the original app
by `B162` and built by `_location_context_clause`:

- **Sub-locations — always.** `navigate_from(id)["children"]` (inbound `super`
  edges — v1's "zones"), each rendered `(name, appearance:0.4)` inside one
  `:0.8` group:

  ```
  the different zones in {name} are ((A, …:0.4) and (B, …:0.4)):0.8),
  ```

- **Ancestor chain — opt-in per location.** `Entity.prompt_include_ancestors`
  (the **Surroundings** toggle in the GM panel, next to the imagen button) gates
  it, because surrounding geography makes an exterior read right and is usually
  noise for an interior. `get_location_ancestors` returns the chain
  nearest-first and the weight decays ×0.6 per level:

  ```
  located in (Wilderness, … in (Verdant Dominion in (Valley of Ascension:0.216):0.36):0.6)
  ```

  Non-location parents are skipped — a `super` parent may be a character, and
  only a place describes where a place is.

Where v1 read a location's `description`, v2 has no such field: both clauses use
the `appearance` trait's `statement` + `notes`, the same content the appearance
clause carries (see `B159`).

### Occupant location context

A **GMC or asset** prompt can also say where it is — the place it is in, then
that place's ancestors, in the same nested `located in (…)` form with the same
×0.6 decay (`B168`; v1 gave this to npc and asset via `flask/app.py:5551`). It is
gated by that entity's own **Surroundings** toggle, so a GMC with it off builds
exactly the prompt it did before.

- **The body's location wins.** `Projection.current_location` is read before
  `Entity.current_location`, because a projection can be somewhere its soul is
  not (four live entities differ). Otherwise a body would be described as
  standing wherever the soul happens to sit.
- **No sub-locations.** `the different zones in X are …` describes what a place
  *contains* — right for a location's own backdrop, wrong for someone standing
  inside it.
- **Characters are excluded**, matching v1: a PC is generated wherever the player
  wants, not pinned to the soul's location.

> [!warning] There is no cutoff
> With the toggle on, the **whole** chain to the root is included. A passage in a
> dungeon at a theme park is told about the theme park. Expressing "knows it's in
> the dungeon, not that it's in Disneyland" needs a per-location boundary marker
> meaning *"describe me, then stop"* — that is **not built** (raised as a
> question, not a requirement). `B168` records it, and a test documents the
> current behaviour so the gap is visible rather than assumed.

### Imagen (static)

`run_imagen` → ComfyUI Flux → `_save_image_variants` (Original/Large/Small/Mini
WebP) → `MediaImage`. If the result is the sole image for its owner, all three
roles are auto-selected.

**The first image generated for a projection is also cut out** (`B166`). The
generated image becomes the projection's `background`; the transparent cutout
becomes its `navdot` **and** `sheet`, so a body renders a floating portrait
rather than a cropped circle. The trigger is the first *generated image* for the
projection, not entity creation — a cutout needs a source, and creation has no
image. It reuses the sole-image condition above (`owner and not existing`), and
because the owner had no images there are no siblings holding those roles to
strip.

Two paths intentionally do **not** trigger it: **uploads**, and **entity-level**
generation (the gallery's main Imagen button, `projection_id` empty) — the rule
is scoped per projection. See `B129` for whether to widen it.

If the cutout fails the generation is unaffected: the image is already recorded,
and the source keeps all three roles rather than giving up `sheet`/`navdot` to a
cutout that does not exist.

### Remove background (static cutout)

`run_remove_background(owner_id, image_id, display_name)` turns an existing
static image into a transparent cutout. It is **non-destructive**: the source is
untouched and the result is a new `MediaImage` of type `cutout`, owned by the
same owner **and the same tier** as the source — the *source image* decides that,
never the caller — with `transparent=true` and no role tags.

It works for **any owner**:
`POST /remove-background/{owner_id}?owner_kind=entity|trait` (`entity` is the
default, so the image viewer's call is unchanged), and both the progress stream
and the job registry at `GET /imagen/jobs` are keyed by `owner_id` — a trait's
picture is cut out under the trait's id exactly as an entity's is under its own.
`owner_id` and `display_name` are only the progress key and the file name; a
trait has no `Entity` and needs none.

> [!note] A trait's cutout is a second image, tagged like any other
> A cutout is **added, never swapped in** — the same non-destructive contract an
> entity cutout has. The source keeps its file and its roles; the new transparent
> image arrives untagged. The GM trait editor lists **every** image with the three
> role checkboxes (Sheet / BG / Nav), so placing the cutout is an act the author
> performs and can undo — the first cut of this editor moved the roles onto the
> cutout automatically, which read as an in-place edit and buried the original.
>
> Role assignment is unique per (owner, role), so ticking a role strips it from
> whichever sibling held it: the tag *moves*. To put the transparent version on
> the surfaces you tick its boxes; to leave the original alone, you don't.
>
> Verified on the live stack: the cutout came back RGBA with all four corners
> fully transparent and the subject opaque (70% of pixels transparent), while the
> source stayed RGB and untouched.

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

## Container build & pins

`src/imagen/Dockerfile` builds the ComfyUI + Ollama container (`tv2_imagen`,
ComfyUI on 8188 → host `127.0.0.1:8190`). Two things there are pinned, and both
matter:

**The PyTorch stack.** `torch==2.11.0+cu129`, `torchvision==0.26.0+cu129`,
`torchaudio==2.11.0+cu129`. torchaudio mirrors torch's version; torchvision is
torch's minor + 15 (2.11 → 0.26); the `+cu129` local tag exists only on the
PyTorch index, so these pins cannot be satisfied by PyPI.

> [!warning] Do not unpin torch — it takes the whole pipeline down
> The pins live in `PIP_CONSTRAINT=/app/torch-constraints.txt`, not merely in a
> `-c` on the install command, because ComfyUI's own `requirements.txt` lists
> bare `torch torchvision torchaudio` — a later `pip install -r` will re-resolve
> and silently upgrade torch. With nothing pinned, pip takes the highest version
> across PyPI *and* the `cu129` index, and those disagree at the top: cu129 stops
> at torch 2.13.0 and torchaudio 2.11.0, so `torch` comes from PyPI as a **cu130**
> build while `torchaudio` stays cu129. ComfyUI then dies during import —
> `main.py → execution → latent_preview → comfy.sd →
> comfy.ldm.lightricks.vae.audio_vae → import torchaudio` — with *"PyTorch has
> CUDA version 13.0 whereas TorchAudio has CUDA version 12.9"*, the container
> exits about five seconds into every start, and imagen / animate /
> remove-background all go down together (the API reports it as
> `ClientConnectorDNSError: Cannot connect to host imagen:8188`). See `B160`.

**The remote clones.** ComfyUI and its 15 remote custom nodes are checked out to
fixed commits. Changing the torch layer invalidates every layer after it, so an
unpinned `git clone` would swap ComfyUI and the nodes for whatever is on master
that day — a rebuild that changes two things at once cannot tell you which one
broke it. (The White Rabbit nodes are a local `COPY`, so they need no pin.)

### Workflow inputs must satisfy every node version

The workflow JSON is read at runtime from `WORKFLOW_DIR=/app/workflows` (mounted
from the repo), so editing a workflow needs no image rebuild.

> [!warning] ComfyUI ignores unknown inputs — use that, and know when it stops
> `validate_inputs` iterates only the node class's **known** inputs and never
> checks the submitted workflow for unknown ones:
>
> ```python
> valid_inputs = set(class_inputs.get('required', {})).union(set(class_inputs.get('optional', {})))
> for x in valid_inputs:      # the class's inputs, not the prompt's
> ```
>
> So a workflow can carry a **superset** of the inputs different node versions
> need, and each version reads what it knows: `Image Save` keeps `output_path`
> (old WAS) *and* `root`/`bit_depth` (new WAS); `Text Multiline` carries
> `dynamic_prompts`, which only the new WAS requires. That is what keeps one
> workflow valid in both the dev container and a local ComfyUI install on a
> different node version (`B165`).
>
> This only works while the differences are *added* inputs. If a node ever
> **renames or changes the type** of an input, one name carries two meanings and
> the versions have to be aligned for real — the trick cannot paper over a
> conflict.

## Role assignment & auto-select

Roles are **unique per (owner, role)**, where owner = `projection_id` when set,
else `owner_id`. Assigning a role strips it from sibling images with the same
owner.

Auto-select of all three roles happens whenever an image becomes the **sole**
image in its owner scope:

- **upload** — sole image on its rung (the owner's definition tier).
- **generation** — sole image for the entity or projection.
- **drop** — dragging an image onto an empty entity/projection gallery.

The one case where that three-role result is deliberately redistributed is a
**projection's first generated image**: the generated image keeps `background`
and a new transparent cutout takes `navdot` + `sheet` (`B166`; see
[[#Imagen (static)]]). Upload and drop do not cut out.

## Provenance flags (AI)

`MediaImage.flags` labels how an image came to exist. The vocabulary is fixed —
`IMAGE_FLAGS` in `domain/views.py` — because these labels are read by the UI and
by anything asking whether an image involved AI, so a typo should fail loudly
rather than quietly mean "no disclosure".

| flag | who sets it | meaning |
| --- | --- | --- |
| `ai` | **a human** | AI was somewhere in this image's workflow — your call to make, e.g. art made elsewhere with AI in the chain |
| `ai_generated` | the imagen pipeline, and the animate pipeline when it generates the still | Flux made the picture |
| `ai_animated` | the animate pipeline | WanVideo made the motion |

Both of the animate pipeline's own claims apply when it generated the still: a
**fresh loop is Flux *and* WanVideo**, so it carries `ai_generated` *and*
`ai_animated`. Animating an **existing** picture declares only the motion and
inherits whatever that picture already said about itself — a hand-made upload
stays unlabelled, an AI-generated one keeps its label. Labelling the imagery of a
sourced animation as generated would be the same over-claim the cutout rule
rejected.

**`flags` is deliberately a separate field from `roles`.** Roles are unique per
(owner, role) — assigning one strips it from sibling images — which is right for
"where does this render" and catastrophic for a provenance label: putting `ai` in
`roles` would make ticking one image's `[AI]` silently untag every other image of
that owner. So flags are additive, not unique per owner, and resolution never
consults them. (`tests/test_media_image_owner.py` pins both halves of that
contrast in one test.)

A **cutout inherits and adds nothing.** It is tempting to treat BiRefNet as an
AI step and label every cutout `ai`; the human's call is that it should not —
only imagen and animate declare AI, and a cutout is the same picture with its
background removed. A cutout of a Flux image therefore stays `ai_generated`,
because that label describes the picture's origin, which removing a background
does not change; but the cutout pipeline never adds a label of its own. (211
cutouts were stamped `ai` by the first cut of the backfill and corrected; the
script's `--remove-cutout-ai` is that correction.)

Surfaces: the GM image viewer and the GM trait editor both show the three labels;
`[AI]` is a checkbox and the two pipeline labels are read-only, because the
pipelines own them. The upload endpoint takes `flags` (comma-separated) and
`PATCH /imagen/{image_id}` sets them, both validated against the vocabulary.

> [!warning] Existing rows were backfilled from `image_type`
> `image_type` already recorded how most images were made, so
> `backfill_image_flags.py` derives the pipeline label from it — `imagen` →
> `ai_generated`, `animated` → `ai_animated` — and derives **nothing** for
> `cutout` or `uploaded`: a cutout asserts nothing of its own, and an upload's
> provenance is genuinely unknown, which is exactly what the manual `ai` label is
> for. **228 of 1140 live rows** carried a derivable label; the 701 uploads and
> 211 cutouts did not. It is additive (a row keeps flags it
> already has) and idempotent, so re-run it after this branch merges to catch
> images the older code wrote in the meantime:
>
> ```bash
> docker compose exec api python -m transversal.backfill_image_flags          # dry run
> docker compose exec api python -m transversal.backfill_image_flags --apply
> ```

## Credits & citation

`MediaImage` records **who made an image and where it came from**, so a picture
found online can be cited rather than silently borrowed:

- `credits: [{role, name, url}]` — the parties. Roles are `artist`, `source`,
  `publisher`, `rights` (`CREDIT_ROLES` in `domain/views.py`). Several per image;
  `url` is optional and, when set, is rendered as a link.
- `license: str` — a licence URL, or a short name when there is no page.
- `credit_text: str` — the wording to *display* when the rights holder specifies
  one verbatim. Optional: empty means the surfaces compose a line from the
  credits and licence instead.

### The standard it follows

There is no single citation standard, but there is a clear convergent core, and
the field names here are chosen to match it so this data can be exported or
embedded later without a translation table. The short version is Creative
Commons' **TASL** — *Title, Author, Source, Licence* — which is what the CC
"recommended practices for attribution" reduce to and what most people actually
expect to see.

| our field | TASL | Schema.org | IPTC photo metadata |
| --- | --- | --- | --- |
| `credits[role=artist]` | Author | `creator` | Creator / Creator's Job Title |
| `credits[role=source]` | Source | `creditText`, `isBasedOn` | Source, Credit Line |
| `credits[role=publisher]` | — | `publisher` | Credit Line |
| `credits[role=rights]` | — | `copyrightHolder` | Copyright Notice |
| `license` | Licence | `license`, `acquireLicensePage` | Rights Usage Terms, Licensor URL |
| `credit_text` | the rendered line | `creditText` | *(the display string)* |

Two neighbours worth knowing about and **deliberately not adopted**:

- **IPTC / XMP** is the standard for embedding this *in the file* ([IPTC Photo
  Metadata Standard](https://www.iptc.org/std/photometadata/specification/IPTC-PhotoMetadata-2022.1.html)).
  Real fields (`dc:creator`, `photoshop:Credit`, `photoshop:Source`,
  `xmpRights:WebStatement`) and the natural export target if we ever want the
  metadata to travel with the WebP rather than live only in the database. Not
  done now because nothing reads it yet, and a field we populate but no surface
  consults is worse than an honest column.
- **C2PA / Content Credentials** is a *cryptographically signed* provenance
  manifest ([c2pa.org](https://c2pa.org/)), the heavyweight answer to "can this
  claim be trusted" — it is about authenticity chains, not cataloguing, and it
  signs the asset. Overkill for crediting a piece of art in a home game, but it
  is the standard our `ai_generated` / `ai_animated` labels would eventually map
  onto (`c2pa.actions` with `trainedAlgorithmicMedia`) if we ever want them
  verifiable rather than asserted.

[VRA Core 4.0](https://www.loc.gov/standards/vracore/VRA_Core4_Element_Description.pdf)
and Dublin Core are the library/museum vocabularies; VRA's split between the
*work* and the *image of the work* is the one idea worth stealing if this ever
grows — here, `credits` describes the artwork and the image is assumed to be a
faithful copy of it.

### Rules and surfaces

- **Links are scheme-checked.** `url` must start with `http://` or `https://`
  (`_validated_credits` in `api/rest/imagen.py`), because these render as links:
  an unchecked `javascript:` or `data:` URL is a stored-XSS vector, the same
  class of bug that removed `.svg` uploads (SEC-4). Unknown roles are a 400, and
  blank rows are dropped so an empty editor row is not an error.
- **Not roles, not flags.** Credits are independent of where an image renders,
  and many images can credit the same artist — the same reasoning that keeps
  `flags` out of `roles`.
- **A derivative carries the citation forward.** A **cutout** and an **animated
  loop** inherit their source's `credits`, `license` and `credit_text`: the file
  has a new id, but it is not a new work, and losing the artist because you
  removed a background is exactly the silent-omission these fields exist to
  prevent. Both also inherit the source's `flags` and add their own pipeline's
  label on top (see [[#Provenance flags (AI)]]). Credits are copied per record, so
  the two rows are independent afterwards.
- **Where it is set:** the GM image viewer's *Credits & source* block, and each
  row of the trait editor's gallery. Both use `ImageCreditsEditor.vue`; the
  server validates regardless.
- **Where it is shown to players:** the character sheet's portrait viewer
  (`CharacterSheet.vue`) renders `ImageProvenance.vue` under the image, reading
  the resolved record through GraphQL `imageInfo(role)` — which can show an AI
  badge and a source link, and stays silent when an image has neither. Both
  `Entity.image_info` and `Trait.image_info` / `TraitSetting.image_info` expose
  it, so a player-facing trait row or scene chip can do the same.

> [!note] `image(role)` vs `image_info(role)`
> `image(role)` is still the cheap way to get a URL. `image_info(role)` returns
> the resolved image *plus* its flags, credits, licence and credit line, for any
> surface that has to **disclose** something about the picture rather than just
> draw it. Prefer `image_info` when the viewer shows provenance; prefer `image`
> when it just needs something to put on screen.

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

`owner_id`, `variant_id` and `universe` all become filesystem path components, so
all three are validated against `_SAFE_COMPONENT`
(`^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`) before anything touches disk — no
separators, no `..`, no leading dot. A bad *request* value is a 400. The *stored*
universe (`current_universe`, or a trait's first listed universe) is validated on
the same path, so a bad value already in the data cannot traverse either — but
that check runs inside the best-effort registration block, so it skips the gallery
row rather than failing an upload whose file has already been written, which is
what `test_media_upload_guard.py` pins.
