---
title: Roll Table and Life Path Authoring
date: 2026-09-11
tags:
  - transversal
  - manual
  - roll-table
  - life-path
  - gm
aliases:
  - Authoring Roll Tables
  - Roll Table Editor
  - Life Path Editor
  - How to write roll tables
status: draft
---

# Roll Table and Life Path Authoring

A practical guide to writing **roll tables** and **life paths** in the GM panels. A roll table is a named list of outcomes. A life path is a chain of those tables a character walks through to grow.

For the *rules* behind growth, see [[Character Growth]]. For how a shared table hands control back to the path that called it, see [[Life Path Flow and Shared Roll Tables]]. This page is the "how to use the editor" guide.

> [!note] Where it lives
> GM panels → open a **Universe** entity → **🎲 Roll Tables**. Everything below starts there. The button only appears on universe entities, because tables belong to a universe.

---

## The mental model

Three things, smallest to largest:

1. **A roll table** — a named list of **entries**. Each entry has a label (what it is) and effects (what happens).
2. **A life path** — a named chain of tables. It stores only one thing: **where the chain starts** (its *entry table*). Everything else is built from `Next Step` effects that point from one table to the next.
3. **Scope** — which universe a table belongs to, and whether it belongs to a life path.

A table is reached in one of two ways:

- **By a roll** — the result picks the entry.
- **By a menu** — an SFX opens the table and the player picks an entry on purpose.

Same table, same entries. Only the way in differs.

---

## The Roll Tables panel

Opening **🎲 Roll Tables** shows everything for that universe, split three ways:

- **Fundamental** — tables that belong to *every* universe (no universe, no life path). Use these for rules that always apply, like a generic Survive table.
- **Shared** — tables that belong to this universe but to no single life path. Two or more paths can use them.
- **Life paths** — one row per life path, with how many tables it already has.

Click a group to list its tables. Click a life path to open it.

---

## Building a roll table

1. Open **Fundamental** or **Shared** and click **＋ Add roll table** (or add one from inside a life path — see below).
2. Give it a **Name**.
3. Check the **Universe** and **Life path** pickers. Adding from a group fills these in for you; leave **Life path** empty for a shared table.
4. Pick a **Scheme** (see below).
5. Pick a **Roll source** (see below).
6. Add entries with **＋ Add entry**, and fill in each one.
7. Click **Save roll table**.

> [!tip] The panel fills the blanks
> Adding a table from **Fundamental** makes it universe-free. Adding from **Shared** pins it to the current universe. Adding from a life path attaches it to that path. You rarely need to change the pickers by hand.

### Picking a scheme

The scheme decides how an entry is chosen:

- **Range (min–max)** — you give each entry a number range (1–2, 3–5, 6). The rolled number picks the entry that covers it. Good for dice tables.
- **Weight** — entries have relative odds (`w2` is twice as likely as `w1`). Good when you want a feel for frequency rather than exact numbers.
- **Tier** — entries are picked by outcome tier (fail, marginal, success, exceptional, perfect). Use this when the table answers a roll.
- **Index (ordered)** — entries are just a numbered list. Use this for menus and for tables where order *is* the meaning.

### Picking a roll source

- **Fixed die** — the table rolls a die you choose. It takes a **notation**, any `dN`: the Cortex ladder (`d4`–`d12`), a `d20`, a `d100`, or a repeated-digit read (below).
- **Trait dice** — the table rolls dice from the character's traits; set how many. Use this when the character's own abilities should sway the result.

> [!warning] A repeated digit reads dice as digits — it is not one wide die
> `d66` means **two d6 read as digits**: 11, 12 … 66. That is 36 outcomes, and it
> never shows 7, 17, 20 or 60 — so a Range table's entries are written against
> **11–66**, never 1–66. The same rule gives `d88` as two d8 (11–88, 64 outcomes)
> and `d666` as three d6 (111–666).
>
> A number whose digits are *not* all the same is a plain die: `d100` is one
> hundred-sided die, 1–100, not a pair of d10. (`d11` is a plain eleven-sided
> die too — two d1 could only ever show 11.)

### Writing entries

Click **＋ Add entry** in the table editor, or click a row in the table's detail view to open one entry on its own. An entry has:

- **Label** — short and concrete: *"Injured"*, *"Promoted"*, *"Qi backlash"*. This is what the player reads.
- **Description** — one line of flavour, optional.
- **The key** — one field, depending on the scheme: **Min/Max**, **Weight**, or **Tier**. Index tables need nothing; position is the key.
- **Conditions** — gates. The entry only applies if they pass.
- **Effects** — what actually happens.

> [!tip] Write the label as the outcome, not the mechanic
> *"Sword Intent"* reads better than *"gain martial trait"*. The effects column already says what happens mechanically.

---

## Building a life path

1. On the Roll Tables panel, click **＋ Add life path**.
2. Fill in **Name**, **Universe** and **Description**. Hit **Save life path**.
3. Open the path from the list. Click **＋ Add roll table** to build its first table.
4. Repeat for every table in the chain.
5. Go back and **✎ Edit** the path to set its **Entry table id** — the table where a term begins.

From the path's own panel you can also:

