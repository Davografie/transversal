<template>
  <div class="sd-root">
    <input
      ref="inputEl"
      class="sd-input"
      :class="{ 'sd-input-clearable': clearable && hasValue }"
      :value="open ? query : selectedLabel"
      :placeholder="open ? (selectedLabel || placeholder) : placeholder"
      role="combobox"
      aria-haspopup="listbox"
      :aria-expanded="open ? 'true' : 'false'"
      :aria-controls="listId"
      :aria-activedescendant="activeDescendant"
      aria-autocomplete="list"
      @focus="openDrop"
      @blur="scheduleClose"
      @input="onInput"
      @keydown="onKeydown"
    />
    <button
      v-if="clearable && hasValue"
      class="sd-clear"
      title="Clear"
      @mousedown.prevent="clear"
    >×</button>
    <div v-if="open" :id="listId" class="sd-drop" :class="{ 'sd-drop-up': dropUp }" role="listbox">
      <div v-if="loading && !available.length" class="sd-empty">Searching…</div>
      <div v-else-if="!available.length" class="sd-empty">No matches</div>
      <div
        v-for="(opt, i) in available"
        :key="opt.value"
        class="sd-item"
        :class="{ 'sd-item-active': i === highlighted }"
        role="option"
        :aria-selected="i === highlighted ? 'true' : 'false'"
        @mousedown.prevent="pickAt(i)"
        @mousemove="highlighted = i"
      >
        <slot name="option" :option="opt.raw">{{ opt.label }}</slot>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, ref, onUnmounted } from 'vue'
import { useCombobox } from '@/composables/useCombobox.js'

// Single-select typeahead. The list mechanics (filter, highlight, keyboard,
// aria, an async source) come from `useCombobox`; this owns the input, the
// clear affordance, the drop-up flip and the single-value commit.
const props = defineProps({
  // An array, or `(query) => options | Promise<options>` for a server-backed
  // lookup. The function form is new: pickers whose vocabulary is too large to
  // preload can now query as the author types.
  options: { type: [Array, Function], default: () => [] },
  // Currently selected value (single-select mode). Excluded from the
  // dropdown and shown as the placeholder label once resolved.
  modelValue: { type: [String, Number], default: '' },
  // Extra ids to exclude (chip/append mode where several values are chosen).
  excludeIds: { type: Array, default: () => [] },
  placeholder: { type: String, default: 'Search…' },
  valueKey: { type: String, default: 'id' },
  labelKey: { type: String, default: 'name' },
  maxResults: { type: Number, default: 20 },
  // A display name for a value that isn't among `options` (a saved id whose
  // candidate is not in the loaded page). The caller resolves it so the field
  // shows a name instead of a raw id; the raw value stays the last resort.
  fallbackLabel: { type: String, default: '' },
  clearable: { type: Boolean, default: false },
})

const emit = defineEmits(['select', 'clear'])

const inputEl = ref(null)
const query = ref('')
const dropUp = ref(false)
const hasValue = computed(() => props.modelValue !== '' && props.modelValue != null)

const chosen = computed(() =>
  props.modelValue === '' || props.modelValue == null ? [] : [props.modelValue])
const exclude = computed(() => props.excludeIds)

const combo = useCombobox({
  options: computed(() => props.options),
  query,
  chosen,
  exclude,
  maxResults: computed(() => props.maxResults).value,
  armTopOnChange: true,
  // A picker's highlight clamps at the ends: the tag field's wrap-to-nothing
  // convention would let one stray arrow cancel an otherwise armed commit.
  wrapHighlight: false,
  // Single-select compares labels only, matching the long-standing behaviour
  // (a raw id typed into a picker should not silently match a record).
  matchTerm: (it, q) => it.label.toLowerCase().includes(q),
  normalize: (o) => ({
    value: o?.[props.valueKey],
    label: o?.[props.labelKey] ?? '',
    raw: o,
  }),
})
const { listId, open, loading, highlighted, available, activeDescendant, move, openList, closeList } = combo

