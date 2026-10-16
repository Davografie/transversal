---
title: Tenancy Rollout Plan
date: 2026-09-29
last-updated: 2026-09-29
tags:
  - transversal
  - technical
  - tenancy
  - registry
  - plan
aliases:
  - Tenancy Rollout Plan
  - Sandbox Plan
  - Account Plan
  - Registry Rollout
status: draft
---

# Tenancy Rollout Plan

> [!warning] REVISED 2026-10-15 — the phases below assume the package model; the current path is simpler
> The owner replaced the package/sandbox design with **[[Global Multiverse and Forks]]**: one shared
> global multiverse, accounts, and a **verbatim fork** per campaign. That model needs **no** `packages`
> field, closure, reference map or acquisition — so:
> - **Phase 1 stands** (the registry database and accounts), **minus the catalog**; it is now the small
>   routing/permissions table (account → fork → rights on the global).
> - **Phase 2 is reshaped:** provisioning becomes **"clone the canonical database"** instead of
>   "create empty + seed + acquire packages". Its plumbing half — per-request database resolution and
>   the `_db_cache` LRU — is **unchanged and still required**.
> - **Phase 3 stands**, reshaped: the switcher lists your **forks** rather than packages/sandboxes.
> - **Phase 4 largely disappears.** [[B251]] (packages) moves to the **future option** column with
>   [[Content Packages]] and [[Content Registry]].
> - **Phase 5 is unchanged** (enforcement and exposure), and still parked with the platform.
>
> The rest of this document is kept as the **more capable future model**, and its phase structure is
> still the right shape if the sharing work ever returns. Read [[Global Multiverse and Forks]] §7
> before building any of it.

The buildable path from where the code is today to **accounts → forks → a switcher**, which is what
the owner asked for: *"a UI/UX for creating/managing sandboxes, where I can switch between campaigns
and sandboxes connected to my account … and a way to spin up TV instances."*

Design lives elsewhere — [[Identity Programme]] (tenancy, identity, recovery), [[Content Registry]]
(the catalog, sandbox, GPU boundary), [[Content Packages]] (the package mechanism). **This document is
only the order of work**, so it does not repeat their reasoning.

> [!warning] Status — nothing here is built
> Measured on the live tree 2026-09-29: there is **no account concept**, **no campaign concept**
> (only two docstrings that mention the word), **no frontend router at all**, and exactly **two
> ArangoDB databases** (`_system`, `transversal`). The registry database does not exist.
> [[B245]] (SEC-3, identity) is `done`; [[B88]], [[B246]], [[B251]] are `pending`; [[B114]] deferred.

## 1. The question answered: database management, not container orchestration

**Under the architecture already chosen, spinning up a sandbox is a database operation.** The tenant
is an ArangoDB **database**, and one API serves every one of them by resolving campaign → database
**per request** ([[Identity Programme]] §2). So "spin up a TV instance" is:

```
create_database(name) → create its collections → seed shared content → insert one registry row
```

That is a few hundred milliseconds of database work. **No container, no orchestrator.**

Container orchestration would mean each campaign gets its **own API and frontend process** (a port or
a subdomain). Nothing in the requirements needs that, and it is worse on every axis that matters here:
N× memory for N campaigns, N deploys, no shared cache, and — the sharp one — the API would need
**Docker socket access** to spawn its own siblings, which is a container-escape risk in an app whose
open findings already include "the API authenticates nothing". A separate provisioner with a job queue
avoids the escape but is a whole subsystem bought for nothing.

**What is genuinely not isolated under this model, and how it is handled instead:**

