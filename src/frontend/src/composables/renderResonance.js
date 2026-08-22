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
  const renderDivisor = opts.renderDivisor ?? RESONANCE.renderDivisor
  const drift = opts.drift ?? RESONANCE.drift
  const collapseFraction = opts.collapseFraction ?? RESONANCE.collapseFraction
  const transformFraction = opts.transformFraction ?? RESONANCE.transformFraction
  const expandFraction = opts.expandFraction ?? RESONANCE.expandFraction

  const midY = h / 2
  const ampScale = h / 2 - 14
  const driftOffset = progress * drift

  const columns = []
  for (let x = 0; x <= w; x += 2) columns.push(x)

  const sampleTime = (x) => (x / w) / renderDivisor + driftOffset
  const maxAmp = (arr) => {
    let m = 0
    for (const o of arr) if (o.amp > m) m = o.amp
    return m
  }
  const ownY = (o, strength, x) =>
    midY - Math.sin(2 * Math.PI * o.freq * sampleTime(x) + o.phase) * ampScale * (0.35 + 0.65 * strength)

  ctx.save()
  ctx.lineJoin = 'round'
  ctx.lineCap = 'round'
  ctx.globalCompositeOperation = 'lighter'

  // Draw one oscillator, lerping its y toward a per-column target.
  const drawOsc = (o, conv, targetY, color, strength, opacity = 1) => {
    // Halo.
    ctx.beginPath()
    ctx.strokeStyle = color
    ctx.globalAlpha = 0.12 * strength * opacity
    ctx.lineWidth = 3.2
    columns.forEach((x, j) => {
      const own = ownY(o, strength, x)
      const y = own + (targetY(x, j) - own) * conv
      j === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
    })
    ctx.stroke()

    // Core.
    ctx.beginPath()
    ctx.strokeStyle = color
    ctx.globalAlpha = 0.85 * opacity
    ctx.lineWidth = 1.05
    columns.forEach((x, j) => {
      const own = ownY(o, strength, x)
      const y = own + (targetY(x, j) - own) * conv
      j === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
    })
    ctx.stroke()
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
        drawOsc(die, s1, (x) => ownY(g, gStrength, x), color, dStrength, opacity)
      }
    } else {
      const s2 = easeInOutCubic((c - 0.5) * 2)
      const totalG = totalAmplitude(groups, [])
      const entityY = columns.map((x) => {
        const v = totalG > 0 ? sampleAt(groups, sampleTime(x)) / totalG : 0
        return midY - v * ampScale
      })
      const maxG = maxAmp(groups) || 1
      for (const g of groups) {
        const gStrength = g.amp / maxG
        const color = mixColor(getDieColor(g.die, g.negative), '#ffffff', s2)
        drawOsc(g, s2, (x, j) => entityY[j], color, gStrength, opacity)
      }
    }
  }

  // A single white trace blending the source and target entity composites.
  const drawCompositeBlend = (fromOsc, toOsc, tf, opacity = 1) => {
    const totalA = totalAmplitude(fromOsc, [])
    const totalB = totalAmplitude([], toOsc)
    ctx.beginPath()
    ctx.strokeStyle = '#dceaff'
    ctx.globalAlpha = 0.9 * opacity
    ctx.lineWidth = 1.6
    ctx.shadowColor = 'rgba(160, 200, 255, 0.6)'
    ctx.shadowBlur = 4
    columns.forEach((x, j) => {
      const tt = sampleTime(x)
      const a = totalA > 0 ? sampleAt(fromOsc, tt) / totalA : 0
      const b = totalB > 0 ? sampleAt(toOsc, tt) / totalB : 0
      const v = a * (1 - tf) + b * tf
      const y = midY - v * ampScale
      j === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
    })
    ctx.stroke()
  }

  // Draw a set with a horizontal amplitude envelope (used by crossfade/morph).
  const drawEnvelopeSet = (osc, gain, envelope) => {
    if (!osc.length || gain <= 0) return
    const max = maxAmp(osc) || 1
    for (const o of osc) {
      const strength = o.amp / max
      const color = getDieColor(o.die, o.negative)

      ctx.beginPath()
      ctx.strokeStyle = color
      ctx.globalAlpha = 0.12 * strength * gain
      ctx.lineWidth = 3.2
      columns.forEach((x, j) => {
        const nx = x / w
        const y = ownY(o, strength, x) * envelope(nx) + midY * (1 - envelope(nx))
        j === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
      })
      ctx.stroke()

      ctx.beginPath()
      ctx.strokeStyle = color
      ctx.globalAlpha = 0.85 * gain
      ctx.lineWidth = 1.05
      columns.forEach((x, j) => {
        const nx = x / w
        const y = ownY(o, strength, x) * envelope(nx) + midY * (1 - envelope(nx))
        j === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
      })
      ctx.stroke()
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

    const fromGroups = groupByTraitsetDie(from)
    const toGroups = groupByTraitsetDie(to)

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
