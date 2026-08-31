---
title: Pressure-Test Log
date: 2026-08-16
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

## Macro design decisions (locked, ongoing)

From the scenarios 1–2 discussion, beyond per-scenario findings:

- **Tether** — a *sub-trait of the Origin distinction* (negative/challenge): the doom-pool countdown. *(revised from "relationship trait to the origin universe" — folds it under Origin and reuses sub-trait machinery.)*
- **Origin** — a *distinction* that is also relationship-anchored (points at a location edge). A trait can be both: "distinction" is its *kind* (`traitset_id` + ego + statement + SFX), "relationship" is its *anchor* (`from_type`). The model already separates these axes; it needs a small refactor (stop hardcoding `ts-relations`, give relationship traits a real anchor field, fold them into character assembly).
- **Relationship traits** — inline in the character sheet, grouped by trait set (no separate relations set/tab). Character sheet = trait settings from the character *or* from relationships originating from the character.
- **Base traits** — a background roll table (skill packages), not Archetype template entities.
- **Appearance** — a morph trait (per-universe); model already supports it.
- **Duplicates** — need a `duplicates_allowed` flag back (per trait-set/trait): two melee weapons OK, two strengths not. Currently impossible (ID collision + picker hides owned traits).
- **Empty/descriptive traits** (pronouns, nickname, appearance) — a distinct "profile" surface, not the dice editor. *(open — lean yes)*

### Open

- **Prime trait sets** (Cortex rule: which sets always contribute a die to a pool) — unexplored in Transversal; relevant to dice-pool assembly.
- **Trait editor is the convergence point** — must handle direct / relationship / sub-trait attachment, the empty-trait profile, and the duplicates flag.

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
- **Player onboarding exists and is player-facing** (the settings overlay): sign in / find-or-create by name, Player↔Architect mode toggle, "+ New character", claim & relinquish agency, "Find character" search, switch player by name.
- Life-path wizard (grants career traits via roll tables).

### Gaps
- **Onboarding produces a bare shell** — "+ New character" creates a `CHARACTER` entity with name + type + universe only (no location, no traits), then claims it. The "fill in the character" work is still manual / GM-side. *(corrected — earlier logged as "GM-side only")*
- **No starter-character template** — base attributes/skills are hand-added trait-by-trait; nothing grants the standard spread (the seed characters are hand-written the same way).
- **Life path grants career traits, not base traits** — two separate manual jobs, not one flow.
- **Social web manual** — relationships added one edge at a time; relationship *traits* have no UI (carried from Scenario 1).
- **Starter location spawn** — missing (carried).
- **Earth-bond trait** — not built; will be composed from challenge trait + SFX (carried).
- **Support characters** — troupe play, deferred (carried).

---

## Scenario 3 — A simple test

Setting: Kael hacks a security terminal in Krasnoyarsk-45.

### Verified solid ✅
- Pool assembly from the character's traits (the sheet feeds the roller via `addFromSheet`).
- Rolling (both pipelines) + effect-die picking (pool) + result display (total / effect die / hitches / botch).

### Gaps
- **Opposition is never sent** — `doRoll()` calls `/roll` with no opposition; there's no static difficulty / GMC / challenge pool in the test flow, even though the backend resolver supports all three and `useApi.roll()` accepts an `opposition` argument.
- **Razmerit on hitches is computed but discarded** — `razmerit_earned` is returned but never persisted to the character.
- **Effect die does nothing** — picked in the pool pipeline but no wizard applies it (step down a challenge, create a complication, etc.).
- **SFX don't fire** — `on_roll` / `on_complication` / `on_success` / `on_botch` are not wired into the roll flow.

Headline: a "test" is currently "roll dice and see a number" — the difficulty, the consequence, and the economy are all missing.

### Target design (user's read — the Phase 1 spec)

