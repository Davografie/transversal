---
title: Projections and Transversal
tags:
  - transversal
  - game-design
  - projections
  - attunement
  - earth-bond
aliases:
  - Projections
  - Transversal
  - Projection Model
  - Earth Bond
status: canonical
---

# Projections and Transversal

How identity, bodies, and travel across universes work. This is the single source of truth for the projection / transversal model — it supersedes the old `transversal` / `home_universes` flags and the earlier "attunement as location spoofing" notes.

## The Model

**Identity and position are separate.**

- **Entity (occupant)** — character, GMC, or asset: identity, ego traits, relationships, `current_projection` (which body the consciousness inhabits), and `attunements`.
- **Entity (non-occupant)** — location, universe, or faction: identity and `current_universe` only. No projection.
- **Projection** — one per `(entity, origin-universe)`. A body: name, image, current location, and morph traits.

| Field | Meaning |
|-------|---------|
| `id` | `"{entity_id}:{origin_universe}"` — immutable key |
| `origin_universe` | the universe this body is native to (immutable) |
| `universe` | current universe (mutable) |
| `current_location` | where the body is now (mutable) |
| `name` / `background_image` | fall back to the entity's |
| `transversal_type` | provenance / lifecycle record |

- **TraitSetting** — ego traits anchor to the entity; morph traits anchor to a projection. `from_type` is `entity`, `projection`, or `relationship`.
- **Attunement** — `{universe, scope (self | domain), until (None = permanent), source_sfx_id}`. Always a temporary effect, never a passive state.
- **effective_universes** — `{current_projection.universe}` ∪ unexpired attunement universes.
- **Trait availability** — ego traits always; morph traits iff `origin_universe ∈ effective_universes`.

Trait availability is gated by `origin_universe` (identity), not the current universe (position). Occupancy and return-travel use the current universe / location.

## `current_projection`, `current_universe`, `origin_universe`

- `Entity.current_projection` — the active body (which projection the consciousness inhabits). Authoritative for occupants; `universe` and `location` are derived from it, not stored on the entity.
- `Projection.universe` — current universe (where the body is now), mutable.
- `Projection.origin_universe` — native universe (what the body is), immutable, encoded in the projection key.
- `Entity.current_universe` — kept only for non-occupants.

## The three ways to move

### Consciousness transversal
The consciousness projects into a new body in another universe. A `CONSCIOUSNESS` projection is spawned (or reused). On death of the projection, the consciousness snaps back to the home body: razmerit in the projection is lost, and the home body gains *Transversal Shock d6* (fades after a scene).

### Inapposite transversal
Full physical transport. An **in-place update**: the active projection's `universe` and `current_location` mutate, and `transversal_type` becomes `INAPPOSITE`. The projection key stays `"{entity_id}:{origin_universe}"`, so the body keeps its identity and history. Death here is permanent — no snap-back.

### Attunement
A temporary SFX effect that adds a universe to `effective_universes` without moving anything — e.g. the jian's "Law Bridge" lets an Earth body use Three Realms morph traits for a scene. Attunement is always an active effect with a cost and duration.

## `transversal_type` — provenance, not a gate

A narrative / lifecycle record, never read for trait availability:

- **NATIVE** — permanent; "who I am." The return target for consciousness travel; never auto-deleted.
- **CONSCIOUSNESS** — transient; cleaned up on return to the body or when the attunement ends.
- **INAPPOSITE** — a physically relocated body; position mutates in place.

## The Earth-Bond

Earth is the persistent home universe — every main character originates there and carries a mechanical tether to it.

- **Earth-bond** is a **negative challenge trait** (a per-character doom pool): its dice are opposition dice — a player clicking it can auto-roll it or hand it to the GM's pool.
- The GM **buys hitches and botches** against the character by spending from the earth-bond — each complication they escalate draws the bond down.
- **Resistance** emerges in play: when something weird happens, or an antagonist's SFX challenges the character's bond to Earth, the character rolls to resist.
- When the pool is **empty**, the character goes **full-native**.

### Full-native

- The character's consciousness projection **promotes to NATIVE**.
- Their Earth projection **decays** — no more consciousness snap-back; the return ticket is gone.
- Earth-anchored traits and bonds **step down**.

Full-native is an identity shift, not a death — the character is now truly of the world they're in.

### Flashbacks (stub)

Flashbacks are an **SFX on the earth-bond**: spend razmerit to play a scene and strengthen the trait. *(Exact mechanics TBD — this is a stub.)*

## See also

- [[Entities and Traits]] — trait registry, ego/morph traits, entity types
- [[Data Model]] — collections and schema
- [[SFX and Effects]] — the effects system that drives attunement and flashbacks
- [[Character Growth]] — entanglements and relationship traits
- [[Inspired Mechanics]] — challenge / doom-pool mechanics
