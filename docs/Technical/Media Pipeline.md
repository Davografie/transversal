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

| Role | Meaning | Serves |
| --- | --- | --- |
| `background` | location / scene backdrop | the **Animated** render if the picture has one, else `XLarge` |
| `sheet` | character-sheet portrait (small render) | the **Cutout** render at `Small` if it has one, else `Small` |
| `navdot` | map dot / occupant marker | the **Cutout** render at `Large` if it has one, else `Large` |

## Data model

> [!info] Derived files are **renders of the picture** ([[B210]], landed 2026-09-25)
> A cutout is not a second picture and neither is a loop: both are renders of the
> picture they came from, carried in `MediaImage.renders` and chosen by the role
> map. Before this, a derived file modelled as a picture lost its credits
> (`B204`), was mislabelled as AI (`B203`), had roles redistributed around it
> (`B166`), and left loops with no roles at all ([[B205]]). [[Image Tiers Design
> Log]] carries the reasoning, the migration and what the live library changed
> about it.

> [!info] The owner model (`B200`, landed 2026-09-25)
> An image is owned by an **entity** or a **trait**, and may sit one tier below
> its owner. The same change renamed the collection `entity_images` → `images`
> and the class `EntityImage` → `MediaImage` (and the constant `ENTITY_IMAGES` →
> `IMAGES`). [[Trait Images Design Log]] carries the decisions and the reasoning.

`ImageType` (enum): `uploaded` · `imagen` — the **source's** provenance, and
nothing else. Since [[B210]] a matte and a loop are `renders` of the picture, not
types of their own, and the `animated`/`cutout` members are gone.

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
- `renders` — the derived renders this picture carries: `cutout` (a matte) and/or
  `animated` (a loop). The role map reads this, which is why a cutout cannot lose
  its credits, its flags or its id — there is no second record to copy them to.
- `animated_extension` — the loop's container when the picture has an `animated`
  render. `extension` names the **still** (a merged picture is a WebP that also has
  a video), and one field cannot name both.
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

## The variant ladder

| tier | long side | used by |
| --- | --- | --- |
| `Original` | the master | nothing directly — the archival copy |
| `XLarge` | ≤2048 | **`background`** — the only full-bleed role |
| `Large` | ≤1024 | `navdot` (a map dot) |
| `Small` | ≤240 | `sheet` (a panel portrait) |
| `Mini` | ≤48 | list rows, tiny chrome |

The role→variant mapping lives in one constant,
`services/media_utils.ROLE_VARIANT`, shared by the `Entity`, `Trait` and
`TraitSetting` GraphQL resolvers and by the REST batch endpoint — so a role
cannot mean one file in one place and another elsewhere. `background` moved from
`Large` to `XLarge` because a location backdrop is drawn at **viewport** size: a
1080p screen wants ~1920 device pixels and a phone held portrait ~1170×2532,
which `Large` could not reach. The small roles stay small on purpose — a 48px map
dot and a panel portrait pay memory only for pixels nobody sees.

### What a bigger tier costs

Measured on six real `three_realms` backgrounds (photographic-ish, WebP q85):

| long side | pixels | bytes | decoded RGBA |
| --- | --- | --- | --- |
| 700 *(the old median)* | 0.3 MP | 210 KB | 1.3 MB |
| 1024 *(the old cap)* | 0.7 MP | 210 KB | 2.9 MB |
| 1536 | 1.6 MP | 269 KB | 6.5 MB |
| 2048 *(the new cap)* | 2.9 MP | 362 KB | 11.5 MB |
| 2731 | 5.1 MP | 485 KB | 20.4 MB |

**Bytes are not the constraint: 8.4× the pixels costs 1.7× the bytes**, because
this art has large flat areas and compresses very well. Media is also served
`cache-control: public, max-age=31536000, immutable` with an ETag, so the
download is a one-time cost per device. What recurs is **decode and memory**:

- **Desktop** is comfortable to 2048–2560. 4K (8.3 MP, 33 MB decoded) is fine but
  wasteful unless the window really is 4K.
- **Mobile is where it binds**, and the location crossfade keeps **two
  backgrounds live at once** — so the budget is 2× the figures above. 2048 gives
  ~23 MB peak, which is comfortable; 2731 would be ~41 MB and low-end devices
  start evicting there. Decode time matters too: ~3 MP WebP is 30–80 ms on
  desktop and 150–400 ms on a mid-range phone.
