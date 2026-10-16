---
title: Content Registry
date: 2026-09-26
last-updated: 2026-09-26
tags:
  - transversal
  - technical
  - security
  - multi-tenancy
  - entitlements
  - design
aliases:
  - Content Registry
  - Content Sandbox
  - Catalog
status: draft
---

# Content Registry

The shared, cross-campaign surface: a **read-only registry** where created content can be seen,
and a **sandbox** where architects author their own content before sharing or loading it. Plus
the **GPU entitlement** boundary that self-service campaign creation needs.

Sibling design: [[Identity Programme]] (tenancy, identity, invites, recovery). Security-owned
documentation of the trust boundaries; the browsing UX, curation and pricing are **not** mine —
this doc marks where my scope ends.

> [!warning] RETAINED AS FUTURE WORK — this is not the current direction
> As of **2026-10-15** the multi-tenancy direction is the simpler **[[Global Multiverse and Forks]]**
> model: one shared global multiverse, accounts, and a **verbatim fork** per campaign. Under that
> model **only one part of this document survives as current** — the small routing/permissions table
> (account → fork → edit rights on the global), which is §2's "tenancy registry" idea. The **catalog**
> — browsing, curation, publishing, versions, and the **GPU entitlement** boundary in §5 — belongs to
> the future column with [[Content Packages]] and the parked marketplace ([[B114]]).
> See [[Global Multiverse and Forks]] §4 and §7.

> [!warning] Design under review — nothing is implemented
> Written 2026-09-26 from the owner's direction. No code changed.

## 1. Decisions taken (2026-09-26)

| decision | chosen |
|---|---|
| exposure at first | **tailnet-only**, not the public internet |
| registry content | **read-only for viewers**; creators manage their own |
| sandbox | architects build campaigns before sharing/loading them |
| GPU | **not** in the free tier for other architects — no imagen, no animate; **cutout included** (see §5) |
| throttling/payments | **unsettled** on the owner's side |

## 2. Why this is the hard half of B88

[[Identity Programme]] decided a **database per campaign** for structural isolation. This
registry is the opposite kind of thing: **cross-campaign by definition**. It is where the
isolation boundary is deliberately crossed, so it needs its own home and its own rules.

It is *not* the same as the tenancy registry — that one is a small routing table (campaign →
database → recovery methods) which must never use `get_db()`, because that path unconditionally
creates all 18 campaign collections. The content catalog needs its own schema and its own
bootstrap, and it holds **no live play state**: no entities-in-play, no player records, no
campaign messages. If content can be browsed, it must be content that was *published*, never
content that happens to exist.

## 3. Creator identity — the central account

"Create and manage their **own** content" requires knowing who you are **across** campaigns.
That is a central account, and it is the same account [[Identity Programme]] §3 introduces for
recovery — one identity holding your campaigns and your authored content. Recovery is
**email-link only at first** (passkeys and passwords are deliberate later additions), so the
address is the whole credential for now and is verified at enrolment.

This does **not** contradict "no central user register": that decision governs **players**, who
stay campaign-local and account-less. The model is two-tier, and deliberately so:

| | identity | lives in |
|---|---|---|
| player | none — a name in one campaign | that campaign's database |
| owner / creator | central account (passkey / mail / password) | the shared registry |

## 4. The sandbox is a campaign you have not published

The cheapest coherent design is to **reuse the campaign boundary**:

- **Build** — you work in your own campaign database, as normal.
- **Share** — you publish selected content to the catalog.
- **Load** — someone else acquires it into their campaign.

The domain already carries publication vocabulary — `entities` has `hidden`, `unpublished` and
`known_to` — so "published" is an extension of an existing idea rather than a new one. (Those
fields mean GM-drafting visibility *inside* a campaign today; catalog publication is a second,
outer sense and should probably be its own field rather than an overload.)

## 5. GPU entitlement — the boundary as the code actually is

The free tier gets **no GPU**. That is simple to state and, as the code stands, easy to get
wrong, because the obvious split is not the real one.

