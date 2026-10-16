---
title: Earth Skills — the prerequisite tree
tags:
  - transversal
  - reference
  - earth
  - skills
  - lifepath
aliases:
  - Skill Tree
  - Earth Skill Tree
  - required_traits
status: reference
last-updated: 2026-10-17
---

# Earth Skills — the prerequisite tree

> [!info] What this is
> The **skill prerequisite structure**, recovered from the previous application
> (`~/dev/transversal`, the `tv_adb` ArangoDB, database `transversal`) and written
> down here because that database is the **only** copy. Transversal2's trait model
> has **no prerequisite field** (`TraitRef` carries `possibleSubtraitIds`, which is
> containment, not prerequisites), so this is the design record until one exists.

## The mechanic, as it was built

A trait carried `required_traits: [Trait]`, and the picker that offered "what can I
learn next" tested it in AQL:

```aql
FILTER LENGTH(t.required_traits) == 0
    OR LENGTH(MINUS(t.required_traits, connected_traits)) == 0
```

That is: **a skill is learnable when every one of its prerequisites is already
held** — `connected_traits` being the entity's own `TraitSettings`. A second,
independent gate rode the trait's default setting: `locations_enabled` /
`locations_disabled` lists checked against the entity's location hierarchy
(20 levels), though only **4 of 803** traits ever used it.

`Traitsets.duplicates` mattered too: **`skills` was `duplicates=false`**, so a skill
could be held once, while **`know-how` was `duplicates=true`**, so a knowledge trait
could be held several times distinguished by statement.

## The shape, measured

| | |
|---|---|
| skills | **133** |
| with ≥1 prerequisite | **103** |
| prerequisite edges | ~151 |
| roots (no prerequisites) | **30** |
| max depth | **5** (`construct`, `hack`) |
| fan-in | 30 want nothing · 67 want 1 · 25 want 2 · 7 want 3 · 4 want 4 |
| cyclic | **no** — verified every skill for a path back to itself |

**Roots:** `aim, believe, cast, commune, communicate, compare, comprehend, draw,
drive, feel, gather, heal, hear, ignore, imagine, influence, meditate, move,
notice, persevere, play, read, reason, receive, remember, see, talk, transverse,
use, wreck`

**The crossover into `know-how`** — the only edges leaving the set, and the seam
between doing and knowing:

| skill | requires | from |
|---|---|---|
| `deduce` | `logic` | know-how |
| `abduce` | `logic` | know-how |
| `induce` | `logic` | know-how |

> [!warning] Read the `chain` column with care
> It is the **longest** path down to a root, so it shows one route rather than all
> of them, and a skill with several prerequisites has several. `construct` needs
> **four** (`craft`, `build`, `plan`, `design`) and the column shows the one through
> `plan`; the others are in the `requires` column.

## The tree

Depth is the longest prerequisite chain below a skill — 0 is learnable from the start.

