<template>
  <div class="lora-root">
    <p class="lora-hint">Select which LoRAs apply to each entity type during image generation in this universe.</p>
    <div v-if="!availableLoras.length" class="lora-empty">No LoRAs available — check imagEN LoRA server.</div>
    <div v-for="et in entityTypes" :key="et" class="lora-type-row">
      <span class="lora-type-label">{{ et }}</span>
      <div class="lora-selects">
        <select class="lora-select" :value="loraAt(et, 0)" @change="setLora(et, 0, $event.target.value)">
          <option value="">—</option>
          <option v-for="lora in availableLoras" :key="lora.name" :value="lora.name">{{ lora.name }}</option>
        </select>
        <select class="lora-select" :value="loraAt(et, 1)" @change="setLora(et, 1, $event.target.value)">
          <option value="">—</option>
          <option v-for="lora in availableLoras" :key="lora.name" :value="lora.name">{{ lora.name }}</option>
        </select>
      </div>
    </div>

    <div class="steering-block">
      <label class="steering-label" for="prompt-steering">Prompt steering — one sentence</label>
      <textarea
        id="prompt-steering"
        class="steering-input"
        rows="2"
        :value="promptSteering"
        placeholder="e.g. shot on a 35mm lens, natural window light, documentary realism"
        @input="onSteeringInput"
      />
      <p class="steering-hint">Appended to every prompt generated in this universe — use it to steer style, lighting, or realism.</p>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import { ENTITY_TYPES } from '@/constants/entityTypes.js'

const props = defineProps({
  loraConfigJson: { type: String, default: '{}' },
  promptSteering: { type: String, default: '' },
})

const emit = defineEmits(['update:loraConfig', 'update:promptSteering'])

function onSteeringInput(e) {
  emit('update:promptSteering', e.target.value)
}

// Universes don't generate images, so they have no LoRA slots.
const entityTypes = ENTITY_TYPES.filter(t => t !== 'UNIVERSE')
const availableLoras = ref([])
const loraConfig = ref({})

async function fetchLoras() {
  try {
    const r = await fetch('/api/v1/imagen/loras')
    if (r.ok) {
      const d = await r.json()
      availableLoras.value = (d.loras || []).map(l => typeof l === 'string' ? { name: l, path: l } : l)
    }
  } catch {}
}

watch(() => props.loraConfigJson, (v) => {
  try { loraConfig.value = v ? JSON.parse(v) : {} } catch { loraConfig.value = {} }
}, { immediate: true })

function loraAt(entityType, idx) {
  const list = loraConfig.value[entityType] || []
  return list[idx] || ''
}

function setLora(entityType, idx, loraName) {
  const list = [...(loraConfig.value[entityType] || [])]
  while (list.length <= idx) list.push('')
  list[idx] = loraName
  while (list.length && !list[list.length - 1]) list.pop()
  loraConfig.value = { ...loraConfig.value, [entityType]: list }
  emit('update:loraConfig', JSON.stringify(loraConfig.value))
}

onMounted(() => { fetchLoras() })
</script>

<style scoped>
.lora-root { padding: 0; }
.lora-hint { font-size: 10px; color: var(--text-dim); margin: 0 0 8px 0; }
.lora-empty { font-size: 10px; color: var(--text-dim); padding: 8px 0; }
.lora-type-row { margin-bottom: 6px; }
.lora-type-label {
  display: block; font-size: 9px; color: var(--text-dim); margin-bottom: 2px;
  text-transform: uppercase; letter-spacing: 0.5px;
}
.lora-selects { display: flex; gap: 4px; }
.lora-select {
  font-size: 10px; padding: 3px 6px; border-radius: 3px; flex: 1; min-width: 0;
  border: 1px solid var(--overlay-10); background: var(--overlay-4);
  color: var(--text);
}

.steering-block { margin-top: 10px; padding-top: 8px; border-top: 1px solid var(--overlay-10); }
.steering-label {
  display: block; font-size: 9px; color: var(--text-dim); margin-bottom: 2px;
  text-transform: uppercase; letter-spacing: 0.5px;
}
.steering-input {
  width: 100%; box-sizing: border-box; font-size: 10px; padding: 4px 6px;
  border-radius: 3px; border: 1px solid var(--overlay-10); background: var(--overlay-4);
  color: var(--text); font-family: inherit; resize: vertical;
}
.steering-hint { font-size: 9px; color: var(--text-dim); margin: 4px 0 0 0; }
</style>
