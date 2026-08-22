// Razmerit resonance — pure signal model for character/projection transitions.
//
// The idea: a character is a superposition of its trait ratings. Each die in a
// rating contributes a sine wave; the whole character is their sum. Switching
// characters is a crossfade from one superposition to the next; the "collapse"
// is the moment the mix settles into the target's exact signature.
//
// This module is deliberately framework-free so it can be reused by the player
// settings screen, a future portal/resleeve transition, and tests.

// Die type → base frequency. A consonant pentatonic-ish ladder so the combined
// wave reads as "harmonic" rather than noise.
const DIE_FREQ = {
  d4: 220.0,
  d6: 261.63, // C4
  d8: 329.63, // E4
  d10: 392.0, // G4
  d12: 440.0, // A4
}

const FALLBACK_FREQ = 261.63

// Trait categories occupy distinct octave bands so entity/projection/ego
// traits stay separable in the mix.
const CATEGORY_BAND = {
  entity: 1.0,
  projection: 1.5,
  relationship: 2.0,
  ego: 0.75,
}

// Number of razmerit at which the amplitude is ~99% of full scale.
const RAZMERIT_SATURATION = 25

// Die size → relative amplitude. A d12 trait is stronger than a d4 trait.
const DIE_WEIGHT = {
  d4: 4,
  d6: 6,
  d8: 8,
  d10: 10,
  d12: 12,
}

// Polarity sign → phase. Positive oscillators start at 0; negative ones are
// phase-inverted so assets and complications read as opposed waves.
const POLARITY_PHASE = {
  positive: 0,
  negative: Math.PI,
}

// Golden angle — deterministic, non-repeating horizontal spread for repeated
// dice of the same type (e.g. eight d8s fan out instead of stacking).
const GOLDEN = Math.PI * (3 - Math.sqrt(5))

export function easeInCubic(x) {
  return x * x * x
}
export function easeOutCubic(x) {
  return 1 - Math.pow(1 - x, 3)
}
export function easeInOutCubic(x) {
  return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2
}

// Deterministic tiny detune per traitset so same-die traitsets still read as
// distinct voices rather than a braid.
function hashString(s) {
  let h = 2166136261
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return Math.abs(h)
}
function traitsetDetune(id) {
  return (hashString(String(id || '')) % 1000) / 1000 * 4 - 2 // ±2 Hz
}

export function dieFrequency(die) {
  return DIE_FREQ[String(die || '').toLowerCase()] ?? FALLBACK_FREQ
}

export function categoryBand(fromType) {
  return CATEGORY_BAND[String(fromType || '').toLowerCase()] ?? 1.0
}

// Log-normalised amplitude. 0 razmerit still yields a faint floor so the
// transition is visible even when the entity has no hyper-dimensional material.
export function razmeritAmplitude(razmerit) {
  const n = Math.max(0, Number(razmerit) || 0)
  const t = Math.log10(1 + n) / Math.log10(1 + RAZMERIT_SATURATION)
  return 0.12 + 0.88 * Math.min(1, t)
}

/**
 * Build a character's oscillator set from its trait settings.
 *
 * @param {Array} traitSettings — GraphQL `traitSettings` (dice, polarity,
 *   fromType, ego, traitId/id).
 * @param {number} razmerit — entity's current razmerit balance (amplitude).
 * @param {number} egoBoost — amplitude multiplier for entity-anchored (ego) traits,
 *   so an identity's fundamental stays recognisable across projections.
 * @returns {Array} oscillators [{freq, amp, phase, kind, die, traitId}]
 */
