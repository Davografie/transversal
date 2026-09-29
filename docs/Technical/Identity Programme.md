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

> [!success] SEC-3 is landed and live
> The first slice (SEC-3 alone, against the current single database, no campaigns) is merged to
> `release-build` and running. Backend: **2333 tests pass**, including a flow test that drives the
> whole passage against the real database. Frontend builds and is rewired to ask the server who it
> is. **Verified live** on the running stack: architect entry, opening a window, a device joining
> with no player, claiming, an architect revoke ejecting that device from `/session` *and*
> `/roster`, and a closed token refusing further entry.
>
> `ARCHITECT_TOKEN` is required in `.env` **and must be named in `docker-compose.yaml`** — compose
> only passes the variables a service lists, so putting it in `.env` alone leaves the container
> without it. SEC-6 and SEC-8 (campaigns, the registry) are still design only.

## 1. Decisions taken (2026-09-26)

| decision | chosen |
|---|---|
| tenant boundary | **a separate ArangoDB database per campaign**, plus a shared registry |
| campaign ownership | **different people own different campaigns** — friends, and possibly paying architects |
| who may invite | **any member** |
| player registration | **local to the campaign** — no central user register |
| the token | **admits to the campaign, not to a player** — reusable, ~30 min, one QR for the whole table, closable early |
| the player | **taken after admission** — new or existing; there is no per-player secret |
| sessions | **sliding 30-day signed cookie** carrying the campaign **and the player taken**; revoking that account ends its sessions |
| architect accounts | **never takeable** — reached only through the recovery email link, so a member cannot promote themselves |
| hard eject | **rotate the campaign's access** — revoke every session and mint a new token; everyone re-admits and re-takes their account, and the **recovery link is auto-sent** to the architect |
| **first slice** | **SEC-3 only, against the current single database** — campaigns, the registry and per-campaign databases come later as their own change, because SEC-8 is a migration of live game data |
| taking a player | **pick from the campaign roster**, not by typing a name — a typo would otherwise silently create a permanent duplicate |
| recovery | **email link only at first** — passkey and password are deliberate later additions |
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

The token is **authorization to the campaign, not to a player**: it proves nothing about who
holds it, and it says nothing about which player the holder will be. Accepting it issues a
campaign session; the **player is then taken** — a new record, or an existing one (§4). There is
no per-player secret anywhere, and that is deliberate.

The campaign is therefore the **only identity boundary**, and within it players are mutually
trusted: taking a player account is how you assume that character, and nothing stops one member
taking another's. See §5.1 and §5.9.

What the cookie and the player record must carry:

- The session is **signed** and carries `campaign + player_taken + issued_at + epoch`. It must
  name the campaign, because with a database per campaign the request has to be routed *before*
  anything can be looked up — and it names the **player taken**, so the architect can act on that
  account. The signature stops a client editing it; but because *taking* is free within a
  campaign, the server must additionally refuse to take an **architect** account (§4). A signed
  session naming one must never be issuable to a member — an unsigned player id in a cookie would
  be exactly SEC-3 again.
- A **sliding 30-day lifetime**, refreshed while the player keeps playing. Implementation note:
  refresh when the remaining life drops below a threshold, not on literally every request, or
  every API response carries a `Set-Cookie`.
- A **per-player epoch** on the record, checked when validating the cookie. A signed cookie
  cannot be recalled, so this is the *only* way "remove this person" has an implementation:
  bumping the epoch kills every session that player holds.

**Ejecting** a member is **revoking on their player account** — an epoch bump that ends every
session bound to it. It deliberately does **not** delete the player: their characters are entities
owned through `agency` edges, and deleting the record would orphan them.

Per-member revocation alone is **soft**, because it cannot remove someone who still holds a valid
token — they take another account, or make one. So the **real eject is rotating the campaign's
access**: revoke *every* session (a campaign-wide epoch bump) and mint a new join token. The owner
hands the new token to the people they want to keep, and everyone **re-admits and re-takes their
own account**. The excluded person is simply not given it.