- `XLarge` therefore sits at 2048: it covers 1080p exactly-ish and a phone
  well, without pushing the crossfade past what a phone can hold.

> [!note] The tiers never invent detail — the masters are the ceiling
> Re-rendering fixed *delivery*: it recovers the resolution the masters already
> had (846 of 848 backgrounds went from ~0.3–0.7 MP to their master, ≈2.4× the
> pixels). It does not add detail, because most masters are 832×1216 (1.0 MP).

### Putting detail back into the masters

The human's call: upscale the masters with a model, **backgrounds only** — those
are drawn full-bleed, and they are what big screens expose.

**The model was chosen by measuring, and the measurement contradicted the
reputation.** Three were available; two were put against real Transversal art at
the size actually served (2048 long side), with a plain Lanczos resize to the
same size as the control:

| model | illustrated art (Earth) | painted ink (three_realms) |
| --- | --- | --- |
| *(no model — Lanczos)* | clean but soft | mushy foliage, flat cliff |
| `RealESRGAN_x4plus` | **smears the line work** — the ink hatching goes to soft blobs | better: rock structure appears |
| **`4x-UltraSharp`** | **crispest — keeps the illustrated lines** | **most texture: rock striations, resolved foliage, defined terraces** |

So **`4x-UltraSharp`**, on both styles. Worth noting Earth's backgrounds are not
all photographic — the sampled one is a flat-colour illustrated piece with ink
hatching, which is exactly the case the photographic model mishandles. The
`anime_6B` checkpoint is still on disk as a third option.

**The master is capped at 2048**, equal to `XLarge`: the model is 4×, so an
832×1216 master returns 3328×4864 (16 MP), and storing that would cost ~1 MB per
image and slow every tier re-render for pixels nothing ever serves. Resampling
the 4× result *down* to 2048 is a better 2048 than upscaling straight to it —
there is more information to resample from. The **pre-upscale master is kept** as
`{filename}_PreUpscale.{ext}` (~150 KB each): upscaling is irreversible and this
is the only copy of the art. It can be deleted once the result is trusted.

**It is a per-image action, not a batch.** The human's call: an **Upscale** button
in the image viewer, offered only where there is something to gain — spending the
GPU on the pictures that need it, from the surface where you are already looking
at the picture.

- `POST /upscale/{image_id}` — async, `202`. Refused with a 400 when the master is
  already at the ceiling (nothing can be gained) or when the image is a loop (a
  video has no tiers). Progress streams on `imagen_progress` and `GET /imagen/jobs`
  keyed by the image's **owner**, so the gallery that offered the button polls for
  it exactly as it does for a cutout.
- The list exposes the two things the UI needs, so the **ceiling stays server-side**
  and is never retyped in the frontend: `can_upscale` (master below the cap → show
  the button) and `upscaled` (a `_PreUpscale` backup exists → already through).
- The gallery tags an image **`XL`** when `can_upscale` is false. Worth being
  precise about what that means, because every image has an `_XLarge.webp` *file*
  on disk: **below the ceiling, `XLarge` is a copy of the master**, so the tag marks
  the images where the tier is genuinely larger — upscaled, or natively big enough.
  (If it should instead mark only images that went through the pass, that is one
  word: `upscaled` rather than `can_upscale`.)
- Both buttons — the GM entity image viewer and each row of the trait gallery —
  drive the same server code.

`ImagenOrchestrator.run_upscale` is the one implementation; the script below is only
a bulk loop over it, because the two copies of the variant writer are the
cautionary tale. It drives ComfyUI through that method, which takes the
orchestrator's `_gpu_lock` — but that lock is per-process and the script is a
separate process, so it *also* waits while ComfyUI's own queue holds anyone else's
work. ComfyUI's queue is the honest signal and covers every submitter. Skipping
that guard would put a sweep on the same 4090 as a user's generation and have the
two fight for VRAM.

```bash
docker compose exec api python -m transversal.upscale_backgrounds --limit 5 --apply  # trial
docker compose exec api python -m transversal.upscale_backgrounds --apply            # whole role
```

Idempotent — an image already at the cap is refused and counted as a skip. Measured
at **~4–7 s per image** on the 4090.

```bash
docker compose exec api python -m transversal.rerender_image_variants          # dry run
docker compose exec api python -m transversal.rerender_image_variants --apply
```

## Storage layout

Static images are saved as WebP in one ladder of size variants:

