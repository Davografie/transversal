---
title: Perspective Model
date: 2026-09-10
tags:
  - transversal
  - technical
  - perspective
  - gm
  - roaming
  - frontend
aliases:
  - Perspective & Roaming Model
  - Entity Switching Model
  - Who Am I Looking At
status: draft
---

# Perspective Model

> [!note] Status
> Draft v2 — **collapse to one `entityId`** (the 3-variable split was speculative). Ground
> truth from `App.vue` (2026-09-10); Q1–Q3 settled with the human. Persistence is
> **device-local**; server-side identity is a future note, not this design.

## Goal

One variable for "who am I", one transient variable for "whose sheet am I peeking at",
and one rule for what survives a refresh — so the GM never snaps back to their starter
entity, and the codebase stops carrying three overlapping perspective values.

## Why now (grounded problems)

1. **Refresh snaps the GM back.** `entityId` is persisted only when *not* in GM mode —
   the watcher is guarded by `if (!entityId.value || gmMode.value) return`. Every GM
   perspective switch is ephemeral by design, and on refresh `entityId` re-initializes from
   `selfEntityId` (the last persisted value = the starter entity).
2. **Six variables, three overlapping.** `entityId`, `actingEntityId`, `viewingEntityId`
   answer nearly the same question; plus `selfEntityId`, `currentSupport`, and a switch-undo
   bookmark.
3. **The identity/perspective/acting split is speculative.** In the current code
   `actingEntityId` *never* genuinely diverges from `entityId` — every mutation runs through
   `switchPerspective`/`returnToSelf`/`switchViewLocation`, which keep them in lockstep, and
   the DiceRoller receives `acting-entity-id="gmMode ? actingEntityId : entityId"` (always
   equal). "View A while acting as B" was scaffolded but never built. So one variable
   suffices.

## Current state (`App.vue`)

| Variable | What it holds | Persisted? |
|---|---|---|
| `selfEntityId` | stable identity (`localStorage['entityId']`, fallback `kael-1`) | yes |
| `entityId` | current perspective; `null` = GM free-roam view | players only (GM guard) |
| `actingEntityId` | GM: entity being *acted as* (lockstep with `entityId`) | no |
| `viewingEntityId` | read-only location inspect (cleared on switch) | no |
| `currentSupport` | computed: perspective IS an owned SC (assume-support) | derived |
| `charSwitchPreviousEntityId` | one-step switch-undo bookmark | no |

Plus `currentLocationId`, which *is* persisted and already survives refresh.

## Target model

### One persisted variable: `entityId`

`entityId` = **who you are** — the entity whose sheet, location, and dice context the UI
shows, and who your rolls act as. One value, no sibling.

- **Player:** their main, or their assumed support character.
- **GM:** the entity they are currently being; **`null` = free-roam** (the god view).

Persisted **in all modes** — the `gmMode` guard is removed. Refresh restores `entityId`
(plus the already-persisted `currentLocationId`).

### One transient variable: `viewingEntityId`

`viewingEntityId` = the read-only **inspect** — "character A looking at character B's
sheet" without becoming B. Never persisted; cleared on any real switch. (Today it is used
for the location-inspect path; it becomes the *only* sheet-peek mechanism.)

### Derived — no variables

- **"Self" / return-to-main target:** the player's own main (`agency.main`, already in the
  troupe data model). For the GM: **free-roam** (settled Q1). No stored `selfEntityId` —
  `entityId` itself is the memory across refresh.
- **Support:** when `entityId` is a support character the player owns (`agency`,
  `main: false` + `support` edge), they are "supporting" — the return-to-main target is the
  main, and availability rules read from the `support` edge. A pure computed, no state.
- **Free-roam presence:** with `entityId = null` the GM still *exists* on the map — a
  **draggable** mapdot using the **architect icon** (the same role icon used in the player
  settings overlay), **visible to the GM only — invisible to players** (settled Q3). New
  requirement; also feeds [[Tickets#B34]] (role icon instead of "Y").

### Deleted plumbing

`actingEntityId`, `selfEntityId` (as a separate value), and the switch-undo bookmark
(transient at most — a one-step undo stack or drop it). Consumers that took
`acting-entity-id` / `fallback-entity-id` props take `entityId` + the derived main instead.

## Rules

- **Player:** `entityId` = main or assumed SC; inspect via `viewingEntityId`; "return to
  main" sets `entityId` := own main.
- **GM:** `entityId` freely switchable; `null` = free-roam with the architect mapdot;
  "return to self" := free-roam.
- **Refresh:** restore `entityId` + `currentLocationId` (all modes); `viewingEntityId`
  resets.
- **Assume-SC:** `entityId` := SC; support derived; availability from the `support` edge.

## Persistence

Device-local `localStorage`: keep the existing `entityId` key, now written in every mode
(remove the `gmMode.value` guard). Each device remembers its own perspective — accepted.
Server-side perspective/identity (per-player session state, on the existing session /
presence services) is a **future** upgrade if multi-device consistency ever matters.

## Consumers & ownership

- [[navigation]] — `LocationViewer` (`:entity-id`) + the free-roam architect mapdot.
- [[character-sheet]] — `CharacterSheet` active entity; inspect via `viewingEntityId`.
- [[applied-mechanics]] — `DiceRoller`: drop `acting-entity-id`/`fallback-entity-id`,
  use `entityId` + derived main.
- [[gm-panels]] — `GmPanel` assume/roam UI; scene-overview assume = `entityId` switch.
- [[Effects]] / troupe — support availability, derived from `entityId`.

**Steward: [[ui-ux]]** (cross-cutting interaction conventions) owns this doc; the
implementing roles take their consumer slices. [[Tickets#B68]] (GM assume & roaming
semantics) absorbs the GM behavior.

## Resolved (2026-09-10)

- **Q1** — GM "self" = free-roam (no pinning, no derived main).
- **Q2** — keep the name `entityId`.
- **Q3** — the free-roam mapdot is draggable by the GM and invisible to players.

## Decomposition

- **[[Tickets#B95]]** — perspective collapse + persistence fix (remove the GM guard, delete
  `actingEntityId`/`selfEntityId` plumbing, persist `entityId` in all modes). ui-ux primary
  + gm-panels, applied-mechanics, character-sheet as consumers.
- **[[Tickets#B96]]** — free-roam architect mapdot (draggable, GM-only). navigation.
- **[[Tickets#B68]]** — GM assume/roam behavior, defined against this model.

## Related

- [[SFX Activation Model Plan]] — the same convergence treatment for a tangled area.
- [[UI-UX Design]], [[Location Viewer]], [[GM Panel Development]], [[System Architecture]].
- [[Tickets#B68]], [[Tickets#B34]], [[Division of Labor]].
