<template>
  <div class="pf-root">
    <span class="pf-label">{{ title }}</span>
    <span v-if="stepCount" class="pf-count">{{ stepCount }} {{ stepCount === 1 ? 'step' : 'steps' }}</span>
    <span class="pf-summary" :class="{ 'pf-summary-none': !stepCount }">{{ summary }}</span>
    <Button class="pf-open" variant="secondary" size="sm" @click="open">
      {{ stepCount ? 'Edit path' : 'Build path' }}
    </Button>
    <Button
      v-if="stepCount"
      class="pf-clear"
      variant="danger-ghost"
      size="sm"
      title="Clear this path"
      @click="clear"
    >✕</Button>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { usePanel } from '@/composables/usePanel.js'
import Button from '@/components/ui/Button.vue'
import GmPathEditPanel from './GmPathEditPanel.vue'

// One targeting path, shown as a single line with an affordance to edit it.
//
// The builder itself is tall — every step is a row of controls — and a condition
// or an effect can carry one, which made the SFX/effect panels scroll for
// screenfuls. The path is therefore edited in a **child panel** (the author's
// ask, 2026-09-26): the parent keeps a compact, honest summary of the same path,
// and the panel gives the path the whole surface while it is being built.
const props = defineProps({
  modelValue: { type: Object, default: () => ({ steps: [] }) },
  destination: { type: Object, default: null },
  sourceElement: { type: String, default: '' },
  variables: { type: Object, default: null },
  title: { type: String, default: 'Targeting path' },
  booleanTerminal: { type: Boolean, default: false },
})

// `resolve` is forwarded from the builder inside the child panel: an effect that
// means different things at different destinations reads it (a rating die can be
// timed, a pool die cannot), so it must keep arriving after the move.
const emit = defineEmits(['update:modelValue', 'resolve'])

const panel = usePanel()

const steps = computed(() =>
  (props.modelValue && Array.isArray(props.modelValue.steps) ? props.modelValue.steps : []))
const stepCount = computed(() => steps.value.length)

// Handed to the child panel through the spec's `context` (see `GmPathEditPanel`).
const pathBinding = {
  get: () => props.modelValue || { steps: [] },
  set: (v) => emit('update:modelValue', v),
}

function open() {
  panel.open({
    component: GmPathEditPanel,
    title: props.title,
    context: { pathBinding },
    props: {
      destination: props.destination,
      sourceElement: props.sourceElement,
      variables: props.variables,
      title: props.title,
      booleanTerminal: props.booleanTerminal,
    },
    listeners: { resolve: (element) => emit('resolve', element) },
  })
}

function clear() {
  emit('update:modelValue', { steps: [] })
}

function valueText(v) {
  if (Array.isArray(v)) return v.join(', ')
  if (v === '' || v == null) return '…'
  return String(v)
}

/** A step in its own words. Deliberately catalog-free: this is one line at rest,
 *  and the full, properly-labelled phrasing is what the rendered card is for.
 *  The kinds and the fields are enough to recognise which path this is. */
function stepText(s) {
  if (!s || !s.kind) return '?'
  switch (s.kind) {
    case 'select':
      return `select ${s.collection || '…'}${s.collection === 'variable' && s.variable ? ` ${s.variable}` : ''}`
    case 'filter':
      return `filter ${s.field || '…'} ${s.operator || ''} ${valueText(s.value)}`.trim()
    case 'navigate':
      return `navigate ${s.edge || '…'}`
    case 'aggregate':
      return `aggregate ${s.fn || '…'}${s.field ? ` ${s.field}` : ''}`
    case 'choose':
      return `choose ${s.count || 1}`
    case 'evaluate':
      return `evaluate ${s.field || ''} ${s.operator || ''} ${valueText(s.value)}`.trim()
    default:
      return s.kind
  }
}

const summary = computed(() =>
  stepCount.value ? steps.value.map(stepText).join(' → ') : 'no path')
</script>

<style scoped>
.pf-root {
  display: flex; align-items: center; gap: 6px;
  font-size: 10px; padding: 4px 6px; min-width: 0;
  background: var(--overlay-4); border: 1px solid var(--overlay-10); border-radius: 4px;
}
.pf-label { flex: none; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; font-size: 9px; }
.pf-count { flex: none; font-family: monospace; font-size: 9px; color: var(--accent); }
/* The one long thing: ellipsised rather than wrapped, so a deep path cannot make
   the row tall again — which is the whole point of the summary. */
.pf-summary {
  flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  font-family: monospace; color: var(--text);
}
.pf-summary-none { color: var(--text-dim); font-style: italic; }
.pf-open, .pf-clear { flex: none; }
</style>
