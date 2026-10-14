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

The human's characterisation, 2026-09-29. These are **arcs**, not labels: each sect is failing in a different way, and the failure modes are what the players will be moving through. **Rosters re-measured 2026-09-29** after the human populated Silent Fang and the Wang family.

| Faction | Id | Members | Ties | Becoming |
|---|---|---|---|---|
| **The Azure Dawn Sect** | `faction-40725783` | **38** | 24 | **Corrupted by pride and revelry** |
| **Iron Roots** | `faction-41014575` | **29** | 29 | **Declining by stagnation and isolation** |
| **Silent Fang** | `faction-159266724` | **6** | 11 | **Resorting to tyranny through lack of oversight** |
| **Wang family** | `faction-133378037` | **8** | 26 | **Behind it** — capturing influence for its descendants |

**Silent Fang's roster:** `"Weasel" Feng` · `Silent Fang guard` · `Shang Mu` · `Lan Qing` · `Iron Claw` · `Staliairtm Tra`. Two of those are not names — **`Staliairtm Tra` reads like a migration mangle**, and `Silent Fang guard` is a role, not a person.

**The Wang family's roster:** `Wang Yanjin` · `Wang Luo` · `Wang Shan` · `Wang Xiaoyu` · `Wang Yuanliang` · `Wang Min` · `Wang Ritualist Pod` · `Wang Ancestor`. **`Wang Ancestor` and `Wang Ritualist Pod`** are the two that tell you what the family really is.

**`Banished Wang Branch` is still empty** — 0 traits, 0 members, 1 tie.

## Zhu Yan is the Emperor

**`gmc-207814498` is Zhu Yan**, and he was already identified in this campaign as the **holder of the Aegis of the Unspoken Pact** — the sixth artifact the Transportation Array's event names. He is the **`role: "Valley Lord"`**, resident at **The Nine Heavens Pagoda** in Tan Gang.

So the man the human describes as an evil emperor who lures cultivators in and sacrifices them **already holds the soul-binding contract artifact, rules the city, and calls himself Lord of the Valley.** That is not a coincidence to be designed around — it is the plot, already in place: *the contract is the harvesting tool, and the man enforcing it is the ruler.*

## The demonic cultivators — the cast survived, the conspyramid did not

**The conspyramid did NOT survive the migration.** Zero `commands` edges have ever existed. What migrated is a **roster of individuals**, confirmed by the human from the archetype `Entities/335897730` in the old app. **This is the old app's list of eight; the Valley roster is seven after Si Youyou's removal.**

| Demonic cultivator | Id | Where |
|---|---|---|
| **Beggar Douchi** | `gmc-338666720` | Wangnuo Gate |
| **Kestrel Xu** | `gmc-338673352` | Wangnuo Village |
| **Zhang** | `gmc-335974687` | **Fading Vein** |
| **Jin Mu** | `gmc-344199386` | Wilderness |
| **Liao Yulian** | `gmc-344373745` | Wilderness |
| **Seven Wounds Zhang** | `gmc-344250133` | Wilderness |
| **Mist-Weaver Shen** | `gmc-344405382` | Misty Mountain |
| **Si Youyou** | `gmc-123858524` | **Mud-Silk Weavers (Iron Roots)** |

**There is no Valley demonic faction yet — the roster is unfactioned by design, not by omission.** The three existing dark factions (`demon clan`, `Demon Race`, `Devilish Path`) predate this work, each still has **0 members**, and the human confirmed on 2026-09-29 that **the Valley's demonic cultivator faction has not been created.** So the conspyramid's home is a thing to author, not a thing to find. **The table above lists the eight the old app held; the Valley roster is now seven** — Si Youyou was moved out to Daxu (below). And more importantly:

> [!warning] Nothing in the live data marks a demonic cultivator as demonic — but two traits come close
> There is no `demon` trait, no faction membership, no tag. The affiliation exists only in the *old application's archetype* (`Entities/335897730`), which did not migrate. What the cohort shares instead is a **technique signature**, and I measured it rather than guessing:
>
> | Trait | Holders | Who |
> |---|---|---|
> | **`cursed` / "Qi Blood Addiction"** | **9** | **all eight of the roster**, plus the generic `Demonic Cultivator` |
> | **`foundation` / "Essence Leeching"** | **6** | Beggar Douchi · Kestrel Xu · Seven Wounds Zhang · Si Youyou · Zhang · `Demonic Cultivator` |
>
> **So `cursed` / "Qi Blood Addiction" is the fingerprint** — it catches every known member exactly, with no false positives. `foundation` / "Essence Leeching" is the *second* mark and is **not universal**: Jin Mu, Liao Yulian and Mist-Weaver Shen lack it. **If a member was missed in the old app, `Qi Blood Addiction` is the query that finds them.**
>
> **And a correction to this note's earlier draft:** I had offered Si Youyou's `cursed` / **"Stone-Wood Manacles"** as part of the tell. It is not. The manacles are an **Iron Roots sect item** — *"bind the outer sect disciples of the Iron Roots sect… a constant test of will and a crucible for growth"* — held by **21 entities**, including Antonov, Andy and `pip2`. They say "Iron Roots disciple", not "demonic". **The membership edge is still the missing mark** — until it exists, the conspyramid cannot be queried and neither can its reach.

