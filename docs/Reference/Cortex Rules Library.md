---
title: Cortex Rules Library
tags:
  - transversal
  - reference
  - cortex
  - rules
  - raw
aliases:
  - Cortex RAW
  - Cortex Library
  - Cortex Reference
  - Local Cortex
status: canonical
---

# Cortex Rules Library

> [!note] What this is
> A **local, searchable copy of the Cortex rules corpus** — the Cortex Prime Game Handbook, the free *Cortex Lite*, the *Tales of Xadia* primer, and the licensed Cortex games (Marvel Heroic, Smallville, Leverage, Firefly, Serenity, TorchLite, and others). This is the project's first-hand RAW source, so [[Sessions|session agents]] can read and **cite** rules without relying on web search.

> [!warning] Not in git, by design
> These are ~622 MB of commercial PDFs. They live on the external disk and are **never committed**; this note is the committed pointer. Extracted text is derived and also uncommitted. See *Copyright* below before quoting at length.

## Where it lives

| What | Path |
| --- | --- |
| The PDFs | `/media/dave/Disk2/TTRPG-merged/Cortex/` |
| Extracted plain text (one `.txt` per PDF, `\f`-separated pages) | `/media/dave/Disk2/TTRPG-merged/.index/text/Cortex/` |
| Manifest (path, bytes, pages, title, text file) | `/media/dave/Disk2/TTRPG-merged/.index/manifest.tsv` |

Parent library and how it was merged: [[TTRPG Library]].

> [!tip] Access
> Reading these paths requires filesystem access **outside** the workspace. A session running with the default `workspace-write` policy may be denied; sessions that need RAW should run with full access, or ask the [[Overseer]] for an alternative.

## How to read and cite

```bash
RULES=/media/dave/Disk2/TTRPG-merged/.index/text/Cortex
grep -rn -i "effect die" "$RULES/Cortex_Prime.pdf.txt" | head    # find the passage
pdftotext -f 21 -l 24 -layout \
  /media/dave/Disk2/TTRPG-merged/Cortex/"Cortex Prime.pdf" -   # read it with layout
```

For a **page-accurate** citation, get the page from the text (`pdftotext` separates pages with a form feed) and quote the PDF path plus the page.

> [!warning] Page numbers are PDF indices, not printed folios
> The pages in the topic map below are `pdftotext` page indices (1-based). They are usually **offset** from the printed page numbers by the front matter. Always confirm the passage before citing a printed page number.

> [!note] One metadata bug worth knowing
> `Tales Of Xadia - Rules-Primer.pdf` carries the PDF *Title* metadata "Cortex Prime Game Handbook". The filename is right; the embedded title is wrong. Do not trust `pdfinfo` titles alone.

## The books

| File | Pages | What it is |
| --- | --- | --- |
| `Cortex Prime.pdf` | 256 | **The Game Handbook** — the primary RAW: trait sets, dice pools, tests/contests, effect dice, hitches, complications, SFX, growth. |
| `Cortex Lite v1.0.0 (Pages).pdf` | 34 | The free, condensed Cortex rules. Fast orientation; closest to a rules summary. |
| `Tales Of Xadia - Rules-Primer.pdf` | 28 | Free primer for the licensed Dragon Prince game — clean modern restatement of core rules. |
| `Tales of Xadia.pdf` | 312 | The full licensed game; strong worked examples of trait sets and character creation. |
| `TorchLite-v1.0.1.pdf` | 236 | Licensed fantasy Cortex; useful for trait-set variants and fantasy content. |
| `Terraverse.pdf` | 36 | Small licensed Cortex game — concise, good for a minimal implementation read. |
| `Xine One v1.0.0 (Pages).pdf` | 16 | Very small Cortex game; the shortest complete rules statement in the set. |
| `The Arcanist's Toolkit.pdf` | 25 | Magic-system supplement. |
| `Marvel Heroic Roleplaying.pdf` | 234 | The classic Cortex Heroic build: **doom pool**, affiliations, milestones. |
| `MHRP Hero Datafiles.pdf` | 48 | Ready-made MHRP characters — good templates. |
| `MHRP Player Sheet.pdf` / `MHRP Watcher Sheet.pdf` | 1 / 2 | Play sheets (layout reference). |
| `Smallville.pdf` | 220 | **Pathways character creation**, Values/Relationships, Stress/Trauma — the closest analogue to Transversal's life-path creation. |
| `Leverage.pdf` | 210 | Heist structure, Roles, flashbacks. |
| `Firefly.pdf` | 367 | Full licensed build; extensive ship/asset rules. |
| `Serenity.pdf` | 225 | Earlier Cortex build (Cortex Classic lineage) — historical comparison. |
| `Hackers Guide.pdf` | 264 | Firefly supplement. |
| `Legends of the Wulin.pdf` | 45 | Wuxia-flavoured Cortex — relevant to the cultivation material. |
| `Rules Menu v3.3.1.pdf` | 1 | One-page rules reference sheet. |
| `Character files/*` | — | Transversal's own early character sheets and SVGs (`Traversal_v1.pdf`, `Values.pdf`, `Distinctions.svg`, …) plus the fonts they use. See [[TTRPG Library]]. |

