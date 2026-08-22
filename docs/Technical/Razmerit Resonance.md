---
title: Razmerit Resonance
tags:
  - transversal
  - technical
  - game-design
  - resonance
  - razmerit
  - projections
aliases:
  - Resonance
  - Signal Model
  - Razmerit Resonance Theory
status: draft
---

# Razmerit Resonance

A theoretical and visual model of Transversal: every occupant is a **superposition of trait-oscillators**, and crossing from one projection to another is a **resonant collapse** from one superposition into the next.

This is the grounding for the character-switch animation and, eventually, portal/resleeve transitions. It is not yet canonical — see [[#Open questions]].

## Thesis

- An **entity** is not a single object; it is a *spectrum*.
- Each trait contributes a sine wave. The **die rating** sets its frequency and amplitude; the **polarity** sets its phase; the **razmerit** sets the overall amplitude of the whole signature.
- The entity's live **resonance signature** is the sum of its active trait waves — a single irregular composite waveform.
- **Switching characters / resleeving** is the composite collapsing from one signature and re-expanding into another.

## Mapping: trait → wave

| Game concept | Signal concept | Rule |
|---|---|---|
| Die type (`d4…d12`) | Frequency | `d4=220Hz`, `d6=261.63`, `d8=329.63`, `d10=392`, `d12=440` (consonant ladder) |
| Repeated dice in a rating | Phase spread | golden-angle offset so equal dice don't stack |
| Traitset | Voice detune | deterministic ±2 Hz per traitset, so same-die traitsets differ |
| Polarity (positive / negative) | Phase | positive `0`, negative `π` (inverted) |
| Razmerit balance | Amplitude | log-normalized, saturating around `~25` |
| Trait anchor (`from_type`) | Octave band | entity / projection / relationship occupy distinct bands |
| Active projection | Harmonic profile | only the active projection's morph traits participate (see below) |

## Superposition and collapse

The composite is the **arithmetic sum** of the active component waves — additive synthesis, not a metaphor.

The transition has three phases:

1. **Collapse** — the individual dice converge onto the composite. First they coalesce into per-traitset × die-type peaks (phase-aligned, amplitude-emphasized), then those peaks merge into one irregular line.
2. **Transform** — the single composite morphs from the source entity's signature to the target's.
3. **Expand** — the target composite splits back into the target's individual dice.

The phases overlap and lerp into each other, so it reads as one continuous motion rather than three clips.

## Projection as tuning

The multiverse is a set of **frequency domains**. A [[Projections and Transversal|projection]] is a body tuned to a universe:

- **Ego traits** (`from_type = "entity"`) persist across projections — they are the identity's fundamental.
- **Morph traits** (`from_type = "projection"`) belong to a body; they participate only when that body's `origin_universe` is within the entity's `effective_universes`.

So "resonating into a projection" means: the ego fundamental stays, and the morph harmonics re-tune to the active body. This is why active filtering matters — a signature must not leak every projection at once.

> ⚠️ The ego/morph model is being refactored. The current `character(id)` path is mid-migration; do not treat the frontend's old `ego` field as the source of truth.

## Razmerit as amplitude

Razmerit is the **energy** of the signal ([[Setting and Narrative]] describes it as boundary-born material that "resonates" and "tunes" to universes). A high razmerit balance = a strong, bright signature; zero razmerit = a faint floor. It saturates, so hoarding does not clip.

## Agency as coherence (draft)

A player's **agency** over an entity is the right to hold its signature in coherence. Relinquishing agency does not destroy the entity — it releases the lock, so the entity can be re-tuned by someone else.

## The instrument

The visualization is the *measurement device* for the theory:

- `src/frontend/src/composables/resonance.js` — pure signal model (`signatureOf`, `groupByTraitsetDie`, `morphWaves`, `sampleAt`, `RESONANCE`).
- `src/frontend/src/composables/renderResonance.js` — canvas renderer (hierarchical collapse, die colors, drift, phase blending).
- `src/frontend/src/components/RazmeritWaves.vue` — live switch renderer.
- `src/frontend/src/components/ResonanceLab.vue` — tuning editor (scrub, play, knobs, variable output).

Tunables live in `RESONANCE`: `mode`, `renderDivisor`, `drift`, `height`, `durationMs`, `collapseFraction`, `transformFraction`, `expandFraction`.

## Open questions

- **Active-projection filtering** — the signature should include ego traits + only the active projection's morph traits. Needs `currentProjection` / `origin_universe` / `effective_universes` once the backend settles.
- **Resleeve** — same entity, different projection: reuse the same collapse/transform/expand with a projection swap rather than an entity swap.
- **Universe traits** — should universes contribute their own fundamental/harmonics? Deferred.
- **Drift semantics** — currently a right-to-left scroll with per-wave rates; decide whether drift should encode *temporal* flow or *universe* pressure.
