---
title: Pressure-Test Log
tags:
  - transversal
  - plan
  - pressure-test
  - findings
  - scenarios
aliases:
  - Scenarios
  - Findings Log
  - Session Walkthrough
status: working
---

# Pressure-Test Log

> [!note] Status
> Running log. Each scenario walks a concrete GM/player flow through the *actual* codebase and tags every step ✅ built · 🟡 built but clunky · ❌ missing · ❓ needs a decision. Findings here become the completeness check for the build order in [[Release Plan]].

## Method

- One scenario at a time, chronological through a session's lifecycle.
- Verify against code, not docs — a step is "built" only if it works end-to-end.
- Bugs and decisions are logged here; the build order consumes them later.

## Scenario list

1. GM preps a session
2. Players arrive & make characters
3. A simple test
4. A contest
5. Consequences & stakes (challenge pools, earth-bond)
6. Moving around & switching characters (transversal, troupe rotation)
7. Growth & session close

---

## Scenario 1 — GM preps a session

Setting: Krasnoyarsk-45. Party gets a tip, pokes around a rail yard, draws heat.

### Verified solid ✅
- Universes exist as entities (`universe-earth`, `universe-three_realms`).
- Location CRUD + nested tree + zones/backgrounds.
- Bare GMC & faction creation.
- Challenge-trait *data model* (negative polarity) + resolver comparison.
- Relationships & messages.
- Session + player management.

### Bugs (frontend, confirmed against code)
1. New location/zone ignores the tree selection as parent — "Railyard" created under the Earth universe instead of Krasnoyarsk.
2. Create-entity panel's location points at the current location viewer, not the tree selection (same root cause as #1).
3. Universe is not creatable from the create panel — its type list omits `UNIVERSE`.
4. Create panel renders `razmerit` unconditionally (`GmEntityCreatePanel.vue`); the edit panel (`GmEntityForm.vue`) hides it by type, so the two are inconsistent.
5. No "add this GMC to that faction" membership shortcut (Dmitry → Russian Maffia).

### Design decisions locked
- **Doom / crisis pool** = location-scoped "looming dice" (a labeled dice cluster rendered atop the screen, applying to a location + its sub-locations). Group/party-faction scoping deferred ("someday", since factions are entities).
- **"Hooks" → "Events"**: an event = a condition (when) + effects (what). Not a new entity type.
- **Starter location** = roll-table random default; the effect-targeting system needs a **random** target mode alongside **choose**.
- **Relationship traits UI** = missing in frontend (backend done: `add_relationship_trait`, `ts-relations` seeded). Needs a home — relations trait set or a tab.

### Open questions
- Unify `trigger` / `condition` / `limit`? Today: effects are shared; triggers are SFX-only; limits are SFX-only free text; conditions are roll-table/life-path-only. An "event" would pair a condition with effects — worth deciding whether trigger and condition are one concept and whether limit folds into condition.
- Full-native SFX exact effect list (Earth projection decay, Earth-trait step-down) — still TBD.

---

*Scenarios 2–7 pending.*
