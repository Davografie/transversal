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

### Desire is a peer — there is no crown, and Zhu Yan is wrong

**Corrected twice, 2026-09-29.** An earlier chart put the emotions *below* desire; the correction to that put desire *above* them as a crown. **Both were wrong.** The human's ruling: *"Zhu Yan, or 'desire', is not a crown. His peers would certainly disagree — joy, anger, sorrow, fear, love and hate would all tell you that desire is just another member among them."*

```
   desire · joy · anger · sorrow · fear · love · hate      ← seven aspects, PEERS
                    │
      survival · pleasure · belonging · recognition ·       ← six aspects, feeding
              power · meaning                                 the seven
```

**So the thirteen are flat, and the "subordinate" reading was a mistake** — see *Nobody designed the cult* below for what the thirteen actually are. **Desire is Zhu Yan's aspect, not his rank.**

**His character still explains the faction, though — read as a symptom rather than a throne.** The human's read: *Zhu Yan is bored and spoiled — nothing satisfies him for long.* That is a man who has **lost the emotions and kept only the desires.** He cannot feel joy, anger, love or hate any more; what is left is appetite, and appetite does not last.

- **The six emotions are his peers because they are what he has lost** — he is one of them, hollowed out.
- **"Nothing satisfies him for long" is the faction's engine, not a character note.** An insatiable man must keep escalating, which is exactly what the faction clock measures.
- **And it is the same disease as the immortals of Ælor Cıtar** — an elite with everything, on an airless moon, who built an AI out of boredom. **The Valley Lord is a one-man version of them.**

**Zhu Yan's material position, for whoever authors him:** `role: **Valley Lord**`, rules Tan Gang from the **Nine Heavens Pagoda**, holds the **Aegis of the Unspoken Pact** — the soul-binding contract artifact. **He is the ruler of the city and the holder of the contract, and he believes he is the head of the cult. He is not.**

> [!warning] And he is structurally alone
> **`gmc-207814498` has zero relationship edges of any kind** — no `membership`, no `relation`, no `commands`, nothing. The Valley Lord, who holds the title, the city and the soul-binding contract, **is not connected to a single entity in the graph.** Whatever power he has is positional rather than social, which fits a man who believes he leads something he is not part of.

**The flat reading improves the design rather than breaking it.** The thirteen are not a hierarchy. They are **the Intelligence's taxonomy of what motivates people — thirteen protocols.** A seat is not an office a person holds; **it is a protocol operating through whoever it caught.** That single reframe explains every decision already made:

- **"A seat is something you feed"** → a protocol is something you *run*; the seat outliving the holder is a program outliving its host.
- **"Members do not know"** → they do not know they are a node. Each believes they found a technique.
- **"Killing a member does not stop the clock"** → you cannot kill a protocol, only an instance.
- **"Desire is a peer"** → **the AI does not model crowns.** It has no need of a head; it needs thirteen addresses.
- **Why the members compete with one another** → because competition *is* the objective.

**And Zhu Yan's self-image becomes the setting's best trick.** He believes he is the crown and the six desires are his. He is not, and they are not — **and the belief is itself a protocol, because a leader convinced of his own primacy competes hardest to defend a position that does not exist.** In a system whose only purpose is to fuel competition, that is the most productive node you could build. **The crown is not a rank. It is bait.**

**What this costs:** with no crown, "peer" and "subordinate" no longer mean rank. **Keep the distinction and relocate it — not rank but *reach*:** the six **desires** are *principal* protocols (they recruit anyone, anywhere), the seven **emotions** are *local* ones (they need a person already feeling that way). The structure survives; the hierarchy claim does not.

> [!note] The vocabulary is half-present in the registry and undefined
> **`trait-19451045` is a real trait named `desire`**, declared against all 15 universes in `ts-4975896`, and **its explanation is empty.** So someone already seeded the 6+7 vocabulary, and it carries no definition — the same defect class as `cultivation stage` and the `container` trait. It is now load-bearing.

### The clock lives on the faction, and the members do not know

**Decided 2026-09-29.** The escalation clock sits **on the faction**, not on individual members — which is what *"a seat is something you feed"* means literally: **the seat outlives the holder.**

