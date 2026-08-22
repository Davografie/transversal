import { RESONANCE, morphWaves, groupByTraitsetDie, sampleAt, totalAmplitude, easeInOutCubic } from './resonance.js'

const FALLBACK_DIE_COLORS = {
  d4: '#e88830',
  d6: '#e0e0e0',
  d8: '#d44040',
  d10: '#4088d4',
  d12: '#40b860',
}
const FALLBACK_DIE_COLORS_NEG = {
  d4: '#7a4a1f',
  d6: '#4f4f4f',
  d8: '#7a1f1f',
  d10: '#1f3d6e',
  d12: '#1f5a34',
}

let dieColorCache = null
const groupsCache = new WeakMap()

function getDieColor(die, negative) {
  if (!dieColorCache) {
    dieColorCache = {}
    const styles = typeof getComputedStyle !== 'undefined' && typeof document !== 'undefined'
      ? getComputedStyle(document.documentElement)
      : null
    for (const d of ['d4', 'd6', 'd8', 'd10', 'd12']) {
      const pos = styles ? styles.getPropertyValue(`--die-${d}`).trim() : ''
      const neg = styles ? styles.getPropertyValue(`--die-${d}-neg`).trim() : ''
      dieColorCache[d] = pos || FALLBACK_DIE_COLORS[d]
      dieColorCache[`${d}:neg`] = neg || FALLBACK_DIE_COLORS_NEG[d]
    }
  }
  const d = String(die || 'd6').toLowerCase()
  return negative ? (dieColorCache[`${d}:neg`] || dieColorCache[d]) : dieColorCache[d]
}

function getGroups(arr) {
  let g = groupsCache.get(arr)
  if (!g) {
    g = groupByTraitsetDie(arr)
    groupsCache.set(arr, g)
  }
  return g
}

function mixColor(a, b, t) {
  if (t <= 0) return a
  if (t >= 1) return b
  const hex = (s) => {
    if (!s || s[0] !== '#') return [255, 255, 255]
    const n = parseInt(s.slice(1), 16)
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
  }
  const [ar, ag, ab] = hex(a)
  const [br, bg, bb] = hex(b)
  const r = Math.round(ar + (br - ar) * t)
  const g = Math.round(ag + (bg - ag) * t)
  const bl = Math.round(ab + (bb - ab) * t)
  return `rgb(${r},${g},${bl})`
}

/**
 * Draw one frame of the resonance transition at a given progress (0..1).
 * Shared by the live switch renderer and the Resonance Lab editor.
 */
