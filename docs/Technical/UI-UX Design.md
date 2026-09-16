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
`GmListItem`, `TargetPicker`/`SearchDropdown`, `EntryPicker`, `Button`,
`DangerButton`, `TagInput`, `TraitInstanceEditor`, `SegmentedControl`. (The `gm/`
folder keeps the GM-specific panels, which compose these primitives.) New
surfaces should compose the primitives instead of re-styling raw elements.

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

**It reports what was chosen and nothing else.** Resolving the pick is the
host's, and the hosts genuinely differ: the roll-table and consequence menus
hand off to `EffectTargetWizard` and then apply, while the hitch menu hands the
option back to the dice roller. Baking the wizard into the picker would have
made it a one-host component.

- **An entry** is `{ id?, key?, label, description?, cost?, costFree?, hint?,
  tone?, disabled?, weight? }`. `key` is the leading cell (a roll table's
  range), `tone` is a semantic edge (`gm` / `player` — the consequence menu's
  sides), `cost` is the trailing figure and `hint` the fallback when there is no
  cost.
- **The random pick is opt-in** (`allow-random`, off by default): rolling is
  native to a roll table, while a consequence or a hitch is usually a deliberate
  choice, so each host decides. A list carrying `weight`s rolls a die over the
  cumulative weights and reports the number as a third `pick` argument; an
  unweighted list picks uniformly and reports none. Disabled and zero-weight
  entries are never rolled.
- **The index is 0-based** — `pick(entry, index, roll)`. The roll-table API it
  feeds is **1-based**, so `RollTableMenu` adds the 1 at the boundary.
- **Busy is not loading.** While a host is applying a pick the list stays on
  screen and goes inert (`busy`); it only reads *Loading…* before it has options.
- **Not yet on it:** the life-path wizard. It has the same shape (a table of
  entries with a weighted roll) but resolves server-side per term and drives the
  dice, so it is the natural next adopter rather than something to force.

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
and picker chips, toggles, wizard candidate rows, the composite imagen button, and the 🛠
panel anchor — its 42px geometry feeds the rail anchor math. Segmented controls have their
own primitive now ([[#SegmentedControl]]), so they are a `SegmentedControl` migration, not
a `Button` one.

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
- **Own vs foreign sheet**: your own sheet always shows the pills; a foreign sheet hides them and swaps in the relationship widget + "add relationship" affordance.

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
`--panel-closed-y` on `.dice-panel-wrapper`, and the `.open` class sets
`transform` itself:

```css
.dice-panel-wrapper      { transform: translateX(-50%) translateY(var(--panel-closed-y, 0px)); }
.dice-panel-wrapper.open { transform: translateX(-50%) translateY(0); }
```

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

- **Peer chips** (`app/PeersBar.vue`, the strip above the sheet) — two states, styled
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
sheet** (middle) · **dice roller** (bottom). The desktop layout is untouched
above the breakpoint. **Architect (GM) mode gets the same stack**; while a GM
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
in that same CSS block. The band drag's own `BAND_DRAG_SLOP` / `_DISTANCE` /
`_VELOCITY` live in `useMobileBands.js` and match the dice panel's
`PANEL_DRAG_*` feel. The desktop wrapper's slide/peek mechanics (hover,
`syncClosedPosition`, panel drag) are inert while the stack is active.

## Theming

Light and dark are **fallback layers** over one token API; a future
per-universe palette is an **override layer** (universe entity → inline
`--` overrides on `:root`). Both share the rule that no palette color appears
as a literal in components.

- **Tokens are the only API.** `:root` holds the dark values (the default);
  `html.light` overrides the same tokens with light values. `color-scheme`
  is set per block so native controls and scrollbars follow.
- **Neutral overlays are text-mixed** (`--overlay-N: color-mix(in srgb,
  var(--text) N%, transparent)`) so hovers/borders flip automatically when
  `--text` flips. Hue tints (`--accent-12`, `--danger-45`, …) mix from the
  base hue, so a universe palette only needs to override the base color.
- **Detection** — `useColorMode` (VueUse) in `App.vue`: follows the OS,
  persists a manual override to `localStorage`, toggles a `.light`/`.dark`
  class on `<html>`, and keeps the `theme-color` meta in sync. No toggle UI
  yet (settings overlay later).
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
## Razmerit

`− value +` controls around the amount, with touch-friendly round buttons (no background). Tapping the value opens direct numeric input.

## Related

- [[System Architecture]] — component inventory and data flow.
- [[Dice Mechanics]] — resolution rules the roller implements.
- [[Entities and Traits]] — trait model the sheet renders.
- [[Relational Canvas]] — GM graph interaction conventions.