That is a deliberately expensive act — the whole table re-onboards — which is exactly why it is the
answer to "I need this person gone" rather than something that happens by accident.

**Rotating signs the architect out too, so the recovery link is auto-sent as part of the act.** This
is the mechanism, not a convenience: the rotation kills every session including the one that
triggered it, and the emailed link is how the architect gets back in. Two useful properties fall
out of that. It proves the architect still controls the recovery mailbox at the moment they most
need to, and it doubles as a notification — if someone else rotated the campaign, the owner finds
out because a link arrives unprompted.

Concretely:

- the auto-send **is** the ordinary recovery flow, invoked automatically — one mechanism, one set of
  controls (single-use, short-lived, rate-limited), and the manual path stays available as the
  fallback if the send fails;
- the architect re-enters **through that link only**. They must not use the new join token: architect
  accounts are not takeable, so it would not admit them anyway;
- the new join token is **not** bundled into the email. It is handed out separately, by QR or chat,
  to the people the architect chooses. Putting campaign access inside the recovery mail would make
  one intercepted message both the way in *and* the way in for everyone else;
- rotation is architect-only, so a member cannot trigger it or flood the mailbox with it. Rate-limit
  it regardless, so a double-click cannot send twice.

One hazard this creates, stated plainly: **a rotation is a one-way door if the recovery mailbox is
dead.** By the time the mail is attempted, every session is already gone — so a *transient* send
failure is recoverable through the manual flow, but an address nobody can reach leaves the campaign
reachable only through server-side access. The address is verified at enrolment for exactly this
reason, and the rotation confirmation should say so rather than let it be discovered afterwards.

The rotation is only as strong as the distribution of the new token — anyone who receives it can
take any account, which is the standing property of campaign-level admission.

### The one central identity — for owners, not players

Recovery credentials and authored content both need to know who you are *across* campaigns, so
**owners and creators hold a central registry account**, and it is the same account that holds
their recovery address. This is **not** a contradiction of "no central user register" — that
decision was about *players*, and it stands. The model is two-tier: anonymous-ish campaign-local
players, and account-holding owners/creators.

## 4. The UX

### Create a campaign
The owner names the campaign, gives a **recovery email address** and verifies it, and becomes its
architect. The registry records campaign → database → recovery address; the database is created
and bootstrapped on first use. Self-service is the intent, but throttling and payments are still
open on the owner's side.

### Admission — one token for the whole table
In the **Troupe** panel, **Admit players** opens a **campaign join token**: one token, shown as a
QR and as a short readable code (for voice), valid for a short period — **~30 minutes** by
default. Everyone scans the same one. There is no per-participant link to regenerate, and it can
be **closed early** without waiting for the clock.

The token grants **campaign access**. It is not a claim about who you are.

### Taking a player
Once admitted, you **take a player**: type a name that does not exist and a new local player
record is created, or take an **existing** player — which is exactly how a returning player gets
back onto a new device, with their characters intact. You then hold a 30-day sliding session
bound to that player.

