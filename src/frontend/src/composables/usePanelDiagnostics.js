// Drag-release diagnostics for the GM panel layout.
//
// The symptom this exists for: "sometimes the rail buttons are rendered halfway
// inside their own panel". That is a geometry mismatch, and the interesting
// state lives *inside* the components (bridges, slide offsets, cached
// measurements) rather than in the DOM — so panels register a reporter that
// returns their internal layout snapshot, and a dump merges:
//
//   1. the live DOM (every `.panel-node`, panel, rail and chip strip rect, plus
//      the rail's computed position values and classes), and
//   2. each panel's own view of the world (measured rects, bridges, effective
//      offsets, viewport fix, rail centre, how often it has re-measured).
//
// Comparing the two answers the key question the DOM alone can't: is a cached
// measurement stale (panel-reported rect ≠ live rect), and which rail is
// positioned from what.
//
// Dumps are silent unless `window.__PANEL_DEBUG__` is set, but they are always
// retrievable afterwards — the last few events are kept in
// `window.__PANEL_DUMPS__`, so a repro can be captured after the fact with
// `copy(JSON.stringify(window.__PANEL_DUMPS__))`.
const reporters = new Map() // panel uid -> () => snapshot
let seq = 0
const MAX_DUMPS = 12

export function nextPanelDiagId() {
  return `pd${++seq}`
}

export function registerPanelReporter(id, fn) {
  reporters.set(id, fn)
}

export function unregisterPanelReporter(id) {
  reporters.delete(id)
}

function rectOf(el) {
  if (!el) return null
  const b = el.getBoundingClientRect()
  return {
    t: Math.round(b.top), b: Math.round(b.bottom),
    l: Math.round(b.left), r: Math.round(b.right),
    w: Math.round(b.width), h: Math.round(b.height),
  }
}

function centreOf(rect) {
  return rect ? { x: Math.round((rect.l + rect.r) / 2), y: Math.round((rect.t + rect.b) / 2) } : null
}

function styleOf(el, props) {
  if (!el) return null
  const s = getComputedStyle(el)
  const out = {}
  for (const p of props) out[p] = s.getPropertyValue(p)
  return out
}

function overlapArea(a, b) {
  if (!a || !b) return 0
  const w = Math.min(a.r, b.r) - Math.max(a.l, b.l)
  const h = Math.min(a.b, b.b) - Math.max(a.t, b.t)
  return w > 0 && h > 0 ? w * h : 0
}

function domSnapshot() {
  return [...document.querySelectorAll('.panel-node')].map((node, i) => {
    const panelEl = node.querySelector('.panel')
    const railEl = node.querySelector('.panel-actions')
    const panel = rectOf(panelEl)
    const rail = rectOf(railEl)
    const railCentre = centreOf(rail)
    return {
      i,
      uid: node.dataset.panelUid || null,
      depth: node.dataset.panelDepth ?? null,
      window: node.dataset.panelWindow || null,
      hidden: panelEl ? getComputedStyle(panelEl).display === 'none' : null,
      nodeRect: rectOf(node),
      panel,
      rail,
      railClasses: railEl ? railEl.className : null,
      railStyle: styleOf(railEl, ['position', 'left', 'right', 'top', 'bottom', 'transform']),
      tabs: rectOf(node.querySelector('.panel-tabs')),
      nodeInlineStyle: { top: node.style.top, left: node.style.left, visibility: node.style.visibility },
      // The tell for the reported symptom, in numbers:
      //  - railCentreInsidePanel: the rail's centre is inside the panel box
      //  - railOverlapPanel: pixels the rail and panel share
      //  - gap: the distance from the rail to the panel's anchor-facing edge
      railCentreInsidePanel: !!(panel && railCentre &&
        railCentre.x > panel.l && railCentre.x < panel.r && railCentre.y > panel.t && railCentre.y < panel.b),
      railOverlapPanel: overlapArea(panel, rail),
      gapFromPanelEdge: rail && panel
        ? { left: rail.l - panel.l, right: panel.r - rail.r, top: rail.t - panel.t, bottom: panel.b - rail.b }
        : null,
    }
  })
}

function panelSnapshots() {
  return [...reporters.values()].map((fn) => {
    try {
      return fn()
    } catch (e) {
      return { error: String(e) }
    }
  })
}

export function collectPanelLayout(reason) {
  return {
    reason,
    at: new Date().toISOString(),
    viewport: {
      w: window.innerWidth,
      h: window.innerHeight,
      dpr: window.devicePixelRatio,
      scrollX: window.scrollX,
      scrollY: window.scrollY,
    },
    dom: domSnapshot(),
    panels: panelSnapshots(),
  }
}

// Called on drag release (and drag start, for a before/after pair).
export function dumpPanelLayout(reason, detail = {}) {
  if (typeof window === 'undefined') return null
  const dump = { ...collectPanelLayout(reason), detail }
  const list = Array.isArray(window.__PANEL_DUMPS__) ? window.__PANEL_DUMPS__ : []
  list.push(dump)
  while (list.length > MAX_DUMPS) list.shift()
  window.__PANEL_DUMPS__ = list
  window.__PANEL_LAST_DRAG__ = dump
  if (window.__PANEL_DEBUG__) {
    console.log('[panels] layout dump', reason, JSON.stringify(dump, null, 1))
  }
  return dump
}

// Two frames: one for Vue's DOM update, one for the coalesced re-measure.
export function dumpPanelLayoutSoon(reason, detail = {}) {
  if (typeof window === 'undefined') return
  requestAnimationFrame(() => requestAnimationFrame(() => dumpPanelLayout(reason, detail)))
}
