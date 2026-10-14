---
title: Three Realms
date: 2026-09-29
tags:
  - transversal
  - game-design
  - three-realms
  - valley-of-ascension
  - factions
aliases:
  - Three Realms
  - Valley of Ascension
  - The Valley
status: draft
---

# Three Realms

The setting bible for the **Three Realms**, and for the **Valley of Ascension** inside it — its background, its present state of affairs, and the state of the assets that carry both.

> [!note] Why this is its own note
> [[Setting and Narrative]] carries the *canon* — physics, the jian, the cultivation ladder, session one. This note carries the **Valley as a place with politics**: who is in it, what each faction is becoming, what is already authored, and where the holes are. It exists because the assets need to be checked against a picture, and because a faction with no identity reads as unrelated furniture.

## The Valley of Ascension

The arrival point of every consciousness transversal that uses the jian as an anchor, and a place of extraordinary qi density that has drawn practitioners for tens of thousands of years. It is a formation laid down by an ancient array master, and **the formation suppresses cultivation to the foundation building realm** — cultivators from outside feel their realm suppressed and their memories fading.

**Ten named regions sit directly under it** (`loc-40642106`):

| Region | Contents of note |
|---|---|
| **Astral Peaks** | Star-Gazer's Spire (Compass of Celestial Law), Mirror-Shatter Falls |
| **Gilded Basin** | **Tan Gang** (Nine Heavens Pagoda → Aegis of the Unspoken Pact), Borderlands |
| **Verdant Dominion** | Azure Dawn, Wangnuo Village, Yinling Creek, Wilderness, Misty Mountain, Wang Pagoda, Silent Fang, The Azure Dawn Sect |
| **River** · plus regional members and a `flying ship` asset | |

**The Verdant Dominion is where the campaign actually lives.** It holds the two player-facing sects, the village the party is scattered across, the mine, and the Wilderness — including the **Transportation Array** the party has already found.

> [!warning] The Valley is sealed, and the sealing is deliberate
> **Liánhuā and Yan sabotaged the Reality Diagnostic Probe** on their way to sealing the valley — *"they didn't just hide it. They sabotaged this probe to prevent it from both sending out a detectable signal and from receiving terrifying data about the Storm's approach, which would have caused panic. They chose blissful ignorance."* Any repair of that probe **re-opens the signal they closed**. The 40 sites carrying `curse` — *"forming a golden core will summon a heavenly tribulation"* — are the same seal expressed as a mechanic.

## The four factions, and what each is becoming

The human's characterisation, 2026-09-29. These are **arcs**, not labels: each sect is failing in a different way, and the failure modes are what the players will be moving through.

| Faction | Id | Members | Ties | Becoming |
|---|---|---|---|---|
| **The Azure Dawn Sect** | `faction-40725783` | **38** | 24 | **Corrupted by pride and revelry** |
| **Iron Roots** | `faction-41014575` | **29** | 29 | **Declining by stagnation and isolation** |
| **Silent Fang** | `faction-159266724` | **0** | 11 | **Resorting to tyranny through lack of oversight** |
| **Wang family** | `faction-133378037` | **1** | 26 | **Behind it** — capturing influence for its descendants |

### Iron Roots — decline is already written

**This one needs the least authoring; the arc is in the data already.** `isolationist` reads *"sealed behind the Valley of Ascension"* and `longevity` *"older than the Verdant Dominion; the Still Water Immortal's remnant"* — an old sect that sealed itself. Its live **agenda** is *"reforge the Still Water Immortal's blade and hold the Valley of Ascension"*, carried by a four-step portent chain (forge-fires relit → recruiters canvass → the sealed shelf opened → the Great Earthen Kiln lit).

**The tension to preserve:** stagnation *and* an active escalation agenda are in the same faction. That is the story — a sect whose only way out is to reopen what older members sealed. Its `secret` (*"what the Root-Weave Repository keeps is not spoken"*) is the hook on which the Valley's whole return plot can hang.

### The Azure Dawn Sect — pride is already written

Two traits already say it, and they are good:

- **`cursed` / "Cycle of Arrogance"** — *"The long history and elite status have bred a certain arrogance. We can be dismissive of 'lesser' sects and slow to accept outside ideas."*
- **`cursed` / "The Dying Ember Prophecy"** — *"A central, grim prophecy foretells a future where their sacred flame is extinguished. This creates an underlying current of paranoia."*

Its `duty` set reads **Preserve the Eternal Flame**, **Burn Away Corruption**, **Guide Rebirth**, alongside flaws *"Consumed by the Flame"*.

**What is missing is revelry.** The authored sect is arrogant and paranoid, not decadent. Three PCs are sitting in it — Margaret and Sean at the Phoenix Feather Pavilions, Harold at the Botanical Terraces — so this is the faction most likely to be played at first, and the one where the human's addition is a genuine gap rather than a rename.

**It is also the largest roster (38) and it has no agenda and no portent chain**, where Iron Roots — half the size — has both. The sect that dominates the Valley politically has no stated intention.

### Silent Fang — the arc has no faction to land on

**Live traits: 2.** `identity` / *"modelled after the white tiger"* and `organisation` / `decentralized`. That is all.

**Zero members but 11 relation-edges.** So the faction is present as *a web of ties with no roster* — which is either a faction in mid-definition, or a name attached to characters held elsewhere. The human's arc, **tyranny through lack of oversight**, fits a decentralised body perfectly: no one is accountable because no one is in charge. But there is currently nothing for that to be true of.

