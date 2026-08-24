<template>
  <div class="sd-root">
    <input
      ref="inputEl"
      v-model="search"
      class="sd-input"
      :class="{ 'sd-input-clearable': clearable && hasValue }"
      :placeholder="selectedLabel || placeholder"
      @focus="openDrop"
      @blur="scheduleClose"
      @input="open = true"
    />
    <button
      v-if="clearable && hasValue"
      class="sd-clear"
      title="Clear"
      @mousedown.prevent="clear"
    >×</button>
    <div v-if="open" class="sd-drop" :class="{ 'sd-drop-up': dropUp }">
      <div v-if="!filtered.length" class="sd-empty">No matches</div>
      <div
        v-for="opt in filtered"
        :key="opt[valueKey]"
        class="sd-item"
        @mousedown.prevent="pick(opt)"
      >
        <slot name="option" :option="opt">{{ opt[labelKey] }}</slot>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onUnmounted } from 'vue'

const props = defineProps({
  options: { type: Array, default: () => [] },
  // Currently selected value (single-select mode). Excluded from the
  // dropdown and shown as the placeholder label once resolved.
  modelValue: { type: [String, Number], default: '' },
  // Extra ids to exclude (chip/append mode where several values are chosen).
  excludeIds: { type: Array, default: () => [] },
  placeholder: { type: String, default: 'Search…' },
  valueKey: { type: String, default: 'id' },
  labelKey: { type: String, default: 'name' },
  maxResults: { type: Number, default: 20 },
  clearable: { type: Boolean, default: false },
})

const emit = defineEmits(['select', 'clear'])

const search = ref('')
const open = ref(false)
const dropUp = ref(false)
const inputEl = ref(null)
let closeTimer = null

const selectedLabel = computed(() => {
  if (props.modelValue === '' || props.modelValue == null) return ''
  const opt = props.options.find(o => o[props.valueKey] === props.modelValue)
  return opt ? opt[props.labelKey] : ''
})

const hasValue = computed(() => props.modelValue !== '' && props.modelValue != null)

const filtered = computed(() => {
  const s = search.value.trim().toLowerCase()
  const excluded = new Set(props.excludeIds)
  if (props.modelValue !== '' && props.modelValue != null) excluded.add(props.modelValue)
  return props.options
    .filter(o => {
      if (excluded.has(o[props.valueKey])) return false
      if (s && !String(o[props.labelKey] ?? '').toLowerCase().includes(s)) return false
      return true
    })
    .slice(0, props.maxResults)
})

function pick(opt) {
  emit('select', opt)
  search.value = ''
  open.value = false
}

function clear() {
  emit('clear')
  search.value = ''
  open.value = false
}

async function openDrop() {
  open.value = true
  await nextTick()
  const rect = inputEl.value?.getBoundingClientRect()
  if (!rect) {
    dropUp.value = false
    return
  }
  // Dropdown max-height is 140px; flip upward when there's not enough room below.
  dropUp.value = (window.innerHeight - rect.bottom) < 160
}

function scheduleClose() {
  clearTimeout(closeTimer)
  closeTimer = setTimeout(() => { open.value = false }, 150)
}

onUnmounted(() => clearTimeout(closeTimer))
</script>

<style scoped>
.sd-root { position: relative; width: 100%; }
.sd-input {
  width: 100%; font-size: 11px; padding: 4px 6px; border-radius: 3px; box-sizing: border-box;
  border: 1px solid rgba(255,255,255,0.1); background: rgba(255,255,255,0.04); color: var(--text);
}
.sd-input::placeholder { color: var(--text-dim); }
.sd-input-clearable { padding-right: 20px; }
.sd-clear {
  position: absolute; right: 4px; top: 4px; font-size: 12px; line-height: 1;
  padding: 0 2px; cursor: pointer; background: none; border: none; color: var(--text-dim);
}
.sd-clear:hover { color: #e06060; }
.sd-drop {
  position: absolute; top: 100%; left: 0; right: 0; z-index: 10;
  max-height: 140px; overflow-y: auto;
  background: #1a1a2e; border: 1px solid rgba(255,255,255,0.1); border-radius: 3px;
}
.sd-drop-up { top: auto; bottom: 100%; }
.sd-item {
  font-size: 10px; padding: 4px 8px; cursor: pointer; color: var(--text);
}
.sd-item:hover { background: rgba(0,200,150,0.1); color: var(--accent); }
.sd-empty { font-size: 10px; padding: 6px 8px; color: var(--text-dim); }
</style>
