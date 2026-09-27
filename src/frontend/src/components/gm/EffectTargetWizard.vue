<template>
  <div class="etw-root" :class="{ 'etw-embedded': embedded }">
    <div class="etw-title">{{ title }}</div>
    <div v-if="current" class="etw-step">
      <div class="etw-step-head">
        <span class="etw-step-count">
          <template v-if="isLoop">Loop · round {{ current.iteration }}</template>
          <template v-else>Target {{ stepIndex + 1 }} / {{ pendingChoices.length }}</template>
        </span>
        <span v-if="!isLoop" class="etw-kind">{{ isStructured ? `element: ${current.element}` : `kind: ${current.kind}` }}<template v-if="!isStructured && current.scope"> · {{ current.scope }}</template></span>
      </div>
      <div v-if="current.sfx_name" class="etw-sfx">
        <div class="etw-sfx-name">{{ current.sfx_name }}</div>
        <div v-if="current.sfx_description" class="etw-sfx-desc">{{ current.sfx_description }}</div>
      </div>
      <div v-if="isStructured" class="etw-candidates">
        <button
          v-for="c in current.candidates"
          :key="c.id"
          type="button"
          class="etw-candidate"
          :class="{ selected: isSelected(c.id) }"
          @click="pick(c)"
        >
          <span class="etw-cand-name">{{ c.name || c.id }}</span>
          <span v-if="c.rating" class="etw-cand-sub etw-cand-rating"><DieIcon :die="c.rating" /></span>
          <span v-else-if="c.subtitle" class="etw-cand-sub">{{ c.subtitle }}</span>
        </button>
        <div v-if="current.count > 1" class="etw-multi-hint">Select up to {{ current.count }}.</div>
      </div>
      <div v-else-if="isLoop" class="etw-loop">
        <div class="etw-loop-q">
          Run <strong>{{ current.sfx_name || current.sfx_id }}</strong> again? This rule caused the
          change it is handling, so it would keep going on its own.
        </div>
        <div class="etw-loop-why">
          You decide each round — nothing more happens until you say so.
        </div>
      </div>
      <TargetPicker
        v-else
        :model-value="targets[current.index] || ''"
        :kind="current.kind"
        :scope="current.scope || ''"
        :action="current.effect?.action || ''"
        :filter="current.filter || null"
        :allow-filters="false"
        :entity-id="targetEntityId"
        :placeholder="`Choose ${current.kind}…`"
        allow-random
        @update:model-value="targets[current.index] = $event"
        @select="onPickerSelect"
      />
    </div>
    <div v-else class="etw-empty">No targets to resolve.</div>
    <div class="etw-actions">
      <Button class="etw-btn" variant="neutral" :disabled="stepIndex === 0" @click="back">Back</Button>
      <template v-if="isLoop">
        <Button class="etw-btn etw-primary" variant="primary" @click="runAgain">Run again</Button>
        <Button class="etw-btn etw-cancel" variant="neutral" @click="declineLoop">Stop here</Button>
      </template>
      <template v-else-if="needsConfirm">
        <Button v-if="!isLast" class="etw-btn etw-primary" variant="primary" :disabled="!hasSelection" @click="next">Next</Button>
        <Button v-else class="etw-btn etw-primary" variant="primary" :disabled="!hasSelection" @click="apply">Apply</Button>
      </template>
      <Button v-if="!isLoop" class="etw-btn etw-cancel" variant="neutral" @click="$emit('cancel')">Cancel</Button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import TargetPicker from '@/components/ui/TargetPicker.vue'
import DieIcon from '../DieIcon.vue'
import Button from '@/components/ui/Button.vue'

const props = defineProps({
  entityId: { type: String, required: true },
  pendingChoices: { type: Array, default: () => [] },
  title: { type: String, default: 'Resolve targets' },
  // Draw the card, or let the host be the container.
  //
  // The roller and the menus are hosts that want the wizard to arrive as an
  // object of its own, so the card is the default. A **sheet panel** is the other
  // case: the panel already *is* the container, and the life path's table sits
  // flat in that same panel — which is why this exists, since a card there reads
  // as a card inside a box. Chrome belongs to the component that draws it, so the
  // choice lives here rather than in each host's scoped styles
  // (`LifePathWizard` carries the same prop for the same reason).
  embedded: { type: Boolean, default: false },
})
const emit = defineEmits(['resolve', 'cancel', 'run-loop'])

const stepIndex = ref(0)
const targets = ref({})

const current = computed(() => props.pendingChoices[stepIndex.value] || null)
const isStructured = computed(() => !!current.value?.structured)
// A loop prompt is a yes/no, not a target: the rule has already run once and
// its own effect brought us back here, so the table decides whether to go on.
const isLoop = computed(() => !!current.value?.loop)
const currentTarget = computed(() => (current.value ? targets.value[current.value.index] || '' : ''))
const hasSelection = computed(() => {
  const v = currentTarget.value
  return Array.isArray(v) ? v.length > 0 : !!v
})
const isLast = computed(() => stepIndex.value >= props.pendingChoices.length - 1)

// Picking a candidate *is* the choice on a single-choice step, so the wizard
// commits and moves on without a separate confirm. Multi-select steps keep the
// explicit Next/Apply — nothing is committed there until the user says so.
const needsConfirm = computed(() => (current.value?.count || 1) > 1)

