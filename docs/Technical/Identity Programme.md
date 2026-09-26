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
  - design
aliases:
  - Identity Programme
  - Identity UX
  - Seats
status: draft
---

# Identity Programme

The UX design for **SEC-3 / SEC-6 / SEC-8** — the one programme behind three findings in
[[Security Posture]], and the precondition for [[B88]] and for going online. It is
security-owned documentation.

> [!warning] This is a design under review — nothing is implemented
> Written 2026-09-26 at the owner's request: *"I'd like to know the UX of the identity
> programme before you implement it."* The code still behaves exactly as **What exists
> today** describes. Sections 5 and 10 are the decisions being asked for.

## 1. The problem in one paragraph

The app has **three different things wearing one word**: the *device/session* (a cookie),
the *player* (a person), and the *perspective* (the character you're driving). Only the
third is a game concept. Today the cookie names nobody (SEC-5), the player is established
by *typing a name* — so typing "Andy" makes you Andy (SEC-3) — and the API enforces
nothing at all, so the boundary is the nginx edge or nothing (SEC-6). `role` is a field on
the player record that any client can set to `architect` with one request. The fix is to
give the *player* a real credential, check it server-side, and make `architect` something
only an architect can grant.

## 2. What exists today (the four surfaces)

1. **Entry.** The architect shows a QR encoding `/enter?t=<ACCESS_TOKEN>` — *one static
   shared secret*. Scanning it sets a 30-day `tv2_session` cookie carrying a signed
   **timestamp and nothing else**. Everyone past that door is trusted absolutely. A
   device with no valid cookie gets `UnauthorizedNotice.vue`: *"The way is sealed … ask an
   architect for a fresh link."*
2. **Who are you?** The login overlay (`.name-entry`) asks you to **type a name**, with
   live search over `GET /api/v1/players?q=`. If the name exists you become that player —
   *"You've transversed before, Andy."* If not, you create it — *"New transverser detected.
   Welcome, Andy."*
3. **Switching.** The settings overlay (the `↩` button) shows your name as click-to-edit;
   typing **anyone else's name** and confirming makes you them, previewing their
   characters first. Separately — and legitimately — there is a **character** switch
   (main ↔ GMC ↔ support character), which is the normal, frequent action.
4. **Architect.** `Player.role` drives `gmMode` in the client (`App.vue` `loadPlayerRole`)
   and the GM chrome. `PATCH /api/v1/players/{id}/role` sets it, unauthenticated. There is
   **no UI** to set a role, and no rename path anywhere.

The `GmTroupeOverview` panel ("Troupe") already renders the player roster with presence —
it is the natural home for the new controls, and today the architect has **no way at all**
to hand out access or take it back.

## 3. The design problem, stated as UX

> A person must be able to become a *new* player with as little friction as today, must be
> able to come back on a *new device*, and must **not** be able to become an *existing*
> player (or an architect) without the architect's say-so.

Everything below is a way of answering three questions:

| question | today | must become |
|---|---|---|
| how do I become a new player? | type a new name | *(choose: keep, or architect-issued)* |
| how do I get back in on a new device? | type my name | a credential the architect gave me |
| how do I become an architect? | `PATCH …/role` | only an architect can say so |

## 4. The model: a **seat**

Introduce one concept and the rest follows. A **seat at the table** is a player identity
plus a credential the architect issued:

- The player record gains a **seat token** (stored hashed) and a **seat version**.
- The session cookie becomes `player_id + seat_version + issued_at`, signed. The server
  can now answer *who is calling* — which is what SEC-6 needs and SEC-8 is blocked on.
- **Revoking** a seat bumps its version: every cookie for that player dies, and any
  outstanding invite stops working. This is the control the architect has never had.
- A seat carries a **role** (player/architect) and, later, a **universe** — the field
  SEC-8 will need, carried from day one so it is not a retrofit.

## 5. The UX: three options

All three use the same seat machinery. They differ only in **who may create a seat**.

### Option A — "Take a new seat freely; re-entry needs the architect" · recommended

The login overlay keeps its shape, but the *existing-name* branch changes:

| what you type | today | Option A |
|---|---|---|
| a **new** name | creates it, you're in | **unchanged** — creates it, you're in |
| an **existing** name | **you become them** | *"That seat is taken. Ask your architect for your passage."* |

The architect gets, in the **Troupe** panel, per player: **Show link/QR**, **Revoke**, and
**Make architect**. Showing the link renders `/enter?s=<seat token>` as a QR *and* as a
short typed code, so it works over voice for remote play. Opening it binds that device to
that seat — no typing, and the character picker appears as usual.

- **First run unchanged.** A brand-new person types a name and is playing in one step; the
  table ritual does not change for them.
- **Impersonation closed.** Typing "Andy" no longer makes you Andy; it tells you to ask.
- **Self-escalation closed.** The role control exists only in the architect's Troupe panel.
- **Switching** in settings becomes *"Scan a seat link / enter a seat code"* rather than a
  name search — you can still move a shared tablet between people, but only with the
  credential. Character switching is untouched.
- **Cost:** the architect issues a seat for every returning player's every new device.
  Two clicks each; the one-time re-onboard of the existing troupe is the bulk of it.

### Option B — every seat is architect-issued (strictest)

No name typing at all: the login overlay becomes *"No seat on this device — ask your
architect for your passage"* plus a code field. The architect mints every seat from a new
**Players** screen and hands out the links.

- **Pros:** the strongest posture; the troupe is exactly who the architect invited; no
  accidental duplicate seats; nothing typed can collide.
- **Cons:** every new person waits on the architect, including at a first session;
  the architect is now the IT desk for the whole table.
- Note B is **A with creation disabled** — the same code, one policy flag. Building A
  yields B for free, so this is not an either/or to build twice.

### Option C — name + PIN (self-service re-entry)

A returning player types their name and a short PIN they set the first time.

- **Pros:** the architect is not in the loop for re-entry; survives clearing site data.
- **Cons:** another secret to remember and reset; PINs get shared and reused; name
  collision still needs handling; and it does **not** remove the need for architect-granted
  roles. It buys convenience at the cost of a second weak credential.

### Recommendation

**Option A**, with **Option B available as a flag** and **C rejected** — a shared table
does not need a second password, it needs the architect to be able to hand out and take
back access. A keeps the current first-run feel exactly, closes both holes, and gives the
architect the only new power the design actually requires.

## 6. What each surface becomes

- **Entry (`/enter`).** `?t=<ACCESS_TOKEN>` stays as the **outer door** (the shared
  perimeter is fine on a LAN/tailnet) and gains `?s=<seat token>` for a seat. The
  architect's own seat is bootstrapped from the environment at startup — it is the one
  seat that is not issued from the UI, so the troupe can never be locked out.
- **Login overlay.** Unchanged for a new name; a new refusal line for a taken one.
- **Settings.** Name search → *seat* action (scan/enter a code). Character switching
  unchanged. This is a *removal* of a surface, not an addition to it.
- **Troupe panel (`GmTroupeOverview`).** Grows **Show link**, **Revoke**, **Make
  architect** per row, architect-only. The last architect cannot demote themselves.
- **`UnauthorizedNotice`.** Largely unchanged — a stale cookie still means *"ask an
  architect for a fresh link."*
- **MCP / harness.** See §8 — deliberately not a special case in the UI.

## 7. Migration of the existing troupe

The existing players have no seat, and every device's `localStorage` `playerId` becomes
meaningless. On the day it lands, each device shows the no-seat screen once and the
architect issues that player a seat. That is a **one-time re-onboard of the whole table**,
done by the architect in a few minutes; there is no way to avoid it, because the whole
point is that the old identity was never proven. No player data is touched — a seat is
added to a player record, nothing is renamed or rewritten.

## 8. Machines: MCP and the e2e harness

- **MCP** talks to the API over stdio and is unauthenticated by design today. It should
  present a **service token** (from the environment) that the API resolves to the
  dedicated test player `DSH MCP` (`player-75a410`) — so its writes are attributable, and
  the service token is not a seat that can be used through the browser.
- **The e2e harness** currently logs in by writing `localStorage.playerId` and never
  exercises auth. It should use the **real** path — `/enter?s=<the DSH MCP seat token>`
  from the test environment — which both keeps the suite working and makes it test the
  thing it was skipping.

## 9. What this does *not* change

- **The shared outer door.** `ACCESS_TOKEN` as a perimeter is a deliberate, coherent
  choice for a trusted LAN/tailnet troupe; this programme does not replace it, it adds an
  identity *behind* it. (Retiring or rotating it is a separate question.)
- **Character/perspective switching.** Untouched — it is not an identity claim.
- **The game domain.** Nothing here is dice, effects, contest or traits.
- **One campaign.** With a single universe, SEC-8's scoping is invisible; the seat carries
  a universe field so multi-campaign is a policy change, not a rewrite.

## 10. Questions for the owner

1. **Creation policy** — Option A (new names self-serve; re-entry needs a link) or Option
   B (the architect issues every seat)?
2. **Seat links** — reusable until revoked (fewer "my link stopped working" moments), or
   one-time (a screenshot goes stale)? Recommendation: reusable + a visible Revoke.
3. **Same-name collisions** — if a genuine second "Andy" arrives, what should happen?
   There is no rename path today; do we add "rename player" to the Troupe panel, or push
   people to distinguish at creation?
4. **Shared device** — is a tablet passed around the table a real case (needs scan-to-switch
   to be quick), or is it one device per person?
5. **Seat/cookie lifetime** — 30 days today for the shared cookie. Keep, shorten, or make
   the architect's Revoke the only expiry that matters?
6. **Sequencing** — SEC-3 first, then SEC-6 (API-wide enforcement) and SEC-8 (universe)?
   That order is my recommendation; SEC-6 is what makes SEC-8 mean anything.

## Log

- 2026-09-26 — design written at the owner's request; **implementation deliberately not
  started.** Recommends Option A, rejects C, notes B is A with creation disabled.
