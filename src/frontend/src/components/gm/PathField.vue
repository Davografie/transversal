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
import { computed, onMounted, ref, watch } from 'vue'
import { usePanel } from '@/composables/usePanel.js'
import { useTargetCatalog } from '@/composables/useTargetCatalog.js'
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
  // Forwarded to the builder: a reach path has no source, so `select source` must
  // not be offered there ([[Dynamic SFX Reach]]). Default true — every other host
  // is an effect or a condition, where the source is real.
  allowSource: { type: Boolean, default: true },
  // The identity of this path's child panel. **Two paths must not share it**, or
  // opening the second replaces the first: `Panel.openChild` reuses the panel it
  // finds for the same component and no id, so the first path vanished instead of
  // staying open as a collapsed child, and its half-built steps showed under the
  // second path's title (the author's report, 2026-10-17). Defaults to a
  // per-instance id, which is correct for every host that renders one PathField
  // per field; a host that *reuses* one instance for different fields passes the
  // field's name here.
  panelId: { type: String, default: '' },
})

//: Falls back to an id unique to this component instance, so two path fields are
//: two children by construction rather than by each host remembering to say so.
let pathFieldSeq = 0
const instanceId = `path-${++pathFieldSeq}`

// `resolve` says which element the path lands on — an effect that means different
// things at different destinations reads it (a rating die can be timed, a pool die
// cannot). This row traces it, and the builder inside the child panel forwards its
// own after an edit, so it keeps arriving after the move.
const emit = defineEmits(['update:modelValue', 'resolve'])

// The element a path lands on is resolvable **here**, from the steps this row is
// already summarising — it must not wait for the child panel to be opened. Reading
// it only from the builder left the parent guessing until someone pressed *Edit
// path*, and a guess of "we don't know" reads as "not applicable": an effect with a
// stored duration showed the *leftover* explanation and, on save, dropped a timer the
// form could not see (`EffectForm` emits a duration only where it is offered).
// Same trace the builder runs, so the two cannot disagree.
const { traceSpec } = useTargetCatalog()

const panel = usePanel()

const steps = computed(() =>
  (props.modelValue && Array.isArray(props.modelValue.steps) ? props.modelValue.steps : []))

const trace = ref({ types: [], errors: [], valid: false })
let traceTimer = null

const stepCount = computed(() => steps.value.length)

async function runTrace() {
  const res = await traceSpec(steps.value, props.destination, props.sourceElement || null, props.variables || null)
  if (res) trace.value = res
}

function scheduleTrace() {
  if (traceTimer) clearTimeout(traceTimer)
  traceTimer = setTimeout(runTrace, 150)
}

watch(trace, (t) => {
  const last = t?.types?.[t.types.length - 1]
  emit('resolve', last?.element || '')
})

// On mount rather than debounced, so the destination is known before anything can
// act on it; later edits arrive through the child panel and are debounced like the
// builder's own.
onMounted(runTrace)
watch(steps, scheduleTrace, { deep: true })
watch(() => [props.destination, props.sourceElement, props.variables], () => scheduleTrace(), { deep: true })

// Handed to the child panel through the spec's `context` (see `GmPathEditPanel`).
const pathBinding = {
  get: () => props.modelValue || { steps: [] },
  set: (v) => emit('update:modelValue', v),
}

function open() {
  panel.open({
    // The path's own identity, so this panel is *this* path's. Without it every
    // path in the editor collided on one child (see the `panelId` prop).
    id: props.panelId || instanceId,
    component: GmPathEditPanel,
    title: props.title,
    context: { pathBinding },
    props: {
      destination: props.destination,
      sourceElement: props.sourceElement,
      variables: props.variables,
      title: props.title,
      booleanTerminal: props.booleanTerminal,
      allowSource: props.allowSource,
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
      // `null` is "as many as they like", so it must not read as the falsy 1.
      return s.count == null ? 'choose any' : `choose ${s.count}`
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
