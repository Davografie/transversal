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
        <span class="tag-label">{{ labelFor(tag) }}</span>
        <button
          v-if="!disabled"
          type="button"
          class="tag-x"
          :aria-label="`Remove ${labelFor(tag)}`"
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
        :aria-activedescendant="activeDescendant"
        :aria-label="ariaLabel || placeholder"
        @keydown="onKeydown"
        @focus="onFocus"
        @blur="onBlur"
        @input="openList"
        @paste="onPaste"
      />
    </div>

    <!-- The list also opens for the *create* row alone: a free-form field whose
         typed text matches no existing tag still has something to offer, and
         hiding that behind `available.length` made "create" reachable only by
         pressing Enter. -->
    <ul v-if="open && (available.length || createText)"
        :id="listId" class="tag-dropdown" role="listbox">
      <li v-if="loading && !available.length" class="tag-option is-searching">Searching…</li>
      <li
        v-for="(s, idx) in available"
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
        v-if="createText"
        class="tag-option is-create"
        role="option"
        :aria-selected="highlighted === available.length ? 'true' : 'false'"
        :class="{ 'is-highlighted': highlighted === available.length }"
        @mousedown.prevent="addTag(text.trim())"
      >
        {{ createText }}
      </li>
    </ul>
  </div>
</template>

<script setup>
import { computed, nextTick, ref } from 'vue'
import { useCombobox } from '@/composables/useCombobox.js'

// Shared multi-tag input with autosuggest. Serves both a free-form tag field
// (Blue Book threads: type anything, existing tags suggested) and a
// restricted multi-select (trait universes, effect enum filters: pick from the
// given list). The list mechanics come from `useCombobox`; this owns the chips
// and the multi-value commit.
//
//   <TagInput v-model="threads" :suggestions="allThreads" placeholder="Threads…" />
//   <TagInput v-model="form.universes" :suggestions="allowedUniverses"
//             :allow-custom="false" placeholder="Add universe…" />
//
// `suggestions` may also be `(query) => options | Promise<options>` for a
// vocabulary too large to preload.
//
// Selected values are the model; suggestion labels are presentation. Commits
// on Enter (highlighted suggestion, else the typed text when `allowCustom`),
// comma, option click, or paste of a comma-separated list. Backspace on an
// empty field removes the last tag.
const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  // string[] or { value, label, hint? }[], or a query function returning either
  suggestions: { type: [Array, Function], default: () => [] },
  // false = only values from `suggestions` can be added
  allowCustom: { type: Boolean, default: true },
  placeholder: { type: String, default: 'Add tag…' },
  ariaLabel: { type: String, default: '' },
  disabled: { type: Boolean, default: false },
  max: { type: Number, default: 0 },          // 0 = unlimited
})

const emit = defineEmits(['update:modelValue', 'add', 'remove'])

const text = ref('')
const inputEl = ref(null)

const combo = useCombobox({
  options: computed(() => props.suggestions),
  query: text,
  chosen: computed(() => props.modelValue),
  allowCustom: props.allowCustom,
  armTopOnChange: true,
})
const {
  listId, open, loading, highlighted, available, createText,
  activeDescendant, optionId, move, resolve, labelFor, openList, closeList,
} = combo

const atMax = computed(() => props.max > 0 && props.modelValue.length >= props.max)

// Adds one or many values with a SINGLE emit — sequential addTag() calls would
// each read the same stale modelValue and only the last would survive.
function addValues(values) {
  if (props.disabled) return
  const next = [...props.modelValue]
  let added = null
  for (const raw of values) {
    if (props.max > 0 && next.length >= props.max) break
    const v = resolve(raw)
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
    case 'Escape': closeList(); break
    case 'Tab': closeList(); break
  }
}

function commitHighlightedOrText() {
  // A highlight on the create row (index === available.length) falls through to
  // the text path, which splits a pasted comma list as it always has.
  if (highlighted.value >= 0 && highlighted.value < available.value.length) {
    addTag(available.value[highlighted.value].value)
  } else {
    commitText()
  }
}

// Comma typed (or a comma-pasted list): commit everything before the cursor.
function commitText() {
  const parts = text.value.split(',').map((p) => p.trim()).filter(Boolean)
  if (!parts.length) return
  addValues(parts)
  text.value = ''
  highlighted.value = -1
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

function onFocus() { if (!props.disabled) openList() }
function onBlur() {
  // A blur with pending text commits it (typing and clicking away shouldn't lose it).
  if (props.allowCustom && text.value.trim()) commitText()
  closeList()
}
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
  border-radius: var(--radius-sm);
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
  border-radius: var(--radius-pill);
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
  border-radius: var(--radius-pill);
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
  border-radius: var(--radius-sm);
  box-shadow: 0 6px 18px var(--shadow);
}

.tag-option {
  display: flex;
  align-items: baseline;
  gap: 6px;
  padding: 5px 8px;
  font-size: 12px;
  color: var(--text);
  border-radius: var(--radius-xs);
  cursor: pointer;
}
.tag-option.is-highlighted { background: var(--accent-12); color: var(--accent); }
.tag-option.is-create { color: var(--text-dim); font-style: italic; }
.tag-option.is-searching { color: var(--text-dim); font-style: italic; }
.tag-option-hint { font-size: 10px; color: var(--text-dim); }
</style>
