---
title: UI-UX Design
tags:
  - transversal
  - design
  - ui
  - ux
  - frontend
aliases:
  - UI/UX Design
  - Interaction Design
  - UX
status: working
---

# UI-UX Design

Living interaction-design reference for the Transversal frontend. Captures the conventions, patterns, and tunable "feel" knobs so UI behavior stays consistent as the app grows.

> [!abstract] At a Glance
> - **Touch-first** — no interaction may rely on hover alone; every affordance has a touch equivalent.
> - **Focused** — one thing at a time: drill-in (`list → detail → editor`) instead of crowded accordions.
> - **Direct manipulation** — things that look draggable are draggable, and gestures follow the finger.
> - **State clarity** — "mine" vs "foreign" vs "GM" is always visible without explanation.

## Principles

1. **Touch-first, hover-optional.** Desktop hover is a *progressive enhancement*, never the only path (see [[#Dice roller and dice panel]]).
2. **Less on screen.** Prefer drill-in navigation over stacked sections. The trait-set list → trait list → trait editor flow replaced the old accordion for this reason.
3. **Follow the finger.** Drag gestures track 1:1 while active and settle with a spring-like snap; nothing teleports on release.
4. **Consistent selection semantics.** The same concept (e.g. "select a character") must behave identically across surfaces (see [[#Peer selection]]).

## Shared primitives

The reusable UI set lives in `src/frontend/src/components/ui/`: `GmList`/
`GmListItem`, `TargetPicker`/`SearchDropdown`, `EntryPicker`, **`ChoiceTable`**,
`Button`, `DangerButton`, `TagInput`, `TraitInstanceEditor`, `SegmentedControl`.
(The `gm/` folder keeps the GM-specific panels, which compose these primitives.)
New surfaces should compose the primitives instead of re-styling raw elements.

One resolver backs the row surfaces: `composables/useLabelResolver.js` — see
[[#Choice table]]. Anything that would otherwise carry its own id → name map
should take it from there instead.

### Autocomplete core

Every "type and a list suggests" surface shares one headless core,
`composables/useCombobox.js`. It is the list; the components are the rendering.
Four surfaces had grown the same mechanics separately, and the mechanics are the
bug-prone half — what is excluded, what Enter commits, which arrow does what,
the aria wiring, and fetching.

| Surface | Shape | Notes |
|---|---|---|
| `ui/SearchDropdown` | single value, input **is** the control | the base under `TargetPicker` and `UniversePicker` |
| `ui/TagInput` | many values, chips + inline input | free-form tags or a restricted multi-select |
| `useEntityFilter` (GM panel filter) | many values, chips | keeps its own filter semantics, borrows the list |
| `TargetSpecBuilder`'s `<datalist>` | one free-form value | **not** on the core — the browser's native list |

What the core owns: normalising options to `{ value, label, hint, raw }`,
filtering against what is already chosen, the highlight (and the two movement
modes below), the create row, open/close, and the aria ids. What each shell
keeps: its markup, and what a commit *means* — one value, many chips, or a
filter chip.

- **Options may be an array *or* a query function.** The function form is called
  with the query text (debounced) and may return a promise; that is what lets a
  multi-select work over a vocabulary too large to preload. A function is taken
  as **authoritative** — its results are not re-filtered client-side, because it
  matched on fields this list never sees, and a second filter would silently
  drop rows it deliberately returned. A superseded response can never overwrite
  a newer one.
- **Two highlight modes.** The tag field wraps (`-1 → 0…n-1 → -1`), which lets a
  stray arrow cancel a commit; a picker clamps instead, because the top option
  is armed as you type and wrapping would make one ArrowDown *deselect* it.
- **`requireQuery`** lists nothing until something is typed — the GM panel's
  long-standing behaviour, kept so an empty box does not open onto ten
  arbitrary entities.

Semantics worth not re-deriving: `resolve()` maps typed text to a stored value
(by label, then value) and refuses it when `allowCustom` is false; `exactMatch`
suppresses the create row so it never offers to create what the list holds.
`scripts/check-combobox.mjs` pins all of it and runs without a browser.

### Entry picker

`ui/EntryPicker.vue` renders a list of options to choose from — the row a
roll-table entry, a consequence and a hitch all need — plus an optional 🎲 and a
cancel. Three menus had grown this separately; they now share it.

**It is the *compact* face of [[#Choice table]]** — the rows are rendered by
`ChoiceTable` with `density="compact"`, so the app has one row engine and one set
of row CSS rather than two. Its own contract is unchanged, because three hosts
were written against it:

- **An option** is `{ id?, key?, label, description?, cost?, costFree?, hint?,
  tone?, disabled?, weight? }` — literally the choice table's row vocabulary.
- **It reports what happened and nothing else.** `pick(option, index)` is the click
  that takes a row; `roll(option, index, number)` is the 🎲 *finding* one. Resolving
  either is the host's, and the hosts genuinely differ: the roll-table and
  consequence menus hand off to `EffectTargetWizard` and then apply, while the
  hitch menu hands the option back to the dice roller.
- **The random roll is opt-in** (`allow-random`, off by default): rolling is
  native to a roll table, while a consequence or a hitch is usually a deliberate
  choice, so each host decides. A list carrying `weight`s rolls a die over the
  cumulative weights and reports the number rolled; an unweighted list picks
  uniformly and reports none. Disabled and zero-weight entries are never rolled.
  In both cases it **marks** the row — it does not take it (see [[#Choice table]]).
- **The index is 0-based** — `pick(option, index)`. The roll-table API it feeds is
  **1-based**, so `RollTableMenu` adds the 1 at the boundary.
- **Busy is not loading.** While a host is applying a pick the list stays on
  screen and goes inert (`busy`); it only reads *Loading…* before it has options.

### Choice table

`ui/ChoiceTable.vue` is the one surface behind everything that says *"here are
things you may take"*: a played roll table, a life-path step, character creation
from an archetype table, the consequence and hitch menus. Before it there were
four implementations of one idea — `RollTableMenu`, `LifePathWizard` (its own
`<table>`), and `ConsequenceMenu` / `HitchMenu` (two near-identical pickers) —
each with its own rows, its own name map and its own idea of what a key meant.

**It is presentational, and it is not a flow.** It renders what a row *is* and
reports what was chosen; resolving the pick stays with the host. The **drivers**:

| Driver | Fills the surface with | Owns |
|---|---|---|
| table resolver | a table's entries | which scheme's key applies, rolling |
| menu assembler (`useConsequences`, `useHitchMenu`) | options assembled at a moment | `menuContext`/`side`/`effectDie`, exclusions |
| flow step (`LifePathWizard`) | one step of a path | the checkpoint, `Back`, the named exits, mustering |
| availability list | rules you may press | one phrase per unmet condition ([[B193]]) — **not a consumer yet**: the sheet's SFX cards are [[character-sheet]]'s and stay theirs |

**Three acts it refuses to conflate.** These were the handoffs' warnings, and
each one is a way a generic list would have been *wrong* rather than plain:

1. **A roll finds a row; the click takes it.** The 🎲 is a separate control, never
   a row, and opt-in per host — but it only **marks** the row it lands on. Taking a
   row is always the click, on that row *or on another one*. There is deliberately
   **no confirm button anywhere in the surface**: a marked row that needs a second
   press to take is a step with nothing in it, and a roll that took the row itself
   would take the choice away from the player. So "the dice said the third one" and
   "actually, I want the first" stay one click apart rather than two presses. The
   same mark is used when the roll comes from outside — the dice roller reporting
   `rolledIndex` — which is how a life-path step works.
2. **A flow is not a list.** `Back` is not a navigation stack — a life path
   returns through `return_map`, and a shared table has more than one valid way
   out. The surface therefore offers no `Back`; a driver puts its own exit in the
   `#actions` slot (`↩ Paths`), and the surface never guesses what leaving means.
3. **Creating is not gaining and cost is not benefit.** A pick that *creates* an
   entity (archetype → support character) orders pay → create → own → effects,
   and its row can be picked exactly like one that only applies effects. The
   price always has its own cell and is never merged into the label, because the
   ordering guarantee (`cost_effects` first) is only legible if the cost is.

**The key's meaning belongs to the table's `scheme`, never the row.** A row cannot
own it, because the same row means different things in different tables:

| scheme | a row is | the key cell shows |
|---|---|---|
| `RANGE` | a band of the roll | `min–max` |
| `INDEX` | one of N, in order | the position |
| `TIER` | an outcome tier | the tier |
| `WEIGHT` | a slice of a weighted roll | `w` |

With no scheme (an archetype list, an authoring list) the surface reads the row:
`tier` → `weight` → band → position. The fallback is not decoration — the live
`rt-support-cast` table declares `RANGE` and **no entry declares min/max**, so
the honest key for it is the position, which is exactly what the fallback
produces. (`WEIGHT` remains implemented with **no live instance**.)

**One resolver, supplied once.** `composables/useLabelResolver.js` is the app's
id → label map and the phrasing built on it (a condition's "if …", an effect's
"→ target (die)", a cost's "2 razmerit"). It is **registry-wide and
universe-independent**: traits are read through *every traitset* (36 sets → all
802), never `traitsByUniverse`.

> [!warning] Why the resolver exists — a live defect, not tidiness
> Each runtime surface used to resolve names from its own map, and every failure
> was silent. `LifePathWizard` read `traitsByUniverse(<the path's universe>)`, so
> in a `three_realms` path `trait-rel-tenure` — stamped `universes: ["earth"]` —
> rendered as a **raw id**, on the two traits the life-path ladder is built from.
> The canvas's `RollTableNode` resolved roll-table names only, so *every* trait
> target there rendered raw. Both were correct code for their own map. A host
> that carries a name map is now a bug, and `scripts/check-choice-table.mjs`
> fails if the universe-scoped read comes back — the guard strips comments first,
> because these files *explain* the read they replaced.

**"Why not" renders in the row, not in a tooltip.** There are **four** gates and
they are not interchangeable. The surface owns only the *presentation*; which gate
is which is the driver's business:

| Gate | Rendered as |
|---|---|
| row `conditions` ([[B179]]) | an `if …` line on the row — a *declaration*: whether it holds is resolved server-side at apply time, where a failing entry falls back for a roll and is refused **by name** for a pick |
| locked / unaffordable | `why` in the row (🔒 **needs 9 razmerit**) plus `disabled` — never hidden ([[B190]]) |
| path walkability ([[B194]]–[[B197]]) | visible and disabled carrying why — the human's call, not hidden |
| offering (`factionIds`, derived) | the same, e.g. **no offering faction** |
| path discovery | **inert today** — no production caller |

**A row is:**

```
{ id?, key?, label, description?, cost?, costEffects?, costFree?, hint?,
  tone?, state?, why?, disabled?, locked?, conditions?, effects?,
  minValue?, maxValue?, weight?, tier? }
```

- `conditions` / `effects` are the **domain objects**; the surface phrases them.
  A host with pre-phrased text passes `conditionLines` / `effectLines` / `cost`.
- `state` is the GM lists' vocabulary (`active` · `disabled` · `warning` ·
  `danger` · `success` · `muted`), so a row means the same thing here as in a
  panel. `tone` (`gm` / `player`) is a semantic *edge*, not a fill, so a mixed
  list still reads as one control.
- **The `#row` slot is the escape hatch.** Rows are unbounded stacked blocks, so
  an authoring host whose cells are data-driven (the effect form's merged field
  list, a condition's type-dependent columns) can render its own cells inside the
  same shell and keep the marking, states and actions. The slot is handed
  `{ row, index, rolled }`.

**Responsive by container, not viewport.** The same surface is a ~290–340px column
when the character sheet is docked, ~534px as a modal, and a phone's full width —
so it asks how much room *it* has (`container-type: inline-size`, `@container
ct`), not how wide the window is. **Two layouts, not three**: the result and the
price side by side, then the price wrapped under the result (`≤520px`). The
**legend is dropped the moment the price wraps**, because a header that labels
columns which no longer exist is worse than no header.

**The key is a corner chip, not a column** (changed 2026-09-26, the human: *"I'd
like the rows to be more compact … if the `[ 1 ]` would sit in the top-right then
we'd lose a lot of height already"* — and it did). The key used to own a 58px
left column, which at the dock's ~290px collapsed to **a line of its own above
every row**; floated into the content's top-right, it shares the label's first
line and the text flows under it, so a row pays for the key only when the row is
one line tall. Measured on live tables at the dock, as total height for six rows:

| table | before | after |
|---|---|---|
| `rt-26339016` (Birth — one-line labels, one effect each) | 438px (`93,69×5`) | **264px** (`59,41×5`) — **−40%** |
| `rt-ironroots-escalation` (long labels + a full-sentence description) | 1032px (`172,186,158,172×3`) | **736px** (`132,146,104,118×3`) — **−29%** |

The saving is the 16px pip plus the 8px grid gap it no longer needs, per row —
and the row padding (7→6px), the pip (`2px`→`1px`, `min-width` 34→26px) and the
effect chips (`2px`→`1px`) each give back a little more. Two details make it
hold: the conditions/effects stack carries `clear: right`, so a chip never
overlaps the float's last pixel, and an effect phrase is `overflow-wrap:
anywhere` with `max-width: 100%` — before that, a long effect chip painted out
of its own row (a 314px chip inside a 291px row, clipped rather than wrapped).
`choice-table.spec.js` pins the contract as geometry at every viewport: the key's
top matches the label's, and its right edge matches the content's.

**Where a prompt lives** (settled 2026-09-25, answering [[Effects]]' open question
2 — it was blocking [[B5]]'s client half; the third host landed 2026-09-26,
[[B230]]). A choice is a **flow step, not a roll's panel**, and it is asked
**where the question was raised** — the server tags every choice with an `origin`
and the shell routes by it, so no host has to guess:

| where it was raised | `origin` | host |
|---|---|---|
| a manual press on a character sheet | `sheet` | the sheet's own prompt slot |
| a roll — or an effect that fired with the roll | `roll` | the roller's panel (compact density, under the result) |
| an **automatic** rule: a state change or a timer nobody pressed | `auto` | the floating panel (`app/FloatingChoicePanel.vue`) |

- **A choice that outlives the roll cannot live in the roller.** It is transient, a
  GM in free-roam has none at all, and the next roll clears it — so a parked branch
  put there would be lost by the act of playing on. That is what the sheet's slot
  is for, and what the floating host is for when nobody is looking at the sheet.
- **The floating host asks without taking over.** It is **non-modal and there is no
  scrim**: the change that raised the question is the context for answering it, so
  dimming the table would hide the thing being asked about, and a parked question
  must not block play. It **never dismisses itself** — no timer, no auto-close; the
  only ways out are answering it or the wizard's own Cancel, which writes nothing
  (the branch stays parked server-side and is recoverable). It is **fixed, not
  draggable**: a question should be where you last saw it, and on touch the bands
  already own the drag gestures. Desktop takes the free corner (bottom-right — the
  sheet docks left, the roller sits bottom-centre, the ✨ rail owns the left edge);
  a phone takes the top as a full-width banner, because the band stack owns the
  bottom.
- **Only one copy, in one host.** `App.vue` splits the pending list three ways
  (`rollerChoices` / `sheetChoices` / `autoChoices`), and `auto` is filtered *out*
  of the roller rather than falling through to it — a question whose answer is
  somewhere in the world is not something a reader looking at a dice pool will
  find. The answer travels back through one pair of handlers that carry the origin,
  so the *next* question in a chain lands where this one was (`retagChoices`).
- **A host positions the wizard; it does not draw a second card.**
  `EffectTargetWizard` renders its own surface (`.etw-root`), and a host that adds
  another with a different token set is why the same table once looked different
  depending on where it appeared. The one exception is the floating host, which is
  the *only* surface there is and so supplies a readable one
  (`--bg-panel-solid` — a 2%-overlay inset is invisible over a location photo).
- **The prompt is non-modal and never auto-dismisses** in every host. A parked
  choice waits ([[B5]]), and *answering nothing is a legitimate default* — so the
  only way to leave it is an explicit "leave it" that writes nothing.
- **Every host drives the same surface**, fed by different things: the roller's copy
  by the roll's result, the sheet's by the parked prompt, the floating one by a
  server-raised choice. The rows carry their choice `kind`, and the kind decides
  whether a pick resolves immediately (a branch) or opens the target wizard — a
  property of the *driver*, not of the row, so one surface is sufficient for all
  three.

**Flashy, and restrained.** A die-pip key at the content's top-right, tabular so it
reads as a number rather than as text, a short
staggered entrance, and a *landing beat* when a roll finds a row — one lift and one
ring as the dice land, while the mark itself **persists** until the row is taken or
the rows change. The beat is the arrival; the mark is the record. So "the dice found
this" reads differently from "you chose this", and the row is still waiting for the
click that takes it. All of it is off under `prefers-reduced-motion: reduce`.

**What it is not.** It is not `GmList`'s replacement *yet*. `GmList`/
`GmListItem` keep the authoring half — drag-reorder with a ⠿ handle, `selectable`
✓/+ picking, and the `.entity-row` shell — and 17 call sites use it. `ChoiceTable`
shares the state vocabulary, `useDragDrop`'s row model and the `.entity-row`
line-row shape, but reorder is deliberately **not** duplicated here until
[[gm-panels]]' call sites migrate; a half-built second reorder path would be
worse than one list primitive with a settled API. Editable cells still need form
primitives that `components/ui/` does not have (there is no text/number/select
input in the shared set), so the authoring editors stay on `GmList` until those
exist.

`scripts/check-choice-table.mjs` (64 assertions, no browser) pins the scheme's
key and its fallback order, the condition/effect/cost phrasing, the
roll-marks-then-click rule (including that no confirm control can creep back), and
— as shipped text — the resolver's registry-wide read. `e2e/tests/choice-table.spec.js`
measures the layout at all four viewports **plus the wrapped-price state between
them** — the modal is `min(560px, 96vw)`, so the named viewports alone never reach
it — and drives the two gates, the marking roll, and the click that takes a row
against the live app.

### Button

`Button.vue` is the standardized button: every visual decision (fill, border,
state, size) comes from props, and colors come from the theme tokens, so
buttons follow light/dark automatically.

- **Variants** — `primary` (the one action a surface wants, accent fill),
  `secondary` (default actions, accent-dim fill — the app default),
  `neutral` (neutral list/form chrome), `ghost` (low emphasis / icon buttons),
  `danger` (destructive, danger tint), `danger-ghost` (subtle row-remove: dim
  until hovered, then danger), `success` (confirm/commit), `link` (inline
  text action). Add `solid` for the filled treatment of the tinted variants
  (save/commit buttons).
- **Sizes** — `sm` · `md` (default) · `lg` · `icon` (square, for glyph
  buttons).
- **States** — idle, hover, pressed (`:active`), `:focus-visible` (2px accent
  ring), `loading` (spinner + `aria-busy`, implies disabled, label stays put
  so the width doesn't jump), `disabled` (dimmed, inert), `active` (toggle /
  selected, variant-tinted so an armed danger button stays dangerous), plus
  `block` for full width.

```vue
<Button variant="primary" :loading="saving" @click="save">Save</Button>
<Button variant="ghost" size="icon" title="Close">×</Button>
<Button variant="danger" block :disabled="!canDelete">Delete</Button>
```

Notes: hover/press mix the fill with `--text`, so they brighten in dark mode
and darken in light mode ("intensify" either way). `prefers-reduced-motion`
drops transitions and slows the spinner. `DangerButton` is built on `Button`
(`variant="danger"` + `active` for the armed confirm state).

### TagInput

`TagInput.vue` is the shared multi-tag input with autosuggest. It covers both
shapes the app needs: a **free-form tag field** (type anything, existing values
suggested) and a **restricted multi-select** (values must come from the list).

```vue
<!-- Blue Book threads: free-form, suggests existing threads -->
<TagInput v-model="composeTags" :suggestions="allThreads"
          placeholder="Threads: dreams, investigation" aria-label="Threads" />

<!-- Trait universes: restricted to the allowed list -->
<TagInput v-model="form.universes" :suggestions="allowedUniverses"
          :allow-custom="false" placeholder="Add universe…" aria-label="Universes" />
```

- **Props** — `modelValue` (string[]), `suggestions` (string[] or
  `{ value, label, hint? }[]`, or a query function — see
  [[#Autocomplete core]]), `allowCustom` (default true), `placeholder`,
  `disabled`, `max` (0 = unlimited), `ariaLabel`.
- **Built on** [[#Autocomplete core]], so it shares its list mechanics with the
  pickers instead of keeping a second copy; the chips and the multi-value commit
  are what it adds.
- **Emits** — `update:modelValue` (batched: one emit per change), plus `add` /
  `remove` for side effects.
- **Interaction** — type to filter; Enter commits the armed (first/arrowed)
  option, or the typed text in free-form mode; `,` (or pasting a
  comma-separated list) adds every part at once; Backspace on an empty field
  removes the last tag; the chip `×` removes; clicking away commits pending
  text; ArrowUp/Down walk the list; Escape/Tab close.
- **A11y** — combobox + listbox roles with `aria-expanded`,
  `aria-activedescendant` and per-option `aria-selected`; chip buttons carry
  `aria-label="Remove …"`.
- **Adopted** — the Blue Book compose view (threads) and `GmTraitEditPanel`
  (trait tags, edit + create) both use it. `ChipInput` (in `gm/`) remains an
  overlapping older primitive, still used by `GmTraitsetDetail` — retiring it
  is a small cleanup (gm-panels).

**Migration (in progress, surface by surface).** Migrated so far: the GM
list/form button patterns — `save-btn` (→ `success solid`), `ps-add-btn`
(→ `secondary block`), `row-del-btn` (→ `danger-ghost sm`), 20 sites across 10
GM panels; their local rules were deleted and only layout hooks (margins,
`width`) kept. Also 21 of `CharacterSheet.vue`'s 41 buttons, in the same idiom
([[character-sheet]], `385b00c`) — its header pills and rating-type toggles are
segmented controls, so they are out of scope here.

### Migration guide (for surface owners)

Each surface owner migrates their own buttons — ui-ux owns the primitive and
this mapping, not the surfaces. Take your surface in one pass and verify it in
both themes.

1. **Replace the markup**, keep the layout class if the component styles
   margins/width through it:

   | Old pattern | Use |
   |---|---|
   | `.save-btn`, `.commit-btn` (filled success) | `<Button variant="success" solid>` |
   | `.ps-add-btn`, `button` default (accent-dim fill) | `<Button variant="secondary" block>` |
   | `.row-del-btn`, row removes | `<Button variant="danger-ghost" size="sm">` |
   | `.cancel-btn`, `.section-btn`, neutral chrome | `<Button variant="neutral">` |
   | icon-only glyph buttons | `<Button variant="ghost" size="icon">` |
   | inline text actions | `<Button variant="link">` |

2. **Delete the local rules** that the primitive now provides (fill, border,
   radius, padding, hover/disabled). Keep only layout declarations.

3. **Wire the loading state — always.** If the handler awaits anything
   (save, create, apply, roll, submit), pass `:loading` and keep it true until
   the work settles. The spinner + `aria-busy` + implied disabled is how the
   user knows the click landed; a button that silently waits reads as broken.
   A label swap (`{{ saving ? 'Saving…' : 'Save' }}`) may stay on top of
   `:loading` — the label keeps its width either way.

   ```vue
   <Button variant="success" solid block :loading="saving" @click="save">
     {{ saving ? 'Saving…' : 'Save' }}
   </Button>
   ```

   > [!warning] The first pass skipped this step — check for it
   > The GM list/form migration moved the markup but wired **no** `:loading`, so every
   > save and create silently waited. [[gm-panels]]' audit (`a1b9ff5`) found it and fixed
   > the six that await. Do it in the same pass, and watch the **stale-prop trap** the fix
   > exposed: `GmEntityCreatePanel` was handed `saving: saving.value` snapshotted when the
   > panel opened, so its busy state could never become true. Pass the live ref or the
   > shared singleton — never a copied value.

4. **Don't** hand-roll a spinner, disable via CSS opacity, or leave a
   double-submit window open — `:loading` implies `disabled`.

Still un-migrated: the player surfaces (login/settings overlay, dice roller, blue book),
the GM action rails (`.section-btn`, `.cancel-btn`, `.shortcut-btn`), canvas and
location-viewer controls, and the rest of the character sheet's buttons.

**Raw by design — do not convert these** (their surface owner's call, and [[gm-panels]]
audited the list): segmented controls (mode / media-quality, the die-variable toggle), die
and picker chips, toggles, the composite imagen button, and the 🛠
panel anchor — its 42px geometry feeds the rail anchor math. Segmented controls have their
own primitive now ([[#SegmentedControl]]), so they are a `SegmentedControl` migration, not
a `Button` one.

A **wizard candidate row** is no longer raw *by design*: the life-path wizard's rows are
[[#Choice table]] rows now. `EffectTargetWizard`'s `.etw-candidate` ([[gm-panels]]' file) is
the last one standing, and migrating it is theirs to take or to leave.

### Trait instance editor

One editor for a trait's rating, shared by the [[Character sheet]] (the drill-in
trait editor) and the effect form's *Gain Trait* action — see
`components/ui/TraitInstanceEditor.vue`.

- **Controlled, host owns persistence.** Every field is a `v-model`
  (`ratingType`, `dice`, `capacity`, `die`, `polarity`, `statement`, `notes`) and
  each edit also emits `change` **naming the field**, so a host can save live
  (the sheet: debounced for text, immediate for dice/rating) or hold a draft
  (the effect form). `recover-die` and `field-blur` cover the sheet's extra
  affordances.
- **Rating type is canonical uppercase** (`STATIC` / `RESOURCE` / `CHALLENGE` /
  `EMPTY`); hosts that speak lowercase (the effect form) adapt at the boundary.
- **Two modes.** `mode="array"` gives a row of die chips plus the popup
  `DiePicker` (dice, capacity, and the recoverable spent dice for `RESOURCE`);
  `mode="single"` gives one inline picker with an optional `Die`/`Variable`
  toggle for effects. The sheet hides polarity (`show-polarity="false"`) because
  its own Type block owns ego/morph, projection and polarity together.
- **Dice rows speak one interaction language.** `+` opens the picker on the next
  empty slot and **stays open after each pick**, so faces are added one after
  another (resource/challenge ratings); a chip opens it on that slot; whichever
  slot the picker is on is **marked** (`.editing` — accent chip, or the `+` chip
  for the empty slot), so it is unambiguous which die a face click will change.
  An **edit commits and closes**; clicking the open slot again closes; the
  picker's `×` clears the edited die, and on an empty slot it just dismisses.
  The dice and capacity rows behave identically (one `dieRowState()` backs both).
- **Two skins.** `variant="panel"` is bare sections for the sheet's full-panel
  view; `variant="box"` is the compact bordered chrome used inside editor forms.
- **Extras ride slots:** `after-dice` (SFX chips), `after-fields` (ego/morph,
  projection, sub-traits) and `actions` (Done/Delete). Slot markup is compiled in
  the host's scope, so host-scoped styles still apply to it — the sheet's
  `.edit-field` / `.edit-label` rules stay where they are.

### SegmentedControl

A small set of mutually exclusive, always-visible choices — mode, media
quality, die/variable. **Not a `Button`**: the segments keep an equal width and
read as one object, so the primitive owns its chrome
(`components/ui/SegmentedControl.vue`).

```html
<SegmentedControl
  v-model="mode"                        <!-- string | number | boolean | null -->
  :options="[{ value: false, label: '🎭 Player' },
             { value: true,  label: '🏛 Architect' }]"
  aria-label="Mode"
  :class="'settings-segmented'"          <!-- host constrains width/placement -->
/>
```

- `role="radiogroup"` + `role="radio"`/`aria-checked`; arrows (←/→/↑/↓) move the
  selection and wrap, disabled options are skipped.
- The control fills its container; the host sets `max-width`/alignment (the
  settings overlay uses `.settings-segmented`).
- **Remaining migration:** `EffectForm.vue`'s `.ee-result-mode` (Die/Variable)
  still hand-rolls this — its owner (gm-panels) migrates it (B104).

## Pickers

Picking is already one system; new surfaces should compose it rather than reach
for a raw `<select>` (that was the point of **B47**).

- **`ui/TargetPicker`** — the universal picker: a search field plus a filtered
  dropdown, backed by the server's `targetCandidates(kind, entityId, scope,
  action, filter)`. The *kind* is the whole vocabulary, and it is server-defined:
  `location` (410 candidates), `trait` (802), `roll_table`, `universe`, plus the
  scoped kinds (`character` / `gmc` / … resolve within an entity or location —
  an empty list just means "none in scope"). It also takes `excludeIds`,
  `allowRandom` (🎲) and `clearable`. Nine call sites today, from the canvas and
  the effect/condition builders to the entity panel's location fields.
- **`ui/SearchDropdown`** — the input + dropdown it is built on; use it directly
  for a free-text search that isn't a target lookup. Since it moved onto
  [[#Autocomplete core]] it is **keyboard-navigable** (arrows, Enter, Escape,
  combobox/listbox roles) and takes an async `options` function — so
  `TargetPicker`'s nine call sites gained keyboard support without changing
  them. It is controlled: listen for `@select` / `@clear`, there is no
  `v-model`.
- **`DiePicker`** — die faces (d4…d12), single or `multiple`. This is the
  **rating-die picker**: `TraitInstanceEditor` and the sheet's trait editor use
  it for ratings, the GM forms for effect dice.
- **GM-specific**: `gm/UniversePicker`, `gm/GmScopePicker`, `gm/GmSfxPickerPanel`
  (sfx/scope picking inside effect authoring).

### Picker filters

`TargetPicker` offers **result filters** behind a ⚙ button (B47): the backend
describes which candidate fields can narrow a kind (`targetFilterFields`:
`field` / `label` / `valueType` / `kinds` / `options`), and the picker renders
the applicable ones as a small popout — checkbox for `boolean`, select for a
field with `options`, text otherwise. Selections merge over the `filter` prop
and ride along with every candidate lookup; the button carries a count badge and
a Clear, and it only appears when the kind actually has filter fields.

Because the vocabulary is server-sourced, **new filter fields show up in every
picker without a frontend change** — that is the point: broadening what can be
filtered is a backend `FILTER_FIELDS` entry, not a UI project.

Today that vocabulary is thin (`starter_location` for locations; `type` for
entity/occupant). The richer facets asked for — trait set, default rating, "this
entity has an instance", parent location, location traits — are **backend
fields**, not UI work. Callers that build their own filter UI (the effect form,
the target wizard) pass `:allow-filters="false"` so filters appear exactly once
per surface.

**Not yet using it:** the GM panels still hand-roll `<select>`s where a search
would be better (`TargetSpecBuilder` has 15, `EffectForm` 10, the trait panels
8 each) — each panel owner's call, since some are genuinely short enumerations.

## Character sheet

Navigation lives in the header **pills**: 👤 profile · 🎲 traits · 📘 bluebook · 🛤️ lifepath (GM also gets 🌍 show-all-traits).

- **Profile first** (leftmost). Its traits render in a wrapping flexbox with no per-trait border.
- **Traits tab** is a drill-in:
  1. **Trait-set list** — set name + limit dots.
  2. **Trait list** — tap a set to drill in; the set name becomes the click-to-return title.
  3. **Trait editor** — a full-panel view (replaces the trait list) with rating type, dice, polarity, statement, SFX.
- **SFX cards come in three sizes**, because where a card sits decides how much
  text it earns: the **trait teaser** (list row) shows the **name only**; the
  entity / projection / trait-set strips add the description; and only the
  **trait detail clickthrough** carries the derived natural-language rules line
  (the "translation"). One `SfxCard`; the text comes from
  `sfxCardModel(sfxId, variant)` — `'chip'` · `'card'` (default) · `'full'`.
- **Next set**: a `Next: <name> →` button sits under the trait list (right-aligned), jumping to the next set without picking. When a set fills to its limit, the view **auto-advances to the next set** (and returns to the list on the last set).
- **Own vs foreign sheet**: your own sheet always shows the pills; a foreign sheet hides
  them and swaps in the relationship widget + "add relationship" affordance.
- **The one-click tie needs someone to be acting as.** The header `+` runs
  `createRelationship(from: viewerEntityId, to: the entity you are viewing)` — a *character's*
  social tie toward the person you are looking at. So it is `isForeignSheet && !relationship
  && viewerEntityId`: not a GM rule but the handler's own precondition. A **roaming GM** has
  no acting entity, and there the handler early-returns — the button was simply **dead** — so
  it is hidden. A **GM acting as an entity** keeps it, because the tie belongs to the entity
  they are acting as, not to the GM. (First cut gated on `!gmMode`, which was wrong: it took
  the button from a GM who *was* acting as someone.) Reading the precondition instead of the
  role also covers any other no-acting-entity case for free.

### Sub-traits and containers

Nesting is **plain recursion**, not a special case: a **container** is an ordinary trait
carrying the `container` tag (registry ∪ instance tags, B116), so it inherits statements,
notes, SFX, polarity, provenance and fog-of-war for free, and it may even carry a rating.
The model and the decision behind it live in [[Container Traits Design Log]]; what follows
is the interaction convention.

- **One recursive row.** `sheet/TraitRow` renders itself for `subTraitSettings`, one
  `depth` per level, so nesting is as deep as the query delivered. The query spells out
  `QUERY_DEPTH = 4` levels as chained fragments in `CharacterSheet.vue` — raising one
  without the other silently truncates or over-fetches.
- **Expand to organize. Drill in to inspect.** Both affordances exist on purpose: the
  **name** always opens the trait detail/editor, while **expand** discloses a container's
  contents inline. Expand is the only one of the two that can support reordering, because
  a drag needs source and destination visible at once.
- **A container keeps its rating and adds a disclosure** — a chevron plus a count of
  everything beneath it (`countDescendants`), and the disclosure appears **only when there
  is something to disclose**. An empty container renders exactly like any other trait,
  because a chevron that opens nothing is a dead affordance (and empty is the state a
  container is in the moment it is tagged). On a container **with** contents, the row body
  *is* the expand toggle.
- **Sub-traits are chips.** Their list wraps and packs to the **right** — the edge the
  parent's own die sits on — rather than stacking as full rows. The morph tint rides the
  whole node, the trait *and* its contents, so a body's details read as the body's.
- **Grips are gated by destination.** A grip means "this can be picked up and put
  somewhere": a *root* row shows one only while some **open** container can receive it
  (never itself or its own descendant), and a nested row only when it sits **directly
  inside** a container, so it can be pulled back out. A sub-trait of a sub-trait is part of
  its parent and never moves.
- **"Open" for arranging means expanded *or empty*.** An empty container has no chevron,
  so requiring a tap to expand it would deadlock: it could never be opened, so nothing
  could ever be dropped into it.
- **Drop zones are forgiving.** A container row takes the trait; **any other row** means
  "out, to the top of the set" — on touch the row you drag past on the way out is exactly
  the one above the container, so the whole row is the out-zone on purpose. Landing a trait
  opens its new container, so the trait does not appear to have vanished.
- **Set order is ego → morph → containers last** (`sortSetTraits`, stable). Reordering
  within a group is **deferred**: `TraitSetting` has no `order` field and there is no
  mutation to persist one, so today the grip only moves a trait *in and out of* containers,
  and the row layout does not yet reserve grip space ([[Container Traits Design Log]]).
- **The set limit counts picks, not ownership.** A sub-trait is part of its parent, so a
  non-container contributes 1 however many sub-traits ride along; a **container contributes
  its children instead of itself**, so an empty container costs nothing and a container
  never enters the pool. This is a client-side convention — nothing on the server enforces
  it.

## Dice roller and dice panel

The bottom panel (`#dice-panel-wrapper`) is a retractable sheet. Open/close is a `transform` between fully-open (`translateY(0)`) and a `PANEL_CLOSED_PEEK` peek.

- **Desktop**: hover reveals (mouse-enter/leave + close timer).
- **Touch**: the **whole DiceRoller is the drag handle**.

### Drag-to-open/close gesture

1. `touchstart` on the roller begins the gesture (skipped for dice/slot drags and during PICKING).
2. `touchmove` translates the wrapper to **follow the finger 1:1** (transition disabled while dragging).
3. `touchend` settles — in priority order:
   1. **Flick velocity** → open/close.
   2. **Distance** dragged → open/close.
   3. Otherwise **revert** to the prior state.

Tunable constants:

| Constant | Location | Meaning | Current |
|---|---|---|---|
| `PANEL_CLOSED_PEEK` | App.vue | px left visible when closed | 56 |
| `PANEL_DRAG_DISTANCE` | App.vue | slow-drag px that triggers open/close | 72 |
| `PANEL_DRAG_VELOCITY` | App.vue | flick px/ms that triggers open/close | 0.5 |
| `PANEL_DRAG_SLOP` | DiceRoller.vue | dead-zone px before a touch is a drag | 8 |


**Panel position is stateless (B48).** The desktop sheet's closed offset lives in
`--panel-closed-y`, and the `.open` class sets `transform` itself:

```css
.dice-panel-wrapper      { transform: translateX(-50%) translateY(var(--panel-closed-y, 0px)); }
.dice-panel-wrapper.open { transform: translateX(-50%) translateY(0); }
```

**Which element carries that depends on the layout (B169).** Normally it is the
bottom-centre column; once the sheet has docked, the column *is* the dock and the peek
moves onto `.roller-band`, which is `position: fixed` there:

```css
.stage.dock-sheet .roller-band      { transform: translateX(-50%) translateY(var(--panel-closed-y, 0px)); }
.stage.dock-sheet .roller-band.open { transform: translateX(-50%) translateY(0); }
```

`App.vue` names that element `panelEl()` — the whole column, or the roller band when
`sheetDock`. The drag, `syncClosedPosition()` and `panelResizeObserver` all go through
it, so neither a drag nor a resize can write the peek onto the wrong element, and the
watcher on `sheetDock` clears any inline transform left on the one that just stopped
carrying it.

The closed offset used to be written as an **inline** `transform`, which beats a
class rule — so any code path that opened the panel (the sheet/peer/perspective
handlers set `sheetVisible = true`) without clearing that inline style left the
panel sitting at the 56px peek while the app believed it was open ("the
DiceRoller is sometimes hardly visible"). Only a live drag sets an inline
transform now, and both `openPanel()` and `closePanel()` clear it.
### Result/effect slots

- Slots are **draggable** (mouse + touch), just like pool dice.
- Dropping onto an **occupied** slot **swaps** the two dice; pool → occupied slot displaces the existing die back to the pool.
- An occupied slot renders **only the die** — no border, no background. Totals render as `DieIcon` with a larger result font.
- Every selection change is pushed to the server via the `select` endpoint (not only at commit).

## Peer selection

Two surfaces select a character (see [[System Architecture]] component table), and since
`fb78654` they **deliberately differ** — a chip is a rail you can act from, a dot is the
map itself. One `viewingEntityId` (the peek) sits beside `entityId` (who you are).

- **Peer faces follow the image's own nature.** A peer's sheet image is drawn either
  circle-cropped (a photo bubble) or as a **cutout**: when the image is background-removed,
  the face loses its circular crop, gains a bottom-only radius and
  hairline, and stands out of its own slot — the navdot / sheet-portrait treatment scaled
  to a chip, at the same ~45% overhang the sheet portrait uses (14px on a 20px slot). It
  is *drawn* wider than the slot (24×34 in 20×20) rather than resizing it, so a chip never
  changes size because of its art. Only the dock rail needs anything extra for this: its
  gap is 16px, so one tab's cutout rises into the gap instead of into the tab above it.
  **The flag must come from the resolution that produced the URL.** The image comes from
  `/entities/images`, which resolves through each entity's **active body**; the
  entity-level `sheetPortraitTransparent` is a *different* chain (`sheetPortrait`'s) and
  reports `false` whenever a body carries the image — which is normal, since sheet images
  are projection-scoped. So the peers ask for the active projection's own
  `sheetImageTransparent`, in one batched query for just the peers on screen. Asking the
  whole ~1000-row entity list for a transparency field measured **0.08s → 0.94s** per fetch,
  because each field costs a DB read.
- **Peer chips** (`app/PeersBar.vue` — the strip above the sheet, or the vertical rail
  at the dock's right edge on wide landscape, see *Landscape dock*) — two states, styled
  apart: **`.assumed`** (you *are* it — `entityId`) takes the solid accent fill;
  **`.viewing`** (you are only peeking — `viewingEntityId`) takes the accent border alone,
  no fill.
- **Occupant navdots** (on the location map) — their own semantics, below.

**Chips** (`onPeerClick`). A player's chip toggles inspect and never assumes: your own
chip (`entityId` *or* your main) returns to self — `viewingEntityId = null`, which brings
the header pills back — and another chip views it, a second click on that same chip
returning to self. A **GM** chip is view-then-assume:

1. first click on a peer → **view only** (foreign sheet), never assume;
2. second click on the peer you are viewing → **assume** it;
3. clicking the entity you already act as → drop the peek and keep acting on it; with
   nothing being viewed, it exits to free-roam.

A **location** chip is view-only at every step — a location is never assumed.

**Dots are not the chip toggle** (`onInspectEntity`). A player's self dot opens their own
sheet; a foreign dot opens it if it is closed or showing someone else, and closes it if it
is already showing that character. A GM's dot routes through the chip path with `fromMap`,
which changes exactly one thing — the mobile stack is not yanked to the sheet — and it
*selects* the sheet's content without opening the panel, since only `sheetVisible` opens it.

The distinction is the point: "who am I" and "who am I looking at" are different questions,
and a single `.active` class answered neither.

## Mobile focus stack

Player phones/portraits (≤ 820px) replace the desktop bottom-sheet
with three first-class vertical bands: **location** (top) · **character
sheet** (middle) · **dice roller** (bottom). Above the breakpoint the layout
depends on orientation — **portrait keeps the bottom-centre pop-out column,
landscape docks the sheet to the left** (see *Landscape dock* below).
**Architect (GM) mode gets the same stack**; while a GM
panel is open (`PanelStack`'s `.panel-viewport` exists) the sheet and roller
bands hide and the map takes the whole stage — the overlay controls in the
viewer hide too, leaving a clean design workspace (CSS-only via `:has`).

- **Focus = height.** The focused band grows; teaser bands keep a tappable
  strip. Bands size directly against the stage (explicit heights) so every
  height animates monotonically — no crossfade overshoot. Focus states:
  `location` (loc 77% / sheet 7% / roller 16%), `sheet` (loc 20% / sheet 64% /
  roller 16%), `dice` (content-dependent bottom stack: the roller takes its
  measured content height with **no viewport cap**, so a targeting wizard or
  consequence menu gets the room it needs while the bands above shrink to
  their minimums — location 10%, sheet teaser 56px, roller takes the rest).
- **Tap *or drag* a teaser to expand it.** App renders a capture layer
  (`.band-tap`) over every non-focused band; a tap expands the band, removing
  the layer. The focused band gets no capture layer, so its own interactions
  (travel dots, trait taps, dice drags) work normally. Focus is user-driven
  only — no auto-focus on phase changes (an earlier phase watcher caused
  surprising focus yanks around rolls).
- **Dragging a teaser pulls its band open.** The handle is the same
  `.band-tap` layer the tap uses — deliberately *not* the band body, which is
  full of the bands' own gestures (the roller's drag, travel dots, occupant
  drags, trait grips and long-press); a band-wide handle would fight all of
  them. The gesture reuses the dice panel's vocabulary: an 8px dead-zone so a
  tap stays a tap, then the bands interpolate between the current and target
  focus states at **1:1 with the finger**, then the release settles on flick
  velocity (0.5 px/ms) or distance (72px), else reverts to where it started.
  A drag swallows the click the browser fires on release, so it cannot
  double-apply.
  - The handle sits on a *teaser*, so you grab the band you want and pull it
    open; the sheet band is reachable from either direction.
  - **The target layout is measured, not duplicated.** The gesture needs the
    bands' heights in the target state, and those live in CSS and differ per
    state — `focus-dice` mixes percentages, a 56px sheet teaser and the
    measured `--roller-h`, and `:has(.kind-empty-pool)` and `sheet-empty`
    each redistribute again. So the drag swaps the focus class with
    transitions off for one synchronous frame, measures, and swaps back:
    no second copy of the numbers to drift. (Consequence worth knowing: with
    an **empty pool** the roller band collapses to 0 while the location is
    focused, so there is no roller teaser to grab there — the roller is
    reached from the sheet teaser.)
  - The empty-pool and empty-sheet rules still apply at the endpoints; a
    band that cannot grow simply does not start a drag.
- **Empty pool hides the roller.** While the location is focused and the
  roller shows nothing (`kind-empty-pool` — no dice, no roll in flight, no
  results), the roller band collapses to 0 (93% / 7% / 0) and the location
  absorbs the space in the same 0.45s motion. The band glides back the
  moment a die enters the pool or a roll starts. The roller stays reachable
  through the sheet teaser. (CSS-only via `:has(.roller-band
  .kind-empty-pool)` — no JS state.)
- **Empty sheet collapses (GM).** A GM with no acting/viewed entity has no
  sheet content — the band is removed entirely (`.sheet-empty`, peers bar is
  enough), the sheet focus state is unreachable, and location/dice states
  redistribute (loc 84% / roller 16%; dice focus drops the 56px sheet
  reservation). It returns the moment the GM acts as or inspects an entity.
- **Empty pool + sheet focused** — the roller teaser shrinks to a slim 7%
  strip (≈ the 56px sheet teaser of dice focus) and the [+] add-die toggle is
  hidden (dice come from the sheet anyway): 20% / 73% / 7%. Both return once
  a die is in the pool.
- **Organic transitions.** Every band height is a single animated length
  (`flex-basis`), so the whole column redistributes as one motion on a plain
  `ease-in-out` (~450ms). No `flex-grow`, no springy overshoot — an earlier
  bouncy `cubic-bezier` made panel heights look like they overshot their
  target and was removed.
- **Teaser camera (size-driven).** The whole scene renders relative to the
  viewer's container, so dots and background always share one coordinate
  space — the band can shrink without squeezing dots or drifting. The camera
  is a pure function of band height: full map down to 60% of window height,
  then a continuous 2× zoom (`TEASER_ZOOM`) toward the self character
  (centered at 20%). The band's own 0.45s focus animation drives the zoom —
  no recalculation jump, no discrete camera flag. Dots outside the crop clip
  via the band overflow. Desktop is unaffected (its container is the window).

Tunables: breakpoint `MOBILE_MAX_WIDTH = 820` (App.vue) mirrored by the
`@media (max-width: 820px)` block in `styles.css`; the focus grow ratios live
in that same CSS block. (`ArmedSfxRail.vue` carries a third `820` in its own
media block, and the `styles.css` one is *redundant*: every rule inside it is
prefixed `.stage.mobile-stack`, and that class only exists once the JS gate has
already matched — so `useMobileBands` is the source of truth and the media
wrapper guards only a one-frame flash on a widening resize.) The band drag's
own `BAND_DRAG_SLOP` / `_DISTANCE` / `_VELOCITY` live in `useMobileBands.js`
and match the dice panel's `PANEL_DRAG_*` feel. The desktop wrapper's
slide/peek mechanics are inert while the stack is active.

## Landscape dock

The third layout (B169). Above the phone breakpoint **and in landscape** the sheet
stops riding in the roller's bottom-centre column and docks to the left of the map as a
**permanent panel**. Portrait keeps the pop-out — a portrait tablet's column has height
to spare, and docking there would spend the wrong axis. Below the breakpoint nothing
changes.

- **The gate is width *and* orientation** — one `matchMedia` in `useMobileBands`
  (`(min-width: 821px) and (orientation: landscape)`), exposed as `sheetDock`. Both
  conjuncts carry weight: orientation alone would dock an iPhone SE in landscape
  (667×375) and leave it a 267px map. It is deliberately **not** keyed on available
  height — every standard iPad landscape viewport is ≥744px tall (1133×744 mini,
  1180×820, 1194×834, 1366×1024), so a height ceiling would never fire on a tablet in
  landscape; it would dock only the phone-landscape case and refuse the tablet one.
  The two gates are mutually exclusive by width, so `.dock-sheet` and `.mobile-stack`
  can never both apply.
- **Permanent, and decoupled from the roller.** Nothing summons the dock and nothing
  dismisses it: it does not follow the roller's hover, the phase, or whether a character
  was explicitly picked. `sheetShown` short-circuits to `true` when docked, and the
  sheet's `:visible` / `.sheet-hidden` bindings both carry a `sheetDock` exemption so a
  hidden sheet cannot be left behind. The reverse holds too — `rollerOpen()` is
  `hoverOpen` alone when docked, so selecting a character no longer drags the roller
  open with it. (It is `hoverOpen || sheetVisible` in the pop-out, where sheet and roller
  genuinely are one column.)
- **A phone in landscape gets a narrower dock.** 400px is about half of an 873px phone,
  so when the viewport is **short** (≤500px — phones held sideways are 360–430px tall,
  while tablets in landscape are ≥744px) `--dock-w` drops to **224px** and the map takes
  the rest (649px of 873 measured). *Shortness* is the discriminator, not being in
  landscape, so a tablet in landscape keeps the full-width dock — pinned by a test.
  That mode also carries **12px of top room**: the sheet's portrait pops above its own
  header, and the narrower the sheet the taller that header gets, so on the narrowest
  phone measured (873×393) the portrait was clipped 5px off the top of the screen. 8px
  cleared it; 12px gives margin and lifts the peers bar off the screen edge too.
- **That width is tunable from the address bar**: `?dockw=340` sets and remembers it,
  `?dockw=reset` forgets it. It feeds `--dock-w-short`, which only the short-viewport dock
  consumes, so a desktop can never inherit a phone's number. It exists because this is a
  feel number judged on a phone, where there is no devtools.
- **The peer strip is rotated into the seam.** As a horizontal strip it was 400px pinned
  in the screen's top-left corner, scrolling sideways once the roster outgrew it (4 of 7
  chips visible at 1194×834); it is now a vertical rail on the dock's right edge —
  between the sheet and the map — that the whole roster fits down. `writing-mode:
  vertical-rl` rather than `transform: rotate()`, so the chips turn with the text (the
  rail stays ~40px wide and the sheet keeps its width) while the portraits inside stay
  upright. The dock is a two-column grid for this: sheet | rail.
- **That rotation cost the sheet the top room the rail had been providing.** The sheet's
  portrait overhangs its own header by ~34px; with the strip moved out of the dock's top
  the sheet band began at the screen edge and the portrait was clipped 34px off the top of
  the display (measured). The sheet band now carries 40px of top padding instead, so the
  overhang has somewhere to go.
- **Scope:** the dock is one code path, so this is what wide *landscape* gets — tablet and
  desktop alike. Portrait tablets (and narrow desktop) keep the pop-out with the
  horizontal strip above the floating sheet, and the mobile band stack is untouched.

- **Where the sheet stops being cramped** (measured at 873×393). The toolbar is four
  ~43px pills laid *beside* the sheet's portrait, so it only regains a row once
  `dock − portrait` is wide enough. **160/200/224 are identical on every metric that reads
  as cramped** — placeholder 3 lines, pills 4 rows, 2 peer chips visible. 260 gives 2 rows
  / 2 lines, 300 a single-line placeholder, and **340** is where nothing wraps (1 row,
  1 line, 4 chips), costing map 533px. So the honest trade is ~340 for an un-cramped sheet
  against ~224 for a taller map. The real remaining fix is downstream and already logged:
  a narrow-width pass on the sheet's own header (reflow or drop the portrait beside the
  toolbar) is what would let a ~224px dock be comfortable — [[character-sheet]]'s
  verification debt, written when ~400px looked like the floor.
- **The dock is the wrapper.** `.dice-panel-wrapper` becomes a full-height left column
  (`--dock-w` — 400px by default, the width the sheet already had in the pop-out). It is
  inert itself (`pointer-events: none`, so its box cannot eat map clicks) and its children
  re-arm events for themselves.
- **The dock is deliberately transform-free.** A transformed ancestor would both drag
  the dock along with the roller's drag and capture the roller band's `position: fixed`
  — the peek lives on the band, not the column (see *Drag-to-open/close gesture*).
- **The map is inset, not overlaid.** `.location-viewer` takes `left: var(--dock-w)`,
  so its own top-left overlay controls ride along at 12px of the remaining map instead
  of disappearing under the sheet, and the viewer's `ResizeObserver` drives the camera.
  The Active SFX rail — which owns the left edge — steps right of the dock for the same
  reason.
- **The roller keeps its peek on a different element.** `.roller-band` becomes
  `position: fixed`, centred on the map area the dock leaves
  (`calc(50% + var(--dock-w) / 2)`, not 50%), and carries `--panel-closed-y` itself.
  It still opens on hover and settles on drag; hovering it reaches through the inert
  dock because the band re-arms pointer events for itself.
- **GM panels** draw over the dock exactly as they already drew over the roller
  (`.panel-viewport` is `z-index: 25`; the dock is 12).

Verified in the browser (Firefox + Chromium, `e2e/tests/dock.spec.js`): the dock is up
at 1280×950 **before anything is clicked**, with the map inset to 880 and the sheet
uncapped; selecting a character leaves the roller peeked and hovering the roller opens
the roller without disturbing the sheet; 834×1194 keeps the pop-out and its
`100dvh − 240px` cap; 390×844 keeps the band stack; 844×390 docks narrow (224px, map
inset to 649, no horizontal overflow); 1194×834 — a tablet in landscape — keeps the
full 400px dock, which is the boundary; and rotating hands the peek back to the column. The rail is
pinned as geometry *and* as a working control — a chip click has to land, because
rotating it moved the chips to a seam the sheet paints across and a dead rail passes a
pure-geometry check. A cutout peer face is checked by
stubbing the transparency flag over the wire — the testing character has no cutout art at
its location, and the stub has the side benefit of proving the field reaches the
component. A separate case pins the `?dockw` knob's contract (sets, persists, resets, and never
touches the desktop dock). The existing sheet-definition suite passes unchanged *inside*
the dock.

## Theming

Three layers over one token API, bound by one rule: **no palette colour appears
as a literal in a component.**

1. **Dark** — `:root` (the default).
2. **Light** — `html.light`: the same tokens with light values.
3. **Universe** — a palette on the universe entity, applied **inline** on
   `<html>` while that universe is in play (see [[#The universe palette]]).

- **Tokens are the only API.** `:root` holds the dark values (the default);
  `html.light` overrides the same tokens with light values. `color-scheme`
  is set per block so native controls and scrollbars follow.
- **Neutral overlays are text-mixed** (`--overlay-N: color-mix(in srgb,
  var(--text) N%, transparent)`) so hovers/borders flip automatically when
  `--text` flips. Hue tints (`--accent-12`, `--danger-45`, …) mix from the
  base hue, so a universe palette only needs to override the base color.
- **Detection** — `useColorMode` (VueUse) in `App.vue`: follows the OS,
  persists a manual override to `localStorage`, toggles a `.light`/`.dark`
  class on `<html>`, and keeps the `theme-color` meta in sync. `useThemeMode`
  also exposes `isLight` — the **resolved** theme — because a universe palette
  has to know which of its two halves to paint, and the *preference* cannot
  answer that in Auto.
- **Theme-stable surfaces** stay dark in both themes because they render on
  their own dark canvas: the location map (`LocationViewer`, `MapDot`), the GM
  graph (`canvas/*`), dice (`DieIcon`, `PoolDiceRing`, die chips), and the
  resonance divider (`WaveformDivider`). Their colors are kept as literal or
  as `--map-*` / `--dot-*` / `--die-*` tokens.
- **Light variants** darken the base hue tokens ~10–15% for contrast on light
  surfaces (`--accent`, `--danger`, `--success`, `--warn`, `--resource`,
  `--offered`); `--accent-dim` flips to a pale blue `#b9d3ec` so its
  `background + var(--text)` pairing stays readable in both themes.

**In-app control.** Settings → *Appearance* offers Auto / Light / Dark
(`app/AppearanceBlock.vue` over a `SegmentedControl`). It stores the
*preference*, not the resolved theme: `useThemeMode` runs `useColorMode` with
`emitAuto`, so Auto stays visible and the `theme-color` meta tracks whatever
theme is actually applied (in Auto, the device's).

### The universe palette

**The universe in play repaints the app's chrome** — accent, surfaces, borders
and type — so Earth reads as a filing system and the Three Realms as jade and
bamboo paper. The **map, the GM canvas and the dice do not follow it**: they
render on their own dark canvas and answer to the scene's art and to the
semantic colour of a die face, not to the universe's ink.

**Authored, not coded.** The palette is a field on the **universe entity**
(`Entity.palette`, a JSON object — the same shape as `lora_config`: one field
per universe, a JSON string on the GraphQL wire, no frontend release per
universe). `db/universe_palettes.py` is the shape reference and carries two
worked examples; `seed_universes` gives a *new* universe its example, and
`backfill_universe_palettes.py` fills a blank one on an existing database —
**never overwriting an authored palette**, because the entity is the source of
truth from the moment it has a value.

**Two halves in one object.** The palette carries both themes, because it is
written inline where it would otherwise outrank `html.light`:

```json
{
  "font":   { "ui": "…", "display": "…" },
  "radius": "0px",
  "dark":   { "accent": "#4a7fb5", "bgDeep": "#0e1013", "…": "…" },
  "light":  { "accent": "#1f4e79", "bgDeep": "#e6e2d6", "…": "…" }
}
```

`font` and `radius` sit **outside** the theme groups, because type and shape
are not per-theme: a light/dark flip must not change them.

**Semantic knobs, one mapping table.** `assets/universePalette.js` is the only
place a knob becomes a token, so the token API can move without breaking
authored content and a misspelled knob is *reported* instead of silently doing
nothing (`check-universe-theme.mjs` fails on one; the composable warns once).

| Group | Knobs | Tokens |
|---|---|---|
| accent | `accent` · `accentDim` · `accentActive` | `--accent` (and every `--accent-N` tint, mixed from it), `--accent-dim`, `--accent-active` |
| surfaces | `bgDeep` · `bgOverlay` · `bgPanel` · `bgPanelSolid` · `bgPanelRaised` | the `--bg-*` family |
| text | `text` · `textDim` | `--text` (neutral overlays derive from it), `--text-dim` |
| borders | `border` · `borderSoft` · `borderStrong` | `--border`, `--border-soft`, `--border-strong` |
| type | `font.ui` · `font.display` | `--font-ui`, `--font-display` |
| shape | `radius` | `--radius` + the derived step scale |

**The step scale is derived, so a palette sets one number.** `--radius-lg`,
`-sm`, `-xs` and `-chip` are computed in `styles.css` from `--radius`
(−2/−4/−6 px, +10 px, each clamped at 0), and their defaults at `--radius: 10px`
are **exactly** the values the app shipped with (8/6/4/20). A palette that sets
`radius` also squares the pills (`--radius-pill` follows it), because a corner
language is one decision, not two.

**Four rules the layer keeps:**

1. **Inline, and re-applied on a theme flip.** `useUniverseTheme` watches the
   resolved theme and repaints, because an inline override outranks
   `html.light`; an unreactive palette would leave a dark accent in light mode.
2. **Cleared, then written.** The vars a palette can write are removed before
   the next one is painted, so a knob the *next* universe does not set returns
   to the stylesheet's value instead of following the player across universes
   (a dark-only palette contributes no colour in light mode).
3. **A missing or broken palette is not a failure.** No palette — or none for
   this theme — leaves the app's own tokens standing; unparseable content is
   warned about and the universe keeps the default look.
4. **Nothing else may set a palette token inline.** The composable owns the
   `:root` overrides; `html[data-universe="<key>"]` names the owner and is an
   inspection hook, never a style hook.

**Not on the scale yet, deliberately.** ~315 `border-radius` literals remain in
surface files. `styles.css`, the shared `ui/` primitives, `gm/Panel` and the
sheet's own chrome are on the scale; a component that hard-codes a radius
simply does not follow the knob, and migrating it is its owner's call
(`var(--radius-sm|-lg|-xs)` — the defaults are unchanged). Typography is
similarly partial: `--font-ui` reaches the body, buttons, inputs, textareas and
the four real headings (settings title, player name, panel title, sheet name),
and `--font-display` reaches only those headings.

**Verification, three ways.** `scripts/check-universe-theme.mjs` (mapping: every
var it writes exists in `styles.css`, nothing it can paint escapes the clear
list, a dark-only palette paints no dark colour in light, unknown knobs are
reported). `src/api/tests/test_universe_palettes.py` (the authored examples:
vocabulary shape, opaque colours, and the 3:1 text-on-panel visibility floor in
both themes — the same floor `check-theme-tokens.mjs` applies to the stylesheet,
which cannot see runtime overrides). `e2e/tests/universe-theme.spec.js` (the
wiring, in a browser: the palette reaches `:root` for the universe in play, a
live theme flip repaints the other half without a reload, and a different
palette clears what the last one set).

**Authoring it: the universe palette panel** (a universe entity's editor → *🎨
Universe Style*, landed 2026-09-26). It hangs off the **universe entity**, beside
*LoRA Configuration* and *Roll Tables*, because that is where the palette lives: a
universe's look is a field of the universe, and whoever is editing that universe is
already in its editor. It opens on that universe — the editor hands it the key —
and a picker at the top can switch, so two universes can be compared without going
back. (It is still its own panel rather than a block in the form: the doorway is
the entity, the surface is separate.)

- **The vocabulary is the mapper's, not a second list.** The panel is built from
  `KNOWN_KNOBS` and saves through `cleanPalette`, so it cannot author a knob the
  runtime would ignore, and it names **no CSS property itself** — `paletteVars`
  stays the only knob → token table (`check-universe-theme.mjs` fails on a `--`
  property in the panel's template).
- **Blank means unset, not empty.** An omitted knob is how the runtime keeps the
  app's own value, so `cleanPalette` drops blank fields and empty groups, and a
  palette with nothing left is saved as `""` — the resolver's "clear it". Writing
  `""` into a knob would paint an invalid value instead of falling back.
- **Live preview, through the one writer.** `setPalettePreview` hands the
  in-progress palette to `useUniverseTheme`, which still owns the `:root`
  properties; the panel touches no style. A preview paints the **edited** palette
  whatever universe is in play (an author is looking at what they are making), and
  it is released on save, on revert, and when the panel unmounts — an unsaved
  experiment must not keep painting once the panel is gone.
- **It never silently no-ops a save.** The editable rows do not exist until the
  universe list has loaded, precisely so a keystroke cannot land in a form that is
  about to be replaced by `adopt()` — which is what happened before the load state
  existed: a Save that did nothing, then the typed value wiped.
- **The visibility floor is shown where it applies.** A palette can be unreadable,
  and the person authoring it is the one who can fix it, so any of `text` /
  `textDim` / `accent` below 3:1 against its own theme's `bgPanelSolid` is flagged
  **in that row**, with the ratio and the surface it was measured against
  (`paletteContrastWarnings`; the same floor the API test applies to the shipped
  examples, and the same reason translucent values are skipped rather than guessed
  at).
- **Buttons:** Save (loading state, implies disabled), Revert (re-read from the
  entity), Clear (back to the app's default look — `backfill_universe_palettes.py`
  can put a shipped example back, since it fills a *blank* palette).

**Element CSS: a universe styles shapes, not only colours.** A palette's
`styles` map names an **element** and carries a block of CSS **declarations** for
it — no selector — so a universe can make its rows bamboo slats (the Three Realms
example: a vertical gradient of the roll's shading) without a release and without
the author knowing a class name. The vocabulary is fixed (`STYLE_TARGETS` in
`assets/universePalette.js`): the character sheet panel, trait rows, choice-table
rows — adding another is one line there, plus the mirror in `db/universe_palettes.py`.

- **The runtime supplies the selector, scoped to the universe**:
  `html[data-universe="three_realms"] .trait-row { … }`. That prefix is not only
  the scope — it is the **precedence**: a component's own scoped rule is 0-2-0
  (`.trait-row[data-v-…]`) and the prefixed one is 0-2-1, so an ordinary
  declaration restyles a row without `!important`. A *state* variant (a trait in
  the pool, the row a roll found, `:hover`) still wins on purpose, so state reads
  through the styling; `!important` is the escape hatch inside a declaration when
  a universe disagrees.
- **One block per element, both themes.** There is no per-theme split — an element
  is declared once — so a theme-aware treatment uses `light-dark(a, b)` (the app
  sets `color-scheme` per theme, so it resolves by itself) or the palette's own
  tokens, which already flip. The bamboo example does the former.
- **The composable owns the stylesheet**, exactly as it owns the `:root`
  properties: one `<style id="universe-style">`, written with `textContent` (so
  authored CSS is never parsed as markup), cleared with the vars so a universe
  change cannot leave rules behind, and removed on teardown. Declarations cannot
  escape their rule, which is why the vocabulary is declarations rather than raw
  CSS.
- **It previews like everything else** — `styles` rides in the palette object, so
  the panel's live preview (below) shows the slats while they are typed.

**The colour picker is a library** (`vanilla-colorful`, MIT, no dependencies,
~15KB): a hue/saturation area with an **alpha** slider, rendered as one
`<hex-alpha-color-picker>` per open swatch, in the row it is editing rather than a
popover that could clip inside the panel. It speaks hex with an alpha byte while
the palette stores what CSS wants — opaque as `#rrggbb`, translucent as
`rgba(…)`, which is what the surfaces already use — so `toPickerColor` /
`fromPickerColor` convert at the boundary and a stored colour survives
picker → palette → picker. Vue's compiler is told it is a custom element
(`vite.config.js`), or it would be resolved as a component and render nothing.

> [!note] Adding a frontend dependency is an image change
> `src/frontend/Dockerfile` runs `npm install` at *image* build time, and the dev
> containers mount only `src/`, `public/` and `vite.config.js`. So a new
> dependency needs `docker build -t transversal2-frontend:latest src/frontend`
> **and** a running dev server that can resolve it — either recreated, or given
> the package with `docker exec tv2_frontend npm install <pkg>` (which is what
> landed here, so `:3000` never stopped serving).

**Adding a palette without the panel** — write the JSON on the universe entity (an
MCP `update_entity`, or a new example in `db/universe_palettes.py` plus the
backfill); keep both `dark` and `light` readable; check it in the app in both
themes. Nothing in the frontend changes, and a universe without one keeps the
app's default look.

## Activation splash

The surface for everything the **engine** does to a player who asked for nothing
([[B229]]): `app/SplashPanel.vue`. It sits where the floating choice host sat
(bottom-right on a desktop — the sheet docks left, the roller bottom-centre, the ✨
rail left; the top banner on a phone, where the bands own the bottom), above the GM
panel viewport and below the login overlay. **One surface, two faces** — the author's
rule is that the splash *is* where engine-initiated prompts appear, so a question and
a "here is what changed" must not be two different corners of the screen.

| face | what it is | how it ends |
|---|---|---|
| **prompt** | a choice the engine raised: an automatic rule, a routed question, a [[B5]] branch | only an interaction — answered, or the wizard's own Cancel (writes nothing) |
| **note** | what an activation did, including **why an effect did nothing** ([[B236]]) | it **fades**: ~2 s for a change, ~5 s for a rule that has run its course |

- **A note is a report, not a decision.** It never blocks anything, never has a
  scrim, is never interactive, and is announced (`role="status"`) rather than only
  seen. Its lines carry a `silent` flag for an effect that did nothing — the whole
  point of the surface, because a refusal used to be indistinguishable from a
  success on the wire.
- **The queue shows one at a time, in order.** A burst of changes is not a stack
  of dialogs; each is a brief banner that waits its turn.
- **A note's dwell is the time it is on screen.** The clock starts only when the
  note is actually visible, so a report that arrives while a question is up is
  *held* rather than ageing unseen behind it, and released when the question is
  answered or left.
- **The audience is the player it happened to**: the entity they are acting as, or
  the place they are standing in. A change to someone else's sheet is not theirs to
  read — deliberately not even a GM's, whose acting entity is the one that counts.
- **The shell owns the timing, the surface owns the shape.** `App.vue` holds the
  queue, the dwell and the audience; the component renders the prompt or the head
  of the queue. That is what keeps "1–2 seconds" a decision in one place instead of
  a number in a component.

### What the effects layer emits for it

A prompt needs nothing new: `sfx_choice_required` already carries `origin`
(`auto` for a rule nobody pressed), `entity_id` and the `choices` — so **a routed
question ([[B229]] item 4) is aimed by setting `entity_id` to the chosen entity and
emitting to *their* session**; the surface renders whatever it is handed, and its
`entity_id` is what the wizard resolves against.

A note is one event, and its shape is the contract:

```
event: effects_changed
data: {
  entity_id:   "<whose change this is>",     // the audience
  location_id: "<the place>",                // optional: a change *in* their location
  title:       "<the rule's name>",
  kind:        "change" | "summary",         // the dwell: ~2 s | ~5 s
  lines:       [ "what it did", { text: "why it did nothing", silent: true } ]
}
```

## Razmerit

`− value +` controls around the amount, with touch-friendly round buttons (no background). Tapping the value opens direct numeric input.

## Related

- [[System Architecture]] — component inventory and data flow.
- [[Dice Mechanics]] — resolution rules the roller implements.
- [[Entities and Traits]] — trait model the sheet renders.
- [[Relational Canvas]] — GM graph interaction conventions.
