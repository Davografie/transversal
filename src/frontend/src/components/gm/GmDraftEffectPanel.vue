<template>
  <div class="reep-root">
    <EffectForm
      :value="editingEffect"
      :universe="universe"
      :life-path="lifePath"
      :output-variables="outputVariables"
      :scope-variables="scopeVariables || {}"
      :portal-destination="portalDestination"
      :portal-target-type="portalTargetType"
      :portal-universe="portalUniverse"
      :portal-root-id="portalRootId"
      @save="onSave"
    />
  </div>
</template>

<script setup>
import { computed, inject, ref, watch } from 'vue'
import EffectForm from './EffectForm.vue'
import { useTargetCatalog } from '@/composables/useTargetCatalog.js'

// **One effect of a list**, edited in a child panel — the same shape the SFX editor
// uses for `GmEffectEditPanel`, and the reason it is a panel rather than an inline
// form: an effect is a stacked builder of unbounded height, and the list has to stay
// in view while one is edited.
//
// It is deliberately **draft-agnostic**: it reads `effects` off whatever object the
// opener hands it in `rowDraft` and writes back to the same one. Two lists use it
// today — a roll-table row's effects and a life-path step's — and it persists
// nothing itself: the panel that owns the draft is the commit point, and its
// `universe` / `lifePath` scope the targeting wizard. (It was named
// `GmRollTableEntryEffectPanel` until the second consumer arrived; a shared
// component named after one of them is a lie the next reader has to unlearn.)
//
// It is separate from `GmEffectEditPanel` because the drafts differ: that one edits
// the SFX composer's shared `sfxEdit` draft and persists on save.
const props = defineProps({
  // Identity only (Rule 6): which effect of the row to edit, or null to add. The
  // effects themselves live in the row draft, handed across in the spec context.
  index: { type: Number, default: null },
  universe: { type: String, default: '' },
  lifePath: { type: String, default: '' },
  // A portal's effects are the third consumer of this panel, and they need the
  // destination in scope so the form can offer portal-relative targets — the same
  // four props `EffectEditor` used to forward when that list was edited inline.
  // Empty for the other two consumers, which is exactly the old behaviour.
  portalDestination: { type: String, default: '' },
  portalTargetType: { type: String, default: '' },
  portalUniverse: { type: String, default: '' },
  portalRootId: { type: String, default: '' },
})

// A panel cannot `provide` to its own child panels (they are rendered by
// `Panel.vue`, as siblings of the slot outlet), so the row draft arrives through
// the spec's `context`.
const draft = inject('rowDraft', null)
// The row's resolved scope, taken when this panel opened: the table's names plus
// the row's own declarations ([[B281]]). Passed as a snapshot because the entry
// panel is what edits the declarations, so they cannot change while this is open.
const scopeVariables = inject('scopeVariables', null)

const editingEffect = computed(() => (props.index === null ? null : (draft?.effects?.[props.index] || null)))

const { collectVariables } = useTargetCatalog()

// Typed names this effect may reference: the output variables of every effect
// *before* it in the row, plus whatever the enclosing scope already holds — the
// table's bound variables and this row's ([[B281]]). The engine walks the list in
// order, so a later effect can name an earlier one's output.
const outputVariables = ref({})

function priorEffects() {
  const effects = draft?.effects || []
  const limit = props.index === null ? effects.length : props.index
  return effects.slice(0, limit)
}

watch(
  () => [draft?.effects, props.index],
  async () => {
    outputVariables.value = await collectVariables(priorEffects())
  },
  { immediate: true, deep: true },
)

// Write-through: the form emits on every change, so the *first* emit of an add
// appends the row and every later one replaces it. Local, because `props.index`
// cannot change under us — and is null for an add.
let workingIndex = props.index

function onSave(eff) {
  if (!draft) return
  if (workingIndex === null) {
    draft.effects = [...draft.effects, eff]
    workingIndex = draft.effects.length - 1
  } else {
    const next = [...draft.effects]
    next[workingIndex] = eff
    draft.effects = next
  }
  // Nothing is persisted, and nothing closes, on purpose: the panel that owns the
  // draft is the commit point (its auto-save), and the rail is what closes this one.
}
</script>

<style scoped>
.reep-root {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
</style>
