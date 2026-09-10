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
> Draft — ground truth from `App.vue` (2026-09-10), written for review before any role
> touches the variables. **Persistence is device-local** per the human's steer; server-side
> perspective (per-player session state) is a noted future option, not this design.

## Goal

One clear model for "who is the user looking at, who are they acting as, and who are
they", replacing the current tangle of overlapping frontend variables — and one rule for
what survives a refresh, so the GM no longer snaps back to their starter entity.

## Why now (grounded problems)

1. **Refresh snaps the GM back.** `entityId` is persisted only when *not* in GM mode —
   the watcher is guarded by `if (!entityId.value || gmMode.value) return`. So every GM
   perspective switch is ephemeral by design, and on refresh `entityId` re-initializes from
   `selfEntityId` (the last persisted value = the starter entity).
2. **Too many variables with overlapping meanings.** Six values track perspective today;
   three of them (`entityId`, `actingEntityId`, `viewingEntityId`) answer nearly the same
   question.
3. **"Self" is ambiguous for the GM.** `selfEntityId` is the persisted *player* identity;
   for a roaming GM it is "not a main entity" (source comment), yet it is also the
   return-to-self target and the refresh fallback.

## Current state (`App.vue`)

| Variable | What it holds | Persisted? |
|---|---|---|
| `selfEntityId` | stable identity (`localStorage['entityId']`, fallback `kael-1`) | yes |
| `entityId` | current perspective; `null` = GM free-roam view | players only (GM guard) |
| `actingEntityId` | GM: entity being *acted as* (`null` = difficulty / free-roam) | no |
| `viewingEntityId` | read-only location inspect (cleared on switch) | no |
| `currentSupport` | computed: perspective IS an owned SC (assume-support) | derived |
| `charSwitchPreviousEntityId` | one-step switch-undo bookmark | no |

Plus `currentLocationId`, which *is* persisted and already survives refresh.

## Target model

Three **persisted** concepts, three **transient** ones.

### Persisted (device-local, one key each)

- **Identity** (`identityEntityId`, today `selfEntityId`) — who the human *is* on this
  device. Players: their main entity. GM: their return-to-self target (a character they
  own, or a default); not conflated with perspective.
- **Perspective** (`perspectiveEntityId`, today `entityId`) — who they are *looking at*:
  whose sheet, location, and dice context the UI shows. `null` = free-roam view.
  **Persisted in all modes** — this is the refresh fix.
- **Acting** (`actingEntityId`) — GM-only: who the GM's rolls act as. `null` = rolling
  against difficulty. *(Persistence: open question Q2.)*

### Transient (never persisted)

- **Inspect** (`viewingEntityId`) — read-only peek (e.g. inspecting an occupant) that must
  not disturb perspective; cleared on any switch.
- **Support** (`currentSupport`) — derived, never stored: perspective is an SC owned by the
  player (`agency`, `main: false` + `support` edge).
- **Switch-undo** (`charSwitchPreviousEntityId`) — one-step bookmark, cleared on refresh.

## Rules

- **Player mode:** perspective = identity, acting = `null`, support derived. Assume-SC sets
  perspective = SC and "return to main" sets perspective = identity.
- **GM mode:** perspective freely switchable; acting = entity acted as; free-roam =
  perspective `null` + persisted `currentLocationId` restores the roam view.
- **Refresh:** restore identity → perspective → acting; inspect and undo reset. No mode
  guard — GM restores like anyone else.
- **Return-to-self:** perspective := identity. For a GM with no identity entity, return to
  the last free-roam location instead.

## Persistence

Device-local `localStorage` keys: keep `entityId` for identity (backward compatible),
add `perspectiveEntityId` and (per Q2) `actingEntityId`. Each device remembers its own
perspective — accepted for now; server-side perspective (per-player session state, built
on the existing session/presence services) is the future upgrade if multi-device
consistency ever matters.

## Consumers & ownership

The variables live in `App.vue` but are consumed everywhere:

- [[navigation]] — `LocationViewer` (`:entity-id`).
- [[character-sheet]] — `CharacterSheet` (`:main-entity-id`, sheet `activeEntity`).
- [[applied-mechanics]] — `DiceRoller` (`:entity-id` / `:acting-entity-id` / `:fallback-entity-id`).
- [[gm-panels]] — `GmPanel` `currentEntityId`, assume/roam UI.
- [[Effects]] / troupe — `currentSupport` availability.

**Steward: [[ui-ux]]** (cross-cutting interaction conventions) owns this model doc; the
implementing roles take their consumer slices. [[Tickets#B68]] (GM assume & roaming
semantics) absorbs the GM behavior; the persistence fix + variable split is new work.

## Open questions

- **Q1** — free-roam (`perspective = null`): restore on refresh via the persisted location?
  (Leaning: yes.)
- **Q2** — acting entity: persist across refresh in GM mode, or reset to `null` each
  session? (Leaning: persist — the GM picks up where they were.)
- **Q3** — rename the variables (`identity` / `perspective` / `acting`) or keep legacy
  names and change semantics only? (Leaning: rename once, with a mechanical refactor.)
- **Q4** — should the GM's `identityEntityId` be server-side (the GM is one person across
  devices) even while perspective stays device-local?

## Decomposition (pending review)

- **Perspective persistence + model split** — drop the GM guard, split identity vs
  perspective keys, persist acting per Q2, rename per Q3. (ui-ux primary + gm-panels.)
- **B68** — GM assume/roam behavior, now defined against this model.
- **Sheet perspective cleanup** — character-sheet's `activeEntity` handling, aligned with
  the model.

## Related

- [[SFX Activation Model Plan]] — the same convergence treatment for a tangled area.
- [[UI-UX Design]], [[Location Viewer]], [[GM Panel Development]], [[System Architecture]].
- [[Tickets#B68]], [[Division of Labor]].
