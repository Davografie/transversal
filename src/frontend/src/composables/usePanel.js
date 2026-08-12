import { inject } from 'vue'

// Panel navigation context, provided by each gm/Panel.vue instance and
// consumed by the component living inside that panel's slot.
//
//   open(spec)     — push a child panel
//   closeChild()   — pop the current child panel (root/manager panels)
//   close()        — close this panel (self)
//   replace(spec)  — replace this panel with another spec
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