- **Opposition = a location/GMC's own traits**, rolled by the GM *first*: default 2d6 + the relevant location trait (e.g. "digital security d6") = 3d6. The GM's total is the threshold; the GM's effect die is the **stakes**.
- **Two tiers**: full Cortex roll (3+ dice) beats the GM's threshold; simple roll (1–2 dice) just yields a tier, no target number.
- **Consequence menu** (two-sided — winner spends their effect die): *Player's options* — "proceed the narrative" / "decrease the doom pool" (effect die lands there) / "create a scene trait" at effect-die rating. *GM's options* (make things more dangerous) — "increase the doom pool" / "apply a complication to a character" / "give a GMC an asset".
- **Hitch trading**: the player spends the GM's hitches via SFX; the GM buys the player's hitches (doom pool).
- Note: "stakes" is just the opponent's effect die (standard Cortex — winner applies their effect die, loser eats the opponent's). The resolver already computes the player's effect die, but does **not** return the opposition's — so the fix is "also return the opponent's effect die," a small mechanical gap, not a new mechanic. The "GM rolls first" sequence is a frontend flow change (today both sides roll atomically).

---

## Scenario 4 — A contest

Setting: Kael sneaks past a guard (stealth vs perception), head-to-head.

### Verified solid ✅
- Backend contest machinery: `resolve_contest` (pure, 2-party), `ContestTracker` (per-location pools), REST endpoints (add-die / set-opposition / resolve / GET pools).
- Frontend pool sharing: the DiceRoller builds a pool, App.vue broadcasts `pool_updated` over SSE, LocationViewer renders peers' pools around avatars.
- The "◆ Next Beat" button exists in the GM panel.