| depth | skill | requires | one chain down |
|---|---|---|---|
| 0 | `aim` | — | aim |
| 0 | `believe` | — | believe |
| 0 | `cast` | — | cast |
| 0 | `commune` | — | commune |
| 0 | `communicate` | — | communicate |
| 0 | `compare` | — | compare |
| 0 | `comprehend` | — | comprehend |
| 0 | `draw` | — | draw |
| 0 | `drive` | — | drive |
| 0 | `feel` | — | feel |
| 0 | `gather` | — | gather |
| 0 | `heal` | — | heal |
| 0 | `hear` | — | hear |
| 0 | `ignore` | — | ignore |
| 0 | `imagine` | — | imagine |
| 0 | `influence` | — | influence |
| 0 | `meditate` | — | meditate |
| 0 | `move` | — | move |
| 0 | `notice` | — | notice |
| 0 | `persevere` | — | persevere |
| 0 | `play` | — | play |
| 0 | `read` | — | read |
| 0 | `reason` | — | reason |
| 0 | `receive` | — | receive |
| 0 | `remember` | — | remember |
| 0 | `see` | — | see |
| 0 | `talk` | — | talk |
| 0 | `transverse` | — | transverse |
| 0 | `use` | — | use |
| 0 | `wreck` | — | wreck |
| 1 | `abduce` | `logic [Traitsets/2328609]`, `reason` | logic ← abduce |
| 1 | `advocate` | `communicate` | communicate ← advocate |
| 1 | `analyse` | `gather` | gather ← analyse |
| 1 | `build` | `move` | move ← build |
| 1 | `charm` | `influence` | influence ← charm |
| 1 | `climb` | `move` | move ← climb |
| 1 | `command` | `communicate` | communicate ← command |
| 1 | `dance` | `move` | move ← dance |
| 1 | `deduce` | `logic [Traitsets/2328609]`, `reason` | logic ← deduce |
| 1 | `disseminate` | `communicate` | communicate ← disseminate |
| 1 | `dissuade` | `communicate` | communicate ← dissuade |
| 1 | `empathize` | `feel` | feel ← empathize |
| 1 | `farm` | `move` | move ← farm |
| 1 | `fight` | `move` | move ← fight |
| 1 | `find` | `notice` | notice ← find |
| 1 | `gift` | `communicate` | communicate ← gift |
| 1 | `handle` | `influence` | influence ← handle |
| 1 | `hunt` | `move`, `notice` | move ← hunt |
| 1 | `hurt` | `imagine` | imagine ← hurt |
| 1 | `improvise` | `imagine` | imagine ← improvise |
| 1 | `induce` | `logic [Traitsets/2328609]`, `reason` | logic ← induce |
| 1 | `ingratiate` | `influence` | influence ← ingratiate |
| 1 | `inspire` | `influence` | influence ← inspire |
| 1 | `introspect` | `meditate` | meditate ← introspect |
| 1 | `intrude` | `influence` | influence ← intrude |
| 1 | `jump` | `move` | move ← jump |
| 1 | `learn` | `comprehend` | comprehend ← learn |
| 1 | `lie` | `communicate` | communicate ← lie |
| 1 | `listen` | `hear` | hear ← listen |
| 1 | `march` | `move` | move ← march |
| 1 | `negotiate` | `communicate` | communicate ← negotiate |
| 1 | `operate` | `use` | use ← operate |
| 1 | `organize` | `gather` | gather ← organize |
| 1 | `perform` | `believe`, `communicate` | believe ← perform |
| 1 | `persuade` | `influence`, `communicate` | influence ← persuade |
| 1 | `pivot` | `imagine` | imagine ← pivot |
| 1 | `recover` | `persevere`, `heal` | persevere ← recover |
| 1 | `restrain` | `persevere` | persevere ← restrain |
| 1 | `run` | `move` | move ← run |
| 1 | `sail` | `move` | move ← sail |
| 1 | `secure` | `imagine` | imagine ← secure |
| 1 | `shoot` | `see`, `move`, `aim` | see ← shoot |
| 1 | `sneak` | `move` | move ← sneak |
| 1 | `spot` | `see` | see ← spot |
| 1 | `swim` | `move` | move ← swim |
| 1 | `tackle` | `move` | move ← tackle |
| 1 | `teach` | `influence` | influence ← teach |
| 1 | `theorize` | `remember`, `reason` | remember ← theorize |
| 1 | `throw` | `aim` | aim ← throw |
| 1 | `tinker` | `imagine`, `move` | imagine ← tinker |
| 1 | `wield` | `use` | use ← wield |
| 1 | `write` | `read` | read ← write |
| 2 | `administrate` | `organize` | gather ← organize ← administrate |
| 2 | `apply` | `learn` | comprehend ← learn ← apply |
| 2 | `appraise` | `remember`, `compare`, `analyse` | gather ← analyse ← appraise |
| 2 | `assemble` | `tinker` | imagine ← tinker ← assemble |
| 2 | `brawl` | `fight` | move ← fight ← brawl |
| 2 | `compliment` | `notice`, `communicate`, `gift` | communicate ← gift ← compliment |
| 2 | `compose` | `organize` | gather ← organize ← compose |
| 2 | `convince` | `empathize`, `influence` | feel ← empathize ← convince |
| 2 | `craft` | `tinker` | imagine ← tinker ← craft |
| 2 | `evade` | `induce` | logic ← induce ← evade |
| 2 | `execute` | `hurt`, `move`, `ignore` | imagine ← hurt ← execute |
| 2 | `forage` | `find` | notice ← find ← forage |
| 2 | `forge` | `wield`, `persevere` | use ← wield ← forge |
| 2 | `grapple` | `move`, `fight` | move ← fight ← grapple |
| 2 | `hide` | `find`, `imagine` | notice ← find ← hide |
| 2 | `interrogate` | `communicate`, `influence`, `empathize`, `deduce` | feel ← empathize ← interrogate |
| 2 | `intimidate` | `influence`, `hurt` | imagine ← hurt ← intimidate |
| 2 | `investigate` | `abduce` | logic ← abduce ← investigate |
| 2 | `jury-rig` | `improvise`, `tinker` | imagine ← improvise ← jury-rig |
| 2 | `keep` | `handle` | influence ← handle ← keep |
| 2 | `lead` | `influence`, `inspire` | influence ← inspire ← lead |
| 2 | `mediate` | `influence`, `empathize`, `comprehend`, `negotiate` | feel ← empathize ← mediate |
| 2 | `nurture` | `empathize` | feel ← empathize ← nurture |
| 2 | `orate` | `communicate`, `perform` | believe ← perform ← orate |
| 2 | `plan` | `theorize` | remember ← theorize ← plan |
| 2 | `pole-fighting` | `fight` | move ← fight ← pole-fighting |
| 2 | `repair` | `tinker` | imagine ← tinker ← repair |
| 2 | `research` | `analyse` | gather ← analyse ← research |
| 2 | `ride` | `handle` | influence ← handle ← ride |
| 2 | `scavenge` | `find` | notice ← find ← scavenge |
| 2 | `seduce` | `influence`, `charm` | influence ← charm ← seduce |
| 2 | `snipe` | `shoot`, `see`, `aim` | see ← shoot ← snipe |
| 2 | `swordsmanship` | `fight` | move ← fight ← swordsmanship |
| 2 | `trap` | `theorize` | remember ← theorize ← trap |
| 2 | `understand` | `learn` | comprehend ← learn ← understand |
| 3 | `assess` | `appraise`, `fight` | gather ← analyse ← appraise ← assess |
| 3 | `calculate` | `apply` | comprehend ← learn ← apply ← calculate |
| 3 | `concoct` | `assemble`, `gather` | imagine ← tinker ← assemble ← concoct |
| 3 | `deceive` | `convince`, `lie`, `empathize` | feel ← empathize ← convince ← deceive |
| 3 | `experiment` | `plan` | remember ← theorize ← plan ← experiment |
| 3 | `integrate` | `learn`, `understand` | comprehend ← learn ← understand ← integrate |
| 3 | `navigate` | `plan` | remember ← theorize ← plan ← navigate |
| 3 | `program` | `read`, `compose`, `tinker`, `write` | gather ← organize ← compose ← program |
| 3 | `recruit` | `convince` | feel ← empathize ← convince ← recruit |
| 3 | `torture` | `interrogate`, `hurt` | feel ← empathize ← interrogate ← torture |
| 4 | `crack` | `wreck`, `program` | gather ← organize ← compose ← program ← crack |
| 4 | `design` | `imagine`, `experiment`, `draw` | remember ← theorize ← plan ← experiment ← design |
| 4 | `infiltrate` | `deceive` | feel ← empathize ← convince ← deceive ← infiltrate |
| 4 | `track` | `notice`, `navigate` | remember ← theorize ← plan ← navigate ← track |
| 5 | `construct` | `craft`, `build`, `plan`, `design` | remember ← theorize ← plan ← experiment ← design ← construct |
| 5 | `hack` | `program`, `crack` | gather ← organize ← compose ← program ← crack ← hack |

