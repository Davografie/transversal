<template>
  <div class="gsp-root">
    <div class="gsp-input-wrap">
      <input
        v-model="search"
        :placeholder="selectedLabel || placeholder"
        @focus="open = true"
        @blur="close"
        @input="open = true"
        class="gsp-input"
      />
      <button v-if="modelValue" class="gsp-clear" title="Clear" @mousedown.prevent="clear">×</button>
      <div v-if="open" class="gsp-drop">
        <div v-if="!filtered.length" class="gsp-empty">No matches</div>
        <div
          v-for="opt in filtered"
          :key="opt.value"
          class="gsp-item"
          @mousedown.prevent="pick(opt)"
        >
          {{ opt.label }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'

// Searchable single-select for a small id→label list with an explicit
// "empty" option (e.g. universe "Fundamental (all universes)" = '').
const props = defineProps({
  modelValue: { type: String, default: '' },
  options: { type: Array, default: () => [] },   // [{ value, label }]
  emptyLabel: { type: String, default: 'None' },
  placeholder: { type: String, default: 'Select…' },
})

const emit = defineEmits(['update:modelValue'])

const search = ref('')
const open = ref(false)

const allOptions = computed(() => [
  { value: '', label: props.emptyLabel },
  ...props.options,
])

const selectedLabel = computed(() => {
  const opt = allOptions.value.find(o => o.value === props.modelValue)
  return opt?.label || ''
})

const filtered = computed(() => {
  const s = search.value.toLowerCase()
  return allOptions.value.filter(o => {
    if (o.value === props.modelValue) return false
    if (s && !o.label.toLowerCase().includes(s)) return false
    return true
  })
})

function pick(opt) {
  emit('update:modelValue', opt.value)
  search.value = ''
  open.value = false
}

function clear() {
  emit('update:modelValue', '')
  search.value = ''
  open.value = false
}

function close() {
  setTimeout(() => { open.value = false }, 150)
}

watch(() => props.modelValue, () => { search.value = '' })
</script>

<style scoped>
.gsp-root { display: inline-block; width: 100%; }
.gsp-input-wrap { position: relative; }
.gsp-input {
  width: 100%; font-size: 11px; padding: 4px 20px 4px 6px; border-radius: 3px;
  border: 1px solid var(--overlay-10); background: var(--overlay-4); color: var(--text);
  box-sizing: border-box;
}
.gsp-input::placeholder { color: var(--text-dim); }
.gsp-clear {
  position: absolute; right: 4px; top: 4px; font-size: 12px; line-height: 1;
  padding: 0 2px; cursor: pointer; background: none; border: none; color: var(--text-dim);
}
.gsp-clear:hover { color: var(--danger-soft); }
.gsp-drop {
  position: absolute; top: 100%; left: 0; right: 0; z-index: 10;
  max-height: 160px; overflow-y: auto;
  background: var(--bg-panel-raised); border: 1px solid var(--overlay-10); border-radius: 3px;
}
.gsp-item {
  font-size: 10px; padding: 4px 8px; cursor: pointer; color: var(--text);
}
.gsp-item:hover { background: rgba(0,200,150,0.1); color: var(--accent); }
.gsp-empty { font-size: 10px; padding: 6px 8px; color: var(--text-dim); }
</style>
