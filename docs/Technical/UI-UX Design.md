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

## Character sheet

Navigation lives in the header **pills**: 👤 profile · 🎲 traits · 📘 bluebook · 🛤️ lifepath (GM also gets 🌍 show-all-traits).

- **Profile first** (leftmost). Its traits render in a wrapping flexbox with no per-trait border.
- **Traits tab** is a drill-in:
  1. **Trait-set list** — set name + limit dots.
  2. **Trait list** — tap a set to drill in; the set name becomes the click-to-return title.
  3. **Trait editor** — a full-panel view (replaces the trait list) with rating type, dice, polarity, statement, SFX.
- **Next set**: a `Next: <name> →` button sits under the trait list (right-aligned), jumping to the next set without picking. When a set fills to its limit, the view **auto-advances to the next set** (and returns to the list on the last set).
- **Own vs foreign sheet**: your own sheet always shows the pills; a foreign sheet hides them and swaps in the relationship widget + "add relationship" affordance.

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

### Result/effect slots

- Slots are **draggable** (mouse + touch), just like pool dice.
- Dropping onto an **occupied** slot **swaps** the two dice; pool → occupied slot displaces the existing die back to the pool.
- An occupied slot renders **only the die** — no border, no background. Totals render as `DieIcon` with a larger result font.
- Every selection change is pushed to the server via the `select` endpoint (not only at commit).

## Peer selection

Two surfaces select a character and must agree (see [[System Architecture]] component table):

- **Peer chips** (above the character sheet).
- **Occupant navdots** (on the location map).

Shared semantics (both route through the same toggle):

- Click a peer → inspect that character (foreign sheet).
- Click the **same peer again** → return to self.
- Click **your own chip/dot** → return to self (`viewingEntityId = null`), keeping the header pills visible.

## Mobile focus stack

Player phones/portraits (≤ 820px, non-GM) replace the desktop bottom-sheet
with three first-class vertical bands: **location** (top) · **character
sheet** (middle) · **dice roller** (bottom). The desktop layout is untouched
above the breakpoint.

- **Focus = height.** The focused band grows; teaser bands keep a tappable
  strip. Bands size directly against the stage (explicit heights) so every
  height animates monotonically — no crossfade overshoot. Focus states:
  `location` (loc 77% / sheet 7% / roller 16%), `sheet` (loc 20% / sheet 64% /
  roller 16%), `dice` (content-dependent bottom stack: the roller takes its
  natural height up to 42dvh and scrolls beyond; the sheet is a fixed 56px
  header teaser; the location fills the rest).
- **Tap a teaser to expand it.** App renders a capture layer (`.band-tap`)
  over every non-focused band; the first tap expands the band, removing the
  layer. The focused band gets no capture layer, so its own interactions
  (travel dots, trait taps, dice drags) work normally. Focus is tap-driven
  only — no auto-focus on phase changes (an earlier phase watcher caused
  surprising focus yanks around rolls).
- **Organic transitions.** Every band height is a single animated length
  (`flex-basis`), so the whole column redistributes as one motion on a plain
  `ease-in-out` (~450ms). No `flex-grow`, no springy overshoot — an earlier
  bouncy `cubic-bezier` made panel heights look like they overshot their
  target and was removed.

Tunables: breakpoint `MOBILE_MAX_WIDTH = 820` (App.vue) mirrored by the
`@media (max-width: 820px)` block in `styles.css`; the focus grow ratios live
in that same CSS block. The desktop wrapper's slide/peek mechanics (hover,
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

## Razmerit

`− value +` controls around the amount, with touch-friendly round buttons (no background). Tapping the value opens direct numeric input.

## Related

- [[System Architecture]] — component inventory and data flow.
- [[Dice Mechanics]] — resolution rules the roller implements.
- [[Entities and Traits]] — trait model the sheet renders.
- [[Relational Canvas]] — GM graph interaction conventions.