```
media/imagen/{owner_id}/{universe}/{filename}_{variant}.{ext}
    variant ∈ Original · XLarge (≤2048 long side) · Large (≤1024) · Small (≤240) · Mini (≤48)
```

A picture may carry derived renders beside that ladder, each under the same base
name — which is the whole ownership story ([[B210]]):

```
media/imagen/{owner_id}/{universe}/{filename}_Cutout_{tier}.webp   # the matte
media/animated/{owner_id}/{universe}/{filename}.{ext}              # the loop
```

Every tier is scaled to fit its cap on the **long side**, aspect ratio preserved,
and **a tier never upscales**: when the master's long side is already at or below
a cap, that tier is a copy of the master rather than an interpolation. So an
832×1216 master has an `XLarge` that *is* the 832×1216 master — the biggest
honest file that exists — never a resampled 2048. Inventing pixels would make the
file bigger, softer and no more truthful.

`owner_id` is the directory key, and it does not change when an entity gains a
trait image: existing files stayed exactly where they were through the `B200`
backfill.

> [!warning] `width`/`height` describe the **master**, and the UI shows them
> The gallery and image viewer label an image with `MediaImage.width` × `height`
> — the only size a user ever sees. They are written at ingestion and nothing
> maintained them, which failed two ways: **upscaling the master left them
> reporting the old size**, so an upscaled image read as "the upscale did
> nothing", and **708 of 1125 records said `0×0`** because the paths that created
> them (migration, and some upload routes) never measured the image.
> `sync_image_dimensions.py` rebuilds them from `Original` — the archival copy
> every tier derives from — and `upscale_backgrounds.py` now moves them with the
> master it writes.
>
> ```bash
> docker compose exec api python -m transversal.sync_image_dimensions          # dry run
> docker compose exec api python -m transversal.sync_image_dimensions --apply
> ```
>
> Dimensions are **not** the served size: the tier is chosen by role. A gallery
> shows one entry per *image*, never one per variant — five files exist on disk
> per image, and which one a surface fetches depends on the role it is asking
> for. Aspect ratio is preserved by every tier and by the upscale (worst measured
> drift 0.02%), which is what keeps the percentage-based dot positions and the
> panning correct. Trait images land under `media/imagen/trait-…/`, which cannot collide
with entity keys because the ids are type-prefixed.

Alpha survives the variant pass: sources with an alpha channel stay RGBA, so
cutouts are transparent in every tier.

> [!warning] There used to be two of these, and they disagreed
> `_save_image_variants` existed twice — in `api/rest/media.py` and in
> `imagen/orchestrator.py` — with different maths. The orchestrator's copy scaled
> portraits on the *width* axis, so an 832×1216 master was written out as
> 478×700 **and the aspect ratio was wrong**: `Small` came out 240×164 and `Mini`
> 48×32, landscape-shaped. The other copy left anything under 1024 untouched, so
> **the same source produced different files depending on which pipeline wrote
> it** — 622 live backgrounds were generation-produced and squashed, 117 were
> uploads and fine.
>
> Both copies are gone; `services/media_utils.save_image_variants` is the only
> implementation, and `api/rest/media.py` and `imagen/orchestrator.py` both
> delegate to it (keeping the old private name so `migrate_media` and the tests
> still import it). `rerender_image_variants.py` rebuilt every existing file from
> its master: **1117 images, +206 MB**, and the squashed tiers are gone.

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

#### The instance's pick is a pointer, not a copy ([[B288]])

Slice 2's override used to be a **copy**: the instance editor wrote the trait
picture's files onto the setting's rung so a role could point at it. That made one
click in the editor a state change, and it made every variant produced afterwards —
a matte, a loop — belong to the *copy*, so it was visible to that instance alone.

`TraitSetting.picked_image_id` replaces it: the setting **names** one of its
trait's owner-level pictures, and `pick_role_image` prefers it. The rung order is

1. the **picked** owner-level picture — `picked_image_id`;
2. the instance's **own** picture (the variant rung);
3. an owner-level picture in the setting's universe;
4. any owner-level picture.

The pick comes **first** because it is the instance's *chosen* picture, and an
instance that still holds one of `B215`'s copies carries the roles on that copy — a
pick that the copy could outrank would look like it did nothing, which is the exact
complaint this ticket exists for. Nothing is hidden by the order: the pick is shown
in the editor with a Clear control, and clearing it hands the instance back to its
own pictures and then the definition. A variant made on the picked picture is a
render **of that picture**, so every instance that picks it gets it. A pick that
names nothing — a deleted picture, or a variant-owned one — is ignored rather than
fatal, because a stale pointer must not blank a surface.

