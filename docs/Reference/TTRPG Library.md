---
title: TTRPG Library
tags:
  - transversal
  - reference
  - library
  - external
aliases:
  - TTRPG Library
  - Reference Library
  - The Library
status: canonical
---

# TTRPG Library

> [!note] What this is
> The project's **external reference library** — ~16 GB of RPG rulebooks, settings and design material, merged from two overlapping trees into one canonical location and indexed for [[Sessions|session agents]] to read and cite.

> [!warning] External and uncommitted
> The library is **not** in the repository (it is far too large, and much of it is commercial). This note is the committed pointer. Reading it needs filesystem access outside the workspace — see *Access*.

## Where it lives

| What | Path |
| --- | --- |
| **Merged library** (canonical) | `/media/dave/Disk2/TTRPG-merged/` |
| Cortex rules (the priority collection) | `/media/dave/Disk2/TTRPG-merged/Cortex/` → indexed in [[Cortex Rules Library]] |
| Extracted-text cache | `/media/dave/Disk2/TTRPG-merged/.index/` |
| Source trees (kept, untouched) | `/media/dave/Disk2/TTRPG/`, `/media/dave/Disk2/TTRPG2/` |

## How the merge was done

Two trees that largely duplicated each other:

| | Files | Size | Unique to it |
| --- | --- | --- | --- |
| `TTRPG/` | 565 | 7.8 GB | 78 files |
| `TTRPG2/` | 1013 | 15 GB | 526 files |
| **`TTRPG-merged/`** | **1091** | **16 GB** | union |

- `TTRPG2/` was the **base** (it is the superset) and was brought in with **hardlinks** (`cp -al`) — same filesystem, so the 15 GB cost no extra space and no copy time. Only ~2 GB is genuinely new on disk.
- The **78 files unique to `TTRPG/`** were copied in with `rsync --ignore-existing`. `TTRPG/Cortex/Terraverse.pdf` was one of them.
- **6 content conflicts** existed (same path, different bytes). Resolved by rule:
  - Three were **0-byte files in `TTRPG/`** with real content in `TTRPG2/` → `TTRPG2` wins (`Transversal/TransversalPoem.txt`, `Transversal/TransversalCharacterDesign.txt`, `Transversal/CharacterFiles/AiTemplates/A5-Portrait.ait`).
  - Two were **newer copies in `TTRPG/`** (same page counts) → `TTRPG` wins: `Cypher System/Numenera/Liminal Shore.pdf`, `Fiasco/Companion.pdf`.
  - One (`Mystic China.pdf`) → `TTRPG2`'s copy kept.
- ⚠ **Hardlink consequence:** files shared between `TTRPG2/` and `TTRPG-merged/` are the *same inode*. Deleting one is safe; **editing one changes both**. The two files above were deliberately un-linked before overwriting.

> [!note] One malformed filename
> `TTRPG/Lancer/THE KARRAKIN TRADE` contains an **embedded newline** before `BARONIES.pdf` (one file, a bad download). Line-based shell tools will mis-read it — use `find -print0` / `rsync`, not `for f in $(...)`. Left as-is (rename it if it bothers you).

## What's in it

Largest collections (files / size): Dungeons & Dragons 146 / 2.7 G · GURPS 180 / 1.6 G · Savage Worlds 113 / 1.1 G · **Cortex 141 / 622 M** · Call of Cthulhu 562 M · Conan 695 M · Cypher System 532 M · Eclipse Phase 390 M · Traveller 356 M · Ars Magica 146 M · Cyberpunk RED 154 M · Pathfinder 252 M · Fate 256 M · Lancer 275 M · Generic 401 M · TORG 116 M · Amber 100 M · All Flesh Must Be Eaten 342 M.

Also present: Borg, Dragonbane, EZD6, Fiasco, Fully Automated, Solarpunk Futures, Solo, Without Number, and a `Campaigns/` folder.

> [!tip] The priority folder is Cortex
> For project work, start at **[[Cortex Rules Library]]** — it indexes the Cortex books by page, including the Game Handbook and the *Smallville* Pathways rules that Transversal's life-path creation descends from.

## Transversal's own material (in the library)

There is **early project source material** in here — worth reading before designing character creation:

- `Transversal/TransversalCharacterDesign.txt` — **an early character-design spec**, and effectively a first draft of [[Tickets#B126]]: *Name, Year of birth, Plot points*, then **Prime Traits** (Distinctions: Peculiarity / Role / Path / Mission; Level d4–d12: trainee → agent → officer → hero → tyrant), **Secondary Traits** (Skills with descriptor counts per die, Favors rated 1–5 that step up when received and down when used, Abilities with Cost/Effect/Limitation, Assets with Owner/Attributes/Attunement realm), and **Extras** (GMC, Realm). Uses the older "Realm" vocabulary for universe.
- `Transversal/TransversalPoem.txt` — the pitch poem ("Step through the gate, where worlds unite…").
- `Transversal/CharacterFiles/` — early sheets and SVGs (`Traversal_v1.pdf`, `Traversal_v1.1.pdf`, `Values.pdf`, `Distinctions.svg`, `Specializations.svg`, `Aptitudes.svg`, `drawing.svg`) plus the fonts they use, and `AiTemplates/A5-Portrait.ait` — an **Illustrator portrait template**, directly relevant to the character-image work ([[Tickets#B126]], [[Tickets#B129]]).
- `Campaigns/Transversal/` — an early Obsidian vault with the first worldbuilding stubs: **Unbihexium** ("a rare element that enables traveling between universes"), **Earth** (*Realm: Reality*, scale d8, `15d4 Population`, `4d4 Unbihexium`, tech d8), the **United Nations**, the **Technical University of Eindhoven** (owns `d4 Unbihexium` + a **Translation device**), and a **Continua vehicle**. Mostly one-line stubs, but they are the origin of the setting.

## Reading and extracting text

Any PDF can be turned into searchable text on demand:

```bash
LIB=/media/dave/Disk2/TTRPG-merged
pdftotext -layout "$LIB/Cortex/Cortex Prime.pdf" /tmp/cortex-prime.txt   # extract
pdfinfo "$LIB/Cortex/Cortex Prime.pdf" | head                            # pages, title
```

The Cortex collection is already extracted under `$LIB/.index/` — see [[Cortex Rules Library]] for the topic-to-page map.

## Access

Reading these paths requires filesystem access **outside** the workspace. A session on the default `workspace-write` policy may be denied; sessions that need the library should run with full access. If that becomes a blocker for several sessions, the [[Overseer]] can look at a workspace-visible route.