### They are already planted, and that is the finding

Placed on the map, the seven span the whole Valley:

- **Wangnuo** — Beggar Douchi (*Gate*), Kestrel Xu (*Village*), **Zhang (*Fading Vein*, the mine with the Mountain Root Drake*)**
- **Wilderness** — Jin Mu, Liao Yulian, Seven Wounds Zhang (where the **Transportation Array** is)
- **Misty Mountain** — Mist-Weaver Shen

**And Seven Wounds Zhang is inside a sect:** he carries **`subordinate` / "TBD Iron Roots Disciple"** and **`vulnerability` / "Disciple Jiang"** — a planted agent with a named lever held over him, already written. **No other member is inside an institution** — so at present the cult has exactly one known infiltration, and it is in the declining sect.

## The demonic cult — how it is designed to work

**Decided with the human, 2026-09-29.** This is the shape the faction is being authored to, and it is deliberately *not* a sect.

- **It is a corruption, not an institution.** It targets **the weak but ambitious**, leveraging their desires to fuel discord and leech power. It is intended to be **the main antagonist in actual play.**
- **Members reflect the six desires and the seven emotions.** The human's lists: **desires** — survival · pleasure · belonging · recognition · power · meaning; **emotions** — joy · anger · sorrow · fear · love · hate · desire.
- **A seat is something you *feed*, not something you *hold*.** The seat outlives its holder, which is what makes the cult genuinely demonic rather than a third sect with a roster: members are replaceable, the seats are not.
- **Empty seats are the point.** Most are unfilled, so the cult is visibly *recruiting* — and the seats it lacks are a scene and a target list rather than a gap.

### The crown — desire is the Valley Lord's seat

**Settled 2026-09-29: "desire" is the crown, not a peer.** The overlap between the two lists was the answer rather than the problem — *desire* is emotion #7 **and** the category the six desires belong to, so it sits above both.

```
                        desire  ←  the crown
                       Zhu Yan, gmc-207814498 — "Valley Lord"
                        /                    \
        6 PEERS: emotions                6 SUBORDINATES: desires
   joy · anger · sorrow · fear ·        survival · pleasure · belonging ·
        love · hate                     recognition · power · meaning
```

**Thirteen seats: one crown, six peers, six subordinates.** The hierarchy is mechanically real rather than flavour — the six emotions are peers of one another and of the crown's tier, the six desires answer to them.

**And the crown is already seated.** *Zhu Yan* holds `role: **Valley Lord**`, rules Tan Gang from the Nine Heavens Pagoda, and holds the **Aegis of the Unspoken Pact** — the soul-binding contract artifact. **The head of the cult is the ruler of the city and the holder of the contract.** Nothing needs inventing for the top of this hierarchy; it needs a stat block.

> [!note] One thing this settles
> The earlier worry that "desire" duplicated itself is resolved: the crown is desire-as-principle, and the six subordinates are desire-as-appetite. The cult's own doctrine writes itself — *the Lord is what all wanting is; the six are the shapes it takes.*

> [!question] Still open
> **The roster needs work, and it is the real bill.** The human's call: *"the current roster (i.e. every demonic GMC) needs work"*, and more GMCs are needed to fill the seats. Every remaining member has to be re-authored as a *seat-holder* rather than a character who happens to be demonic — and **six of the thirteen seats are open** (joy · anger · love · hate among the peers; belonging · meaning among the subordinates).

### Seat fit, read off the live sheets

Where the **seven** land against the thirteen — Si Youyou is out, see below. **Some are already written; one does not fit at all.**

