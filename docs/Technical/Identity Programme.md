---
title: Identity Programme
date: 2026-09-26
last-updated: 2026-09-26
tags:
  - transversal
  - technical
  - security
  - auth
  - authorization
  - multi-tenancy
  - design
aliases:
  - Identity Programme
  - Identity UX
  - Campaigns
status: draft
---

# Identity Programme

The design for **SEC-3 / SEC-6 / SEC-8**, the tenant boundary, and the invitation model — the
one programme behind [[B88]] and the precondition for going online. Security-owned
documentation.

> [!warning] Design under review — nothing is implemented
> Rewritten 2026-09-26 to the owner's model. The code still behaves exactly as **§7 What this
> rejects** describes. An earlier draft of this doc modelled a global account per player; the
> owner rejected that, and **§3** is the corrected model.

## 1. Decisions taken (2026-09-26)

| decision | chosen |
|---|---|
| tenant boundary | **a separate ArangoDB database per campaign**, plus a small shared registry |
| campaign ownership | **different people own different campaigns** — friends, and possibly paying architects |
| who may invite | **any member** |
| player registration | **local to the campaign** — no central user register |
| email | **exactly one recovery address per campaign**, for access recovery only |

## 2. The tenant is a *campaign*, not a `universe`

This doc previously treated `universe` as the tenancy key. **It is not.** `UNIVERSE` is an
entity type in the live DB — The Emberline, the Dreamlands, Valhalla, Chromotopia, One Piece,
Ælor Cıtar, … — an entity holds `Projection`s into several of them, and `traits` is documented
as a "trait registry **per universe**". A troupe *travels between* universes; that is the whole
premise of the Transversal. Universes partition content **inside** a campaign.

And there is **no campaign concept in the code at all** — `grep -i campaign` across
`src/api/src` and `src/frontend/src` returns one unrelated `localStorage` comment. So the entire
database is today one implicit campaign. See the corrected **SEC-8** in [[Security Posture]].

### Why a database per campaign

`_id` handles are **database-local**, and so are edges and graphs — `relationships` and
`traitsettings` store `_from`/`_to` as `entities/loc-123`, meaningful only in their own
database, and there is no cross-database AQL join. Sharing an authored universe between
campaigns is therefore a **deep copy with every handle remapped**.

That looks like the argument against this choice — until you notice **you need copy-on-acquire
anyway**. If Margaret acquires Harold's Varenya, Harold's later edits must not silently mutate
her live game; you want a version-pinned snapshot with an explicit "update available" pull.
That is a publish/version mechanism in *either* architecture. So the shared-database
alternative's sharing advantage largely evaporates, while its cost does not: isolation would
rest entirely on every resolver, every query and every MCP tool filtering by campaign, in a
codebase where SEC-1 was a raw AQL string interpolation. Arango has no row-level security.

What structural isolation buys, concretely:

- **A query bug cannot cross campaigns.** The database is the wall, not the discipline.
- **Per-campaign export, backup and delete** — `drop_database`. With different owners and
  possible payment, "delete my campaign" is a product requirement, not a nicety.
- **Per-campaign resource limits.**

What it costs:

- The registry below, because "which campaigns exist?" has no home inside any campaign DB.
- Migrations must enumerate every campaign database.
- **Per-request database resolution** — today `get_db()` reads the database from env once per
  process. Serving many campaigns means resolving campaign → database per request.
- **`_db_cache` has no eviction** (`db/arango.py:94`). It holds one connection pool per
  database for the process lifetime — correct for one campaign, unbounded at a thousand. It
  needs an LRU bound.
- The registry must not use `get_db()`: that path unconditionally creates all 18 campaign
  collections and their indexes, which would litter the registry.

The bootstrap is otherwise already on our side: `get_db()` creates the database and all 18
collections on first connect, so a new campaign's schema appears by pointing at a new name.

**[[B88]] is jointly owned with [[backend-platform]]** — the boundary design is mine, the
database plumbing (resolution, cache, migrations) is theirs.

## 3. Identity: local players, one recovery email

**Players are campaign-local and already were.** The `Player` document (`domain/players.py`)
lives in that database's `players` collection with `id`, `name`, `role` and spotlight state;
ownership of characters is resolved from `agency` edges. Nothing central is needed — "locally
registered on the campaign" requires **no new entity at all**.

Three things are added:

- A **seat credential** on the player record (stored hashed) plus a **seat version**.
- The session cookie becomes signed `campaign + player + seat_version + issued_at` — it must
  name the campaign, because with a database per campaign the request has to be routed
  *before* anything can be looked up.
- **One recovery email per campaign**, held in the registry, attached to the campaign's
  architect. It is the only email address in the system and exists solely to get the owner back
  in.

**Revoking** a seat bumps its version, killing every cookie for that player — the control the
architect has never had. **Ejecting** a member is revoking their seat, which is the whole of it:
campaigns are sovereign, and there is deliberately no way to ban a person across campaigns.

## 4. The UX

### Create a campaign
The owner names the campaign, gives a **recovery email**, and proves it (a link). They are its
architect. The registry records campaign → database → recovery email; the database is created
and bootstrapped on first use.

### Invite — any member
In the **Troupe** panel, **Invite** produces a link and a QR *and* a short readable code, so it
works over voice for remote play. Hand it over however you like — group chat, or held up at the
table. **No email is sent and no account is created.**

