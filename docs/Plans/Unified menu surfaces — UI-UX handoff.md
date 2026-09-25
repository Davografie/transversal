---
title: Unified menu surfaces — UI-UX handoff
tags:
  - transversal
  - plans
  - ui-ux
aliases:
  - Menu surfaces
  - Unified picker
---

# Unified menu surfaces — handoff for [[ui-ux]]

The author, 2026-09-25: *"I'm thinking of extracting all roll-tables, consequence
menus, character creations and life paths and all those that do very similar things
into a unified UI/UX component."* This note is what the **effects / roll-table**
side knows about those surfaces — their shapes, what they genuinely share, and what
must not be flattened. It is written to be read *before* the design, so the unified
component is built on the contracts rather than on the resemblance.

## The surfaces, and what each is actually for

| Surface | What the player/GM sees | Who picks | Where it is chosen |
|---|---|---|---|
| **Roll table** (menu play) | the table's entries, in order | player (or GM) | `pick_roll_table_entry` → `resolveRollTableEntry`-style mutation |
| **Roll table** (rolled play) | one entry, chosen by a roll/tier | the dice | life-path `resolveStep`, or a table's own `check` |
| **Consequence menu** | options assembled for a moment | player / GM sides | `consequenceOptions(entityId, side, menuContext)` |
| **Life path** | a *flow* of linked tables with a checkpoint | the dice, with player picks at `choose` steps | `startTerm`, `resolveStep` |
| **Character creation** | a table entry that *makes* a character | player, from a table | `createSupportCharacter`, or `createEntity` |
| **SFX card list** (sheet, place rules, armed rail) | rules you may press | player | `availableSfxIds` + friends |
| **Choice / branch prompt** | one question with options | player | `sfx_choice_required` → an answer mutation |

They look alike because **the same four things keep appearing**: a *list*, a *pick*,
a *cost*, and an *effect*. They are not the same because each answers a different
question about *when the list exists* and *what a pick means*.

## The axes they share (the union the component would model)

| Axis | Values seen live |
|---|---|
| **what makes the list** | a table's entries · a menu context assembled at a moment · a rule's options · the rules available to an entity |
| **how the pick is made** | a roll maps to a row (`range`, `weight`, `tier`, `index`) · a human chooses · a boundary raises a question |
| **cost** | `cost_effects` (paid *before* the benefit), razmerit, nothing |
| **gating** | entry `conditions` ([[B179]], with fall-back) · SFX conditions ([[B193]]) · phase/stakes · none |
| **on pick** | apply `effects` · create an entity · advance a flow checkpoint · run a branch option |
| **why not available** | *"unmet: …"* per condition ([[B193]]) · greyed with a reason ([[B190]]) |

## Contracts this side already exposes (verified, safe to build against)

- **Tables**: `rollTables { id name universe lifePath scheme rollSource die check entries { label description minValue maxValue weight tier conditions costEffects effects } boundVariables { name spec } }`.
- **Menu options**: `consequenceOptions(entityId, side, menuContext)`; `menuContext` ∈ `test_success`, `simplified_roll`, `contest_win`, `contest_give_in`. Authored per-entity options: `setConsequenceOptions`.
- **Life path**: `startTerm(...)`, `resolveStep(...)`, and the step result shape (`done`, `table_id`, `entry_label`, `applied[]`, `scheduled`, `pending_choices`, `pending_term`, `mustered`, `mishap_muster`).
- **Choices**: the `sfx_choice_required` SSE event carries `entity_id` and `choices[]` — each already has a `kind` (a target kind such as `location`/`occupant`/`trait`/`rating_die`, or `branch`), a `field`, and the effect whole. Answers: `resolveEffectTargets` (target steps), `resolveSfxLoop` (a rule offering another round), **`resolveParkedBranch(eventId, optionId)`** (a choice node, [[B5]]).
- **Availability**: `availableSfxIds`, `inFlightSfxIds`, `armedSfxIds`, and **`unavailableSfx(entityId, universe, sfxIds) { sfxId reasons }`** — `reasons` is one human phrase per unmet condition.
- **Table-side names available to an entry's effects** (so a component can *show* what a row is about): `path_faction`, `term_faction`, `term_path`, `table_id`, `roll`, `entry_tier`, `entry_effect_die`, `entry_label`, `entry_index`, `entry_min`, `entry_max`; a table may also declare its own ([[B164]]).

