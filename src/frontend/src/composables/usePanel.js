import { inject } from 'vue'

// Panel navigation context, provided by each gm/Panel.vue instance and
// consumed by the component living inside that panel's slot.
//
//   open(spec, opts?)       — push a child panel; `opts.sibling` appends a
//                            sibling, otherwise the current children are replaced
//   closeChild(key?)        — close a specific child (or the last when omitted)
//   close()                 — close this panel (self)
//   replace(spec)           — replace this panel with another spec
export const panelKey = Symbol('gm-panel')

const NOOP_PANEL = {
  open: () => {},
  closeChild: () => {},
  close: () => {},
  replace: () => {},
}

export function usePanel() {
  return inject(panelKey, null) || NOOP_PANEL
}