### Gaps
- **Challenger vs defendant is not modeled** — `set_opposition` stores a unidirectional "opponent"; "ties go to defender" is positional (defender = whoever is the opponent argument), so roles flip depending on who calls resolve.
- **Test vs contest is not first-class** — two separate backend paths (`/roll` vs the contest tracker), no shared concept; the frontend `mode` flag is UI-only.
- **Beat button is cosmetic** — `onNextBeat()` only clears dice pools frontend-side; it never calls the backend, and `tick_beat()` (fires `end_of_beat` effects) has no call site.
- **Opposition/doom dice have no render surface** — character dice render around avatars; location-trait dice and doom-pool dice have no home (the "looming dice" idea is the intended answer, not built).
- **Contest resolve returns only `{winner, pipeline, pushed}`** — no rolls, no effect dice, so no "stakes".
- **`fire_contest_sfx` is dead code** — defined but never called (SFX don't fire on contests).
- **Push has no frontend trigger** — `push_contest` + `pushed_this_beat` exist in the tracker; no UI.

### Open / design
- **Multiway contests** (3+ parties, winner-takes-all) — deferred; the resolver is 2-party.
- **Hero dice + margin step-up** (`(winner − loser) / 5 → step up effect die`) — neither is in Transversal's selected Cortex modules ([[Core Mechanics]]); decide explicitly whether to pull them in.
- **Push as SFX** — "push a contest" is a table-level SFX (owner model), not a hardcoded button; the hardcoded `push_contest` would become that SFX's effect.
- **Complication expiry** — "suppressed d8 for 2 beats" maps onto existing `after_beats` timing (basically free); "expiry in N dice-pool pushes" is new; severity → default expiry maps to the negative-trait severity table.

---

## Scenario 5 — Consequences & stakes

Setting: Krasnoyarsk rail yard; a "regime alert" doom pool; Kael rolls a hitch; a tether is at risk.

### Per-step
1. **Doom pool data** — challenge trait (negative) on a location. Plumbing: `RatingType.CHALLENGE` + `Polarity.NEGATIVE` + `TraitSetting.polarity`; seeded (`regime_alert`, `sect_suspicion`). ✅
2. **Looming dice render** — must be prominent; no frontend challenge/doom rendering exists. ❌
3. **Buy hitch** — spend a doom die to escalate; no code. ❌
4. **Effect die vs challenge** — `_resolve_challenge` computes it. ✅ *But it should route through the consequence menu → effect system (the "challenge rating" effect), not resolver-side persistence.*
5. **Challenge persistence** — stateless today; the write-back belongs to the effect. ❌
6. **Tether** — a *sub-trait of the Origin distinction* (negative/challenge). Reuses sub-trait machinery rather than a separate relationship trait. 🟡 *(revised)*
7. **Full-native trigger** — via the event system: "challenge emptied" → SFX → "switch projection type" effect. None exists. ❌
8. **Full-native consequences** — TBD; missing prerequisites. ❌

### UX note (from the old app)
`vue/src/components/Rating.vue` + `Trait.vue` show the click semantics are non-trivial: static = add-to-pool; resource = click-to-spend (grouped by distinct die); challenge = left-click deplete / right-click increase, and the GM can add challenges; view modes (Neutral/Viewing/Small/Editing) layer on top. This is the "tangled mess" to get right in Transversal2.

---

## Scenario 6 — Moving around & switching characters

### Per-step
1. **Move to a nearby location (same universe)** — `/entities/{id}/move` → `move_to`, `location_changed` SSE, LocationViewer `relocate()`. ✅
2. **Consciousness transversal** — `/entities/{id}/consciousness-travel` → `consciousness_travel`; frontend `relocate(…, consciousness=true)`. ✅
3. **Inapposite transversal** — backend `inapposite_travel` exists; frontend wires via portal `transversal_type`. 🟡 backend solid, frontend path thinner.
4. **Attunement** — `attune` effect (enable/disable) + `Attunement` + `effective_universes`. 🟡 expiry unwired (logged).
5. **Switch which character you control** — player `claim_entity` / `release_entity` + settings-overlay picker. ✅
6. **Morph traits gated by active projection** — `get_effective_traitsettings` + `effective_universes` + `from_type` gating. ✅
7. **Troupe rotation / spotlight recency** — none. ❌ deferred.

### User read — new gaps + design refinements
1. **Projections as first-class units** — nav dots render *projections*, not character entities. Ownership chain: `projection → entity → agency → player`. GM sees all projections; a player sees the projections of "currently playing" players (filtered by live players).
2. **No "live" player tracking** — no server-side "actively-playing-now" concept (only `agency` + session membership + localStorage `entityId`). Needed by #1 and the GM overview.
3. **Transversal edges: support `location → universe`** (not just `location → location`). Traversing to a universe triggers the random starter-location pipeline (roll table).
4. **Inapposite travel: dedicated REST endpoint** — currently only GraphQL; the frontend falls back to generic `/move`, skipping `INAPPOSITE` semantics.
5. **Attunement expiry** — manual `attune disable` is a *patch* (works without a scheduler); the auto-scheduler at timing boundaries is still a desired mechanic.
6. **GM scene overview** — three groups: currently-played character (entity + projection, incl. support characters), each player's main character(s), and current-location GMCs.

---

## Scenario 7 — Growth & session close

### Per-step
1. **Run a life path term** — `start_term` / `resolve_step` GraphQL + `lifepath_executor` + `LifePathWizard`. ✅
2. **Transfer a trait (teach/gift/take)** — `teach_trait` / `gift_trait` / `take_trait` GraphQL + `trait_transfer.py`. ✅
3. **Add/remove relationships + relationship traits** — backend done; relationship-trait UI missing (logged). 🟡
4. **Review the Blue Book** — `BlueBook.vue` + `historical_records`. 🟡 deletion-with-undo and transversal logging are to-do.
5. **Session persistence** — ArangoDB + sessions API. ✅

### User read — new gaps + design decisions
1. **Life paths reuse unaffiliated (shared) roll tables** — a shared table (`life_path=None`) is reusable across paths via the `continuation` return-address stack (`context.return_to` + `next_step("")`). Works for **single-exit** tables (e.g. `Continue`/Muster); **multi-exit** tables (e.g. `Survive`, where injured vs survived diverge) are NOT solved yet. Backend implemented + tested; authoring partial (JSON textarea only); seed not wired. See [[Life Path Flow and Shared Roll Tables]].
2. **Trait transfer has no real UI** — `teach_trait`/`gift_trait`/`take_trait` exist on the backend, but no proper frontend buttons/flows for giving/taking between characters.
3. **Trait transfer via effects** — teach/gift/take may be better routed through the effect system (universal mechanism) than three dedicated mutations.
4. **Relationship traits** — must render the `_to` entity's portrait, and be served by the backend the same way the character's own traits are (folded into the character's trait list, not a separate query).
5. **Dice pool persistence** — the assembled pool is in-memory (frontend state + `ContestTracker`); must survive refresh/mobile memory eviction. (Already on to-do: "Own dice pool should persist after refresh.")
