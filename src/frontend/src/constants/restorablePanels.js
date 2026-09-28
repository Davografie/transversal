// The floating GM windows a reload may bring back ([[GM Panel Development]]).
//
// A window's spec is `{ component, title, id, props, listeners, context, badge }`.
// The component is a Vue object and `listeners` / `context` are closures and live
// instances, so a spec cannot be serialized — a window is stored as a **registry
// name + props + geometry** and rebuilt from this map on load. That is why the
// set below is an explicit allow-list rather than "every panel": a restored
// window has no `listeners` (so the opener's reactions — a gallery refresh, a
// tree re-read — do not fire) and no `context` (so a panel that edits a draft
// handed to it would silently edit nothing).
//
// A panel belongs here only when its whole spec is props. Two tests decide it:
//   1. its openers pass plain data (`{ entityId }`, `{ tableId, index }`, `{ lp }`),
//      which `panelWindowPersistence.js` re-checks at save time anyway; and
//   2. it injects nothing that must come from a spec `context`.
//
// Kept out for (2), with the reason each time:
//   GmDisplayNameEditPanel  — injects `displayNamesDraft`; without it it falls
//                             back to the frozen prop and the stale-list bug
//                             returns.
//   GmEffectEditPanel       — injects `sfxEdit`; its fallback is a *private*
//                             draft, so edits would go nowhere visible.
//   GmProjectionEditPanel   — injects `entityEditor`; its fallback is the shared
//                             instance, so the opening panel's list would not move.
//   GmPathEditPanel         — injects `pathBinding`, which is the edit itself.
//   GmRollTableEntryEffectPanel — injects `rowDraft`; without it save is a no-op.
//   GmEntityCreatePanel     — a create form: restoring it would offer to create
//                             the same entity again after a reload.
//
// The panels here *do* inject, but only from App or with a default that is the
// whole answer: `gmCurrentLocationId` / `actingEntityId` / `panelActive` /
// `characterSheetSpec` / `goToLocation` (App), `traitsetFilter` (a search
// convenience, null = unscoped). Those survive a restore because restore does not
// change where the panel is mounted.
import GmEntityEditPanel from '@/components/gm/GmEntityEditPanel.vue'
import GmTraitEditPanel from '@/components/gm/GmTraitEditPanel.vue'
import GmTraitsetDetail from '@/components/gm/GmTraitsetDetail.vue'
import GmSfxEditPanel from '@/components/gm/GmSfxEditPanel.vue'
import GmRollTableDetailPanel from '@/components/gm/GmRollTableDetailPanel.vue'
import GmRollTableEditPanel from '@/components/gm/GmRollTableEditPanel.vue'
import GmRollTableEntryEditPanel from '@/components/gm/GmRollTableEntryEditPanel.vue'
import GmLifePathDetailPanel from '@/components/gm/GmLifePathDetailPanel.vue'
import GmPortalConfigPanel from '@/components/gm/GmPortalConfigPanel.vue'
import ImageViewer from '@/components/gm/ImageViewer.vue'

export const RESTORABLE_PANELS = {
  GmEntityEditPanel,
  GmTraitEditPanel,
  GmTraitsetDetail,
  GmSfxEditPanel,
  GmRollTableDetailPanel,
  GmRollTableEditPanel,
  GmRollTableEntryEditPanel,
  GmLifePathDetailPanel,
  GmPortalConfigPanel,
  ImageViewer,
}

// Matched by **component identity**, falling back to the compiled `__name`.
//
// Identity alone is not enough, and this is not theoretical: the Vite dev server
// serves a module it has invalidated (HMR) under `<path>?t=<stamp>`, so the same
// SFC can exist as two different objects — the one the opener passed and the one
// this registry holds. Identity then silently misses and *nothing* persists,
// which is exactly how the first cut of this failed at `:3000`
// (`usePanelWindows.js?t=…` in the page's resource list). `__name` is the SFC
// filename and survives that. `panelIdentityKey` already relies on it for
// dock-back, so it is a dependency this surface already has, not a new one.
export function restorableNameOf(component) {
  if (!component) return null
  for (const [name, c] of Object.entries(RESTORABLE_PANELS)) {
    if (c === component) return name
  }
  const byName = component.__name || component.name
  return byName && byName in RESTORABLE_PANELS ? byName : null
}

export function restorableComponent(name) {
  return RESTORABLE_PANELS[name] || null
}
