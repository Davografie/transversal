<template>
  <div class="etw-root">
    <div class="etw-title">{{ title }}</div>
    <div v-if="current" class="etw-step">
      <div class="etw-step-head">
        <span class="etw-step-count">Target {{ stepIndex + 1 }} / {{ pendingChoices.length }}</span>
        <span class="etw-kind">kind: {{ current.kind }}<template v-if="current.scope"> · {{ current.scope }}</template></span>
      </div>
      <div v-if="current.sfx_name" class="etw-sfx">
        <div class="etw-sfx-name">{{ current.sfx_name }}</div>
        <div v-if="current.sfx_description" class="etw-sfx-desc">{{ current.sfx_description }}</div>
      </div>
      <ScopedTargetPicker
        :model-value="targets[current.index] || ''"
        :kind="current.kind"
        :scope="current.scope || ''"
        :action="current.effect?.action || ''"
        :filter="current.filter || null"
        :entity-id="targetEntityId"
        :placeholder="`Choose ${current.kind}…`"
        @update:model-value="targets[current.index] = $event"
      />
    </div>
    <div v-else class="etw-empty">No targets to resolve.</div>
    <div class="etw-actions">
      <button class="etw-btn" :disabled="stepIndex === 0" @click="back">Back</button>
      <button v-if="!isLast" class="etw-btn etw-primary" :disabled="!currentTarget" @click="next">Next</button>
      <button v-else class="etw-btn etw-primary" :disabled="!currentTarget" @click="apply">Apply</button>
      <button class="etw-btn etw-cancel" @click="$emit('cancel')">Cancel</button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import ScopedTargetPicker from './ScopedTargetPicker.vue'

const props = defineProps({
  entityId: { type: String, required: true },
  pendingChoices: { type: Array, default: () => [] },
  title: { type: String, default: 'Resolve targets' },
})
const emit = defineEmits(['resolve', 'cancel'])

const stepIndex = ref(0)
const targets = ref({})

const current = computed(() => props.pendingChoices[stepIndex.value] || null)
const currentTarget = computed(() => (current.value ? targets.value[current.value.index] || '' : ''))
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

function next() { if (!isLast.value) stepIndex.value++ }
function back() { if (stepIndex.value > 0) stepIndex.value-- }
function apply() {
  const resolutions = props.pendingChoices
    .filter((c) => targets.value[c.index])
    .map((c) => ({ effect: c.effect, target: targets.value[c.index], field: c.field || 'target' }))
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
.etw-actions { display: flex; gap: 6px; }
.etw-btn { font-size: 10px; padding: 4px 10px; border-radius: 4px; cursor: pointer; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12); color: var(--text); }
.etw-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.etw-primary { background: var(--success); color: #0a0a0f; border-color: transparent; font-weight: 600; }
.etw-cancel { color: var(--text-dim); }
</style>