**The pick answers every role, not only the ones its picture carries**, and that is
not a shortcut: roles are unique per rung (`set_image_roles` strips a role from its
siblings), so at the owner level exactly one picture holds `sheet`. A pick that
answered only the roles its picture carries could therefore only ever name the
picture the ladder already returns — a **provable no-op**, which is what the first
cut of this was until it was measured. Answering every role is also what the copy it
replaces did: on an empty instance rung the sole-image rule gave the copy all three.
Which *render* and tier a role serves stays `ROLE_RENDER`'s decision, so a picked
picture with a matte floats and one without does not.

Verified on the live library 2026-09-26 (a GMC's `qi` setting, then cleared): with
no pick all three roles served the roled definition picture (`ffe974d0`, opaque);
picking `4b409f07` — a matted, **unroled** registry picture — served
`upload_4b409f07_Cutout_Small.webp` for `sheet`,
`upload_4b409f07_XLarge.webp` for `background` and
`upload_4b409f07_Cutout_Large.webp` for `navdot`, each present on disk.

`POST /media/copy`, the editor's `copyImage` and their tests were retired with it.

A trait's images are **cascaded on deletion**: `delete_trait` removes the rows
and the files, because an owner that can own images has to clean them up —
without that, deleting a trait seeds exactly the orphan class
[[data-migration]] is already carrying 25 rows of.

> [!note] Built so far (corrected 2026-09-26)
> Slice 1's media half has **landed**: the owner model, the collection rename and
> backfill, owner-aware resolution and upload, GraphQL `Trait.image(role)`, and
> the registry editor's Image section — upload, remove, and **cut out**.
> **Slice 2 landed too** ([[B212]]): a setting carries its own picture, and since
> [[B288]] it can also **pick** one of the trait's own by pointer instead of copying
> it. A trait picture is **auto-matted** like an occupant's, on upload or on
> generation ([[B214]]) — so the old note that nothing auto-cuts a trait image is
> history, as is the idea that the three partner surfaces are missing.
>
> **Not built:** the trait-shaped **generation** entry point. Animation rides on it:
> the viewer hides Animate for a non-entity owner, so "cutout or animation" on a
> trait picture is cutout today ([[B288]]).

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

## Migrating to tiers ([[B210]])

```bash
docker compose exec api python -m transversal.migrate_image_tiers          # dry run
docker compose exec api python -m transversal.migrate_image_tiers --apply
```

One idempotent pass that folds every old-shape cutout and loop into the picture it
came from, dry-run first. On the live library (2026-09-25) it reported and then
applied:

| | |
| --- | --- |
| records | **1168 → 916** (−224 cutouts, −28 loops) |
| cutouts | 224 found, **224 merged, 0 unmatched** — 1118 matte tiers renamed |
| loops | 43 found → **27 sourced**, 1 superseded, 15 fresh (14 stamped `ai_generated`) |
| files | 27 videos moved onto their pictures, 112 loop still tiers removed, 17 ladders rebuilt |

Nothing is re-rendered: a matte's files are moved byte-for-byte and only a tier
that was missing is rebuilt from the matte's own `Original`. A loop's source is
*recovered* rather than assumed — the animate pipeline re-encodes what it copies,
so byte equality misses almost all of them and a 64-bit average hash finds them.

Re-run it after any window in which older code could have written
`image_type=cutout`/`animated` rows: the pass still recognises those two strings
and folds them in, even though `ImageType` no longer names them. It reads the raw
value for classification and normalises it only so the row validates, which is
what makes the cleanup independent of the enum it is cleaning up.

## REST API

- ~~`POST /media/copy`~~ — **retired with [[B288]]**. It put an existing picture on
  another rung by copying its files and record, and the instance editor used it to
  take one of the trait's own pictures as an instance's override. Copying made a
  click a state change and scoped every later variant to the copy, so picking is now
  a **pointer** — `TraitSetting.picked_image_id`, written through
  `updateTraitSetting(id, input: { pickedImageId })`, `""` to clear.
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
  pictures only. Any owner: `?owner_kind=entity` (default) or `trait`. Adds the
  transparent `cutout` **render** to that picture (see below); refuses a picture
  that already has an `animated` render.
- `POST /imagen/{entity_id}/cancel` — interrupt the active job.
- `GET /imagen/jobs` — active generation/animation jobs + queue position.
- `GET /imagen/loras` — available Flux LoRAs.
- `GET /entities/images?role=&ids=` — batch role-image resolution (used by the
  peers bar to avoid loading images for the whole entity list).
- `GET /imagen/{entity_id}` — list pictures (with `projection_id`, `roles`,
  `flags`, `renders`, `transparent`, `path_large`, `path_xlarge`, `path_cutout`,
  `path_animated`). Any owner id works — a trait's gallery reads through the same
  endpoint.
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

### The role map

`services/media_utils.ROLE_RENDER` is the whole render policy:

```python
ROLE_RENDER = {
    "background": ("animated", "XLarge"),   # the loop if present, else the biggest still
    "sheet":      ("cutout",   "Small"),    # the matte if present, at the small tier
    "navdot":     ("cutout",   "Large"),
}
```

`render_for(role, renders)` falls back to the static tier when the preferred render
is absent, and `RepositoryImages.role_image_url(img, role)` builds the URL from
that. **No caller names a tier** — `Entity.image(role)`, `Trait.image(role)`, the
REST list and the batch endpoints all pass a role and let the record decide. The
matte is tiered like any other render (`{base}_Cutout_Small.webp`, …), because a
matte kept only at master size would send a 2048px transparent WebP for a 240px
portrait.

### A matte is part of making an occupant's or a trait's picture

`wants_auto_matte(owner_kind, owner_type)` (`services/media_utils.py`) decides: an
**occupant**'s picture (CHARACTER, GMC, ASSET — the same set the projection
migration calls occupants) or a **trait**'s is a subject and gets a matte; a
location, universe or faction is a scene and does not; a picture that already
carries a matte is left alone. The breadth is deliberate — one BiRefNet pass per
picture, ~4–7 s on the 4090.