**Also note the name appears twice, at different levels:** `Silent Fang` is a **faction** *and* `Silent Fang` is a **location** under the Verdant Dominion, alongside a GMC named `Silent Fang guard`. Two of the three will need renaming so the fiction can refer to one thing.

### Wang family — the engine, and it is structurally right

**One member, 26 relation-ties.** The human's read — *"largely behind this, trying to capture positions of influence for its descendants"* — is exactly what that ratio describes: **almost no bodies and a great deal of reach.** Its only authored trait is an `agenda`, *"Nurture Promising Youth"*, which is a plausible front for exactly that.

**But there is no `Banished Wang Branch` content at all** — `faction-329614043`, **zero traits, zero members, 1 tie**. A banished branch is a superb narrative asset (the family's own rejected, who know how it works) and it is currently a name in a list.

**Wang family members are scattered across other rosters** — `Wang Pagoda`, `Wang Family Member`, `Wangnuo Village`, `Wang family` as a Valley-level node — so the family is already a cross-cutting presence. Whether that is deliberate infiltration or drift is a design call.

## The demonic cultivators — the cast survived, the structure did not

**Answering the human's question directly: the conspyramid did NOT survive the migration.**

| | |
|---|---|
| `commands` edges (conspyramid authority) | **0 — none have ever existed** |
| Demonic factions | **3**: `demon clan`, `Demon Race`, `Devilish Path` |
| Members of all three | **0 each** |
| Demonic GMCs | `demonic golden core cultivator`, `Demonic Cultivator`, `Old Devil Mou`, `Devil Lord`, `Demon King`, `Transformed Demon`, `Demon Ape`, … |
| Demonic locations | `demon emperor yang temple`, `demon emperor yin lake`, `Demonic Sea` |

**The characters and places migrated; the hierarchy between them did not.** So the wild cards exist as a **roster with no chain of command, no roster edges, and no agenda** — three faction *names* and a scattering of individually-authored demons.

This is also why [[B147]] exists: `commands` is the relationship type that carried conspyramid authority, and it is **advertised in the MCP surface but has never had a row written**. The retirement decision (fold to `relation`, or hard-remove) is [[mcp-architect]]'s and [[Overseer]]'s, and it is now entangled with this: **if the demonic conspyramid is to be rebuilt, `commands` is the edge type that would carry it.**

## The Valley's assets — what is in place

| | |
|---|---|
| Locations under `Valley of Ascension` | 10 regions, several hundred locations |
| The two sects | **Azure Dawn** (38 members) · **Iron Roots** (29 members, agenda + 4 portents) |
| The party's ground | Wangnuo Village (**Fading Vein** with `Starsilver`, **Heart-Stone Chamber** and the `Mountain Root Drake`), Yinling Creek, the Wilderness, Azure Dawn |
| The return plot | **Transportation Array** + its six named artifacts, spread across Verdant Dominion, Astral Peaks and the Gilded Basin |
| Tan Gang | **13 children** — the **Jade-Seal Guard** and **three houses** (`Lian`, `Liu`, `Zhao` families), the **Vermilion Pagoda Palace** → **Nine Heavens Pagoda** holding the **Aegis of the Unspoken Pact**, and a **`Wang family compound`** |
| Sealing lore | **Liánhuā** and **Yan**, the sabotage, the tribulation curse on 40 sites |

> [!tip] Tan Gang is already the right shape for the Wang plot
> The city has **three named houses and a guard corps** (`Lian`, `Liu`, `Zhao`, `Jade-Seal Guard`) — and the **Wang family is not one of them**. It holds a `Wang family compound` *inside* a city governed by other families. That is the "capturing positions of influence" arc expressed as geography, and it needs no authoring to be true: a family with one member and 26 ties, housed in someone else's city, is already the thing the human described.

## The holes, in the order they matter

1. **Silent Fang has no content.** 2 traits, 0 members. Its arc cannot be authored until the faction is, and the three `Silent Fang` names (faction / location / guard) need separating.
2. **Azure Dawn has no agenda and no portents**, while the smaller Iron Roots has both. The dominant sect states no intention, and **revelry is unwritten** — the authored sect is arrogant and paranoid only.
3. **The demonic hierarchy does not exist.** The roster and places are there; the conspyramid, rosters and agenda are not — and rebuilding it touches [[B147]]'s `commands` decision.
4. **`Banished Wang Branch` is an empty faction** with one tie. Either it gets content or it should not be a faction.
5. **The Wang family's influence is unmeasured.** 26 ties and 1 member is the right *shape*, but nobody has checked whether those ties actually reach the positions that matter — sect benches, gates, the Bazaar.
6. **Tan Gang's emperor does not exist as an entity.** The city is authored — 13 children, three houses, a guard corps, the Pagoda — but **there is no emperor anywhere in the Three Realms**: the only `emperor` entities are two locations (`demon emperor yang temple`, `demon emperor yin lake`). The human has described an evil emperor who lures cultivators in and sacrifices them for his own advancement, and there is no one authored to be him.

## Related

- [[Setting and Narrative]] — canon: physics, the jian, the Still Water Immortal, cultivation
- [[Hubs and Exits]] — what a portal is here; the Transportation Array's six artifacts
- [[Factions and Organizations Design Log]] — the agenda/portent model both sects will use
- [[B147]] — `commands`, the edge type a rebuilt conspyramid would use
- [[UN Scenario Design Log]] — the party's Earth-side frame