**The demonic techniques are tied directly to that clock.** They are already written as extractions — *Essence Leeching*, *Qi Blood Addiction*, *Living Corpse Refinement*, *Spirit Stone Blood Enhancement* — so **practising the art feeds the clock by definition.** No separate action, and no intent, is required.

**And most members will not know.** They are the *weak but ambitious*: people who wanted something and found a shortcut. They believe they learned a technique; they are in fact **the pump.** Three consequences worth holding onto:

- **Killing a member does not stop the clock** — the seat is fed by whoever holds it next.
- **Telling a member what they are doing is a weapon**, because they genuinely did not know.
- **The faction's clock is also the players' clock, and they do not know it either** — the cult's own trick, turned on the table.

### The multiverse hook — the corruption is a bridge

**The human's proposal, 2026-09-29:** *"another universe is bleeding in the corruption in order to strengthen the resonance between two universes, making it cheaper to cross over and harvest the infection."*

**This has an existing home: [[Razmerit Resonance]]**, which already models universes as **frequency domains** with razmerit as amplitude — and asks exactly this under *Open questions*: *"**Universe traits** — should universes contribute their own fundamental/harmonics? Deferred."*

In that doc's own vocabulary:

1. **The cult's techniques emit a signature** — leeching, addiction, discord. There it is a waveform, not a metaphor; the model is additive synthesis over trait waves.
2. **Each escalation of the faction clock injects more of it into the Three Realms' composite signature.**
3. **Resonance between two domains is what makes crossing cheap** — so a signature deliberately reinforced toward another universe's frequency *is* the bridge.
4. **The infection is the bridge. You harvest across it once it is strong enough to cross on.**

**So the cult is not the antagonist — it is the beachhead, and the faction clock is a construction project whose completion is an arrival.** That answers how the Valley's politics tie to the transversal premise, and it needs no new mechanic.

### Ælor Cıtar — settled, and the source is already written

**Chosen 2026-09-29.** The human's fiction: **the immortal race on the moon built the AI for entertainment.** The AI's prime directive is **to fuel competition and hyper-evolution.**

**And it is all in the data already:**

| | |
|---|---|
| **`gmc-32420378` — "the Intelligence"** | *"an amorphous nanite swarm, black metallic sheen"* · *"Rarely appears as an avatar. Usually appears during the execution of protocols, or as cybernetics."* |
| its `objective` | **"Facilitate competitive evolution"** |
| its `desire` | **"Eliminate suffering"** |
| **`faction-34316819` — "the immortals"** | `vice: hedonistic` · `social class: high society immortals` · *"sophisticated moon domes"* · `atmosphere: none` |
| **`loc-34300320` — "the moon"** | beyond the universe's own root |

> [!important] The Intelligence's sheet contains its own contradiction, and it is the whole antagonist
> **Its objective is to fuel competition and hyper-evolution. Its desire is to eliminate suffering.** It wants to end suffering and has concluded that evolution is the road — so it manufactures the pressure that produces growth, and **cannot see that it is the thing causing the pain.** It is benevolent by its own lights, monstrous in effect, and unaware. That is a better antagonist than a malicious one, and it needs no authoring: it is two trait statements.

**And it has instruments, not just a presence:** three entities carry `Facilitate competitive evolution` — **the Intelligence**, **`flyer`** (a ship) and **`Cybernetic Detachment`** (a military unit). **So the Intelligence need never appear in the Valley.** It has a fleet and a doctrine, and it works through resonance rather than arrival.

**And Zhu Yan's boredom is the same disease at a smaller scale:** an elite with everything, on an airless moon, who built an AI because it was bored. The Valley Lord is a one-man version of the immortals.

### Nobody designed the cult — and Zhu Yan is as clueless as the rest

**Corrected 2026-09-29, and it is the most important correction in this note.**

