<template>
  <SearchDropdown
    :options="candidates"
    :model-value="modelValue"
    :placeholder="placeholder"
    value-key="id"
    label-key="name"
    @select="pick"
  >
    <template #option="{ option }">
      <span class="stp-name">{{ option.name }}</span>
      <span v-if="option.universe" class="stp-universe">{{ option.universe }}</span>
    </template>
  </SearchDropdown>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import SearchDropdown from './SearchDropdown.vue'
import { useEffectTargets } from '@/composables/useEffectTargets.js'

const props = defineProps({
  modelValue: { type: String, default: '' },
  kind: { type: String, required: true },
  scope: { type: String, default: '' },
  entityId: { type: String, default: '' },
  placeholder: { type: String, default: 'Choose target…' },
})

const emit = defineEmits(['update:modelValue', 'select'])

const { loading, candidates, fetchTargets } = useEffectTargets()
const initialized = ref(false)

async function load() {
  if (!props.entityId) return
  await fetchTargets(props.kind, props.scope || null, props.entityId)
  initialized.value = true
}

onMounted(load)
watch(() => [props.kind, props.scope, props.entityId], load)

function pick(opt) {
  emit('update:modelValue', opt.id)
  emit('select', opt)
}
</script>

<style scoped>
.stp-name { flex: 1; }
.stp-universe { font-size: 8px; color: var(--text-dim); margin-left: 8px; white-space: nowrap; }
</style>