## What must not be flattened

1. **A roll and a pick are different acts.** A `range`/`tier` table's row is *found*; a menu's option is *chosen*. A unified component must not offer "roll" as one more list item — the scheme decides whether a row can be picked at all.
2. **A flow is not a list.** A life path is a *sequence with a checkpoint* (`pending_term`: where you are, what returns where). A picker can render one step; only the flow knows the step's position, its named exits (`{return:…}`) and that a term can be abandoned or mustered.
3. **Creating something is not gaining something.** `createSupportCharacter` *makes an entity* and then applies the entry's effects to the new character; a unified "apply this option" would lose the ordering (pay → create → own → effects).
4. **Cost before benefit** is an ordering guarantee, not a display detail (`cost_effects` apply first, then `effects`).
5. **An entry can decline.** With [[B179]] an entry whose conditions do not hold is skipped by **falling back to the previous matching row** for a roll, and **refused by name** for a deliberate pick. The component has to know which act it is rendering, or it will silently re-route a player's choice.
6. **A choice can wait.** A branch at a boundary is *parked* ([[B5]]) — the prompt persists until answered, and answering with nothing is a legitimate default. A component that dismisses on close would lose it.

## Open design questions (for [[ui-ux]], with [[applied-mechanics]] on menu shape)

1. **Is the unified thing a picker, a flow runner, or both?** The four axes above suggest a **presentational list** (rows with label/subtitle/cost/conditions/why-not) that several *drivers* fill: a table resolver, a menu assembler, a flow step, an availability list.
2. **Where does a boundary prompt live?** Today the choice UI is the dice roller's panel, which renders *target* candidates; a session-end choice is not attached to a roll. Either lift that panel to a sheet-level prompt or accept that such a choice only appears in the roller — this one is blocking [[B5]]'s client half.
3. **How is "why not" shown?** One phrase per unmet condition is now available for SFX (`unmet: …`) and is the intent for table rows ([[B190]]). Do they render as a tooltip, a sub-line, or a locked row with the reason on tap?
4. **Does a roll-table row show its own outcome?** The entry's `tier` carries an effect die (`entry_effect_die`) — a unified row could show it, which is the author's reason for wanting entry metadata in the first place.
5. **Costs and returns**: a pick can create an entity and hand it back; the component needs a "what happened" state (the step result's `applied[]` is a summary list, not a model).

## Ownership

- **[[ui-ux]]** — the component, the presentation, the reason surfaces, where the prompt lives.
- **[[applied-mechanics]]** — menu *shape* (they own the assembled consequence menu; [[B118]] is theirs).
- **[[life-path]]** — life-path content and flow semantics (the checkpoint, the named exits).
- **[[character-sheet]]** — the sheet's own surfaces: SFX cards ([[B189]]), the trait-detail "why greyed" ([[B193]]).
- **[[Effects]]** (this side) — the effect layer, the entry scope, availability and its reasons, choice nodes and their answers, and the table/effect contracts above. Ask for a read rather than re-deriving one; several of these were built specifically so a UI could show the *why*.

## Source

Written 2026-09-25 by [[Effects]] at the author's request, from the surfaces' own
code and contracts. Related tickets: [[B5]] (choice nodes), [[B164]] (table names and
the table as a source), [[B179]] (conditional entries), [[B190]] (greyed rows),
[[B193]] (why an SFX is greyed), [[B189]] (card legibility).