| concern | under DB-per-campaign | handled by |
|---|---|---|
| data isolation | **structural** — the database is the wall | ArangoDB itself |
| CPU / memory fairness | not isolated | in-app **quotas at the job-admission choke point** (already the GPU lock's natural place — [[Content Registry]] §5) |
| GPU | one global lock, shared | per-campaign quotas + fair queuing, same choke point |
| app version | one version for all | one deploy — simpler, not worse |
| backup / export / delete | per database | `drop_database` — the reason this model was chosen |

**This becomes orchestration only if** you later want per-campaign **custom domains**, **hard
per-campaign resource caps**, or **per-campaign app versions**. None is a current requirement; each is
a deliberate future purchase, not an accident of the plan.

## 2. The five pieces

| piece | today | where |
|---|---|---|
| **1. Registry database** | does not exist | new — must **not** use `get_db()` |
| **2. Account (central)** | does not exist | new — [[Identity Programme]] §3 |
| **3. Account sessions** | player sessions only | new — a **second session tier** |
| **4. Provisioning** | does not exist | [[B88]] + new service |
| **5. Switcher UI** | no router, single page | new — [[B88]] surface |

**Piece 3 is the subtle one.** SEC-3 built a session **for a player inside a campaign**. An account
session is a *different audience* — it exists before any campaign is chosen and it outlives any one of
them. `api/access_tokens.py` already carries an `aud` claim (`AUD_JOIN` is one), so the precedent for a
distinct `aud` exists; the plan must not conflate the two, or an account session becomes a way to act
as a player and SEC-3 is undone. Identity Programme §3 is explicit that owners/creators hold a central
account and **players never do**.

**Piece 5 has a cost that is easy to miss.** There is **no frontend router** — no `vue-router`, no URL
routing. The Identity Programme §8.4 leaves "campaign in the URL (`/c/<campaign>/…`) versus routing
purely from the cookie" open and recommends the URL. On this codebase the URL form is **new frontend
architecture**; the cookie form is nearly free. That is a decision, not a detail — see §3.

## 3. Decisions needed before building

These are the owner's, and each one changes what gets built:

1. **Routing: campaign in the URL, or cookie-only?** URL means adding a router to a single-page app and
   threading a campaign segment through every surface; cookie-only is free today but makes "two tabs,
   two campaigns" impossible (which Identity Programme §4 wanted).
2. **Who may create campaigns/sandboxes?** Self-service is the intent, but throttling and payments are
   unsettled. **A sandbox is different from a campaign here** — the owner creating their own sandboxes
   needs no throttling; strangers creating campaigns do.
3. **Is a sandbox a campaign with a flag, or a second type?** [[Content Registry]] §4 says a sandbox is
   *"a campaign you have not published"* — reuse the boundary. Confirm, because it decides whether the
   switcher lists one thing or two.
4. **Does a sandbox need a *player* at all?** An architect authoring alone may not want the join-token
   flow at all — the account session may be enough to enter their own sandbox. Worth settling before
   the provisioning service is written, because it decides what gets created alongside the database.

## 4. The phases

Each phase is independently verifiable — that is the point of the ordering.

### Phase 1 — registry + account (foundation; nothing else can land)

- The **registry database**, with its own bootstrap. It must **not** go through `get_db()`, which
  unconditionally creates all 18 campaign collections and would litter the registry.
- `accounts`: id, email, verified-at, recovery methods, created-at. **Email verified at enrolment** —
  Identity Programme §5.3 makes the recovery address the whole credential, so an unverified one is a
  way in.
- `campaigns`: id, name, **database name**, owner account, **kind** (`campaign` | `sandbox`), created-at.
  This is the routing table and the switcher's data source in one.
- **Account sessions** as a distinct audience from player sessions, with the same care SEC-3 applied.
- Auth surface: register → verify → sign in (email link first, per the design) → recover.
- **Verifiable when:** an account can be created, verified and signed into, and its row is the only
  thing that exists — no campaign database yet.

### Phase 2 — provisioning

- **Provisioning service**: create the database, bootstrap collections, seed shared content (the
  registry traitsets/traits/SFX/roll tables a campaign cannot start without), create the owner's
  architect record, mint the first join token, insert the registry row. **Idempotent**, because a
  half-created campaign is worse than none.
- **Per-request database resolution** plus the **`_db_cache` LRU bound** (`db/arango.py:94` holds one
  pool per database for the process lifetime — correct for one campaign, unbounded at a thousand).
  This is [[B88]]'s backend half.
- **Delete/archive** via `drop_database`, which is the property this architecture was chosen for.
- **Verifiable when:** a campaign can be created from the registry and reached, and dropped again.

### Phase 3 — the switcher UI

- Account UI: sign in, account settings, recovery.
- **Switcher**: my campaigns and sandboxes, create one, open one. Executes the §3.1 routing decision.
- Sandbox/campaign distinction per §3.3.
- **Verifiable when:** the owner can create a sandbox, see it and a campaign side by side, and switch
  between them — which is the UI they actually asked for.

### Phase 4 — packages

- [[B251]]: the `packages` dependency field, its closure, and acquisition — so a sandbox can be built
  **from** the registry and a campaign can **acquire** a package.
- **Sequenced last on purpose:** with self-contained packages the `packages` field is empty (see
  [[Content Packages]] §5), so **Phase 2 and 3 do not depend on it**. Authoring an Earth sandbox can
  happen before any of this.

### Phase 5 — going online

[[B246]] (SEC-6, API-wide enforcement) and the exposure lane ([[Public Exposure Plan]]). A separate
gate, listed so it is not mistaken for part of the above.

## 5. What would force container orchestration later

Written down so the decision is visible rather than denied: **custom domains per campaign**,
**hard resource caps**, or **per-campaign app versions**. If any of those becomes a requirement, the
provisioner becomes a real orchestrator and the API must not be the thing holding the Docker socket —
it would need a separate worker with a queue.

## 6. Risks

- **Two session tiers must not blur.** An account session that can act as a player undoes SEC-3. The
  `aud` separation is the control; it needs a test, not a convention.
- **Media does not travel with a database.** `MEDIA_DIR` is a shared filesystem volume, so a sandbox
  and a campaign share one image namespace and a package dump loses every image ([[Content Packages]]
  §7). **Not ticketed.** It blocks "portable package", not the phases above.
- **Migrations must enumerate every campaign database.** One forgotten database is a silent divergence;
  `get_db()`'s bootstrap makes it easy to forget that a schema change is now N changes.
- **Capacity.** [[B88]] and [[B251]] both sit with [[backend-platform]], the busiest session on the
  board, on top of 14 open tickets.
- **The product surface and the package content are unowned** ([[Division of Labor]] § *Unassigned*).
  Phases 1–3 are mechanism; someone still has to own what the switcher *is*.

## 7. Open items

1. The four decisions in §3.
2. Whether the registry and the tenancy table are one database or two. They have different sensitivity —
   one holds recovery identifiers, the other lists campaigns — and [[Content Registry]] §7.5 leaves it
   open.
3. Where the **first join token** comes from when a campaign is provisioned: minted by the provisioner,
   or created by the architect in the Troupe panel afterwards.
4. Whether a sandbox is reachable **before** it has a published package, i.e. is the sandbox the
   authoring surface *and* the playroom, or only the former.

## Log

- 2026-09-29 — written for the owner, who asked what this work actually is (*"is that container
  orchestration? Database management?"*) and for a plan they can follow. Answers it as **database
  management** under the architecture already chosen, with the three conditions that would change that
  written out. Phases ordered so each is verifiable, and Phase 4 deliberately last because
  self-contained packages make the closure engine unnecessary until sharing is wanted. All status
  claims measured on the live tree the same day: no account, no campaign, no router, two databases.
