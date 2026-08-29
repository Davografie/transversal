<template>
  <div class="etw-root">
    <div class="etw-title">{{ title }}</div>
    <div v-if="current" class="etw-step">
      <div class="etw-step-head">
        <span class="etw-step-count">Target {{ stepIndex + 1 }} / {{ pendingChoices.length }}</span>
        <span class="etw-kind">{{ isStructured ? `element: ${current.element}` : `kind: ${current.kind}` }}<template v-if="!isStructured && current.scope"> · {{ current.scope }}</template></span>
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
          <span v-if="c.subtitle" class="etw-cand-sub">{{ c.subtitle }}</span>
        </button>
        <div v-if="current.count > 1" class="etw-multi-hint">Select up to {{ current.count }}.</div>
      </div>
      <TargetPicker
        v-else
        :model-value="targets[current.index] || ''"
        :kind="current.kind"
        :scope="current.scope || ''"
        :action="current.effect?.action || ''"
        :filter="current.filter || null"
        :entity-id="targetEntityId"
        :placeholder="`Choose ${current.kind}…`"
        allow-random
        @update:model-value="targets[current.index] = $event"
      />
    </div>
    <div v-else class="etw-empty">No targets to resolve.</div>
    <div class="etw-actions">
      <button class="etw-btn" :disabled="stepIndex === 0" @click="back">Back</button>
      <button v-if="!isLast" class="etw-btn etw-primary" :disabled="!hasSelection" @click="next">Next</button>
      <button v-else class="etw-btn etw-primary" :disabled="!hasSelection" @click="apply">Apply</button>
      <button class="etw-btn etw-cancel" @click="$emit('cancel')">Cancel</button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import TargetPicker from './TargetPicker.vue'

const props = defineProps({
  entityId: { type: String, required: true },
  pendingChoices: { type: Array, default: () => [] },
  title: { type: String, default: 'Resolve targets' },
})
const emit = defineEmits(['resolve', 'cancel'])

const stepIndex = ref(0)
const targets = ref({})

const current = computed(() => props.pendingChoices[stepIndex.value] || null)
const isStructured = computed(() => !!current.value?.structured)
const currentTarget = computed(() => (current.value ? targets.value[current.value.index] || '' : ''))
const hasSelection = computed(() => {
  const v = currentTarget.value
  return Array.isArray(v) ? v.length > 0 : !!v
})
const isLast = computed(() => stepIndex.value >= props.pendingChoices.length - 1)

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
  } else {
    targets.value[idx] = c.id
  }
}

function next() { if (!isLast.value) stepIndex.value++ }
function back() { if (stepIndex.value > 0) stepIndex.value-- }
function apply() {
  const resolutions = props.pendingChoices
    .filter((c) => {
      const v = targets.value[c.index]
      return Array.isArray(v) ? v.length > 0 : !!v
    })
    .map((c) => {
      const v = targets.value[c.index]
      // Multi-select fan-out (one effect per chosen candidate) is not wired yet;
      // resolve the first selection for now.
      const target = Array.isArray(v) ? v[0] : v
      return { effect: c.effect, target, field: c.field || 'target', entity_id: c.entity_id }
    })
  emit('resolve', resolutions)
}
</script>

<style scoped>
.etw-root { display: flex; flex-direction: column; gap: 8px; padding: 8px; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); border-radius: 6px; }
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
.etw-candidate { display: flex; flex-direction: column; align-items: flex-start; gap: 1px; text-align: left; padding: 5px 8px; border-radius: 4px; background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); color: var(--text); cursor: pointer; }
.etw-candidate:hover { border-color: var(--accent); }
.etw-candidate.selected { border-color: var(--accent); background: rgba(64,136,212,0.15); }
.etw-cand-name { font-size: 11px; }
.etw-cand-sub { font-size: 9px; color: var(--text-dim); }
.etw-multi-hint { font-size: 9px; color: var(--text-dim); }
.etw-actions { display: flex; gap: 6px; }
.etw-btn { font-size: 10px; padding: 4px 10px; border-radius: 4px; cursor: pointer; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12); color: var(--text); }
.etw-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.etw-primary { background: var(--success); color: #0a0a0f; border-color: transparent; font-weight: 600; }
.etw-cancel { color: var(--text-dim); }
</style>
