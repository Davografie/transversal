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
programme behind [[B88]] and the precondition for going online. Security-owned documentation.
The sibling design for the shared content surface is [[Content Registry]].

> [!warning] Design under review — nothing is implemented
> Rewritten twice on 2026-09-26, both times because the owner corrected me. The code still
> behaves exactly as **§7 What this rejects** describes.

## 1. Decisions taken (2026-09-26)

| decision | chosen |
|---|---|
| tenant boundary | **a separate ArangoDB database per campaign**, plus a shared registry |
| campaign ownership | **different people own different campaigns** — friends, and possibly paying architects |
| who may invite | **any member** |
| player registration | **local to the campaign** — no central user register |
| invites | **pure authorization, not identity** — single-use, expiring, owner-visible |
| sessions | **sliding 30-day cookie**; a per-player **epoch** makes eject possible |
| recovery | **multiple methods per campaign** — passkey, mail link, mail + password |
| creators/owners | a **central registry account** (the same one that holds recovery methods); players still have none |
| GPU | **not** in the free tier — all four GPU operations gated ([[Content Registry]]) |

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

## 3. Identity: local players, a session, and one central surface

**Players are campaign-local and already were.** The `Player` document (`domain/players.py`)
lives in that database's `players` collection with `id`, `name`, `role` and spotlight state;
ownership of characters is resolved from `agency` edges. Nothing central is needed — "locally
registered on the campaign" requires **no new entity at all**.

