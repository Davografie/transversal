// TEMPORARY drag-smoothness profiler.
//
// Samples requestAnimationFrame deltas during an occupant drag and logs one
// summary line at drag end. It answers "is the background keeping up with the
// pointer?" — mean/min/1%low fps, frame-time percentiles, dropped-frame count,
// pointer→paint lag, and the JS+render work per frame.
//
// Toggle off with FRAME_PROFILE=false, or delete this file and its call sites
// in LocationViewer.vue once we've measured.

export const FRAME_PROFILE = false

let _running = false
let _rafId = null
let _lastTs = 0
let _deltas = []
let _lags = []
let _work = []
let _lastPointerTs = 0
let _label = ''

function _tick(ts) {
  if (!_running) return
  _deltas.push(ts - _lastTs)
  if (_lastPointerTs) _lags.push(ts - _lastPointerTs)
  _lastTs = ts
  _rafId = requestAnimationFrame(_tick)
}

export function startFrameProfile(label = 'drag') {
  if (!FRAME_PROFILE || _running) return
  _running = true
  _label = label
  _deltas = []
  _lags = []
  _work = []
  _lastPointerTs = 0
  _lastTs = performance.now()
  _rafId = requestAnimationFrame(_tick)
}

// Call on every mousemove during an active drag so we can measure how long the
// visual lags behind the pointer (event time → next painted frame).
export function notePointerEvent() {
  if (FRAME_PROFILE && _running) _lastPointerTs = performance.now()
}

// Call once per applied frame with the JS+DOM work duration (handler + Vue
// render flush). Splits "our code is slow" from "paint/composite is slow".
export function noteFrameWork(ms) {
  if (FRAME_PROFILE && _running) _work.push(ms)
}

export function stopFrameProfile() {
  if (!FRAME_PROFILE) return
  _running = false
  if (_rafId) cancelAnimationFrame(_rafId)
  _rafId = null

  const d = _deltas.slice(1) // drop the first (partial) frame after start
  if (d.length < 3) return

  const sorted = [...d].sort((a, b) => a - b)
  const n = sorted.length
  const mean = d.reduce((a, b) => a + b, 0) / n
  const p95 = sorted[Math.min(n - 1, Math.floor(0.95 * n))]
  const slow = sorted[Math.min(n - 1, Math.floor(0.99 * n))] // 1% slowest frame
  const max = sorted[n - 1]
  const fps = (ms) => (1000 / ms).toFixed(0)
  const dropped = d.filter((x) => x > 16.7).length

  let lag = ''
  if (_lags.length) {
    const ls = [..._lags].sort((a, b) => a - b)
    lag = ` paintlag=${ls[Math.min(ls.length - 1, Math.floor(0.95 * ls.length))].toFixed(1)}/${ls[ls.length - 1].toFixed(1)}ms`
  }

  let work = ''
  if (_work.length) {
    const w = _work.sort((a, b) => a - b)
    work = ` work=${(w.reduce((a, b) => a + b, 0) / w.length).toFixed(1)}/${w[w.length - 1].toFixed(1)}ms`
  }

  console.log(
    `[frameprofile] ${_label} fps=${fps(mean)}/${fps(max)}/${fps(slow)} ` +
    `frame=${mean.toFixed(1)}/${p95.toFixed(1)}/${max.toFixed(1)}ms ` +
    `dropped=${dropped}/${n}${work}${lag}`
  )
}
