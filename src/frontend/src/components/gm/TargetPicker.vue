<template>
  <div class="tp-root">
    <div class="tp-input">
      <SearchDropdown
        :options="candidates"
        :model-value="modelValue"
        :exclude-ids="excludeIds"
        :placeholder="placeholder"
        value-key="id"
        label-key="name"
        :clearable="clearable"
        @select="pick"
        @clear="clear"
      >
        <template #option="{ option }">
          <span class="tp-name">{{ option.name }}</span>
          <span v-if="option.subtitle || option.universe" class="tp-universe">{{ option.subtitle || option.universe }}</span>
        </template>
      </SearchDropdown>
    </div>
    <button
      v-if="allowRandom"
      class="tp-random"
      title="Pick a random target from this scope"
      :disabled="!randomCandidates.length"
      @click="pickRandom"
    >🎲</button>
  </div>
</template>

<script setup>
import { computed, watch, onMounted } from 'vue'
import SearchDropdown from './SearchDropdown.vue'
import { useEffectTargets } from '@/composables/useEffectTargets.js'

// Generic target picker — resolves candidates through the backend's shared
// `targetCandidates` resolver (same candidate set the random mode uses) and
// renders them via the shared SearchDropdown. Every entity picker in the GM
// panel should route through this instead of fetching its own data.
const props = defineProps({
  modelValue: { type: String, default: '' },
  kind: { type: String, required: true },
  scope: { type: String, default: '' },
  filter: { type: Object, default: null },
  entityId: { type: String, default: '' },
  action: { type: String, default: '' },
  placeholder: { type: String, default: 'Choose target…' },
  allowRandom: { type: Boolean, default: false },
  clearable: { type: Boolean, default: true },
  excludeIds: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:modelValue', 'select'])

const { candidates, fetchTargets } = useEffectTargets()

// The 🎲 button never picks an id the caller explicitly excluded.
const randomCandidates = computed(() =>
  candidates.value.filter((c) => !props.excludeIds.includes(c.id))
)

function pick(opt) {
  emit('update:modelValue', opt.id)
  emit('select', opt)
}

function clear() {
  emit('update:modelValue', '')
  emit('select', null)
}

function pickRandom() {
  if (!randomCandidates.value.length) return
  const opt = randomCandidates.value[Math.floor(Math.random() * randomCandidates.value.length)]
  pick(opt)
}

async function load() {
  if (!props.kind) {
    candidates.value = []
    return
  }
  await fetchTargets(
    props.kind,
    props.scope || null,
    props.entityId || null,
    props.action || null,
    props.filter || null,
  )
}

onMounted(load)
watch(() => [props.kind, props.scope, props.entityId, props.action, props.filter], load)
</script>

<style scoped>
.tp-root { display: flex; align-items: center; gap: 4px; width: 100%; }
.tp-input { flex: 1; min-width: 0; }
.tp-random {
  flex: none; width: 26px; height: 24px; line-height: 1; cursor: pointer;
  background: var(--overlay-6); border: 1px solid var(--overlay-12);
  border-radius: 3px; color: var(--text-dim); font-size: 13px;
}
.tp-random:hover:not(:disabled) { color: var(--accent); border-color: var(--accent); }
.tp-random:disabled { opacity: 0.4; cursor: not-allowed; }
.tp-name { flex: 1; }
.tp-universe { font-size: 8px; color: var(--text-dim); margin-left: 8px; white-space: nowrap; }
</style>
