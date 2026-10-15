---
title: Name Generation
date: 2026-09-28
last-updated: 2026-09-28
tags:
  - transversal
  - technical
  - entities
  - content
aliases:
  - Naming Themes
  - Name Generator
---

# Name Generation

> [!info] Built 2026-09-28 ([[B82]]) — the engine, the universe's theme, and the API
> `services/name_generator.py` plus `randomNames` / `namingThemes` on the GraphQL
> surface. The **UI buttons are not built** — see *What is still needed*.

The human's ask: *"generate thematic names. Alien names, fantasy names, Chinese names,
etc. I'd like the universe to be able to set the naming theme."*

## Two generator shapes, because "alien" and "Chinese" are different problems

A single name list cannot do both jobs, so a theme is one of two things:

- **Syllable themes** — onsets, nuclei, codas, a syllable count, and optional suffixes.
  This is what gives a world a *phonology*, and it is the half no name list can
  provide: `fantasy`, `alien`, `elvish`, `guttural`.
- **List themes** — curated given and family names, for the themes where the names are
  **real**: `chinese`, `japanese`, `norse` (patronymic and gender-agreeing), `slavic`,
  `arabic`, `modern`.

`namingThemes` returns the registry so a picker reads it rather than hard-coding the
list, and a universe names one with `Entity.naming_theme`. An **unknown** key — a world
naming a theme a newer build carries — falls back to the default rather than failing.

## Measured: the phonology took two attempts

The first cut gave **every syllable an onset and a coda** and allowed a break at every
boundary. It produced `Dreiciostbriom` and `Tzith'nizzoass` — consonant mush, which
reads as *random* rather than *foreign*. Two rules fixed it:

- a **coda only ever closes the word**; between syllables it collided with the next
  onset, which is where the clusters came from;
- a name takes **at most one** break mark, and only between syllables.

A third coherence rule: with no gender asked for, the patronymic ending follows the name
actually drawn — otherwise the generator emits `Vigdis Hakonsson`. All three are pinned
by tests.

```python
generate("alien",   seed=7) → Vro'vaiq'zaiz …
generate("chinese", seed=3) → Gao Qiang, Chen Kai, Luo Bo
generate("norse", gender="male", seed=2) → Bjorn Eiriksson, Eirik Ragnardsson
```

## Public APIs — probed, then made opt-in

The human is happy with public APIs, so they are supported. They were **measured from
the API container itself** before anything was built on them:

| provider | result |
| --- | --- |
| `behindthename.com` | works, but **needs a free key** (`{"error_code":1,"error":"invalid key"}`) — **and is the only one that takes a `usage=` code**, i.e. the only public source for `chinese` / `japanese` / `norse` |
| `randomuser.me` | ✅ keyless, 0.43 s — but `nat` is **western** (`nat=cn` returns a *French* name; there is no Chinese) |
| `namey.muffinlabs.com` | ✅ keyless, 1.1 s — western, no locale control |
| `uinames.com` | ❌ **dead: TLS certificate expired** |
| `fakerapi.it` | ❌ 502 Bad Gateway |
| `api.namefake.com` | ❌ 404 |

Two consequences, and they are the design:

1. **Remote is opt-in** (`NAME_REMOTE=1`). A game has to name an NPC on a machine with
   no uplink, and the table above shows providers rot — one of them died between being
   recommended and being probed.
2. **Every failure falls back to the local generator**, and a **seeded request is never
   remote**: a seed means *"give me that name again"*, which an API cannot honour.

A key for Behind the Name is read from `BEHINDTHENAME_KEY`. With it set, the thematic
themes gain a real source; without it, nothing changes. That key is the one open
decision — it is the only way to get public *Chinese* names, and it is the human's to
obtain.

## The API

```graphql
randomNames(theme: String, universe: String, count: Int, gender: String, seed: Int): [String!]!
namingThemes: [NameThemeRef!]!
```

`universe` takes a universe **handle** (`earth`), not an entity id — that is what an
entity stores in `current_universe`. `theme` wins when both are given. `gender` is
honoured where a theme carries gendered names and ignored elsewhere. `count` is clamped
to 50.

## What is still needed

- **The UI buttons** ([[gm-panels]], [[character-sheet]]) — the human asked for them on
  the entity creation panel and the character sheet:
  - `GmEntityCreatePanel.vue` — beside `<input v-model="form.name">`; the universe comes
    from `resolveUniverse(form.location)`.
  - `GmEntityForm.vue` — beside `<input v-model="local.name">`; uses
    `local.current_universe`.
  - `CharacterSheet.vue` — the `projection-name-input` (the sheet's editable name is the
    *projection's*), using the entity's current universe.
- **The universe authoring field** — nothing sets `naming_theme` yet, so every world is
  on the default. The GM universe panel and the MCP `update_entity` passthrough both want
  it ([[gm-panels]], [[mcp-architect]]).
- **Behind the Name's key**, if public Chinese names are wanted.

## Related

- [[B82]] — the ticket.
- [[Data Model]] §`entities` — `naming_theme`.
