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

## Backend inventory — known implementation gaps

Found during the pre-scenario code walkthrough; not surfaced by any single scenario.

1. **Attunement expiry unwired** — `attune enable` adds an `Attunement` with `until=<timing>`, and `disable` removes it, but nothing schedules the matching `disable` when the boundary fires. Attunements may never auto-expire.
2. **`effective_universes` divergence** — the code unions "all NATIVE projection universes when the entity has >1" (a multiversal-being rule) that [[Projections and Transversal]] doesn't mention.
3. **`fire_contest_sfx` dead code** — defined but never called; contests don't auto-fire SFX (feeds the "triggers fire in the roll/contest flow" release item).
4. **[[SFX and Effects]] top half stale** — "Anatomy of an SFX" / "SFX Categories" / "Effect Types" still describe the old model (singular `effect`, `cost`, `modify_roll`/`modify_outcome`/`create_entity`), while its own "Unified Effect Model" section is correct.
5. **MCP tooling doc drift** — `mcp/server.py` docstring lists `manage_session` and `generate_from_table`; [[API Contract]] says "session management" is among the 5 tools. Neither exists (actual tools: `create_entity`, `create_npc`, `roll_dice`, `get_entity`, `query_entities`).

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

## Scenario 2 — Players arrive & make characters

Setting: new player "Sam" joins the Krasnoyarsk session with no character yet.

### Verified solid ✅
- Player sign-in / find-or-create by name (no auth, as decided).
- Claim agency over an existing entity (seeded Kael / Elena claimable).
- Bare entity creation.
- Life-path wizard (grants career traits via roll tables).

### Gaps
- **No starter-character template** — base attributes/skills are hand-added trait-by-trait; nothing grants the standard spread (the seed characters are hand-written the same way). *(new)*
- **Character creation is GM-side only** — no player-facing "make my character" onboarding; a new player has to ask the GM. *(new)*
- **Life path grants career traits, not base traits** — two separate manual jobs, not one flow.
- **Social web manual** — relationships added one edge at a time; relationship *traits* have no UI (carried from Scenario 1).
- **Starter location spawn** — missing (carried).
- **Earth-bond trait** — not built; will be composed from challenge trait + SFX (carried).
- **Support characters** — troupe play, deferred (carried).

---

*Scenarios 3–7 pending.*
