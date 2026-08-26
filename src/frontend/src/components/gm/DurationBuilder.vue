<template>
  <div class="db-root">
    <div v-for="(t, i) in timers" :key="i" class="db-row">
      <select v-model="t.event" class="db-event">
        <option value="scene">Scene</option>
        <option value="beat">Beat</option>
        <option value="session">Session</option>
        <option value="location_changed">Location changed</option>
        <option value="trait_updated">Trait updated</option>
      </select>
      <input v-model.number="t.remaining" type="number" min="0" placeholder="count" class="db-count" />
      <button class="db-del" @click="removeTimer(i)" title="Remove">✕</button>
    </div>
    <button class="db-add" @click="addTimer">+ Add timer</button>

    <div class="db-combine">
      <label>Expire when</label>
      <select v-model="combine">
        <option value="FIRST_TO_FIRE">first timer fires</option>
        <option value="ALL_TRANSPIRED">all timers transpire</option>
      </select>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  modelValue: { type: Object, default: () => ({ timers: [], combine: 'FIRST_TO_FIRE' }) },
})
const emit = defineEmits(['update:modelValue'])

const timers = computed({
  get: () => props.modelValue?.timers || [],
  set: (v) => emit('update:modelValue', { ...props.modelValue, timers: v }),
})

const combine = computed({
  get: () => props.modelValue?.combine || 'FIRST_TO_FIRE',
  set: (v) => emit('update:modelValue', { ...props.modelValue, combine: v }),
})

function addTimer() {
  const next = [...timers.value, { event: 'scene', remaining: 1 }]
  timers.value = next
}

function removeTimer(i) {
  const next = [...timers.value]
  next.splice(i, 1)
  timers.value = next
}
</script>

<style scoped>
.db-root { display: flex; flex-direction: column; gap: 4px; }
.db-row { display: flex; gap: 4px; align-items: center; }
.db-event, .db-count {
  font-size: 11px; padding: 4px 6px;
  background: rgba(255,255,255,0.06); color: var(--text);
  border: 1px solid rgba(255,255,255,0.1); border-radius: 4px;
  font-family: inherit; box-sizing: border-box;
}
.db-event { flex: 2; }
.db-count { flex: 1; min-width: 0; }
.db-del { background: none; border: none; color: var(--danger); cursor: pointer; font-size: 12px; }
.db-add { font-size: 10px; padding: 3px 8px; background: rgba(255,255,255,0.04); border: 1px dashed rgba(255,255,255,0.15); border-radius: 4px; color: var(--text-dim); cursor: pointer; }
.db-add:hover { color: var(--text); }
.db-combine { display: flex; align-items: center; gap: 6px; }
.db-combine label { font-size: 9px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; }
.db-combine select { font-size: 11px; padding: 4px 6px; background: rgba(255,255,255,0.06); color: var(--text); border: 1px solid rgba(255,255,255,0.1); border-radius: 4px; font-family: inherit; }
</style>
