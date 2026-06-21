---
title: SFX and Effects
tags:
  - transversal
  - game-design
  - sfx
  - effects
  - automation
aliases:
  - SFX
  - Special Effects
  - Effects System
---

# SFX and Effects

**SFX** (Special Effects) are rule exceptions that modify how the game behaves for specific entities and situations. The **Effects System** is the backend automation layer that applies SFX-triggered changes to the gamestate.

## SFX Overview

In Cortex Prime, SFX are attached to specific traits (usually Distinctions) and provide conditional rule modifications. Transversal preserves this model while adding structured automation so the system can resolve SFX without human adjudication.

### Anatomy of an SFX

```yaml
sfx:
  name: "Dimensional Echo"
  trigger: "When you roll a complication on a task related to dimensional travel"
  effect:
    type: "modify_roll"
    action: "step_up_die"
    target: "complication_die"
  cost: 1  # Razmerit cost (0 = free)
```

| Field | Description |
|-------|-------------|
| `name` | Human-readable name |
| `trigger` | The condition that activates the SFX (declarative description) |
| `effect` | What the SFX does when triggered (structured effect object) |
| `cost` | Razmerit cost to activate (0 for always-on SFX) |

### SFX Categories

| Category | Description | Example |
|----------|-------------|---------|
| **Modify Roll** | Change dice in the pool before or after rolling | Step up a die, reroll a die, add a die |
| **Modify Outcome** | Change the result after resolution | Increase effect die, add a raise, negate a complication |
| **Create/Modify Entity** | Add, remove, or change traits/assets | Create a temporary asset, step up a trait |
| **Spoof Location** | Temporarily change the effective universe for trait availability | Activate the jian to access Three Realms traits on Earth |
| **Narrative** | Declare a story fact | "You recognize this technology from your home dimension" |

## The Effects System

The effects system is the technical layer that executes SFX. When an SFX triggers, the effects system:

1. **Validates** — checks that the trigger conditions are met and the cost can be paid
2. **Applies** — executes the structured effect against the gamestate
3. **Records** — logs the change for undo, replay, and UI updates

### SFX Scheduling

Every SFX declares a **timing** that determines when its effect fires relative to its trigger:

| Timing | Behavior | Example |
|--------|----------|---------|
| `immediate` | Fires instantly when trigger conditions are met | Step up a die before rolling |
| `end_of_beat` | Fires after the current beat resolves and dice pools clear | "After your attack, gain +1 razmerit" |
| `end_of_scene` | Fires when the location changes or the scene ends | "Your buffed trait returns to normal" |
| `end_of_session` | Fires when playtime ends | "At session end, resolve all outstanding debts" |
| `after_beats(N)` | Fires after N beats have elapsed since activation | "For the next 3 beats, your qi is doubled" |
| `on_condition` | Fires when a specified narrative or mechanical condition is met | "When the gate opens, you gain an insight" |

If no timing is specified, `immediate` is the default. Deferred effects are queued by the effects system and executed when their boundary arrives. This enables buffs, debuffs, delayed consequences, and session-wrap cleanup without GM manual tracking.

### Effect Targets

Effects can target many parts of the application:

| Target | Example Action |
|--------|---------------|
| `razmerit` | Add or deduct razmerit from an entity's pool |
| `trait` | Create, delete, step up, step down, or set a trait rating |
| `dice_pool` | Add, remove, step up, step down, or reroll dice in an active pool |
| `entity` | Create or delete an entity (asset, GMC, location) |
| `relationship` | Create, modify, or remove a relationship between entities |
| `known_to` | Reveal hidden entities by adding to `known_to` lists |
| `projection` | Create or modify a universe projection |
| `location_spoof` | Apply a temporary universe spoof for trait availability |

### Effect Types

#### modify_roll

Changes dice within an active dice pool.

| Action | Description |
|--------|-------------|
| `step_up_die` | Increase a die by one step (d6→d8) |
| `step_down_die` | Decrease a die by one step (d8→d6) |
| `double_die` | Add a second copy of a die to the pool |
| `reroll_die` | Reroll a single die, keep the new result |
| `add_die` | Add a new die to the pool (specified by size) |
| `remove_die` | Remove a die from the pool |

```yaml
# Example: "Relentless" SFX — step up your primary trait die before rolling
effect:
  type: "modify_roll"
  action: "step_up_die"
  target: "highest_trait_die"
```

#### modify_outcome

Changes the result after the roll is resolved.