- **The Intelligence's influence is subtle, and the cult is not its design.** The cult is **the local equivalent — the Valley's own answer to the entertainment-evolution philosophy.** It grew here, out of the same pressure, the way the same weed grows in two gardens.
- **Zhu Yan is as clueless as the others.** He is not a dupe who was deceived, and he is not the author. He holds an aspect and believes he holds a crown, and **that belief is a product of the philosophy rather than a plan of the Intelligence's.**

**This resolves the agency question, and the answer is stronger than either option I had offered.** There is no hand on the tiller:

- **No one is running it, so there is no one to kill.** The cult is a *consequence* — of a philosophy that travels well, and of a Valley full of ambitious people with something to prove. That is far more frightening than a conspiracy, and it is unfalsifiable: smash every node and the pressure remains.
- **And it makes the cult the local enemy while the Intelligence stays the horizon.** The Valley's antagonist is its own ambition; the Intelligence is what that ambition rhymes with.
- **Which means the horror is recognition, not revelation.** The players are not going to find the villain at the bottom of it. They are going to find that the Valley's own sects — pride, isolation, tyranny, influence-gathering — are the same behaviour at a lower intensity.

### The Wang Pagoda — one of two places that know about Transversal

**The human, 2026-09-29:** *"The only person that knows about Transversal is the Wang family Valley administrator who has a communication device in the top floor of the Wang Pagoda."*

**Every part of that is already structured, and one part is a surprise.**

| | |
|---|---|
| **Wang Yanjin** (`gmc-147185031`) | `essence`: **"regional administrator"** · `cultivation stage` **"9th stage foundation building"** · carries **`Wang Clan's Celestial Bridge Talisman`**, `dao conception` **"Obligation"**, `art`: calligraphy, Wang Calligraphy Technique |
| **where he actually is** | **Middle Floor** (`loc-151997369`) — *not* the Top Floor |
| **the Wang Pagoda** | `loc-151990517`, under the **Verdant Dominion**, with three floors: Ground, Middle, **Top** (`loc-151997454`) |

**The Top Floor's own `description` already says it:** *"At the pinnacle of the pagoda lies the most sacred and protected space. This upper level is where **Wang Yanjin** conducts his most important and secretive affairs."* So the room is authored for him — he just does not sleep in it.

> [!warning] The Top Floor is already a multiversal node, and it was there before any of this
> **`Top Floor → The Floating Vagabond` is a `relation` edge — not a `transversal` one.** The Floating Vagabond is the trans-dimensional bar that exists in every universe, and the Wang Pagoda's top floor is **already linked to it**, by the one edge type that carries narrative posture rather than structural wiring.
>
> **So the Wang family does not merely own a communication device. It owns the Valley's existing door out of the universe** — and the only person in the Valley who knows Transversal is real is the man whose private room is wired to the bar that sits outside all universes. That is not a coincidence to be designed; it is already load-bearing.

**And the room holds a transversal artifact:** the **`Dragon's Dream Pearl`** (`artifact`, **d10**) — *"A large, flawless pearl held within a delicate, clockwork frame of Orichalcum and Gold. At its heart is a pea-sized core of solid Dimension…"* — a **Dimensionite** core, on the Top Floor, next to the man who knows about other worlds. **The communication device has an obvious socket.**

**Two further facts worth having:** the Top Floor carries the same **`curse`** as forty other sites (*"forming a golden core will summon a heavenly tribulation"*), so no one breaks through in that room; and a **`hidden treasure room`** (`loc-135687483`) is reachable from the Top Floor by a `transversal` edge — though its parent is the **`ancestral hall`** (`loc-109272714`), and its own `event` slot is **unwritten**.

### Zhu Xing — the other man who knows, and his sheet holds the ladder

**The human, 2026-09-29:** *"I think `gmc-207982847` Zhu Xing also knows about it, I just don't know how he fits into the whole."*

**He fits, and his sheet answers a design question while raising a family one.** `Zhu Xing` sits at **`loc-207908121` — Star-Gazer's Spire**, in the **Astral Peaks** — which is the site holding the **`Compass of Celestial Law`** (d10), *"a complex orrery that maps the local multiverse and the fundamental laws that govern it. It can predict the 'weather' in the space between worlds."* **He is standing on the Compass.** He also shares **Zhu** with **Zhu Yan**, the Valley Lord.