That is the whole of re-admission, and it needs no architect action: any member opens a token,
and the returning player takes their own account. *(An earlier draft of this section proposed a
per-player "targeted window" for this; the owner's model makes it unnecessary.)*

**The token is the security bound, and the bound is campaign-shaped.** Anyone who obtains it
inside its life is in the campaign and may take any player in it, so:

- a leaked token admits an outsider **and hands them every player in the campaign** — the blast
  radius is the campaign, not a player, unlike every earlier draft of this doc;
- **architect accounts are the one exception and must not be takeable**, or a member could
  promote themselves to owner. The architect enters through the recovery email link instead.

### Recovery — the owner's way back in
*Recover campaign access* → enter the recovery address → a **single-use, short-lived email link**
→ a fresh architect session is minted while every old session dies (epoch bump). **Email is the
only method for now**; passkeys and passwords are deliberate later additions (§8).

The same flow fires **automatically when campaign access is rotated**, because rotation kills the
architect's own session — see §3. That is the only other trigger, and it is why mail is no longer
strictly "recovery only".

The consequence to keep in view: with one method, **the mailbox is a single point of failure for
the campaign**, and mailbox compromise is campaign compromise. So the address is verified at
enrolment, links are single-use and short-lived, sends are rate-limited per address and per
campaign, and lookups never reveal whether an address has a campaign.

### Campaign switching
Because the cookie names a campaign and the app needs a campaign in its URL (e.g.
`/c/<campaign>/…`), a person in two campaigns switches with a **campaign switcher**, not by
re-authenticating. Two tabs, two campaigns, no re-login.

### The architect's controls (Troupe panel)
Per member: **Revoke · Make architect** — *Revoke* is the epoch bump on that player's account.
Campaign wide: **open a join token**, **close it / close all**, **rotate access** — the hard eject,
behind a confirmation that spells out what it does to the whole table *and* that it will sign the
architect out and email them a link back in — and the recovery address.
The last architect cannot demote themselves, and **an architect account is never takeable**.

## 5. Security consequences — what this model *forces*

1. **The token is the whole of admission control, and its blast radius is the campaign.** It
   cannot be bound to a person — we never learn who the person is — and it does not name a
   player, so a **reusable** token trades use-count for a short life: it admits everyone who scans
   it until it expires or is closed, and each of them may then take **any** player in the
   campaign. That is a deliberate trade for the table ritual (one QR, no per-person links), and
   the accepted consequence is that a leaked token is full access to the campaign's play surface
   for its lifetime. Hence: short expiry, close-early, high entropy, a join cap, a visible
   roster, and **architect accounts excluded from taking**.
2. **Any member can admit, so the owner needs visibility, and exclusion is all-or-nothing.** A
   member can open a token and admit someone the owner would not have. Per-member revocation
   cannot keep anyone out on its own, because the token is what admits and any member can open
   one; the mechanism that *does* exclude is **rotating the campaign's access** — every session
   revoked, a new token, the whole table re-onboards (§4). Expensive, deliberate and effective,
   which is the right shape for "I need this person gone", and worth knowing before someone is
   paying for a campaign: you cannot quietly remove one person without disturbing everyone.
3. **Recovery is the crown jewel, and the address must be verified at enrolment.** Recovery
   reconstitutes the architect's session, so an unverified address *is* a way in — a mistyped one
   sends the single link that hands the campaign to a stranger. This is the one place that
   deserves the verification players do not need. With email as the only method, the mailbox is
   the campaign's **single point of failure**, and that is the debt a second method pays off.
4. **The registry is the PII honeypot and the enumeration surface.** It is the only place
   mapping a recovery identifier → campaign. Lookups must be rate-limited and must answer
   identically whether or not an identifier has a campaign, or it becomes a directory of who
   plays what. Recovery sends are capped per address and per campaign.
5. **Recovery replaces the session set rather than adding one** — the epoch bump is what makes a
   stolen or lost device stop working at the same moment.
6. **Lockout is the residual risk.** With email as the only method, losing the mailbox means the
   campaign is unrecoverable through the app; the database still exists, so server-side access is
   the honest fallback. A second method — or printable recovery codes — would close it. See §8.
7. **The join token must be self-describing.** It has to say *which campaign* before any database
   can be opened, so it carries a signed `campaign + token + expiry` payload. The campaign
   database holds the token record, so authenticity comes from the signature and liveness (open,
   unexpired, unclosed) from the record. No global index is needed.
8. **The outbound-email surface is tiny — this is the model's quiet win.** Mail goes out on exactly
   two triggers: a manual recovery request, and the automatic link after a rotation. Both are rare,
   both are architect-scoped, and there is **no per-player mail at all** — no verification, no
   notifications, no digests. The SMTP provider is one secret and one dependency, and the abuse case
   (invite spam getting your domain blacklisted) largely disappears because nobody can trigger a
   send by admitting someone.
9. **There is no player-level isolation, by construction — and that is a property, not a
   conflict.** With no per-player secret, a member can take another member's player account and
   see everything scoped to *it*. Nothing in the owner's model asks for otherwise: taking an
   existing player is how you resume as them, so it cannot also be forbidden. Recorded plainly
   because it is the standing consequence of campaign-level admission, not because a ticket
   demands the opposite.

   > [!note] Correction — I had [[B43]] wrong, and it was never a blocker
   > I read B43 as player-level privacy and treated it as conflicting with this model. The owner
   > clarified it is **character-level, not player-level**: *"B43 is about a character that
   > shouldn't be able to read another character's blue book. Not player, character. UI policy."*
   > So it is an in-fiction visibility rule for a surface, settled as **UI policy**, and it belongs
   > to whoever owns the blue book — not to identity, and not to this programme. The conflict I
   > recorded was an artefact of my misreading; withdrawn.
10. **The auto-sent link is the same credential as a manual recovery, so it needs the same care plus
   one more control.** It is single-use and short-lived like any recovery link, and — being sent
   unprompted — rotations must be **rate-limited per campaign**, or an architect session someone
   else has hold of could be used to flood the owner's mailbox. It must never carry the join token
   (§3): the recovery mail is the crown jewel, and bundling campaign access into it would make one
   intercepted message sufficient for the whole table.

## 6. Machines: MCP and the e2e harness

- **MCP** talks to the API over stdio and is unauthenticated today. Each campaign should carry a
  **service credential** for it, so its writes are attributable and it is not a browser session.
- **The e2e harness** currently logs in by writing `localStorage.playerId` and never exercises
  auth. It should use the **real** path — accept a join token for the test campaign and **take**
  the `DSH MCP` player — which keeps the suite working *and* makes it test what it was skipping.

## 7. What this rejects

- **A global account per *player* / central user register.** Rejected by the owner: players are
  campaign-local, and a player in two campaigns has two unrelated records. Correct — and it means
  revoking someone from one campaign cannot touch another. **Owners and creators are a separate
  matter** and do hold a central account (§3), because their recovery methods and authored
  content are theirs across campaigns.
- **Email per player.** There is no player email at all. Only recovery ever sends mail.
- **Any per-player credential at all.** No seat link, no PIN, no targeted window — the token
  admits to the campaign and the player is **taken** within it, which is what makes re-admission
  work without architect action. The cost is player-level privacy; see §5.9.
- **`universe` as the tenant.** See §2 and SEC-8.
- **Per-player isolation *inside* a campaign.** Taking an existing player is *how* you resume as
  them, so it cannot simultaneously be forbidden. Character and perspective switching remain
  untouched — they were never identity claims.
- **A shared static `ACCESS_TOKEN` as the door.** Superseded by per-campaign join tokens; the
  outer perimeter survives only as the tailnet/LAN wall.

## 8. Open items

1. **Join token length and cap** — ~30 minutes is the working figure; how many joins should one
   token allow before it closes itself?
2. **Duplicate players, and no rename path exists.** Roster-picking removes the common case, but
   a genuinely new player can still be created twice by mistake — and there is **no rename or
   merge anywhere** in the app (no API, no MCP tool, no UI). The Troupe panel probably wants a
   rename before this ships, or the duplicates become permanent.
3. **Second recovery method** — email-only is the v1 decision; a passkey is the natural next, and
   a password door needs rate limiting and lockout before it is worth offering.
4. **Campaign in the URL** — `/c/<campaign>/…` with a switcher (recommended) versus routing
   purely from the cookie.
5. **Who creates campaigns** — self-service is wanted, but throttling and payments are unsettled
   on the owner's side, and GPU is *not* in the free tier. See [[Content Registry]].
6. **Sequencing** — SEC-3 (identity) first, then the campaign boundary (SEC-8), then SEC-6
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
- 2026-09-26 — **third correction, from the owner.** (a) Invites are **reusable within a short
  window (~30 min)**, not single-use — one QR shown to the whole table, no per-participant link.
  Recorded what makes that sound: a leaked token can only mint a *new member*, never assume an
  existing player, so the blast radius is bounded by the window rather than by the use count.
  (b) The cookie carries the **player**, and eject is **revoking on that player's account** — an
  epoch bump that ends sessions without deleting the record (characters hang off `agency` edges
  and would be orphaned). (c) Recovery is **email link only at first**; passkey and password are
  deferred. (d) Found and recorded a hole the reusable window opens: it admits *new* players, so
  it cannot re-admit an **existing** player to a new device — proposed a **targeted mode** of the
  same window (single-use, bound to one player) rather than a duplicate record that would orphan
  their characters.
- 2026-09-26 — **fourth correction, from the owner, and it withdraws my fix rather than adding to
  it.** The token grants **campaign access, not access to a player**, so an existing player is
  re-admitted simply by **taking their account** — which removes the re-admission gap I had
  raised, so the "targeted window" mode I proposed is dropped. What that costs, recorded plainly:
  the blast radius of a leaked token becomes the **whole campaign** rather than a single new
  member, and **player-level privacy is gone by construction**, which collides with the ticketed
  ask [[B43]] (*"when player, shouldn't be able to see each others blue book"*). Also recorded:
  **eject is soft** — revoking an account cannot remove someone who still holds a valid token,
  and any member can re-admit them. One rule added as non-negotiable: **architect accounts are
  never takeable**, or a member could promote themselves to owner.
- 2026-09-26 — **hard eject answered by the owner: rotate the campaign's access.** Per-member
  revocation is soft — the token is what admits, and any member can open one — so real exclusion is
  a campaign-wide epoch bump plus a new join token: everyone re-admits and re-takes their own
  account, and the excluded person is simply not given the new token. Recorded as an expensive,
  deliberate act rather than an accident, with two properties to preserve: the architect must not
  lock themselves out of their own rotation, and the rotation is only as strong as the distribution
  of the new token. **[[B43]] remains unanswered** — this answer implies free taking stands, which
  would make B43 UI policy, but the owner did not say so and I have not assumed it.
- 2026-09-26 — **the owner resolved B43, and corrected my reading of it.** It is **character-level,
  not player-level**: *"a character that shouldn't be able to read another character's blue book.
  Not player, character. UI policy."* So it was never a blocker for identity — it is an in-fiction
  visibility rule for a surface, owned by whoever owns the blue book, and the "conflict" I had
  recorded in §5.9 was an artefact of my misreading. **Withdrawn, and §5.9 reframed**: no
  player-level isolation is a *property* of this model, not a problem with it.
  Also decided the shape of the work: **implementation starts with SEC-3 alone, against the
  current single database** — no campaigns, no registry, no data migration — with a player taken
  by **picking from the campaign roster** rather than typing a name. A small **additive groundwork
  pass** landed ahead of the flow: a defaulted `Player.epoch` (the revocation counter, persisted
  but not yet enforced or exposed) and `api/access_tokens.py` with `mint`/`verify` for signed
  expiring tokens, both with tests and no behaviour change.
- 2026-09-26 — **the owner closed the rotation lockout I had flagged:** the recovery link is
  **auto-sent** when campaign access is rotated. Recorded as the mechanism rather than a
  convenience — rotation kills the architect's own session, so the emailed link *is* how they get
  back in. Noted the two properties that fall out (it re-proves mailbox control at the critical
  moment, and it doubles as a notification if someone else rotated), and the controls it needs: the
  auto-send is the **ordinary recovery flow invoked automatically** (one mechanism, one set of
  limits), the architect re-enters by that link **only** and must not use the join token, the new
  token is **never bundled into the email**, and rotations are rate-limited so a double-click or a
  stolen architect session cannot flood the mailbox. This makes mail fire on two triggers, so §5.8
  was corrected from "recovery only".
