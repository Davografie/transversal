---
title: Dice Mechanics
tags:
  - transversal
  - game-design
  - dice
  - rolling
  - cortex-prime
aliases:
  - Rolling
  - Dice Pool Resolution
  - Resolution Pipelines
status: canonical
---

# Dice Mechanics

Transversal uses a **dual-pipeline** resolution system. The number of dice in the pool determines which pipeline fires:

| Pool Size | Pipeline | Description |
|-----------|----------|-------------|
| 1–2 dice | **Simplified** | Roll, take highest, map to outcome tier |
| 3+ dice | **Dice Pool** | Cortex Prime "keep two and add" |

This gives players a tactical choice: go light and fast with fewer dice, or build a bigger pool for the bell-curve reliability of Cortex Prime standard resolution.

## Pipeline Selection

The pipeline is determined **after** the pool is assembled but **before** dice are rolled. SFX that modify the pool (adding or removing dice) can change which pipeline fires.

> [!example] Pipeline Switch
> Kael assembles 2 dice (Simplified). He activates "Overcharge" SFX which steps up a die and adds a d6 to the pool. Now he has 3 dice — the pipeline switches to Dice Pool.

The system evaluates the final pool size after all `on_roll` SFX have fired, then routes to the correct resolver.

---

## Simplified Pipeline (1–2 Dice)

The simplified pipeline is fast and swingy. It's used for quick actions, minor checks, or when the player wants to conserve resources.

### Procedure

1. **Assemble** the pool (1–2 dice from traits available in the current universe, assets, or complications)
2. **Roll** all dice — plain rolls, dice do not explode
3. **Take the highest** single die result
4. **Map to outcome tier**

### Outcome Tiers

The highest die maps to an outcome tier and a virtual **effect die** used for comparisons against challenge pools, SFX resolution, and narrative magnitude.

| Highest Die | Outcome | Effect Die | Narrative Description |
|-------------|---------|------------|----------------------|
| 1–2 | **Fail** | None | The action fails; the situation worsens |
| 3–5 | **Marginal Success** | d4 | Barely succeeds; comes with a cost or complication |
| 6–8 | **Success** | d6 | Solid, clean success; exactly what was attempted |
| 9–11 | **Exceptional Success** | d8 | Succeeds with style; a bonus narrative benefit |
| 12 | **Perfect Success** | d10 | Flawless execution; the player narrates an additional significant advantage |

> [!note] Effect Die Cap
> The simplified pipeline's effect die caps at d10. A d12 effect is only achievable in the Dice Pool pipeline (by reserving an unused d12 from the pool). This reflects the ceiling of the simplified system — it's faster but has a lower power ceiling.

> [!note] Difficulty Adjusts the Threshold
> The GM sets a **required tier** for the task:
> - Easy: Marginal (3+) is enough
> - Standard: Success (6+) required
> - Challenging: Exceptional (9+) required
> - Heroic: Perfect (12) required
>
> If the highest die doesn't meet the required tier, the action fails even if a lower tier was rolled.

### Simplified Contest

When two parties each roll 1–2 dice against each other:

1. Both sides roll and take their highest die
2. Compare tiers — the higher tier wins
3. If both achieve the same tier, the side with the higher individual die value wins
4. A tie on both tier and value goes to the defender (or status quo)

> [!example] Simplified Contest
> Kael (d8 Shooting) and a guard (d6 Agility) both fire.
>
> Kael rolls d8 → **6** (Success tier)
> Guard rolls d6 → **4** (Marginal tier)
>
> Kael wins. His higher outcome tier gives him a clean shot.

### Effect Die in Simplified

In the simplified pipeline, the **outcome tier directly determines the effect die** — no separate die selection is needed. Marginal = d4, Success = d6, Exceptional = d8, Perfect = d10. This virtual effect die is used for any effect-die comparisons (challenge pools, SFX triggers, narrative magnitude).