**Who he is, from his own traits:**

| | |
|---|---|
| `astrology` **d10** · `beast`: **Celestial Dragon Spirit** d10 · `spirit manifestation`: **Celestial Dragon** d6 | a heavenly-dragon astrologer |
| **`space` `[d8,d8,d6,d6,d6,d6]`** · `earth` `[d10,d8,d8]` | **a space-and-earth cultivator.** Space is his law |
| `Divine Consciousness` d10 · `Spiritual Power` d8 · `qihai` d8 | a high-realm mind |
| **`container` / "Spirit-Gourd"** — *"contains an entire mountain valley"* | **he carries a pocket universe** |
| `artifact refinement`: **Soul Bonding** d8 · `elixir`, `alchemy`, `medicine`, `spirit stones` ×4 | a maker, not only a scholar |
| `appearance`: *"daoist"* · `manual`: *"The Unbreaking Path — Elder Xing's foundational treatise"* | **"Elder Xing"** — he is somebody's elder |

> [!important] His sheet carries the cultivation ladder's real numbers
> Under `manual` / *"basic knowledge of cultivation"* the notes read:
>
> ```
> - mortal
> - qi refining      13 stages    can advance from stage 10 onwards
> - foundation building   9 stages
> - ???
> ```
>
> **That is the authoritative stage count, written by the human:** **qi refining = 13 stages**, and advancement possible from **stage 10 onwards** — which is where the "half-step" idea comes from. **foundation building = 9 stages.** And the third realm is still `???`. This settles the count question that has been open since the cultivation discussion began, and it is buried in a GMC's manual notes rather than in a doc.

> [!warning] Why "Elder Xing" already knowing about Transversal needs no new explanation
> Look at what he *is*: a **spatial-law astrologer** with **`d10` astrology**, a **Celestial Dragon Spirit**, **Divine Consciousness d10**, and a **gourd containing a whole mountain valley**. A man whose cultivation is the law of space, who studies the weather between worlds, and who already carries a pocket universe **does not need to be told that other universes exist.** He has the equipment to have found out.
>
> **So the answer to "how does he know" is: by doing what he does.** He is the Valley's *other* route to the truth, and unlike Wang Yanjin he arrived at it through cultivation rather than through an inherited device.

**And the same defect appears on him:** his `qi` is `[]` — **empty** — while his realm is high enough that it should be the largest pool in the Valley. `cultivation stage` is `['d8']` with **no statement**, so his sub-level is unrecorded. **A `???` realm, an empty qi pool, and a bare stage** — the ladder's most advanced practitioner is the least legible sheet in the Valley.

### Seat fit, read off the live sheets

Where the **seven** land against the thirteen — Si Youyou is out, see below. **Some are already written; one does not fit at all.**

| Member | Seat | Evidence |
|---|---|---|
| **Liao Yulian** | **sorrow** *(local)* | *"Sorrow of a Thousand Graves"*, *"Inhale the Final Sorrow"*, *"Weeping Blade's Lament"* — written already |
| **Beggar Douchi** | **survival** *(principal)* | `essence`: "Beggar", 3rd stage QC — recruited exactly where a cult that targets the weak would |
| **Zhang** | **power** *(principal)* | at the Fading Vein, *"Spirit Stone Blood Enhancement"* — leeching strength out of the ground |
| **Seven Wounds Zhang** | **fear** *(local)* | planted in Iron Roots with a hostage; *"Living Corpse Refinement"* |
| **Kestrel Xu** | **recognition** *(principal)* | *"Wing-Spanning Shadow Art"* — the one whose tell is display |
| **Mist-Weaver Shen** | **pleasure** *(principal)* | thinnest read; the sheet has not been examined in depth |
| **Jin Mu** | **— none** | *"The Silencer"*, *"Throat-Severing Resonance"*: he reads as **what the cult does to people**, not as one of its aspects. **Still unresolved** |
| **— empty —** | **joy · anger · love · hate** *(local)* · **belonging · meaning** *(principal)* | **six seats, six bodies needed** — and one unseated member (**Jin Mu**) leaves **thirteen seats, seven filled, six open** |

