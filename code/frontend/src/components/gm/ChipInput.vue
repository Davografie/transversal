<template>
  <div class="chip-input" @click="focusInput">
    <span v-for="(item, i) in modelValue" :key="i" class="chip">
      {{ item }}
      <button class="chip-x" @click.stop="remove(i)">×</button>
    </span>
    <input
      ref="inputEl"
      v-model="text"
      class="chip-text"
      :placeholder="modelValue.length ? '' : placeholder"
      @keydown.enter.prevent="addCurrent"
      @keydown.backspace="onBackspace"
      @focus="open = true"
      @blur="onBlur"
    />
    <div v-if="open && suggestions.length" class="chip-dropdown">
      <div v-for="s in suggestions" :key="s" class="chip-option" @mousedown.prevent="add(s)">
        {{ s }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick } from 'vue'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  options: { type: Array, default: () => [] },
  placeholder: { type: String, default: '' },
})

const emit = defineEmits(['update:modelValue'])

const text = ref('')
const open = ref(false)
const inputEl = ref(null)

const suggestions = computed(() => {
  const q = text.value.trim().toLowerCase()
  if (!q) return props.options.filter(o => !props.modelValue.includes(o))
  return props.options.filter(o => o.toLowerCase().includes(q) && !props.modelValue.includes(o))
})

function add(item) {
  emit('update:modelValue', [...props.modelValue, item])
  text.value = ''
  open.value = false
  nextTick(() => inputEl.value?.focus())
}

function addCurrent() {
  if (suggestions.value.length) add(suggestions.value[0])
}

function remove(i) {
  const next = [...props.modelValue]
  next.splice(i, 1)
  emit('update:modelValue', next)
}

function onBackspace() {
  if (!text.value && props.modelValue.length) {
    remove(props.modelValue.length - 1)
  }
}

function focusInput() {
  inputEl.value?.focus()
}

function onBlur() {
  setTimeout(() => { open.value = false }, 150)
}
</script>

<style scoped>
.chip-input {
  display: flex; flex-wrap: wrap; gap: 4px; align-items: center;
  padding: 4px 6px; min-height: 32px;
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 6px; background: rgba(255,255,255,0.04);
  cursor: text;
  position: relative;
}
.chip {
  display: inline-flex; align-items: center; gap: 2px;
  padding: 1px 6px; font-size: 11px;
  background: var(--accent-dim); color: var(--accent);
  border-radius: 4px;
}
.chip-x { font-size: 12px; padding: 0 2px; background: none; border: none; color: var(--accent); cursor: pointer; }
.chip-x:hover { color: #fff; }
.chip-text {
  flex: 1; min-width: 60px; font-size: 12px;
  background: none; border: none; outline: none; color: var(--text);
  padding: 2px;
}
.chip-dropdown {
  position: absolute; top: 100%; left: 0; right: 0; z-index: 30;
  background: var(--bg-panel); backdrop-filter: blur(12px);
  border: 1px solid rgba(255,255,255,0.1); border-radius: 0 0 6px 6px;
  max-height: 140px; overflow-y: auto;
}
.chip-option { padding: 4px 8px; font-size: 11px; cursor: pointer; }
.chip-option:hover { background: rgba(255,255,255,0.06); }
</style>
