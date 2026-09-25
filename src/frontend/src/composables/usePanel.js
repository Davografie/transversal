import { inject, ref } from 'vue'

// Panel navigation context, provided by each gm/Panel.vue instance and
// consumed by the component living inside that panel's slot.
//
//   open(spec)             — push a child panel (parallel: appended as a
//                            sibling; replaces if the same component+id is open)
//   closeChild(key?)       — close a specific child (or the last when omitted)
//   close()                — close this panel (self)
//   replace(spec)          — replace this panel with another spec
//   onChildClose(fn)       — hear a child *close* (not detach); returns an
//                            unsubscribe
export const panelKey = Symbol('gm-panel')

const NOOP_PANEL = {
  open: () => {},
  closeChild: () => {},
  close: () => {},
  replace: () => {},
  onChildClose: () => () => {},
}

export function usePanel() {
  return inject(panelKey, null) || NOOP_PANEL
}

// ── Panel identity registry ───────────────────────────
// Dock-back must find a *live* panel by what it is, not by an instance: a
// floating window remembers its parent as "component + spec id", and a parent
// that was closed and re-opened registers the same identity again — so the
// window can dock back into it. Panels register themselves on mount and
// unregister on unmount (see Panel.vue).

export function panelIdentityKey(component, id) {
  if (!component) return null
  const name = component.__name || component.name || 'component'
  return `${name}:${id ?? ''}`
}

// Plain store + an explicit version ref: the dock affordance is a *render* read,
// so tracking must not depend on reactive-collection subtleties (and handles
// must stay unproxied objects, since they are compared by identity).
const identities = new Map() // key -> [handle]
const identityVersion = ref(0)

function bumpIdentities() {
  identityVersion.value++
}

export function registerPanelIdentity(key, handle) {
  if (!key || !handle) return
  identities.set(key, [...(identities.get(key) || []), handle])
  bumpIdentities()
}

export function unregisterPanelIdentity(key, handle) {
  if (!key || !handle) return
  const list = (identities.get(key) || []).filter((h) => h !== handle)
  if (list.length) identities.set(key, list)
  else identities.delete(key)
  bumpIdentities()
}

// The most recently registered live panel with that identity (last one wins),
// or null — which is what hides the dock affordance.
export function lookupPanelIdentity(key) {
  identityVersion.value // read: callers in render/computeds re-run on changes
  if (!key) return null
  const list = identities.get(key)
  return list && list.length ? list[list.length - 1] : null
}
