// Timestamped load-path logging.
//
// Every load phase logs one line: `[perf] +1234.5ms 09:15:22.123 label detail`.
// The `+ms` value is relative to page load, so per-phase durations and the total
// time-to-ready can be derived straight from a console copy/paste.
const _t0 = performance.now()

function _stamp() {
  const d = new Date()
  const p = (n) => String(n).padStart(2, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}.${String(d.getMilliseconds()).padStart(3, '0')}`
}

export function perfMark(label, detail) {
  const elapsed = (performance.now() - _t0).toFixed(1)
  let d = ''
  if (detail !== undefined && detail !== null) {
    d = typeof detail === 'object' ? JSON.stringify(detail) : String(detail)
  }
  console.log(`[perf] +${elapsed}ms ${_stamp()} ${label}${d ? ' ' + d : ''}`)
}