| Member | Seat | Evidence |
|---|---|---|
| **Liao Yulian** | **sorrow** *(peer)* | *"Sorrow of a Thousand Graves"*, *"Inhale the Final Sorrow"*, *"Weeping Blade's Lament"* — written already |
| **Beggar Douchi** | **survival** *(subordinate)* | `essence`: "Beggar", 3rd stage QC — recruited exactly where a cult that targets the weak would |
| **Zhang** | **power** *(subordinate)* | at the Fading Vein, *"Spirit Stone Blood Enhancement"* — leeching strength out of the ground |
| **Seven Wounds Zhang** | **fear** *(peer)* | planted in Iron Roots with a hostage; *"Living Corpse Refinement"* |
| **Kestrel Xu** | **recognition** *(subordinate)* | *"Wing-Spanning Shadow Art"* — the one whose tell is display |
| **Mist-Weaver Shen** | **pleasure** *(subordinate)* | thinnest read; the sheet has not been examined in depth |
| **Jin Mu** | **— none** | *"The Silencer"*, *"Throat-Severing Resonance"*: he reads as **what the cult does to people**, not as one of its aspects. **Still unresolved** |
| **— empty —** | **joy · anger · love · hate** *(peers)* · **belonging · meaning** *(subordinates)* | **six seats, six bodies needed** — and one unseated member (**Jin Mu**) leaves **thirteen seats, seven filled, six open** |

### Si Youyou — removed from the Valley

**Resolved 2026-09-29.** She is a character from the donghua *Tales of Herding Gods*, created at Iron Roots absent-mindedly with the Demonic Cultivator archetype. The human moved her out: she now sits at **`Daxu`** (`loc-346324438`), which is **a top-level sibling of the Valley** — *"Daxu"*'s parent is `universe-three_realms`, with no Valley ancestry. **So she is out of scope, and the Valley roster is seven.**

**One wrinkle for whoever queries the cult:** she **kept** `cursed` / *"Qi Blood Addiction"*, so the fingerprint still returns her. `Qi Blood Addiction` is a **Three Realms-wide** query, not a Valley one — a Valley-scoped search must also filter on location.



**The party is standing in the middle of it.** Three PCs are at Azure Dawn, Andy is at Iron Roots alongside the cult's one known infiltrator (Seven Wounds Zhang), and Filip is at Wangnuo Village with Kestrel Xu.

## The four factions in detail

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

**The demonic cult is now the top of this list, because it is the main antagonist in actual play.**

1. **The demonic cult needs authoring from nothing: the faction, the seats, and a re-worked roster.** The seven individuals exist and are placed, but **every one needs re-authoring as a seat-holder**, **six of the thirteen seats are open**, and the faction itself does not exist. `cursed` / **"Qi Blood Addiction"** is the fingerprint that finds anyone missed. **The one remaining design question is what Jin Mu is** — he fits no seat and reads as the cult's *function* (the Silencer) rather than one of its aspects. **Settled since:** the crown is desire, seated by Zhu Yan; Si Youyou is out, back to Daxu.
2. **Zhu Yan needs a stat block worthy of a Valley Lord.** He is the Emperor, he holds the Aegis, and his sheet is **five settings** — `role: Valley Lord`, the artifact, `appearance`, an empty `description`. The main antagonist's head is currently thinner than his own guards.
3. **Tan Gang has no emperor-shaped *position* in its structure.** It has three houses and a Jade-Seal Guard, but nothing that says who rules it and how — which is why the ruler reads as one more GMC in a city rather than the head of a hierarchy.
4. **Silent Fang has no content worth the name.** 6 members now, but **2 traits total** and no arc-bearing stat block. Its arc cannot be authored until the faction is, and the three `Silent Fang` names (faction / location / guard) need separating.
5. **Azure Dawn has no agenda and no portents**, while the smaller Iron Roots has both. The dominant sect states no intention, and **revelry is unwritten** — the authored sect is arrogant and paranoid only.
6. **`Banished Wang Branch` is an empty faction** with one tie. Either it gets content or it should not be a faction.
7. **The Wang family's influence is unmeasured.** 26 ties and 8 members is the right *shape*, but nobody has checked whether those ties actually reach the positions that matter — sect benches, gates, the Bazaar, the three houses of Tan Gang.

**Cross-cutting:** the cult's authority structure touches [[B147]]'s `commands` decision. And **`Staliairtm Tra`** (Silent Fang) reads like a migration mangle rather than a name.

## Related

- [[Setting and Narrative]] — canon: physics, the jian, the Still Water Immortal, cultivation
- [[Hubs and Exits]] — what a portal is here; the Transportation Array's six artifacts
- [[Factions and Organizations Design Log]] — the agenda/portent model both sects will use
- [[B147]] — `commands`, the edge type a rebuilt conspyramid would use
- [[UN Scenario Design Log]] — the party's Earth-side frame
