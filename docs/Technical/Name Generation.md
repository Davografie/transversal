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

A key for Behind the Name is read from `BEHINDTHENAME_KEY`, and — measured 2026-09-28 —
**the key alone is not enough**: it must also be *named in `docker-compose.yaml`*
(compose passes only what a service lists) **and** the seam needs `NAME_REMOTE`, since
remote use is opt-in. Both are now in the api service's environment. The key was in
`.env`, absent from the container, and the seam therefore off.

### The `usage` codes are codes, not names (found by probing, 2026-09-28)

The first mapping passed display names — `usage=chinese`, `usage=English` — and
**every one of them answered** `{"error_code":60,"error":"name could not be generated"}`.
Behind the Name takes a **three-letter code** from
[`/api/appendix2.php`](https://www.behindthename.com/api/appendix2.php): `chi`, `jap`,
`sca-anci` (Old Norse), `sla`, `ara`, `eng`. `number` is capped at **6**, and the key
allows 2 requests/second, 400/hour, 4000/day.

**The fallback hid it completely.** With a bad code every call failed and every call was
silently answered by the local generator, so the result *looked* like a working API
call — the only tell was that the names were the curated ones. Verified against the real
key after the fix:

```
chinese  → Ruoxi, Lijuan, Xiaoming, Han        japanese → Airi, Emi, Hideaki, Sousuke
norse    → Alfarr, Gunnhildr, Gunnarr          arabic   → Khayriyya, Manzur, Shawqi, Zeina
```

### What the key also unlocks — the fantasy categories

Behind the Name is not only real-world. It carries **invented fantasy cultures** and
**mythologies**, which is arguably a better answer to *"fantasy names, alien names"* than
a syllable generator, and they were probed too:

| code | what it is | sample |
| --- | --- | --- |
| `fntsr` | Romanto (fantasy) | Goxious, Copistrus, Arer |
| `fntsg` | Gluttakh (fantasy) | Zhid, Hazin, Ghauztsawodh |
| `fntsx` | Xalaxxi (fantasy) | Suouc, Noai, Aqchux |
| `lite-k` | Arthurian Cycle | Mordred, Gaheriet, Pelles |
| `sca-myth` | Norse Mythology | Heiðrún, Oddrún, Gunnarr |
| `fairy` / `witch` / `goth` | whimsical categories | Glittershine, Sprinkleleaf |

**Not wired yet, deliberately**: the constructed themes (`fantasy`, `alien`, `elvish`,
`guttural`) stay local so they behave identically online and off, and mapping them onto
Behind the Name's invented cultures is an authoring choice — *"Gluttakh"* is not a word a
GM can guess at. Two options, both open: give these categories **their own themes**, or
point the constructed themes at them and accept an online/offline difference.

### The route that removes the runtime dependency entirely

Behind the Name also publishes **downloadable name lists** (given names + genders,
surnames) under **CC BY-SA 4.0** — attribution required. Importing those once would give
the real-world and fantasy themes full offline coverage, no key, no rate limit, no
certificate to expire, and would let the API become a bonus rather than a dependency.
Worth doing before the curated lists are grown by hand.

## The API

```graphql
randomNames(theme: String, universe: String, count: Int, gender: String, seed: Int): [String!]!
namingThemes: [NameThemeRef!]!
```

`universe` takes a universe **handle** (`earth`), not an entity id — that is what an
entity stores in `current_universe`. `theme` wins when both are given. `gender` is
honoured where a theme carries gendered names and ignored elsewhere. `count` is clamped
to 50.

## The frontend (built 2026-09-28)

`src/frontend/src/composables/useNaming.js` is the one place that knows how to read the
themes and generate a name, so the surfaces cannot drift. The theme list is fetched
**once** and shared through a module-level ref — a component mounting after the first
fetch sees the loaded list rather than an empty dropdown — and `generateName` takes a
*universe* when no theme is given, because the world decides how its people are named
and a button should not have to know that.

| surface | what it offers |
| --- | --- |
| `GmEntityForm.vue` | 🎲 beside the Name field; a **Naming theme** dropdown for UNIVERSE entities |
| `GmEntityCreatePanel.vue` | 🎲 on the name field, universe resolved from the chosen location |
| `CharacterSheet.vue` | 🎲 on the projection-name input, using the entity's universe |

Three things worth keeping:

- **The dropdown is read, not hard-coded** (`namingThemes` + `namingDefaultTheme`), which
  is what makes `theme_keys()` a completeness guarantee: a theme declared on the server
  appears in the picker with no frontend change, and an unknown theme cannot be typed.
- **The sheet's name input commits on blur**, so its 🎲 carries `@mousedown.prevent`.
  Without it the click blurs the field, the edit ends and the button unmounts before it
  can fire — the kind of thing that only shows up in a browser.
- **The button only fills the field.** Committing stays the existing Enter/blur, so it can
  be pressed repeatedly to cycle without writing anything until you accept.
- **The dropdown's list is fetched on demand, and the fetch must not be gated on
  `onMounted`.** It shipped as `onMounted(() => isUniverse && loadThemes())`, and the
  dropdown had **one option, "Default ()"** — because the GM panel mounts the form
  *before* the entity it edits has loaded, so at mount `local.type` was still undefined
  and `namingThemes` was never requested. A `watch(isUniverse, …, { immediate: true })`
  covers both orders. Every node-level check passed while it was broken — the query, the
  composable and the template were all fine, and only a browser showed that the options
  never arrived.

`e2e/tests/naming-theme.spec.js` pins the dropdown: it opens a universe's editor and
requires more than one option, the real labels and a `Default (…)` label, plus the round
trip — with the write stubbed, because a universe's theme is live content. It locates the
select **by its label** so the same spec runs against the tree before and after a fix, and
it polls the save **value** rather than the write count, because the panel autosaves on a
600 ms debounce and an earlier write lands first.

## What is still needed

- **The MCP property** ([[mcp-architect]]) — `naming_theme` is on `UpdateEntityInput` but
  not on the `update_entity` tool schema, so a client cannot set a world's theme over MCP.
- **The fantasy categories** — Behind the Name's invented cultures and mythologies are
  probed and documented above but deliberately unwired; whether they become their own
  themes or the constructed themes point at them is an authoring call.
- **The downloadable lists** (CC BY-SA 4.0) — the route that would end the runtime
  dependency, and the one that removes the silent-fallback hazard described above.
- **Optional: an enum at the API boundary.** The dropdown closes the UI path, but a
  non-UI writer can still store an unknown theme, and the read path answers with the
  default while the field reports what was stored. An enum would reject it at the schema
  — while the *domain* field should stay a string, because pydantic validates every
  entity read and one stale value would break that entity's read (the [[B208]] failure
  mode).

## Related

- [[B82]] — the ticket.
- [[Data Model]] §`entities` — `naming_theme`.