export function signatureOf(traitSettings, razmerit = 0, egoBoost = 1) {
  const baseAmp = razmeritAmplitude(razmerit)
  const boost = Number.isFinite(egoBoost) && egoBoost >= 0 ? egoBoost : 1
  const osc = []
  let oscIndex = 0

  for (const ts of traitSettings || []) {
    const dice = Array.isArray(ts.dice) ? ts.dice : []
    if (!dice.length) continue

    const band = categoryBand(ts.fromType)
    const kind = String(ts.fromType || 'entity').toLowerCase()
    const isEgo = ts.ego ?? kind === 'entity'
    const egoBand = isEgo ? 0.5 : 1
    const egoAmp = isEgo ? boost : 1
    const phase = POLARITY_PHASE[String(ts.polarity || '').toLowerCase()] ?? 0
    const traitId = ts.traitId || ts.id || ''
    const traitsetId = ts.traitsetId || ts.traitset_id || traitId
    const negative = String(ts.polarity || '').toLowerCase() === 'negative'
    const driftMul = 0.5 + (hashString(traitsetId) % 100) / 100 // 0.5..1.5

    dice.forEach((die) => {
      const weight = (DIE_WEIGHT[String(die || '').toLowerCase()] ?? 6) / 12
      osc.push({
        freq: dieFrequency(die) * band * egoBand + traitsetDetune(traitsetId),
        amp: baseAmp * weight * egoAmp,
        phase: phase + oscIndex * GOLDEN,
        kind,
        die,
        traitId,
        traitsetId,
        driftMul,
        negative,
      })
      oscIndex++
    })
  }

  return osc
}

/**
 * Sample a set of oscillators at time t (seconds).
 */
export function sampleAt(osc, t) {
  let sum = 0
  for (let i = 0; i < osc.length; i++) {
    const o = osc[i]
    sum += o.amp * Math.sin(2 * Math.PI * o.freq * t + o.phase)
  }
  return sum
}

/**
 * Whole-signal crossfade between two oscillator sets.
 * progress 0 = pure `from`, 1 = pure `to`.
 */
export function blendedSample(from, to, t, progress) {
  const p = Math.max(0, Math.min(1, progress))
  const a = sampleAt(from, t)
  const b = sampleAt(to, t)
  return a * (1 - p) + b * p
}

/**
 * Group oscillators by trait, returning one representative wave per trait.
 * The representative keeps the trait's dominant frequency/phase and sums the
 * amplitude of all its dice, so a 12-die trait reads as one strong wave.
 */
export function traitWaves(osc) {
  const map = new Map()
  for (const o of osc || []) {
    const key = o.traitId || `${o.kind}:${o.die}`
    const existing = map.get(key)
    if (!existing) {
      map.set(key, { ...o, dice: [o.die], amp: o.amp })
    } else {
      existing.amp += o.amp
      existing.dice.push(o.die)
    }
  }
  return [...map.values()]
}

/**
 * Group dice by (traitset, die type). Each group becomes one phase-aligned,
 * amplitude-summed wave — the "traitset × die type" voice that emphasizes
 * that traitset's peak before the final entity composite.
 */
export function groupByTraitsetDie(osc) {
  const map = new Map()
  for (const o of osc || []) {
    const key = `${o.traitsetId || o.traitId || 'ts'}:${o.die}`
    const existing = map.get(key)
    if (!existing) {
      map.set(key, { ...o, phase: 0, amp: o.amp, dice: 1 })
    } else {
      existing.amp += o.amp
      existing.dice += 1
    }
  }
  return [...map.values()]
}

/**
 * Collapse oscillators into one wave per frequency band (and kind), summing
 * amplitudes. This is the legible "spectrum" used for the collapse/fan-out;
 * the composite itself still uses the full per-die set.
 */
export function spectralWaves(osc, resolutionHz = 12) {
  const map = new Map()
  for (const o of osc || []) {
    const bin = Math.round(o.freq / resolutionHz) * resolutionHz
    const key = `${o.kind}:${bin}`
    const existing = map.get(key)
    if (!existing) {
      map.set(key, { ...o, freq: bin, amp: o.amp })
    } else {
      existing.amp += o.amp
    }
  }
  return [...map.values()]
}

/**
 * Morph one oscillator set into another by gliding each source wave toward its
 * nearest-frequency target. Returns one wave per source oscillator, so a dense
 * source collapses onto a sparse target (or vice versa).
 */
