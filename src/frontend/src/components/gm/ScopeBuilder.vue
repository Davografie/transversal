<template>
  <div class="sb-root">
    <select v-model="mode" class="sb-prefix" @change="onModeChange">
      <option value="">Current context</option>
      <option value="universe">Universe</option>
      <option value="location">Location</option>
      <option value="subtree">Subtree</option>
      <option value="faction">Faction</option>
      <option value="traitset">Trait set</option>
      <option value="raw">Custom (raw)</option>
    </select>

    <template v-if="mode === 'location' || mode === 'subtree'">
      <TargetPicker
        :model-value="value"
        kind="location"
        :scope="universe ? `universe:${universe}` : ''"
        placeholder="Pick a location…"
        @update:model-value="setValue"
      />
    </template>
    <template v-else-if="mode === 'traitset'">
      <select v-model="value" @change="emitScope">
        <option value="">-- pick a trait set --</option>
        <option v-for="t in traitsets" :key="t.id" :value="t.id">{{ t.name }}</option>
      </select>
    </template>
    <template v-else-if="mode === 'universe'">
      <select v-model="value" @change="emitScope">
        <option value="">-- pick a universe --</option>
        <option value="current">Current universe</option>
        <option v-for="u in universeKeys" :key="u" :value="u">{{ universeName(u) }}</option>
      </select>
    </template>
    <template v-else-if="mode === 'raw'">
      <input v-model="value" type="text" placeholder="prefix:value or bare value" @input="emitScope" />
    </template>
    <template v-else-if="mode === 'faction'">
      <input v-model="value" type="text" placeholder="faction id" @input="emitScope" />
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useTraitsConfig } from '@/composables/useTraitsConfig.js'
import { useUniverseNames } from '@/composables/useUniverseNames.js'
import TargetPicker from './TargetPicker.vue'

const props = defineProps({
  modelValue: { type: String, default: '' },
  universe: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue'])

const PREFIXES = ['universe', 'location', 'subtree', 'faction', 'traitset']

const { traitsets, fetchTraitsConfig } = useTraitsConfig()
const { names: universeNames, name: universeName, load: loadUniverseNames } = useUniverseNames()

const mode = ref('')
const value = ref('')

const universeKeys = computed(() => Object.keys(universeNames.value))

onMounted(async () => {
  if (!traitsets.value.length) await fetchTraitsConfig()
  await loadUniverseNames()
})

watch(() => props.modelValue, (scope) => {
  const parsed = parse(scope)
  mode.value = parsed.mode
  value.value = parsed.value
}, { immediate: true })

function parse(scope) {
  if (!scope) return { mode: '', value: '' }
  const idx = scope.indexOf(':')
  if (idx === -1) return { mode: 'raw', value: scope }
  const prefix = scope.slice(0, idx)
  if (PREFIXES.includes(prefix)) return { mode: prefix, value: scope.slice(idx + 1) }
  return { mode: 'raw', value: scope }
}

function currentScope() {
  if (mode.value === '') return ''
  if (mode.value === 'raw') return value.value
  return value.value ? `${mode.value}:${value.value}` : ''
}

function emitScope() {
  emit('update:modelValue', currentScope())
}

function setValue(v) {
  value.value = v || ''
  emitScope()
}

function onModeChange() {
  value.value = ''
  emitScope()
}
</script>

<style scoped>
.sb-root { display: flex; flex-direction: column; gap: 4px; }
.sb-root select, .sb-root input {
  font-size: 11px; padding: 4px 6px;
  background: var(--overlay-6); color: var(--text);
  border: 1px solid var(--overlay-10); border-radius: 4px;
  font-family: inherit; width: 100%; box-sizing: border-box;
}
.sb-prefix { width: 100%; }
</style>