## Topic map — where the project's concerns are covered

Page numbers are `pdftotext` indices; the first entry is often the table of contents. Verify before citing.

### Core resolution

| Concern | Cortex Prime | Cortex Lite | Tales of Xadia primer | TorchLite | Terraverse |
| --- | --- | --- | --- | --- | --- |
| Dice pools / assembling | 21 | 5 | 11 | 15 | 6 |
| Tests vs contests | 19 | 5–6 | 4–6 | 217 | 17 |
| Difficulty / opposition | 10, 21 | 6, 13 | 9, 11 | 13 | 29 |
| Effect die | 21, 22, 24 | 5, 8, 9 | 11, 12 | 15, 18 | 6, 8 |
| Hitches / botches | 10, 11 | 10, 11, 13 | 5, 11 | 18, 19 | 7, 12 |
| Initiative | 102 | — | — | 61 | 7 |
| Step up / step down | see pp. 20–24 | 8 | 11 | 18 | 6 |

### Traits, SFX, resources

| Concern | Cortex Prime | Cortex Lite | Tales of Xadia primer | Smallville | MHRP |
| --- | --- | --- | --- | --- | --- |
| Distinctions | 28 | 14 | 6 | 7 | 13 |
| Trait-set limits | 7, 13 | 4 | 7 | 11 | 10 |
| SFX (rule exceptions) | 13, 21 | 10, 15 | 8, 10 | 119 | 16 |
| Assets | 19 | 8, 10 | 6, 8 | 7 | 13 |
| Resources | — | — | — | — | — |
| Plot points (PP) | 10, 12 | 10, 11 | 5 | 4, 7 | 15 |
| Doom pool | 21, 36 | — | — | — | 10 |

### Growth and character creation

| Concern | Cortex Prime | Cortex Lite | Smallville | MHRP | Tales of Xadia |
| --- | --- | --- | --- | --- | --- |
| Advancement / growth | 49, 70, 80 | — | 22, 32 | 189 | 193 |
| Character creation | see pp. 30–48 | 14 | **Pathways**, 7–32 | 189 | 26 |
| Milestones | — | — | — | 189 | — |
| Values & relationships | 28 | — | 7, 8 | — | — |
| Stress / trauma | 25–27 | — | 57 | 189 | 292 |
| Recovery | 25–27 | — | — | — | — |

> [!tip] For Transversal specifically
> The two most load-bearing models are **Cortex Prime's trait sets + SFX** and **Smallville's Pathways** — Pathways is the direct ancestor of Transversal's life-path character creation ([[B126]]). Marvel Heroic is the source of the **doom pool** idea behind [[Challenge Rating Type]].
>
> The project's own rules docs are the interpretation of record: [[Core Mechanics]], [[Dice Mechanics]], [[SFX and Effects]], [[Character Growth]].

## Copyright

The Game Handbook and the licensed game books are commercial products; `Cortex Lite` and the *Tales of Xadia* primer are free. The extracted text exists for **local search and citation**. Do not commit the PDFs or their extracted text to the repository, and keep quotations short and attributed to the book and page.