// Resolve candidates against the effect's own subject entity (e.g. {buying_entity}
// for an opportunity, {hitch_entity} for a GM hitch), falling back to the roller.
const targetEntityId = computed(() => {
  const e = current.value?.effect?.entity
  if (typeof e === 'string' && e.trim() && e !== 'self' && !e.includes('{')) return e.trim()
  return props.entityId
})

watch(() => props.pendingChoices, () => {
  stepIndex.value = 0
  targets.value = {}
})

function isSelected(id) {
  const v = targets.value[current.value?.index]
  return Array.isArray(v) ? v.includes(id) : v === id
}

function pick(c) {
  const idx = current.value.index
  if (current.value.count > 1) {
    const arr = Array.isArray(targets.value[idx]) ? targets.value[idx] : []
    targets.value[idx] = arr.includes(c.id) ? arr.filter((x) => x !== c.id) : [...arr, c.id]
    return
  }
  targets.value[idx] = c.id
  advance()
}

// Dropdown/random picks arrive here too (TargetPicker emits `select`), so the
// same "the pick is the choice" rule holds for every picker in the wizard.
// A clear (`null`) is not a commit — it just empties the step.
function onPickerSelect(opt) {
  if (!opt || !opt.id) return
  targets.value[current.value.index] = opt.id
  if (!needsConfirm.value) advance()
}

function advance() {
  if (isLast.value) apply()
  else stepIndex.value++
}

function next() { if (!isLast.value) stepIndex.value++ }
function back() { if (stepIndex.value > 0) stepIndex.value-- }

// The loop answer travels on its own channel: it is not a target resolution but
// "run this rule one more round for this moment", which the server re-resolves
// from live state — so a round that has become impossible does nothing.
function runAgain() { emit('run-loop', current.value) }

// Declining is not an error, it is the loop ending. Step to any other pending
// choice; if that was the last one, the request is simply over.
function declineLoop() {
  if (isLast.value) emit('cancel')
  else stepIndex.value++
}
function apply() {
  const resolutions = props.pendingChoices
    .filter((c) => {
      const v = targets.value[c.index]
      return Array.isArray(v) ? v.length > 0 : !!v
    })
    .map((c) => {
      const v = targets.value[c.index]
      if (c.structured) {
        // Resumable mid-path choose: send the accumulated answers (echoing the
        // backend's answers_so_far) plus this step's selection.
        const ids = Array.isArray(v) ? v : [v]
        const answers = [...(c.answers_so_far || []), { stepIndex: c.step_index, ids }]
        return {
          effect: c.effect,
          field: c.field || 'target',
          answers,
          sourceKind: c.source_kind || '',
          sourceId: c.source_id || '',
          sourceSfxId: c.source_sfx_id || '',
          continuation: c.continuation || [],
          entity_id: c.entity_id,
        }
      }
      // Multi-select fan-out (one effect per chosen candidate) is not wired yet;
      // resolve the first selection for now.
      const target = Array.isArray(v) ? v[0] : v
      return { effect: c.effect, target, field: c.field || 'target', continuation: c.continuation || [], entity_id: c.entity_id }
    })
  emit('resolve', resolutions)
}
</script>

<style scoped>
.etw-root { display: flex; flex-direction: column; gap: 8px; padding: 8px; background: var(--overlay-2); border: 1px solid var(--overlay-8); border-radius: 6px; }
/* The host is the container: no card, no padding of its own — the flat shape the
   life path's choice table already has inside the very same panel. */
.etw-embedded { padding: 0; background: transparent; border: 0; border-radius: 0; }
.etw-title { font-size: 10px; font-weight: 600; color: var(--accent); text-transform: uppercase; letter-spacing: 0.5px; }
.etw-step { display: flex; flex-direction: column; gap: 4px; }
.etw-step-head { display: flex; justify-content: space-between; align-items: baseline; font-size: 9px; color: var(--text-dim); }
.etw-step-count { font-weight: 600; color: var(--text); }
.etw-kind { font-family: monospace; }
.etw-sfx { display: flex; flex-direction: column; gap: 2px; }
.etw-sfx-name { font-size: 10px; font-weight: 600; color: var(--accent); }
.etw-sfx-desc { font-size: 9px; color: var(--text-dim); }
.etw-empty { font-size: 10px; color: var(--text-dim); }
.etw-candidates { display: flex; flex-direction: column; gap: 4px; max-height: 220px; overflow-y: auto; }
.etw-candidate { display: flex; flex-direction: column; align-items: flex-start; gap: 1px; text-align: left; padding: 5px 8px; border-radius: 4px; background: var(--overlay-4); border: 1px solid var(--overlay-10); color: var(--text); cursor: pointer; }
.etw-candidate:hover { border-color: var(--accent); }
.etw-candidate.selected { border-color: var(--accent); background: var(--accent-16); }
.etw-cand-name { font-size: 11px; }
.etw-cand-sub { font-size: 9px; color: var(--text-dim); }
.etw-cand-rating :deep(.die-icon) { width: 18px; height: 20px; }
.etw-multi-hint { font-size: 9px; color: var(--text-dim); }
.etw-actions { display: flex; gap: 6px; }
</style>
