import { ref } from 'vue'

// Drag-to-anchor: which panel a *dragged* floating window would land in, and the
// registered way to insert into it.
//
// The registry is a `WeakMap` keyed by the panel's own DOM node rather than by an
// id or an identity key, for two reasons. A `WeakMap` needs no unregister — the
// node going away is the cleanup — and it makes **every** panel a legal target,
// including the GM panel's chain root, which has no `spec.id` and so is invisible
// to the identity registry that dock-back (⤓) uses. Hit-testing a pointer then
// costs one `querySelectorAll` and a rect each, with no state to keep in sync.
const handles = new WeakMap()

// The node currently under the drag, for the drop affordance. Module-level: the
// dragged window writes it and every candidate panel renders from it, which is
// the only reason a highlight needs no prop drilling across units.
export const dropTargetEl = ref(null)

export function registerDropTarget(el, openChild) {
  if (el && openChild) handles.set(el, openChild)
}

// Insert `spec` as a child of the panel at `el`. False when nothing is registered
// there, so a caller can fall back to leaving the window floating.
export function openChildAt(el, spec) {
  const open = el ? handles.get(el) : null
  if (!open) return false
  open(spec)
  return true
}

// The panel under (x, y) — or null. **The unit on top wins**, because units
// genuinely overlap (a detached window parks exactly on the box its panel
// occupied); within one unit the *smallest* panel wins, so a child panel is
// preferred to the chain root that contains it.
//
// `excludeUnit` is the unit being dragged: a window must not be able to target
// itself, or letting go over its own panel would swallow it.
export function targetAt(x, y, excludeUnit) {
  if (typeof document === 'undefined') return null
  let best = null
  for (const el of document.querySelectorAll('.panel-node')) {
    if (!handles.has(el)) continue
    const unit = el.closest?.('[data-panel-unit]')
    if (excludeUnit && unit?.dataset?.panelUnit === excludeUnit) continue
    const r = el.getBoundingClientRect()
    if (x < r.left || x > r.right || y < r.top || y > r.bottom) continue
    const z = Number(unit?.style?.zIndex) || 0
    const area = r.width * r.height
    if (!best || z > best.z || (z === best.z && area < best.area)) {
      best = { el, z, area }
    }
  }
  return best ? best.el : null
}