Both entry points use it, so the rule is about *what a picture is* rather than
*when it arrived* ([[B214]]; before, only a projection's **first generated** image
was cut out, and uploads never were):

- **upload** queues the cutout as a `BackgroundTask` — an upload response must not
  wait on the GPU, and the gallery already polls `/imagen/jobs` for that owner, so
  the matte lands on its own a few seconds later;
- **`run_imagen`** cuts out every occupant picture, entity-level generation
  included.

> [!warning] A matte with no subject is a failure, not a render
> Some pictures have nothing the model can find — a scene sitting on an occupant,
> for instance — and BiRefNet then returns a **fully transparent** frame. Recording
> that makes `sheet` and `navdot` serve an invisible picture. It was reachable
> before through the Remove BG button, but the author was looking at the result and
> could undo it; automatically, nobody chose it and nobody is watching. So
> `run_remove_background` **refuses** a matte with no subject: the manual path
> reports the failure, the automatic path is best-effort and leaves the picture
> opaque, which is how it looked before.

### Imagen (static)

`run_imagen` → ComfyUI Flux → `_save_image_variants` (Original/Large/Small/Mini
WebP) → `MediaImage`. If the result is the sole image for its owner, all three
roles are auto-selected.

**An occupant's generated picture also gains a matte** ([[B214]], superseding
`B166`'s first-image trigger — see § A matte is part of making an occupant's or a
trait's picture above). The generated image keeps every role auto-select gave it
and simply gains the `cutout` render, so `sheet` and `navdot` serve the floating
portrait without any role being moved onto a second record. A matte needs a source,
so the trigger is the picture *arriving*, never entity creation — and it is **not**
scoped per projection: an entity-level generation (the gallery's main Imagen
button) is cut out too, while a location's is not. [[B129]] asked for that widening
and is **closed**.

If the matte fails the generation is unaffected: the picture is already recorded
and simply renders opaque, exactly as it would have without the render.

### Remove background (static cutout)