- **🗺** — open the path in the canvas, to see and arrange the chain visually.
- **Delete life path** — removes the path (tables are separate; check them first).

> [!warning] The entry table is typed by hand today
> The editor asks for the entry table's id (`rt-…`), not a picker. Copy it from the table's detail panel. See [[#Not yet in the UI]] below.

### Discovery

A life path can be hidden until the character earns it — a hidden valley, an old master, an inherited dao. The path's panel shows its **Discovery** rules, and a path with none is *"visible to all"*.

Discovery rules are currently **read-only in the panels** — they are set through the effects/trigger layer. See [[#Not yet in the UI]].

---

## Wiring the chain

A chain is made of **flow effects** on entries. There are four you will use constantly:

- **Next Step** — go to another table. This is the chain's connective tissue. Leave the target empty to *end the term*.
- **Enroll In Life Path** — record that the character joined this path. Put it on the entry that accepts them.
- **Muster Out** — end the term on good terms; the character leaves the path.
- **Force Muster Out** — end the term badly (dishonourably).

Two more exist for special cases: **Discover Life Path** (unlock a hidden path) and **Draft Into Life Path** (send a character into a different path).

> [!tip] One table, one job
> Give each table a single purpose — Learn, Survive, Advance, Muster — and let `Next Step` join them. A table that does two jobs becomes impossible to reuse.

### Shared tables and named exits

A shared table can be used by many paths, but it cannot know where each path wants to go next. So it does not decide — it **returns**.

1. In the **shared** table, an entry's **Next Step** target is written as a *named exit*, like `{return:injured}` instead of a table.
2. In the **calling** table, the entry that steps into the shared table fills in a **Return To** map: one row per named exit, each pointing at the table that path should go to.

The map only offers exits that the target table actually declares. If it says *"No named exits in this table"*, the table you are calling declares none — go and add them.

> [!note] Why this exists
> *Survive* has two exits: injured and survived. Every path wants "injured" to lead to *its* mishap table and "survived" to *its* advance table. The named exit is how one shared table serves all of them. See [[Life Path Flow and Shared Roll Tables]].

---

## Reading a table at a glance

A table's detail view shows the whole thing on one screen: its scope chips, its check (if any), and every entry as a row of **# · key · label · effects**. Conditions show up under the label as *"if …"*.

This is the fastest way to spot a broken chain: if a label has no `Next Step`, that entry ends the term.

---

## A worked example — one simple term

A minimal path: **join → learn → survive → muster.**

1. **Make the path.** Roll Tables → **＋ Add life path** → name it *"Riverborn"*, universe *three_realms*.
2. **Make the entry table.** Open the path → **＋ Add roll table** → name it *"Entry"*, scheme **Index**.
3. **Write its entries.** Six entries, one per background. Each gets:
   - a label (*"Ferry-child"*),
   - a **gain trait** effect (the skill that background implies),
   - an **Enroll In Life Path** effect,
   - a **Next Step** to the Learn table.
4. **Make the Learn table.** Same path, scheme **Index**, six entries — each grants a trait and steps on to Survive.
5. **Make the Survive table.** Six entries: one *"Injured"* stepping to a Mishap table, five *"Survived"* stepping to Advance.
6. **Make the Advance table.** Scheme **Tier** — fail and marginal loop back to Learn, the rest grant a rank and step to Muster.
7. **Make the Muster table.** Scheme **Range**: 1–2 serves another term (back to Learn), 3–5 **Muster Out**, 6 **Force Muster Out**.
8. **Set the entry point.** Edit the path, set **Entry table id** to the Entry table's id.
9. **Offer it.** Add the path to a faction's suitable life paths so characters can take it.

That is a complete term loop: every entry either steps somewhere or ends the term.

---

## Gotchas

- **A path does nothing without its entry table.** If *Entry table id* is empty, the path can never start.
- **`Next Step` with an empty target ends the term.** That is correct for a "rejected" or terminal entry — just be sure it is what you meant.
- **Scope mismatch is silent.** A table scoped to one universe will not appear for another. Check the **Universe** picker before wondering where a table went.
- **Shared tables need a return map, not a literal target.** A shared table pointing at one path's table works for that path and quietly misroutes every other one.
- **Menu tables need a cost to feel like a choice.** Without a cost effect on the entry, "pick one" becomes "take everything".

---

## Not yet in the UI

Honest list, so you do not hunt for fields that are not there:

- **Entry costs** — an entry's pay-on-pick cost effects cannot be edited in the panels yet. Menu tables (like the support-cast archetypes) have to be set up by an agent until this lands.
- **Discovery rules** — displayed but not editable; they go through the effects layer.
- **Entry table** — a typed id, not a picker.
- **Path universe** — typed by hand, while tables get a picker.
- **Table check** — the dice-pool check on a table is not editable in the panels.

---

## Related

- [[Character Growth]] — what life paths are *for*: how characters grow
- [[Life Path Flow and Shared Roll Tables]] — the return-map model in detail
- [[Troupe Play]] — support-cast tables and the archetype menu
- [[SFX Authoring]] — the other authoring surface, for exceptions
- [[Data Model]] — the fields behind the forms
- [[User Manual]] — back to the manual index