**There are four GPU operations, not two.** Every one of them acquires the orchestrator's single
global lock:

```
run_imagen              → async with self._gpu_lock   (imagen/orchestrator.py:188)
run_animate             → async with self._gpu_lock   (:372)
run_upscale             → async with self._gpu_lock   (:658)
run_remove_background   → async with self._gpu_lock   (:754)
```

- **`cutout` is `remove-background`, and it is GPU-backed.** It is served by the same ComfyUI
  container declared `capabilities: [gpu]` in `docker-compose.yaml`. So "cutout is fine but
  imagen and animate aren't" has nothing to hang on as built — and this doc originally recorded
  the owner's assumption that cutout was free. **Decided 2026-09-26: gate all four.** Making
  cutout genuinely free would mean moving it to a CPU implementation (rembg/onnxruntime), which
  is its own project.
- **`upscale` is a fourth operation** that a gate written against "imagen and animate" would
  have left open — an unmetered route to the same GPU.

Two more requirements:

1. **Enforce at job admission, server-side.** The orchestrator's lock is the natural choke point.
   The frontend's `canCutOut` / `canUpscale` (`components/image/imageMeta.js`) are *image-state*
   predicates — "does this record support it" — not entitlements, and they gate nothing: the REST
   routes in `api/rest/imagen.py` and the MCP server both bypass the UI.
2. **The single global lock means one campaign can starve every other.** A yes/no entitlement is
   not enough for a self-service platform; per-campaign **quotas and fair queuing** belong at the
   same choke point. There is currently **no quota or entitlement concept anywhere in the API** —
   every "gpu" hit is the lock or memory cleanup.

Throttling is therefore the honest answer to the owner's open question: the mechanism already
exists (one serialization point), it simply has no policy attached.

## 6. Exposure boundary

Tailnet-only first, which is the right call for two reasons: it lets the registry be built and
used without reopening the go-online gate, and it keeps the first public surface a deliberate
step rather than a side effect.

When it does face the internet, the boundary rules are:

- **Not the same process, not the same database** as live campaigns. A read-only catalog is the
  cheapest thing to expose safely precisely because it shares nothing with play.
- **SEC-3 and SEC-6 must have landed.** A public surface served by an API that authenticates
  nothing is the whole of the current posture undone in one step.
- **No PII, no live play state, no player records** — published content only.
- Content is **user-authored**, so the SEC-4 class applies (stored XSS via uploaded SVG was
  closed by refusing SVG; public images reopen every question about what a served file can do on
  another origin), and [[B204]]'s credits/licence fields are what make attribution and rights
  expressible.
- **Moderation is out of my scope and is a real gate.** Public user-uploaded images carry
  illegal-content obligations that no amount of sandboxing answers. Flagging it, not designing it.

## 7. Open items

1. **Public read-only vs public-with-accounts** — is browsing anonymous once it goes public, or
   does it require a creator account?
2. **What "published" means for a whole campaign** versus individual assets — publish the
   universe and its locations together, or atomically per entity?
3. **Update flow** — copy-on-acquire is decided in principle; does an acquirer see "author
   published a new version", and can they pull it without losing local edits?
4. **Quota shape** — per campaign, per creator, or per account? And does a free tier get a
   *little* GPU rather than none, once fair queuing exists?
5. **Catalog home** — its own database, or a schema in the tenancy registry? They have different
   sensitivity (one holds recovery identifiers, one holds published content).
6. **Ownership** — this is [[B88]] / [[B114]] territory; the isolation and entitlement boundaries
   are mine, the product surface is not yet owned by anyone.

## Log

- 2026-09-26 — written from the owner's direction. Records the GPU finding that **cutout and
  upscale are GPU operations** (both take `_gpu_lock`), correcting the assumption that cutout was
  free; all four are to be gated. Exposure decided **tailnet-only** first. Design split out of
  [[Identity Programme]] at the owner's instruction. Implementation **not** started.
