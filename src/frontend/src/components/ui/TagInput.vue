<template>
  <div class="tag-input-wrap">
    <div
      class="tag-input"
      :class="{ 'is-disabled': disabled, 'is-open': open }"
      role="combobox"
      :aria-expanded="open ? 'true' : 'false'"
      :aria-controls="listId"
      :aria-owns="listId"
      aria-haspopup="listbox"
      @click="focusInput"
    >
      <span v-for="tag in modelValue" :key="tag" class="tag">
        <span class="tag-label">{{ displayLabel(tag) }}</span>
        <button
          v-if="!disabled"
          type="button"
          class="tag-x"
          :aria-label="`Remove ${displayLabel(tag)}`"
          @mousedown.prevent
          @click.stop="removeTag(tag)"
        >×</button>
      </span>
      <input
        ref="inputEl"
        v-model="text"
        class="tag-text"
        type="text"
        :placeholder="modelValue.length ? '' : placeholder"
        :disabled="disabled"
        :aria-autocomplete="'list'"
        :aria-activedescendant="highlighted >= 0 ? optionId(highlighted) : undefined"
        :aria-label="ariaLabel || placeholder"
        @keydown="onKeydown"
        @focus="onFocus"
        @blur="onBlur"
        @input="open = true"
        @paste="onPaste"
      />
    </div>

    <ul v-if="open && availableSuggestions.length" :id="listId" class="tag-dropdown" role="listbox">
      <li
        v-for="(s, idx) in availableSuggestions"
        :id="optionId(idx)"
        :key="s.value"
        class="tag-option"
        :class="{ 'is-highlighted': idx === highlighted }"
        role="option"
        :aria-selected="idx === highlighted ? 'true' : 'false'"
        @mousedown.prevent="addTag(s.value)"
        @mousemove="highlighted = idx"
      >
        {{ s.label }}
        <span v-if="s.hint" class="tag-option-hint">{{ s.hint }}</span>
      </li>
      <li
        v-if="allowCustom && text.trim() && !exactMatch"
        class="tag-option is-create"
        role="option"
        :aria-selected="highlighted === availableSuggestions.length ? 'true' : 'false'"
        :class="{ 'is-highlighted': highlighted === availableSuggestions.length }"
        @mousedown.prevent="addTag(text.trim())"
      >
        Create “{{ text.trim() }}”
      </li>
    </ul>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, watch, useId } from 'vue'

// Shared multi-tag input with autosuggest. Serves both a free-form tag field
// (Blue Book threads: type anything, existing tags suggested) and a
// restricted multi-select (trait universes: pick from the given list).
//
//   <TagInput v-model="threads" :suggestions="allThreads" placeholder="Threads…" />
//   <TagInput v-model="form.universes" :suggestions="allowedUniverses"
//             :allow-custom="false" placeholder="Add universe…" />
//
// Selected values are the model; suggestion labels are presentation. Commits
// on Enter (highlighted suggestion, else the typed text when `allowCustom`),
// comma, option click, or paste of a comma-separated list. Backspace on an
// empty field removes the last tag.
const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  // string[] or { value, label, hint? }[]
  suggestions: { type: Array, default: () => [] },
  // false = only values from `suggestions` can be added
  allowCustom: { type: Boolean, default: true },
  placeholder: { type: String, default: 'Add tag…' },
  ariaLabel: { type: String, default: '' },
  disabled: { type: Boolean, default: false },
  max: { type: Number, default: 0 },          // 0 = unlimited
})

const emit = defineEmits(['update:modelValue', 'add', 'remove'])

const text = ref('')
const open = ref(false)
const highlighted = ref(-1)
const inputEl = ref(null)
const listId = useId()
const optionId = (idx) => `${listId}-opt-${idx}`

const normalized = computed(() =>
  props.suggestions.map((s) =>
    typeof s === 'string' ? { value: s, label: s } : { value: s.value, label: s.label ?? s.value, hint: s.hint }
  )
)

const availableSuggestions = computed(() => {
  const chosen = new Set(props.modelValue)
  const q = text.value.trim().toLowerCase()
  return normalized.value
    .filter((s) => !chosen.has(s.value))
    .filter((s) => !q || s.label.toLowerCase().includes(q) || String(s.value).toLowerCase().includes(q))
})

watch([text, availableSuggestions], () => {
  // Keep the top option armed: Enter commits the best match (or the create
  // row when free-form) without an explicit arrow key.
  highlighted.value = optionCount() ? 0 : -1
})

const exactMatch = computed(() => {
  const q = text.value.trim().toLowerCase()
  if (!q) return false
  return normalized.value.some((s) => s.value.toLowerCase() === q || s.label.toLowerCase() === q)
})

const atMax = computed(() => props.max > 0 && props.modelValue.length >= props.max)

function displayLabel(value) {
  const opt = normalized.value.find((s) => s.value === value)
  return opt ? opt.label : value
}

// Resolve a typed/clicked value to what should be stored, or null when it
// isn't allowed (restricted mode) or is already present.
function resolveValue(raw) {
  const v = String(raw ?? '').trim()
  if (!v) return null
  const byLabel = normalized.value.find((s) => s.label.toLowerCase() === v.toLowerCase())
  const byValue = normalized.value.find((s) => s.value === v)
  if (!byLabel && !byValue && !props.allowCustom) return null
  return byLabel?.value ?? byValue?.value ?? v
}

