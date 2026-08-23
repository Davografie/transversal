<template>
  <div class="stp-root">
    <div class="stp-input">
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
    </div>
    <button
      class="stp-random"
      title="Pick a random target from this scope"
      :disabled="!candidates.length"
      @click="pickRandom"
    >🎲</button>
  </div>
</template>

<script setup>
import { watch, onMounted } from 'vue'
import SearchDropdown from './SearchDropdown.vue'
import { useEffectTargets } from '@/composables/useEffectTargets.js'

const props = defineProps({
  modelValue: { type: String, default: '' },
  kind: { type: String, required: true },
  scope: { type: String, default: '' },
  entityId: { type: String, default: '' },
  action: { type: String, default: '' },
  placeholder: { type: String, default: 'Choose target…' },
})

const emit = defineEmits(['update:modelValue', 'select'])

const { candidates, fetchTargets } = useEffectTargets()

async function load() {
  if (!props.entityId) return
  await fetchTargets(props.kind, props.scope || null, props.entityId, props.action || null)
}

onMounted(load)
watch(() => [props.kind, props.scope, props.entityId, props.action], load)

function pick(opt) {
  emit('update:modelValue', opt.id)
  emit('select', opt)
}

function pickRandom() {
  if (!candidates.value.length) return
  const opt = candidates.value[Math.floor(Math.random() * candidates.value.length)]
  pick(opt)
}
</script>

<style scoped>
.stp-root { display: flex; align-items: center; gap: 4px; width: 100%; }
.stp-input { flex: 1; min-width: 0; }
.stp-random {
  flex: none; width: 26px; height: 24px; line-height: 1; cursor: pointer;
  background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12);
  border-radius: 3px; color: var(--text-dim); font-size: 13px;
}
.stp-random:hover:not(:disabled) { color: var(--accent); border-color: var(--accent); }
.stp-random:disabled { opacity: 0.4; cursor: not-allowed; }
.stp-name { flex: 1; }
.stp-universe { font-size: 8px; color: var(--text-dim); margin-left: 8px; white-space: nowrap; }
</style>