export function morphWaves(from, to, progress) {
  const p = Math.max(0, Math.min(1, progress))
  const targets = [...(to || [])]
  if (!targets.length) return (from || []).map((o) => ({ ...o }))

  return (from || []).map((a) => {
    let best = targets[0]
    let bestDist = Infinity
    for (const b of targets) {
      const d = Math.abs(a.freq - b.freq)
      if (d < bestDist) {
        bestDist = d
        best = b
      }
    }
    return {
      freq: a.freq + (best.freq - a.freq) * p,
      amp: a.amp + (best.amp - a.amp) * p,
      phase: a.phase + (best.phase - a.phase) * p,
      kind: p < 0.5 ? a.kind : best.kind,
      die: p < 0.5 ? a.die : best.die,
      traitId: p < 0.5 ? a.traitId : best.traitId,
    }
  })
}

/**
 * Collapse an oscillator set onto the nearest harmonics of a shared
 * fundamental. Waves landing on the same harmonic are summed into one, giving
 * the single repeating irregular waveform of the "collapse" phase.
 */
export function harmonicProfile(osc, fundamental = 55) {
  const map = new Map()
  for (const o of osc || []) {
    const h = Math.max(1, Math.round(o.freq / fundamental))
    if (!map.has(h)) {
      map.set(h, { ...o, freq: h * fundamental, phase: 0, harmonic: h })
    } else {
      map.get(h).amp += o.amp
    }
  }
  return [...map.values()]
}

/**
 * The three-phase "harmonic collapse" transition:
 *   0–1/3: source dice converge to their nearest harmonics (collapse).
 *   1/3–2/3: the harmonic profile morphs source → target (transform).
 *   2/3–1: the target profile splits back into the target's dice.
 */
export function harmonicTransition(from, to, progress, fundamental = 55) {
  const p = Math.max(0, Math.min(1, progress))
  const fromP = harmonicProfile(from, fundamental)
  const toP = harmonicProfile(to, fundamental)

  if (p < 1 / 3) {
    return morphWaves(from, fromP, easeOutCubic(p * 3))
  }
  if (p < 2 / 3) {
    return morphWaves(fromP, toP, easeInOutCubic((p - 1 / 3) * 3))
  }
  return morphWaves(to, toP, 1 - easeInCubic((p - 2 / 3) * 3))
}

/**
 * Crossfade with each side independently normalised to [-1, 1], so neither
 * character dims the other when their total amplitudes differ.
 */
export function blendedNormalized(from, to, t, progress) {
  const p = Math.max(0, Math.min(1, progress))
  const aTotal = totalAmplitude(from, [])
  const bTotal = totalAmplitude([], to)
  const a = aTotal > 0 ? sampleAt(from, t) / aTotal : 0
  const b = bTotal > 0 ? sampleAt(to, t) / bTotal : 0
  return a * (1 - p) + b * p
}

/**
 * Normalise a sample to [-1, 1] based on the union of both sets' total
 * amplitude, so the renderer doesn't need to guess a scale.
 */
export function totalAmplitude(from, to) {
  const sum = (acc, o) => acc + o.amp
  return Math.max(0.0001, from.reduce(sum, 0) + to.reduce(sum, 0))
}

/**
 * Shared tuning knobs for the resonance transition. Single source of truth so
 * App.vue (timing) and RazmeritWaves.vue (rendering) stay in sync.
 */
export const RESONANCE = {
  durationMs: 3000, // minimum switch/load window (crossfade finishes here)
  fanMs: 800, // brief settle after done before the overlay closes
  collapseFraction: 0.45, // relative weight of the collapse phase
  transformFraction: 0.1, // relative weight of the transform phase
  expandFraction: 0.45, // relative weight of the expand phase
  renderDivisor: 90, // Hz → visible cycles; d4 (220 Hz) = one period across width
  height: 200, // canvas height (CSS px)
  drift: 0.002, // right-to-left scroll rate (signal-seconds per second)
  egoBoost: 2, // entity-anchored (ego) amplitude multiplier vs morph traits
  mode: 'harmonic', // 'harmonic' | 'crossfade' | 'morph'
  presets: {
    harmonic: { mode: 'harmonic' },
    transversalGradient: { mode: 'crossfade' },
    morph: { mode: 'morph' },
  },
  colors: {
    entity: '#5ad4e8',
    projection: '#2ac6a0',
    relationship: '#e8a55a',
    ego: '#b48ae0',
  },
}