Unlike the Dice Pool pipeline, where the effect die is chosen from unused rolled dice, the simplified pipeline derives the effect die from the result itself. This makes simplified rolls faster — one comparison yields both the outcome and the effect magnitude.

### Complications in Simplified

**Hitch**: Rolling a **1** on any die triggers a complication, regardless of the outcome tier. The GM introduces a narrative twist. A complication never reverses a success, but it adds tension or cost.

**Botch**: If **all** dice in the pool show 1, the roll is a **botch** — a catastrophic failure. The action not only fails, but the situation worsens dramatically. With a single die, a 1 is both a hitch and a botch (Fail tier + complication). With two dice, both must show 1 for a botch.

| Condition | Result |
|-----------|--------|
| One die shows 1, other succeeds | Hitch — complication alongside success |
| All dice show 1 | **Botch** — catastrophic failure, severe consequences |
| No 1s | Clean result |

A botch does not earn additional razmerit beyond the standard hitch — the catastrophic outcome is its own penalty.

> [!example] Simplified with Hitch
> Kael rolls d8 + d6 to hack a door. Results: d8→5, d6→1.
>
> Highest is 5 → Marginal Success. The door opens, but the 1 triggers a complication: a silent alarm trips.

> [!example] Simplified Botch
> Kael rolls d8 + d6 to hack a door. Results: d8→1, d6→1.
>
> Both dice are 1s — **botch**. The terminal not only locks him out, it triggers a hard lockdown. Bulkheads slam shut. The GM escalates the scene.

---

## Dice Pool Pipeline (3+ Dice) — Cortex Prime

When the pool has three or more dice, Transversal uses standard Cortex Prime resolution. This produces a bell curve that rewards building larger pools for higher-stakes actions.

### Procedure

1. **Assemble** the pool (3+ dice from traits available in the current universe, assets, SFX, complications)
2. **Roll** all dice
3. **Keep two highest** dice and add their values together — this is the **total**
4. **Compare** the total against the opposition
5. **Choose an effect die** from the remaining dice (not the two used for the total)

### Test (vs. Difficulty)

The GM sets a difficulty threshold. The player's total must meet or beat it.

| Difficulty | Threshold | Example |
|------------|-----------|---------|
| Easy | 7 | Climbing a knotted rope |
| Average | 9 | Hacking a standard terminal |
| Hard | 11 | Convincing a hostile guard |
| Formidable | 13 | Cracking military-grade encryption |
| Heroic | 15 | Talking down a warship captain |
| Near Impossible | 17+ | Hacking an alien dimensional gateway |

### Contest (vs. Opposition)

Both sides assemble pools, roll, and keep their two highest dice. The side with the higher total wins. Ties go to the defender.

> [!example] Dice Pool Contest
> Kael faces off against a corporate security AI.
>
> **Kael's pool**: d10 (Intelligence) + d8 (Hacking) + d8 (Distinction) = d10 + d8 + d8
> **Roll**: 8, 6, 4 → keep 8 + 6 = **14**
>
> **AI's pool**: d10 (Firewall) + d8 (Counter-Intrusion) + d6 (Alerted) = d10 + d8 + d6
> **Roll**: 7, 5, 3 → keep 7 + 5 = **12**
>
> Kael wins (14 > 12). He designates the remaining d8 as his effect die — significant access.

### Effect Die in Dice Pool

After comparing totals, the player chooses one die **not used in the total** as the effect die. If all dice were used (rare, only happens with exactly 2 dice — which would be Simplified anyway), the effect die defaults to d4. The effect die's type determines outcome magnitude.

### Complications in Dice Pool