## How this would land in Transversal2

The prerequisite data has **no home in the trait model** — `TraitRef` has no
`required_traits`. Two candidate homes exist and the choice is not the MCP layer's:

1. **A trait field** (a `required_trait_ids` on `TraitRef`, backend-platform's
   model). Faithful to what was built, cheap to query, but static: a prerequisite
   can only ever be another trait.
2. **Conditions on the offering** — the shape discussed 2026-10-17. A roll table
   whose rows are learnable skills, each row gated by a `TARGET_PATH` condition, so
   "learnable" is evaluated against the acting entity at the moment of offer. This
   is expressible **today** and was traced: `select traitset(ts-899016) →
   navigate traits → filter … → choose` types cleanly (`trait/one`), and the gate
   resolves as `select self → navigate traitsettings → filter trait_id == …`.

   Option 2 is more expressive — a skill could become learnable by holding an ally,
   standing somewhere, or serving a term, none of which a trait-id list can say —
   but it costs one authored condition per prerequisite (~151), against a single
   list field for option 1.

**Both need a read that returns the whole learnable set, and that does not exist.**
`TARGET_PATH` answers *"may I take this one?"* per rule; nothing answers *"what can
I learn right now?"*, which is the surface a player actually touches whether the
offer is random (`aggregate random`) or chosen (`choose`).

## Related

- [[Cortex Rules Library]] — the **skill pyramid** (a mod in the Cortex Prime Game
  Handbook ch. 2): *"if you want a ⑩ rating in a skill, you need at least two ⑧
  rated skills and three ⑥ rated skills"*, with d4 as the baseline. A numeric
  constraint that needs no authored edges.
- [[Character Growth]] — `status: canonical`: *"One growth system, not two. The life
  path system is the training mechanic."*