An invite is **authorization, not identity**: it grants campaign access and proves nothing about
who holds it. Accepting one creates the local player and issues a session. There is deliberately
**no per-player credential and no long-lived seat link** — a returning player on a new device
simply takes a fresh invite. (This doc's first draft proposed a reusable per-player "seat link";
the owner's single-use invite is simpler and equivalent, so it wins.)

What the cookie and the player record must carry:

- The session is signed `campaign + player + issued_at` — it must name the campaign, because with
  a database per campaign the request has to be routed *before* anything can be looked up.
- A **sliding 30-day lifetime**, refreshed while the player keeps playing. Implementation note:
  refresh when the remaining life drops below a threshold, not on literally every request, or
  every API response carries a `Set-Cookie`.
- A **per-player `epoch`** on the record, checked when validating the cookie. A signed cookie
  cannot be recalled, so this is the *only* way "remove this person" has an implementation:
  bumping the epoch kills every session that player holds.

**Ejecting** a member is an epoch bump, which is the whole of it. Campaigns are sovereign, and
there is deliberately no way to ban a person across campaigns.

### The one central identity — for owners, not players

Recovery credentials and authored content both need to know who you are *across* campaigns, so
**owners and creators hold a central registry account**, and it is the same account that holds
their recovery methods. This is **not** a contradiction of "no central user register" — that
decision was about *players*, and it stands. The model is two-tier: anonymous-ish campaign-local
players, and account-holding owners/creators.

## 4. The UX

### Create a campaign
The owner names the campaign, enrols at least one **recovery method** (a passkey, an email
address they verify, or an email + password), and becomes its architect. The registry records
campaign → database → recovery methods; the database is created and bootstrapped on first use.
Self-service is the intent, but throttling and payments are still open on the owner's side.

### Invite — any member
In the **Troupe** panel, **Invite** produces a link and a QR *and* a short readable code, so it
works over voice for remote play. Hand it over however you like — group chat, or held up at the
table. **No email is sent and no account is created.**

Each invite is **single-use and expiring**, and the owner can see and revoke the outstanding
ones. That is the whole of admission control: with no per-player identity, possession is the
only thing that can be checked, so the lifetime of the token is the bound on a leaked link.

### Accept an invite
Open the link → you are in *that* campaign → type your name → you are a new local player with a
30-day sliding session, **playing immediately**. This preserves today's "type your name" first-run
feel, and it cannot collide: accepting an invite creates a player, it never adopts one.

### A returning player, new device
They ask a member for a fresh invite — the previous one was spent, so there is nothing to
re-show. This is the model's one standing cost: a player away longer than the session lifetime
needs a new invite.

### Recovery — the owner's way back in
*Recover campaign access* → satisfy **any** enrolled method — a passkey, a single-use mail link,
or email + password → and a **fresh architect session is minted while every old session dies**
(epoch bump), with the other enrolled methods notified. Losing a phone costs a recovery
round-trip, not the campaign.

Multiple methods exist so a campaign cannot be lost, and each is enrolled while already
authenticated. The structural caveat: **a campaign is only as strong as its weakest method**, so
a password door carries rate limiting and lockout, and passkeys are the recommended primary —
phishing-resistant and nothing to type. Adding or removing a method requires holding another one
(or server access).

### Campaign switching
Because the cookie names a campaign and the app needs a campaign in its URL (e.g.
`/c/<campaign>/…`), a person in two campaigns switches with a **campaign switcher**, not by
re-authenticating. Two tabs, two campaigns, no re-login.

### The architect's controls (Troupe panel)
Per member: **Show link · Revoke · Make architect** — where Revoke is the epoch bump. Campaign
wide: the **outstanding invite list** with revoke, and the enrolled recovery methods. The last
architect cannot demote themselves.

## 5. Security consequences — what this model *forces*

1. **Invites are pure authorization and, with no central register, they are the whole of
   admission control.** They cannot be bound to a person, because we never learn who the person
   is. They are therefore **single-use, expiring, revocable and campaign-scoped**, and the owner
   must be able to *see* them. This is the direct consequence of "any member can invite" plus
   "locally registered", and it is the largest risk in the model: a link pasted into the wrong
   chat is live access until it is used or expires.
2. **Any member can invite, so the owner needs visibility and eject.** A member can admit
   someone the owner would not have. That is a legitimate table dynamic, but the owner must be
   able to see the roster and the outstanding invites, and revoke either — otherwise whoever is
   paying cannot manage what they are paying for.
3. **Recovery is the crown jewel, and every method must be verified at enrolment.** Recovery
   reconstitutes the architect's session, so an unverified method *is* a way in: a mistyped
   address sends the single link that hands the campaign to a stranger, and an unverified
   password is a guess away. This is the one place that deserves the verification players do not
   need. Multiple methods multiply the attack surface — each is a door — so all need the same
   care, and the weakest sets the campaign's strength.
4. **The registry is the PII honeypot and the enumeration surface.** It is the only place
   mapping a recovery identifier → campaign. Lookups must be rate-limited and must answer
   identically whether or not an identifier has a campaign, or it becomes a directory of who
   plays what. Recovery sends are capped per address and per campaign.
5. **Recovery replaces the session set rather than adding one** — the epoch bump is what makes a
   stolen or lost device stop working at the same moment.
6. **Lockout is the residual risk, and it is why recovery is plural.** With several enrolled
   methods, losing one device or one mailbox is survivable; losing *all* of them still leaves the
   database, so server-side access is the honest fallback. Printable recovery codes would close
   even that — see §8.
7. **Invite tokens must be self-describing.** The link has to say *which campaign* before any
   database can be opened, so the token carries a signed `campaign + invite + expiry` payload.
   The campaign database then holds the invite record, so authenticity comes from the signature
   and liveness from the record — no global invite index is needed.
8. **The outbound-email surface is tiny — this is the model's quiet win.** Only recovery ever
   sends mail, and rarely. No per-player verification, no notifications, no digests. The SMTP
   provider is one secret and one dependency, and the abuse case (invite spam getting your domain
   blacklisted) largely disappears because nobody can trigger a send by inviting.

## 6. Machines: MCP and the e2e harness

- **MCP** talks to the API over stdio and is unauthenticated today. Each campaign should carry a
  **service credential** for it, so its writes are attributable and it is not a browser session.
- **The e2e harness** currently logs in by writing `localStorage.playerId` and never exercises
  auth. It should use the **real** path — accept an invite for the `DSH MCP` player in the test
  campaign — which keeps the suite working *and* makes it test what it was skipping.

## 7. What this rejects

- **A global account per *player* / central user register.** Rejected by the owner: players are
  campaign-local, and a player in two campaigns has two unrelated records. Correct — and it means
  revoking someone from one campaign cannot touch another. **Owners and creators are a separate
  matter** and do hold a central account (§3), because their recovery methods and authored
  content are theirs across campaigns.
- **Email per player.** There is no player email at all. Only recovery ever sends mail.
- **A per-player seat link.** This doc's first draft proposed one for re-entry; the owner's
  single-use invite is simpler and equivalent, so it wins.
- **`universe` as the tenant.** See §2 and SEC-8.
- **The old name-adoption flow.** Typing an existing player's name currently makes you that
  player; it will create a *new* player instead, and never adopt an existing one. Character and
  perspective switching are untouched — they are not identity claims.
- **A shared static `ACCESS_TOKEN` as the door.** Superseded by per-campaign invites; the outer
  perimeter survives only as the tailnet/LAN wall.

## 8. Open items

1. **Invite expiry window** — single-use is decided; how long before it must be reissued (~24h?
   a week?).
2. **Which recovery methods ship first** — passkey and mail link are the safe pair; the password
   door needs rate limiting and lockout before it is worth offering.
3. **Campaign in the URL** — `/c/<campaign>/…` with a switcher (recommended) versus routing
   purely from the cookie.
4. **Who creates campaigns** — self-service is wanted, but throttling and payments are unsettled
   on the owner's side, and GPU is *not* in the free tier. See [[Content Registry]].
5. **Sequencing** — SEC-3 (identity) first, then the campaign boundary (SEC-8), then SEC-6
   (API-wide enforcement). SEC-6 is what makes the others mean anything, and the campaign
   database boundary is what the marketplace ([[B114]]) is gated on.

## Log

- 2026-09-26 — first draft: player records + seat credentials, options for who may create a
  seat. Recommended new-names-self-serve.
- 2026-09-26 — **rewritten to the owner's model.** Owner rejected the global-account/central-
  register approach: players local to the campaign, invites the only admission path. Tenancy
  decided as **database per campaign + shared registry**; campaigns owned by different people;
  **any member may invite**. Corrected the doc's own error — `universe` is a fictional world
  inside a campaign, not the tenant — and filed the same correction against SEC-8.
- 2026-09-26 — **second correction, from the owner.** (a) An invite is *authorization, not
  identity*, and I had wrongly called it a credential; the control that actually matters is that
  it is single-use and expiring. (b) The per-player seat link is dropped in favour of a fresh
  invite. (c) Sessions are a sliding 30-day cookie; because a signed cookie cannot be recalled,
  a per-player **epoch** is what makes eject implementable. (d) Recovery becomes plural — passkey,
  mail link, mail + password — which introduces the **one central identity**, for owners and
  creators only, while players stay campaign-local. Implementation **not** started.