**Hitch**: Any die that shows a **1** is a hitch — a complication opportunity for the GM. Hitches do not affect the total (you can still use a die that rolled 1 in your two-dice total if it's one of your highest), but they trigger narrative complications. Two or more 1s escalate the complication.

**Botch**: If **all** dice in the pool show 1, the roll is a **botch**. The action fails catastrophically regardless of the total. The GM introduces a severe narrative consequence — equipment breaks, allies are endangered, a new and dangerous complication enters the scene.

| Condition | Result |
|-----------|--------|
| One or more 1s, but not all | Hitch(es) — complication(s) alongside the result |
| All dice show 1 | **Botch** — catastrophic failure, severe consequences |
| No 1s | Clean result |

> [!example] Dice Pool Botch
> Kael rolls d10 + d8 + d8 to slice a military firewall. Results: 1, 1, 1 — **botch**.
>
> The hack doesn't just fail. The system traces his location, deploys counter-intrusion ICE that locks his rig, and alerts human security. The GM escalates the entire encounter.

> [!note] Razmerit Generation
> When the GM activates a complication against a player character in either pipeline, that character earns **1 razmerit**. This is the primary way players generate razmerit during play. See [[Entities and Traits#Razmerit]].

---

## Comparing the Pipelines

| Aspect | Simplified (1–2 dice) | Dice Pool (3+ dice) |
|--------|----------------------|---------------------|
| **Speed** | Very fast — pick highest | Moderate — add two dice |
| **Swing** | High variance, wild outcomes | Bell curve, consistent results |
| **Max Result** | 12 (d12) | 24 (d12 + d12) |
| **Best For** | Quick checks, low-stakes actions | High-stakes conflicts, dramatic moments |
| **Build Incentive** | Conserve resources (razmerit, SFX costs) | Invest resources for reliability |

> [!tip] Tactical Choice
> A player with a single d10 trait might deliberately keep their pool small (Simplified) to fish for a 9+ exceptional success. Or they might spend razmerit to add a third die, pushing into Dice Pool territory for the bell-curve consistency. Both are valid strategies.

---

## Assisted Rolls (Teamwork)

### Simplified Teamwork
The lead character rolls their pool. Each assistant adds +1 to the highest result for each die in their relevant trait that's d6 or higher (max +3). The outcome tier is determined after the bonus is applied.

### Dice Pool Teamwork
The lead character rolls their pool and adds one bonus die from each assisting character (d6 for competent assistance, d8 for expert). This can push a 2-dice simplified pool into a 3+ dice pool pipeline.

---

## Extended Actions

Some tasks require accumulating successes over multiple rolls. An extended action:

- Has a **success threshold** (varies by pipeline):
  - **Simplified**: accumulate outcome tiers (Marginal = 1 point, Success = 2, Exceptional = 3, Perfect = 4). Reach the target point total.
  - **Dice Pool**: each successful roll (total ≥ difficulty) contributes 1 point, plus 1 bonus point for every 5 points over the threshold.
- Complications can set back progress or introduce mid-task obstacles.

---

## Design Notes

> [!quote] Why Dual Pipelines?
> Pure Cortex Prime "keep two and add" is excellent for dramatic, high-stakes rolls — but adds friction for the dozens of minor checks in a session. A unified Savage Worlds-style target-number system (the previous design) solved speed but lost the bell-curve reliability players expect for big moments.
>
> The dual-pipeline design gives both: **Simplified** for speed and swing, **Dice Pool** for depth and consistency. The pool-size threshold (3 dice) is intuitive — one or two dice feel like a quick check; three or more feel like you're committing real resources. The system naturally rewards pool-building without forcing it.

---

## SFX Integration

SFX fire at interception points in both pipelines. The effects system routes to the correct pipeline's hooks:

```
Assemble Pool → [Pipeline determined: 1-2 = Simplified, 3+ = Dice Pool]
  → [on_roll SFX fire] → Re-evaluate pipeline if pool size changed
  → Roll
  → Check for botch (all dice = 1) → [on_botch SFX fire if triggered]
  → [on_complication SFX fire] for individual hitches
  → Simplified: take highest → map to tier
  → Dice Pool: keep two highest → add → compare
  → [on_success / on_failure SFX fire]
  → Choose Effect Die
  → [on_result SFX fire]
  → Apply Outcome
```

See [[SFX and Effects]] for the full SFX catalog and trigger system.

---

## Challenge Pools

Challenge traits (positive and negative) use a specialized rolling procedure where the player targets a specific die from the challenge pool. See [[Inspired Mechanics#Rolling Against Challenge Pools]] for the full procedure in both pipelines.

---

## Conflict

A **conflict** is a structured sequence of beats where two or more sides are actively opposed — combat, social showdowns, chase sequences. Conflicts use the contest framework (see [[Core Mechanics#Tests vs. Contests]]) with additional structure.

### Initiative

**Challenger acts first.** The side that initiates the conflict declares their action and assembles their pool. The defender responds. There are no turn orders or rounds — the narrative drives who acts when. If it's unclear who should go next, the GM decides.

### Resolving Conflict Actions

Each action within a conflict is a **contest beat**: the active side assembles a pool and rolls, the opposing side does the same, totals or tiers are compared per the active pipeline.

### Minor GMCs

Minor GMCs (guards, spirit beasts, unnamed cultivators) are defeated by a single successful contest. Win one opposed roll and they're removed from the conflict. They have simplified trait blocks — one distinction, one trait set, no razmerit pool.

```yaml
type: gmc
name: "Argent Meridian Outer Disciple"
distinction: "Loyal but Inexperienced d6"
traits:
  sword_art: d6
  qi_sense: d4
```

### Major GMCs

Major GMCs (named rivals, sect elders, bosses) accrue **stress** — negative traits that accumulate across multiple contest beats. Each time a player wins a contest against a major GMC, the effect die determines the stress inflicted:

| Effect Die | Stress Inflicted |
|------------|-----------------|
| d4 | d4 stress |
| d6 | d6 stress |
| d8 | d8 stress |
| d10 | d10 stress |
| d12 | d12 stress |

When a major GMC's stress dice accumulate to a point where they cannot reasonably continue (GM judgment, typically when total stress dice exceed their highest trait), they are defeated. Stress is a negative trait — it adds to future opposition pools against them.

### SFX Push

A player may **push** after a failed or tied contest beat: they assemble a new dice pool (same or different traits) and roll again against the same opposition. Pushing is free, and contests go back and forth until one side gives in or fails to beat the difficulty. The new result replaces the old one.

---

## Negative Traits in Detail

Negative traits represent harm, conditions, and ongoing disadvantages. They are the primary stakes in conflict — characters don't have hit points; they accumulate negative traits until they can't continue.

### How They Work

A negative trait's die is added to the **opponent's** dice pool when the trait is narratively relevant. If Kael has *Cracked Ribs d8*, an enemy striking his torso adds that d8 to their attack pool.

### Stress and Trauma

| Type | Recovery | Example |
|------|----------|---------|
| **Stress** | Temporary — resolves with rest, first aid, or a scene of downtime | Bruised, winded, rattled, superficial cuts |
| **Trauma** | Persistent — requires significant narrative effort | Broken bone, qi deviation, poisoned, cursed |

Stress typically ranges d4–d8. Trauma typically ranges d6–d12. Stress can become trauma if left untreated.

### Defeat

A character is defeated not when they hit zero of something, but when their accumulated negative traits make victory narratively impossible. The GM decides, but a guideline: when a character's total negative trait dice exceed their highest positive trait die, continuing becomes reckless.

Defeat in consciousness transversal: the projection dies, consciousness snaps back to the home body. All razmerit in the projection is lost. The home body gains a temporary negative trait (*Transversal Shock d6*) that fades after a scene.

Defeat in inapposite transversal: permanent death. No snapback.

### Recovery

Players recover from negative traits through narrative action — resting, medical treatment, cultivation cycling, or time skips. Recovery is not a roll; it's a narrative condition. When the condition is met, the negative trait steps down or is removed. The GM adjudicates pacing.

---

## Next

- [[Core Mechanics]] — Dice pool assembly, negative traits overview, beats and sessions
- [[SFX and Effects]] — How SFX modify conflict rolls and stress
- [[System Architecture]] — How the backend implements conflict resolution
