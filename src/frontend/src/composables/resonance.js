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
 * @returns {Array} oscillators [{freq, amp, phase, kind, die, traitId}]
 */
export function signatureOf(traitSettings, razmerit = 0) {
  const baseAmp = razmeritAmplitude(razmerit)
  const osc = []

  for (const ts of traitSettings || []) {
    const dice = Array.isArray(ts.dice) ? ts.dice : []
    if (!dice.length) continue

    const band = categoryBand(ts.fromType)
    const egoBand = ts.ego ? 0.5 : 1
    const phase = POLARITY_PHASE[String(ts.polarity || '').toLowerCase()] ?? 0
    const kind = String(ts.fromType || 'entity').toLowerCase()
    const traitId = ts.traitId || ts.id || ''

    dice.forEach((die, i) => {
      const freq = dieFrequency(die) * band * egoBand
      // Repeated dice in a rating beat against each other — literally "two dice".
      const detune = i * 0.35
      const weight = (DIE_WEIGHT[String(die || '').toLowerCase()] ?? 6) / 12
      osc.push({
        freq: freq + detune,
        amp: baseAmp * weight * (1 / (1 + i * 0.08)),
        phase,
        kind,
        die,
        traitId,
      })
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
  fanMs: 5000, // final "deposit to the right" phase, then close
  mergeFraction: 0.35, // fraction of durationMs spent sucking source into the line
  renderDivisor: 220, // Hz → visible cycles; d4 (220 Hz) = one period across width
  height: 200, // canvas height (CSS px)
  drift: 0.002, // slow horizontal flow — max signal-time offset (s) by the end
  minSpread: 6, // how wide the centre "line" is (px) at full collapse
  mode: 'crossfade', // 'crossfade' | 'morph'
  presets: {
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
