<template>
  <div class="sd-root">
    <input
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
    <div v-if="open" :id="listId" class="sd-list" role="listbox">
      <div v-if="loading && !available.length" class="sd-state">Searching…</div>
      <div v-else-if="!available.length" class="sd-state">No matches</div>
      <div
        v-for="(opt, i) in available"
        :id="optionId(i)"
        :key="opt.value"
        class="sd-item entity-row"
        :class="{ 'sd-item-active': i === highlighted }"
        role="option"
        :aria-selected="i === highlighted ? 'true' : 'false'"
        @mousedown.prevent="pickAt(i)"
        @mousemove="highlighted = i"
      >
        <slot name="option" :option="opt.raw">
          <span class="entity-name">{{ opt.label }}</span>
        </slot>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, onUnmounted } from 'vue'
import { useCombobox } from '@/composables/useCombobox.js'

// Single-select typeahead. The list mechanics (filter, highlight, keyboard,
// aria, an async source) come from `useCombobox`; this owns the input, the
// clear affordance, the result list and the single-value commit.
//
// **The results are an inline list, never an overlay.** An absolutely
// positioned list is cropped by any ancestor with `overflow` — which is most
// hosts (a GM panel's scroll zone, the sheet, the wizard), so the same field
// clipped in different places depending on where it was embedded. In flow the
// host scrolls and nothing can clip, and the rows are the app's own
// `.entity-row` shell. See [[UI-UX Design#Pickers]].
const props = defineProps({
  // An array, or `(query) => options | Promise<options>` for a server-backed
  // lookup. The function form is new: pickers whose vocabulary is too large to
  // preload can now query as the author types.
  options: { type: [Array, Function], default: () => [] },
  // Currently selected value (single-select mode). Excluded from the
  // list and shown as the placeholder label once resolved.
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

const query = ref('')
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
const { listId, open, loading, highlighted, available, activeDescendant, optionId, move, openList, closeList } = combo

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

function openDrop() {
  openList()
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
/* In flow, not an overlay (see the header comment). No max-height and no
   scroller of its own: the host panel is the scroller, so a long list cannot
   produce a second scrollbar inside the first. */
.sd-list {
  display: flex; flex-direction: column; gap: 3px;
  margin-top: 4px;
}
/* The `.entity-row` shell (assets/gm-panel.css) supplies the chrome — row
   padding, radius, fill and hover. Only the picker's own marks live here, and
   the highlight is a token tint rather than the raw rgba this used to carry. */
.sd-item.sd-item-active { background: var(--accent-12); }
.sd-item.sd-item-active .entity-name { color: var(--accent); }
.sd-state { font-size: 10px; padding: 6px 8px; color: var(--text-dim); }
</style>