`run_remove_background(owner_id, image_id, display_name)` adds a transparent
`cutout` render to an existing static picture. It is **non-destructive and
additive**: the picture keeps its file, its id, its roles, its credits and its
flags — only `renders` gains `cutout` — and the matte is written into the picture's
own ladder as `{filename}_Cutout_{Tier}.webp`. There is nothing to copy anything
to, which is why a cutout can no longer lose its citation or its labels
([[B204]], [[B203]]), and no role has to be moved for it to render: `sheet` and
`navdot` serve the matte the moment it exists ([[#The role map]]).

It works for **any owner**:
`POST /remove-background/{owner_id}?owner_kind=entity|trait` (`entity` is the
default, so the image viewer's call is unchanged), and both the progress stream
and the job registry at `GET /imagen/jobs` are keyed by `owner_id` — a trait's
picture is cut out under the trait's id exactly as an entity's is under its own.
`owner_id` and `display_name` are only the progress key and the log line; the
**source image id** decides the picture, so a trait has no `Entity` and needs none.

> [!note] A cutout is a render, not a second entry
> The GM gallery lists one row per **picture** and badges it `CUTOUT`; the trait
> editor does the same. Its role checkboxes stay on the picture, because the matte
> is served automatically — an earlier editor moved all three roles onto the
> cutout, which read as an in-place edit and buried the original.
>
> Role assignment is still unique per (owner, role) for the *pictures*: ticking a
> role strips it from whichever sibling picture held it. What changed is that a
> second render no longer needs a role of its own to appear.
>
> Verified on the live stack before the merge: the matte came back RGBA with all
> four corners fully transparent and the subject opaque (70% of pixels
> transparent), while the picture stayed RGB.

Pipeline: read the picture's `Large` variant → upload to ComfyUI →
`bg_remove.json` → BiRefNet → alpha composite → RGBA PNG → **trimmed to the
subject** → `_save_image_variants` under `{filename}_Cutout` → the picture's
`renders`.

**A matte is trimmed to its subject** ([[B213]]). It used to keep the source's
canvas, so a subject that filled a third of the picture was served at a third of
the size its tier allowed — small, and floating in empty space. Now
`trim_transparent_margins` crops it, with two rules worth knowing: content is
alpha **> 8** (a lossy WebP's alpha plane is noisy right across the canvas, so
"any non-zero alpha" would find the full frame and trim nothing), and a margin
thinner than **2% of the short side is not worth a re-encode**, which is also what
makes the pass stable — an exact bounding box would shave a pixel per pass as the
lossy edge bleeds. An already-tight matte is returned byte-identical.

The **source picture is never touched**: its framing is its own, and the record's
`width`/`height` describe that master, not the matte. Because a tier is fitted to
the long side, trimming also makes the subject *sharper* — `Small` spends its
240px on the subject instead of on empty space. The consequence to be aware of is
that a matte's aspect ratio becomes the subject's, which is rarely the canvas's.

```bash
docker compose exec api python -m transversal.trim_cutout_margins          # dry run
docker compose exec api python -m transversal.trim_cutout_margins --apply
```

Run on the live library 2026-09-25: **148 of 225** mattes trimmed, 77 already
tight, 0 left loose after — the worst were being served at half size or worse
(`Lin` covered 42% of its frame). Idempotent: a second pass reports 0. New cutouts
are trimmed by the pipeline itself, so the pass exists only for what predates it.

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

**Animating an existing picture adds the loop to that picture** ([[B210]]): no
still is written, no second record is created, and the video lands beside the
picture's still under the picture's own base name as `{filename}.{ext}` with
`animated_extension` recording the container. The picture's credits, flags and id
are untouched — only `renders` gains `animated` and `flags` gains `ai_animated`.
The animate pipeline generated no still here, so `ai_generated` is not its to
assert; a hand-made upload stays unlabelled.

**A fresh loop is its own picture**: Flux generated the still, so it is
`image_type=imagen` with an `animated` render and both `ai_generated` and
`ai_animated`. "Fresh" is not guessed: the migration established it by matching
each legacy loop's still against its owner's pictures (see [[#Migrating to tiers
(B210)]]).

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

Nothing is redistributed any more. A **projection's first generated image** gains
a matte as a *render* (`B166`), so it keeps all three roles and `sheet`/`navdot`
serve the matte — see [[#Imagen (static)]]. Upload and drop do not cut out.

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
`roles` would make ticking one image's `AI` silently untag every other image of
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
`AI` is a checkbox and the two pipeline labels are read-only, because the
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
- **A derivative keeps the citation by construction.** A matte and a loop are
  **renders of the picture**, not new records, so they inherit its `credits`,
  `license`, `credit_text` and `flags` because they *are* it. The old shape copied
  them onto a second row and a pipeline forgot once ([[B204]]); there is no copy
  to forget now. A loop adds only `ai_animated` — its own claim — and leaves the
  picture's `ai_generated` alone (see [[#Provenance flags (AI)]]).
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
  animate, **Remove BG**, delete. Remove BG is offered only when there is
  something to gain — hidden from a picture that already has a `cutout` render or
  a loop, both read from `renders` rather than guessed from the file type.

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
