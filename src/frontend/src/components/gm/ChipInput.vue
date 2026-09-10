<template>
  <div class="chip-input" @click="focusInput">
    <span v-for="(item, i) in modelValue" :key="i" class="chip">
      {{ displayLabel(item) }}
      <Button class="chip-x" @click.stop="remove(i)" variant="danger-ghost" size="sm">×</Button>
    </span>
    <input
      ref="inputEl"
      v-model="text"
      class="chip-text"
      :placeholder="placeholder"
      @keydown.enter.prevent="addCurrent"
      @keydown.backspace="onBackspace"
      @focus="open = true"
      @blur="onBlur"
      @input="open = true"
    />
    <div v-if="open && suggestions.length" class="chip-dropdown">
      <div v-for="s in suggestions" :key="s.value" class="chip-option" @mousedown.prevent="add(s.value)">
        {{ s.label }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick } from 'vue'
import Button from '@/components/ui/Button.vue'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  options: { type: Array, default: () => [] },
  placeholder: { type: String, default: '' },
})

const emit = defineEmits(['update:modelValue'])

const text = ref('')
const open = ref(false)
const inputEl = ref(null)

function displayLabel(value) {
  const opt = props.options.find(o => o.value === value)
  return opt ? opt.label : value
}

const suggestions = computed(() => {
  const q = text.value.trim().toLowerCase()
  if (!q) return props.options.filter(o => !props.modelValue.includes(o.value))
  return props.options.filter(o =>
    o.label.toLowerCase().includes(q) && !props.modelValue.includes(o.value)
  )
})

function add(value) {
  emit('update:modelValue', [...props.modelValue, value])
  text.value = ''
  nextTick(() => inputEl.value?.focus())
}

function addCurrent() {
  if (suggestions.value.length) add(suggestions.value[0].value)
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
  setTimeout(() => { open.value = false }, 200)
}
</script>

<style scoped>
.chip-input {
  display: flex; flex-wrap: wrap; gap: 4px; align-items: center;
  padding: 4px 6px; min-height: 34px;
  border: 1px solid var(--overlay-10);
  border-radius: 6px; background: var(--overlay-4);
  cursor: text;
  position: relative;
}
.chip {
  display: inline-flex; align-items: center; gap: 2px;
  padding: 2px 6px; font-size: 11px;
  background: var(--accent-dim); color: var(--accent);
  border-radius: 4px;
}
.chip-text {
  flex: 1; min-width: 80px; font-size: 12px;
  background: none; border: none; outline: none; color: var(--text);
  padding: 4px 6px;
}
.chip-dropdown {
  position: absolute; top: 100%; left: 0; right: 0; z-index: 30;
  background: var(--bg-panel); backdrop-filter: blur(12px);
  border: 1px solid var(--overlay-10); border-radius: 0 0 6px 6px;
  max-height: 140px; overflow-y: auto;
}
.chip-option { padding: 4px 8px; font-size: 11px; cursor: pointer; }
.chip-option:hover { background: var(--overlay-6); }
</style>