### Accept an invite
Open the link → you are in *that* campaign → type your name → you are a new local player and
**playing immediately**. This preserves today's "type your name" first-run feel, and it cannot
collide: accepting an invite creates a player, it never adopts one. (Adopting an existing player
needs that player's own seat link — §7.)

### A returning player, new device
Open the **seat link** the architect shows them (same Troupe row, *Show link*). Bound; no
typing. A brand-new name typed at the door stays self-service as today.

### Recovery — the owner's way back in
*Recover campaign access* → enter the recovery email → a single-use, short-lived link mints a
**fresh architect seat and bumps the seat version**, so every old session dies. Losing a phone
therefore costs a recovery round-trip, not the campaign.

### Campaign switching
Because the cookie names a campaign and the app needs a campaign in its URL (e.g.
`/c/<campaign>/…`), a person in two campaigns switches with a **campaign switcher**, not by
re-authenticating. Two tabs, two campaigns, no re-login.

### The architect's controls (Troupe panel)
Per member: **Show link · Revoke · Make architect**. Campaign-wide: the **outstanding invite
list** with revoke, and the recovery email. The last architect cannot demote themselves.

## 5. Security consequences — what this model *forces*

1. **Invites are bearer credentials, and with no central register they are the whole of
   admission control.** An invite cannot be bound to a person, because we never learn who the
   person is. So invites must be **expiring, single-use by default, revocable, and
   campaign-scoped**, and the owner must be able to *see* them. This is the direct consequence
   of "any member can invite" plus "locally registered", and it is the largest risk in the
   model: a link pasted into the wrong chat is live membership until revoked.
2. **Any member can invite, so the owner needs visibility and eject.** A member can admit
   someone the owner would not have. That is a legitimate table dynamic, but the owner must be
   able to see the roster and the outstanding invites, and revoke either — otherwise whoever is
   paying cannot manage what they are paying for.
3. **The recovery email must be verified, and it is the crown jewel.** If it is merely typed
   in, a typo sends the one link that reconstitutes the architect's seat to a stranger. A click
   to prove control is what makes recovery safe. This single address protects the whole
   campaign, so it deserves the verification the players do not need.
4. **The registry is the PII honeypot and the enumeration surface.** It is the only place
   mapping email → campaign. Lookups must be rate-limited and must answer identically whether
   or not an email has a campaign, or it becomes a directory of who plays what. Recovery sends
   are capped per address and per campaign.
5. **Recovery replaces the seat rather than adding one** — the version bump is what makes a
   stolen or lost device stop working at the same moment.
6. **Lockout is the residual risk.** One email, and if the owner loses their devices *and* the
   mailbox, the campaign is unrecoverable through the app. The database still exists, so
   server-side access is the honest fallback. A second recovery address or printable recovery
   codes would close it — see §8.
7. **Invite tokens must be self-describing.** The link has to say *which campaign* before any
   database can be opened, so the token carries a signed `campaign + invite + expiry` payload.
   The campaign database then holds the invite record, so authenticity comes from the signature
   and liveness from the record — no global invite index is needed.
8. **The outbound-email surface is tiny — this is the model's quiet win.** Only recovery sends,
   rarely. No per-player verification mail, no notifications, no digests. The SMTP provider is
   one secret and one dependency, and the abuse case (invite-spam getting your domain
   blacklisted) largely disappears because nobody can trigger a send by inviting.

## 6. Machines: MCP and the e2e harness

- **MCP** talks to the API over stdio and is unauthenticated today. Each campaign should carry
  a **service seat** for it, so its writes are attributable and it is not a browser credential.
- **The e2e harness** currently logs in by writing `localStorage.playerId` and never exercises
  auth. It should use the **real** path — accept a seat/invite for the `DSH MCP` player in the
  test campaign — which keeps the suite working *and* makes it test what it was skipping.

## 7. What this rejects

- **A global account per player / central user register.** Rejected by the owner: players are
  campaign-local, and a player in two campaigns has two unrelated records. Correct — it also
  means revoking someone from one campaign cannot touch another.
- **Email per player.** There is exactly one address per campaign, for recovery. Notifications
  and per-player verification are out of scope.
- **`universe` as the tenant.** See §2 and SEC-8.
- **The old name-adoption flow.** Typing an existing player's name currently makes you that
  player. It will tell you the seat is taken and to ask for its link. Character/perspective
  switching is untouched — it is not an identity claim.
- **A shared static `ACCESS_TOKEN` as the door.** Superseded by per-campaign seats; the outer
  perimeter survives only as the tailnet/LAN wall.

## 8. Open items

1. **Invite lifetime** — single-use with a short expiry (recommended, given bearer semantics),
   or reusable-until-revoked for convenience? Recommendation: single-use, ~24h, revocable, with
   the owner's invite list visible.
2. **Lockout** — is one recovery address enough, or add a second address / printable recovery
   codes?
3. **Campaign in the URL** — `/c/<campaign>/…` with a switcher (recommended) versus routing
   purely from the cookie.
4. **Seat lifetime** — keep 30 days, shorten it, or make the architect's Revoke the only expiry
   that matters?
5. **Who creates campaigns** — self-service, or provisioned? This is the business half of
   [[B88]] and it determines whether the registry needs a public entry point.
6. **Sequencing** — SEC-3 (identity) first, then the campaign boundary (SEC-8), then SEC-6
   (API-wide enforcement). SEC-6 is what makes the others mean anything, and the campaign
   database boundary is what the marketplace ([[B114]]) is gated on.

## Log

- 2026-09-26 — first draft: player records + seat credentials, options for who may create a
  seat. Recommended new-names-self-serve.
- 2026-09-26 — **rewritten to the owner's model.** Owner rejected the global-account/central-
  register approach: one recovery email per campaign, players local to the campaign, invites are
  the only admission path. Tenancy decided as **database per campaign + shared registry**;
  campaigns owned by different people; **any member may invite**. Corrected the doc's own error
  — `universe` is a fictional world inside a campaign, not the tenant — and filed the same
  correction against SEC-8 in [[Security Posture]]. Implementation **not** started.