export function drawResonanceFrame(ctx, w, h, from, to, progress, opts = {}) {
  const mode = opts.mode ?? RESONANCE.mode
  const layout = opts.layout ?? RESONANCE.layout ?? 'linear'
  const renderDivisor = opts.renderDivisor ?? RESONANCE.renderDivisor
  const drift = opts.drift ?? RESONANCE.drift
  const timeMs = opts.timeMs ?? (typeof performance !== 'undefined' ? performance.now() : 0)
  const collapseFraction = opts.collapseFraction ?? RESONANCE.collapseFraction
  const transformFraction = opts.transformFraction ?? RESONANCE.transformFraction
  const expandFraction = opts.expandFraction ?? RESONANCE.expandFraction

  // Continuous right-to-left scroll. `drift` is a rate in signal-seconds/sec;
  // each wave multiplies it by its own driftMul so it doesn't march in lockstep.
  const baseDrift = drift * (timeMs / 1000)

  // Sample points across the trace (t in 0..1). Linear maps t→x, radial maps
  // t→angle around a base circle.
  const sampleStep = Math.max(2, Math.round(w / 180))
  const N = Math.max(16, Math.round(w / sampleStep))
  const columns = []
  for (let j = 0; j <= N; j++) columns.push(j / N)

  // Projection: a signed amplitude offset (positive = up / outward) → canvas
  // point. Everything upstream stays in 1-D signal space; only this differs.
  let project
  let ampScale
  if (layout === 'radial') {
    const radius = Math.min(w, h) / 2
    const R = radius / 2
    ampScale = radius / 2 - 12
    const cx = w / 2
    const cy = h / 2
    project = (t, off) => {
      const theta = t * Math.PI * 2 - Math.PI / 2
      const r = R + off
      return [cx + Math.cos(theta) * r, cy + Math.sin(theta) * r]
    }
  } else {
    const midY = h / 2
    ampScale = h / 2 - 14
    project = (t, off) => [t * w, midY - off]
  }

  const sampleTime = (t) => t / renderDivisor + baseDrift
  const waveTime = (o, t) => t / renderDivisor + baseDrift * (o.driftMul ?? 1)
  const maxAmp = (arr) => {
    let m = 0
    for (const o of arr) if (o.amp > m) m = o.amp
    return m
  }
  // Signed amplitude offset of one oscillator at trace position t.
  const ownOff = (o, strength, t) =>
    Math.sin(2 * Math.PI * o.freq * waveTime(o, t) + o.phase) * ampScale * (0.35 + 0.65 * strength)

  ctx.save()
  ctx.lineJoin = 'round'
  ctx.lineCap = 'round'
  ctx.globalCompositeOperation = 'lighter'

  // Draw one oscillator, lerping its offset toward a per-column target offset.
  const drawOsc = (o, conv, targetOff, color, strength, opacity = 1) => {
    const trace = (lineWidth, alpha) => {
      ctx.beginPath()
      ctx.strokeStyle = color
      ctx.globalAlpha = alpha
      ctx.lineWidth = lineWidth
      columns.forEach((t, j) => {
        const own = ownOff(o, strength, t)
        const off = own + (targetOff(t, j) - own) * conv
        const [px, py] = project(t, off)
        j === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py)
      })
      ctx.stroke()
    }
    trace(3.2, 0.12 * strength * opacity) // halo
    trace(1.05, 0.85 * opacity) // core
  }

  // Collapse amount c: 0 = individual dice, 1 = entity composite. The first
  // half merges dice into per-traitset peaks; the second half merges those
  // peaks into the jagged entity composite.
  const drawHierarchical = (dice, groups, c, opacity = 1) => {
    if (!dice.length) return
    const groupByKey = new Map()
    for (const g of groups) groupByKey.set(`${g.traitsetId || g.traitId || 'ts'}:${g.die}`, g)

    if (c < 0.5) {
      const s1 = easeInOutCubic(c * 2)
      const maxD = maxAmp(dice) || 1
      const maxG = maxAmp(groups) || 1
      for (const die of dice) {
        const g = groupByKey.get(`${die.traitsetId || die.traitId || 'ts'}:${die.die}`)
        if (!g) continue
        const dStrength = die.amp / maxD
        const gStrength = g.amp / maxG
        const color = getDieColor(die.die, die.negative)
        drawOsc(die, s1, (t) => ownOff(g, gStrength, t), color, dStrength, opacity)
      }
    } else {
      const s2 = easeInOutCubic((c - 0.5) * 2)
      const totalG = totalAmplitude(groups, [])
      const entityOff = columns.map((t) => {
        const v = totalG > 0 ? sampleAt(groups, sampleTime(t)) / totalG : 0
        return v * ampScale
      })
      const maxG = maxAmp(groups) || 1
      for (const g of groups) {
        const gStrength = g.amp / maxG
        const color = mixColor(getDieColor(g.die, g.negative), '#ffffff', s2)
        drawOsc(g, s2, (t, j) => entityOff[j], color, gStrength, opacity)
      }
    }
  }

  // A single white trace blending the source and target entity composites.
  const drawCompositeBlend = (fromOsc, toOsc, tf, opacity = 1) => {
    const totalA = totalAmplitude(fromOsc, [])
    const totalB = totalAmplitude([], toOsc)
    const offs = columns.map((t) => {
      const tt = sampleTime(t)
      const a = totalA > 0 ? sampleAt(fromOsc, tt) / totalA : 0
      const b = totalB > 0 ? sampleAt(toOsc, tt) / totalB : 0
      return (a * (1 - tf) + b * tf) * ampScale
    })

    const trace = (lineWidth, alpha) => {
      ctx.beginPath()
      ctx.strokeStyle = '#dceaff'
      ctx.globalAlpha = alpha
      ctx.lineWidth = lineWidth
      columns.forEach((t, j) => {
        const [px, py] = project(t, offs[j])
        j === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py)
      })
      ctx.stroke()
    }
    trace(4, 0.15 * opacity) // cheap halo instead of per-frame shadowBlur
    trace(1.5, 0.9 * opacity)
  }

  // Draw a set with an amplitude envelope (used by crossfade/morph).
  const drawEnvelopeSet = (osc, gain, envelope) => {
    if (!osc.length || gain <= 0) return
    const max = maxAmp(osc) || 1
    for (const o of osc) {
      const strength = o.amp / max
      const color = getDieColor(o.die, o.negative)

      const trace = (lineWidth, alpha) => {
        ctx.beginPath()
        ctx.strokeStyle = color
        ctx.globalAlpha = alpha
        ctx.lineWidth = lineWidth
        columns.forEach((t, j) => {
          const off = ownOff(o, strength, t) * envelope(t)
          const [px, py] = project(t, off)
          j === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py)
        })
        ctx.stroke()
      }
      trace(3.2, 0.12 * strength * gain) // halo
      trace(1.05, 0.85 * gain) // core
    }
  }

  if (mode === 'harmonic') {
    const clamp01 = (v) => Math.max(0, Math.min(1, v))
    const p = progress
    const c = collapseFraction
    const t = transformFraction
    const e = expandFraction
    const sum = c + t + e || 1
    const collapseEnd = c / sum
    const expandStart = (c + t) / sum
    const blend = Math.min(0.08, (expandStart - collapseEnd) / 3)

    const fromGroups = getGroups(from)
    const toGroups = getGroups(to)

    // Overlapping phase opacities so the phases lerp into each other instead
    // of switching at a hard boundary.
    const ramp = (start, end) => clamp01((p - start) / (end - start))
    const oC = 1 - ramp(collapseEnd - blend, collapseEnd + blend)
    const oT = ramp(collapseEnd - blend, collapseEnd + blend) * (1 - ramp(expandStart - blend, expandStart + blend))
    const oE = ramp(expandStart - blend, expandStart + blend)

    if (oC > 0) {
      drawHierarchical(from, fromGroups, easeInOutCubic(clamp01(p / collapseEnd)), oC)
    }
    if (oT > 0) {
      const tf = easeInOutCubic(clamp01((p - collapseEnd) / (expandStart - collapseEnd)))
      drawCompositeBlend(fromGroups, toGroups, tf, oT)
    }
    if (oE > 0) {
      const s = easeInOutCubic(clamp01((p - expandStart) / (1 - expandStart)))
      drawHierarchical(to, toGroups, 1 - s, oE)
    }
  } else if (mode === 'morph') {
    drawEnvelopeSet(morphWaves(from, to, progress), 1, () => 1)
  } else {
    drawEnvelopeSet(from, 1 - progress, (x) => 1 - x)
    drawEnvelopeSet(to, progress, (x) => x)
  }

  ctx.restore()
}