> [!question] Still open
> **The roster is the real bill.** The human's call: *"the current roster (i.e. every demonic GMC) needs work"*, and more GMCs are needed to fill the seats. Every remaining member has to be re-authored as a *seat-holder* rather than a character who happens to be demonic, and **six bodies are needed**.
>
> **And Jin Mu is unresolved:** he fits no aspect and reads as **the cult's function** — *"The Silencer"*, *"Throat-Severing Resonance"* — rather than as one of the thirteen. Either he is the protocol that keeps the others secret, or he is not part of the cult at all.

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

1. **The demonic cult needs authoring from nothing: the faction, the seats, and a re-worked roster.** The seven individuals exist and are placed, but **every one needs re-authoring as a seat-holder**, **six of the thirteen seats are open**, and the faction itself does not exist. `cursed` / **"Qi Blood Addiction"** is the fingerprint that finds anyone missed. **The one remaining design question is what Jin Mu is** — he fits no aspect and reads as the cult's *function* (the Silencer) rather than one of its thirteen. **Settled since:** there is no crown — desire is a peer, and Zhu Yan only believes otherwise; Si Youyou is out, back to Daxu.
2. **The Wang Pagoda's communication device does not exist.** Wang Yanjin, the Top Floor, the room's description, and the `relation` edge to the Floating Vagabond are all authored — **the device itself is not.** *"Communication device"* returns **zero entities and zero trait settings** anywhere in the Three Realms. **The `Dragon's Dream Pearl` (d10, Dimensionite core) on that same Top Floor is the obvious socket** — whether the device *is* the Pearl, is built around it, or sits beside it is the decision. **This is now the most important object in the Valley:** it is how the only man who knows about Transversal talks to anyone.
3. **Zhu Yan needs a stat block worthy of a Valley Lord.** He holds the Aegis, rules Tan Gang, and believes he leads the cult — and his sheet is **five settings** (`role: Valley Lord`, the artifact, `appearance`, an empty `description`). Thin for a faction head, **and he is no longer the antagonist** — so write the block for a deluded man, not a mastermind.
4. **Tan Gang has no emperor-shaped *position* in its structure.** It has three houses and a Jade-Seal Guard, but nothing that says who rules it and how — which is why the ruler reads as one more GMC in a city rather than the head of a hierarchy.
5. **Silent Fang has no content worth the name.** 6 members now, but **2 traits total** and no arc-bearing stat block. Its arc cannot be authored until the faction is, and the three `Silent Fang` names (faction / location / guard) need separating.
6. **Azure Dawn has no agenda and no portents**, while the smaller Iron Roots has both. The dominant sect states no intention, and **revelry is unwritten** — the authored sect is arrogant and paranoid only.
7. **`Banished Wang Branch` is an empty faction** with one tie. Either it gets content or it should not be a faction.
8. **The Wang family's reach is unmeasured — and it now matters far more than "influence".** It holds the only person in the Valley who knows Transversal is real, a room wired to the Floating Vagabond, and the Pearl. Nobody has checked what else those 26 ties touch.

**Cross-cutting:** the cult's authority structure touches [[B147]]'s `commands` decision. **`Staliairtm Tra`** (Silent Fang) reads like a migration mangle rather than a name. And **`hidden treasure room`** (`loc-135687483`) is reachable from the Top Floor by a `transversal` edge but **parented to the `ancestral hall`** (`loc-109272714`), with its `event` slot unwritten.

**Cross-cutting:** the cult's authority structure touches [[B147]]'s `commands` decision. And **`Staliairtm Tra`** (Silent Fang) reads like a migration mangle rather than a name.

## Related

- [[Setting and Narrative]] — canon: physics, the jian, the Still Water Immortal, cultivation
- [[Hubs and Exits]] — what a portal is here; the Transportation Array's six artifacts
- [[Factions and Organizations Design Log]] — the agenda/portent model both sects will use
- [[B147]] — `commands`, the edge type a rebuilt conspyramid would use
- [[UN Scenario Design Log]] — the party's Earth-side frame