// Adds one or many values with a SINGLE emit — sequential addTag() calls would
// each read the same stale modelValue and only the last would survive.
function addValues(values) {
  if (props.disabled) return
  const next = [...props.modelValue]
  let added = null
  for (const raw of values) {
    if (props.max > 0 && next.length >= props.max) break
    const v = resolveValue(raw)
    if (!v || next.includes(v)) continue
    next.push(v)
    added = added ? `${added}, ${v}` : v
  }
  if (!added) return
  emit('update:modelValue', next)
  emit('add', added)
}

function addTag(value) {
  addValues([value])
  text.value = ''
  highlighted.value = -1
  nextTick(() => inputEl.value?.focus())
}

function removeTag(value) {
  const idx = props.modelValue.indexOf(value)
  if (idx === -1) return
  const next = [...props.modelValue]
  next.splice(idx, 1)
  emit('update:modelValue', next)
  emit('remove', value)
}

function onKeydown(e) {
  switch (e.key) {
    case 'Enter': e.preventDefault(); commitHighlightedOrText(); break
    case ',': e.preventDefault(); commitText(); break
    case 'Backspace': onBackspace(); break
    case 'ArrowDown': e.preventDefault(); move(1); break
    case 'ArrowUp': e.preventDefault(); move(-1); break
    case 'Escape': close(); break
    case 'Tab': close(); break
  }
}

function commitHighlightedOrText() {
  const list = availableSuggestions.value
  if (highlighted.value >= 0 && highlighted.value < list.length) addTag(list[highlighted.value].value)
  else commitText()
}

// Comma typed (or a comma-pasted list): commit everything before the cursor.
function commitText() {
  const parts = text.value.split(',').map((p) => p.trim()).filter(Boolean)
  if (!parts.length) return
  addValues(parts)
  text.value = ''
  highlighted.value = -1
}

function optionCount() {
  return availableSuggestions.value.length + (props.allowCustom && text.value.trim() && !exactMatch.value ? 1 : 0)
}

// Highlight walks -1 (nothing) → 0…count-1 → back to -1.
function move(dir) {
  const count = optionCount()
  if (!count) return
  open.value = true
  const max = count - 1
  if (dir > 0) highlighted.value = highlighted.value >= max ? -1 : highlighted.value + 1
  else highlighted.value = highlighted.value <= -1 ? max : highlighted.value - 1
}

function onBackspace() {
  if (text.value) return
  if (props.modelValue.length) removeTag(props.modelValue[props.modelValue.length - 1])
}

function onPaste(e) {
  const pasted = e.clipboardData?.getData('text') || ''
  if (!pasted.includes(',')) return
  e.preventDefault()
  addValues(pasted.split(',').map((p) => p.trim()).filter(Boolean))
  text.value = ''
  highlighted.value = -1
}

function onFocus() { if (!props.disabled) open.value = true }
function onBlur() {
  // A blur with pending text commits it (typing and clicking away shouldn't lose it).
  if (props.allowCustom && text.value.trim()) commitText()
  open.value = false
  highlighted.value = -1
}
function close() { open.value = false; highlighted.value = -1 }
function focusInput() { if (!props.disabled) inputEl.value?.focus() }
</script>

<style scoped>
.tag-input-wrap { position: relative; }

.tag-input {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  padding: 4px 6px;
  min-height: 30px;
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: text;
  transition: border-color 0.15s;
}
.tag-input:focus-within { border-color: var(--accent); }
.tag-input.is-disabled { opacity: 0.5; cursor: default; }

.tag {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 1px 2px 1px 6px;
  font-size: 11px;
  border-radius: 999px;
  background: var(--accent-12);
  color: var(--accent);
  max-width: 100%;
}
.tag-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.tag-x {
  border: none;
  background: none;
  color: inherit;
  font-size: 12px;
  line-height: 1;
  padding: 0 4px;
  cursor: pointer;
  border-radius: 999px;
  opacity: 0.7;
}
.tag-x:hover { opacity: 1; background: var(--accent-20); }

.tag-text {
  flex: 1 1 80px;
  min-width: 80px;
  border: none;
  outline: none;
  background: transparent;
  color: var(--text);
  font-size: 12px;
  padding: 3px 2px;
}

.tag-dropdown {
  position: absolute;
  z-index: 40;
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  margin: 0;
  padding: 4px;
  list-style: none;
  max-height: 180px;
  overflow-y: auto;
  background: var(--bg-panel-solid);
  border: 1px solid var(--border);
  border-radius: 6px;
  box-shadow: 0 6px 18px var(--shadow);
}

.tag-option {
  display: flex;
  align-items: baseline;
  gap: 6px;
  padding: 5px 8px;
  font-size: 12px;
  color: var(--text);
  border-radius: 4px;
  cursor: pointer;
}
.tag-option.is-highlighted { background: var(--accent-12); color: var(--accent); }
.tag-option.is-create { color: var(--text-dim); font-style: italic; }
.tag-option-hint { font-size: 10px; color: var(--text-dim); }
</style>
