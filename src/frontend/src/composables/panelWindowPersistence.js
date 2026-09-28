// Serializing floating GM windows to client storage, and back.
//
// The rules are the part that can be wrong, so they are plain functions the check
// script runs directly rather than a restatement of them. They use Vue's public
// `isRef`/`isReactive`/`toRaw` predicates and nothing else.
//
// What a window is *not* allowed to carry into storage is the interesting part.
// A spec's `component` is a Vue object, `listeners` are closures and `context`
// holds refs and instances — none survives `JSON.stringify` in a usable form. So
// props are **checked**, and a window whose props cannot be stored is not
// persisted at all rather than persisted into something that would restore wrong.
import { isRef, isReactive, isReadonly, toRaw } from 'vue'

export const WINDOW_STORAGE_KEY = 'gmPanelWindows'

function isStorableValue(v) {
  if (v === null) return true
  const t = typeof v
  if (t === 'string' || t === 'number' || t === 'boolean' || t === 'undefined') return true
  if (t === 'function' || t === 'symbol' || t === 'bigint') return false
  if (t !== 'object') return false
  // A **ref is a live handle**: it serializes to its internals, and a restored
  // plain value would not be the ref the panel expects. Refuse it.
  if (isRef(v)) return false
  // A reactive/readonly proxy is only *decorated* — snapshot the raw object, which
  // is what `JSON.stringify` writes anyway. Refusing these made a panel
  // unrestorable for no good reason: the SFX editor is opened with a record taken
  // straight out of the shared store, so its props are proxies by construction.
  if (isReactive(v) || isReadonly(v)) return isStorableValue(toRaw(v))
  // A DOM node, a component definition, a class instance — only plain objects and
  // arrays are safe. (Arrays are checked before the prototype test.)
  if (Array.isArray(v)) return v.every(isStorableValue)
  const proto = Object.getPrototypeOf(v)
  if (proto !== Object.prototype && proto !== null) return false
  return Object.values(v).every(isStorableValue)
}

export function propsAreStorable(props) {
  if (props == null) return true
  return isStorableValue(props)
}

/**
 * One window → the record written to storage, or `null` when it must not be
 * persisted: an unregistered component (see `constants/restorablePanels.js`) or
 * props that would not survive the round trip.
 */
export function serializeWindow(w, nameOf) {
  const name = nameOf?.(w?.spec?.component)
  if (!name) return null
  if (!propsAreStorable(w.spec?.props)) return null
  return {
    name,
    title: w.spec.title ?? '',
    specId: w.spec.id ?? null,
    badge: w.spec.badge ?? null,
    props: w.spec.props ?? {},
    x: w.x ?? null,
    y: w.y ?? null,
    direction: w.direction ?? 'left',
    collapsed: !!w.collapsed,
    dock: w.dock ?? 'right',
    sourceParentKey: w.sourceParentKey ?? null,
    z: w.z ?? 0,
  }
}

export function serializeWindows(windows, nameOf) {
  const out = []
  for (const w of Array.isArray(windows) ? windows : []) {
    const rec = serializeWindow(w, nameOf)
    if (rec) out.push(rec)
  }
  return out
}

/**
 * Stored records → window objects. `lookup(name)` supplies the component; a name
 * that no longer resolves (the panel was renamed or dropped from the registry) is
 * **dropped**, which is also how a stale entry prunes itself on the next save.
 *
 * `id` is deliberately not restored: it is a per-session handle (`gm-win-N`) that
 * nothing outside the registry refers to, so the caller assigns fresh ones.
 */
export function deserializeWindows(records, lookup) {
  const out = []
  for (const rec of Array.isArray(records) ? records : []) {
    const component = lookup?.(rec?.name)
    if (!component) continue
    out.push({
      spec: {
        component,
        title: rec.title ?? '',
        id: rec.specId ?? null,
        badge: rec.badge ?? null,
        props: rec.props && typeof rec.props === 'object' ? rec.props : {},
        // `listeners` and `context` are absent by construction — see this file's
        // header. A restored window has no host reactions.
      },
      dock: rec.dock ?? 'right',
      collapsed: !!rec.collapsed,
      x: rec.x ?? null,
      y: rec.y ?? null,
      direction: rec.direction ?? 'left',
      sourceParentKey: rec.sourceParentKey ?? null,
      z: rec.z ?? 0,
    })
  }
  return out
}