| Action | Description |
|--------|-------------|
| `step_up_effect` | Increase the effect die by one step |
| `step_up_outcome` | Simplified: bump outcome tier by 1. Dice Pool: add +2 to total |
| `negate_complication` | Cancel one triggering complication |
| `convert_complication` | Turn a complication into a bonus die (adds a d6 to a future roll) |
| `reroll_highest` | Reroll the highest die and keep the new result |

#### create_entity

Creates a new entity or asset in the gamestate.

```yaml
# Example: "MacGyver" SFX — create a temporary asset from available materials
effect:
  type: "create_entity"
  entity_type: "asset"
  traits:
    utility: d6
  duration: "scene"
  name_template: "Improvised {material}"
```

#### modify_trait

Changes an existing trait on any entity.

| Action | Description |
|--------|-------------|
| `step_up` | Increase a trait die by one step |
| `step_down` | Decrease a trait die by one step |
| `set` | Set a trait to a specific die value |
| `add` | Add a new trait to a trait set |
| `remove` | Remove a trait |

#### transfer_razmerit

Moves razmerit between entities.

| Action | Description |
|--------|-------------|
| `pay` | Deduct from source, add to pool |
| `earn` | Add to target from the system pool |
| `transfer` | Move from source entity to target entity |

### Trigger System

SFX triggers can be:

| Trigger Type | Fires When |
|--------------|------------|
| `on_roll` | A dice pool is assembled but before rolling |
| `on_result` | After the roll is resolved but before effect die is chosen |
| `on_complication` | A complication (hitch) occurs |
| `on_botch` | All dice in a roll show 1 (catastrophic failure) |
| `on_success` | A roll succeeds |
| `on_failure` | A roll fails |
| `on_location_change` | An entity changes location |
| `on_trait_change` | A trait value changes on any entity |
| `on_turn` | The entity's turn begins or ends |

Multiple SFX can chain — the effects system resolves them in dependency order, not arbitrarily.

## Example SFX Builds

### "Lucky Break"
```
Trigger: on_complication
Effect: reroll_die (target: the die that rolled 1)
Cost: 1 razmerit
```
When you roll a hitch, spend 1 razmerit to reroll that die. The new result stands.

### "Dimensional Anchor"
```
Trigger: on_location_change (entering a new dimension)
Effect: create_entity (asset: "Anchor Point", trait: stability d8, duration: scene)
Cost: 0 razmerit
```
When you enter a new dimension, you automatically create a temporary anchor point that helps you navigate.

### "Overcharge"
```
Trigger: on_roll
Effect: step_up_die (target: primary trait die), then after resolution step_down_die (target: same trait)
Cost: 1 razmerit
```
Push your abilities beyond normal limits — but suffer temporary depletion afterward.

### "Catastrophe Insurance"
```
Trigger: on_botch
Effect: convert_complication (turn the botch into a standard hitch — the action still fails, but without the catastrophic escalation)
Cost: 2 razmerit
```
When everything goes wrong, burn razmerit to contain the damage. The roll still fails, but the GM downgrades the botch to a single hitch-level complication.

## Integration with Dice Mechanics

The effects system hooks into both resolution pipelines at shared interception points. After `on_roll` SFX fire, the system re-evaluates pool size to determine which pipeline executes:

```
Assemble Pool → [on_roll SFX fire] → Re-evaluate pipeline (1-2 = Simplified, 3+ = Pool)
    → Roll → Check for botch (all dice = 1) → [on_botch SFX fire if triggered]
    → [on_complication SFX fire] for individual hitches
    → Simplified: take highest → map to tier
    → Dice Pool: keep two highest → add → compare
    → [on_success / on_failure SFX fire]
    → Choose Effect Die → [on_result SFX fire]
    → Apply Outcome
```

See [[Dice Mechanics]] for both pipeline procedures.

## Design Principle

> [!quote] Declarative Over Procedural
> SFX are defined declaratively — they describe *what* happens, not *how*. The effects system interprets the declaration and applies it to the current gamestate. This separation means:
> - New SFX can be added without changing core code
> - The system can reason about effect chains and resolve conflicts
> - Rollback and replay are possible because all changes are recorded
> - The GM can create custom SFX during play

## Next

- [[Core Mechanics]] — The fundamentals these exceptions modify
- [[Dice Mechanics]] — Where SFX intercept the rolling procedure
- [[System Architecture]] — How the effects system is implemented