const selectedLabel = computed(() => {
  if (props.modelValue === '' || props.modelValue == null) return ''
  // Only a plain array can be searched for a label; an async source has not
  // necessarily seen the selected record, so it falls through to the caller's
  // resolved name (and the raw value as the last resort).
  const list = Array.isArray(props.options) ? props.options : []
  const opt = list.find(o => o[props.valueKey] === props.modelValue)
  // A value that isn't among the options is still a value — a `{bound_name}`
  // token the author typed, or an id whose record is gone. Falling back to the
  // placeholder hides what is actually set: the field looks empty when it isn't.
  // `fallbackLabel` (a resolved name from the caller) comes first, so an id the
  // author never should see reads as its name; a raw id is the last resort.
  return (opt && opt[props.labelKey]) || props.fallbackLabel || String(props.modelValue)
})

async function openDrop() {
  openList()
  await nextTick()
  const rect = inputEl.value?.getBoundingClientRect()
  if (!rect) {
    dropUp.value = false
    return
  }
  // Dropdown max-height is 140px; flip upward when there's not enough room below.
  dropUp.value = (window.innerHeight - rect.bottom) < 160
}

// A chosen value reads as *text*, not as placeholder-grey: the input shows the
// label unless the author is actively searching — then the label becomes the
// hint, so what is set stays visible while they replace it.
function onInput(e) {
  query.value = e.target.value
  openList()
}

function pickAt(i) {
  const opt = available.value[i]
  if (!opt) return
  emit('select', opt.raw)
  query.value = ''
  closeList()
}

function onKeydown(e) {
  switch (e.key) {
    case 'ArrowDown': e.preventDefault(); move(1); break
    case 'ArrowUp': e.preventDefault(); move(-1); break
    case 'Enter': {
      // Only claim Enter when it actually commits: with nothing highlighted it
      // is not ours to swallow, and a picker can sit inside an authoring form
      // that wants the key for itself.
      if (highlighted.value >= 0 && highlighted.value < available.value.length) {
        e.preventDefault()
        pickAt(highlighted.value)
      }
      break
    }
    case 'Escape': closeList(); break
    case 'Tab': closeList(); break
  }
}

function clear() {
  emit('clear')
  query.value = ''
  closeList()
}

let closeTimer = null
function scheduleClose() {
  clearTimeout(closeTimer)
  closeTimer = setTimeout(() => closeList(), 150)
}

onUnmounted(() => clearTimeout(closeTimer))
</script>

<style scoped>
.sd-root { position: relative; width: 100%; }
.sd-input {
  width: 100%; font-size: 11px; padding: 4px 6px; border-radius: var(--radius-xs); box-sizing: border-box;
  border: 1px solid var(--overlay-10); background: var(--overlay-4); color: var(--text);
}
.sd-input::placeholder { color: var(--text-dim); }
.sd-input-clearable { padding-right: 20px; }
.sd-clear {
  position: absolute; right: 4px; top: 4px; font-size: 12px; line-height: 1;
  padding: 0 2px; cursor: pointer; background: none; border: none; color: var(--text-dim);
}
.sd-clear:hover { color: var(--danger-soft); }
.sd-drop {
  position: absolute; top: 100%; left: 0; right: 0; z-index: 10;
  max-height: 140px; overflow-y: auto;
  background: var(--bg-panel-raised); border: 1px solid var(--overlay-10); border-radius: var(--radius-xs);
}
.sd-drop-up { top: auto; bottom: 100%; }
.sd-item {
  font-size: 10px; padding: 4px 8px; cursor: pointer; color: var(--text);
}
.sd-item:hover, .sd-item-active { background: rgba(0,200,150,0.1); color: var(--accent); }
.sd-empty { font-size: 10px; padding: 6px 8px; color: var(--text-dim); }
</style>
