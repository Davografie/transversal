<template>
  <div class="tp-root" :class="{ 'tp-multi': multiple }">
    <!-- Several picks render as chips and the dropdown appends (it already
         excludes what is chosen), so one value stays a string and several
         become a list — the one-or-several shape every filter follows. -->
    <div v-if="multiple && picked.length" class="tp-chips">
      <span v-for="v in picked" :key="v" class="tp-chip">
        {{ labelFor(v) }}
        <button type="button" class="tp-chip-x" :title="`Remove ${labelFor(v)}`"
                @click="remove(v)">×</button>
      </span>
    </div>
    <div class="tp-input">
      <SearchDropdown
        :options="candidates"
        :model-value="multiple ? '' : modelValue"
        :exclude-ids="excludeCandidates"
        :placeholder="placeholder"
        value-key="id"
        label-key="name"
        :fallback-label="resolvedLabel"
        :clearable="multiple ? false : clearable"
        @select="pick"
        @clear="clear"
      >
        <template #option="{ option }">
          <span class="entity-name">{{ option.name }}</span>
          <span v-if="option.subtitle || option.universe" class="entity-universe tp-universe">{{ option.subtitle || option.universe }}</span>
        </template>
      </SearchDropdown>
    </div>
    <button
      v-if="allowFilters && filterFields.length"
      class="tp-filter"
      :class="{ active: activeCount > 0 }"
      :title="activeCount ? `${activeCount} filter${activeCount > 1 ? 's' : ''} narrowing these results` : 'Filter these results'"
      @click="filtersOpen = !filtersOpen"
    >⚙<span v-if="activeCount" class="tp-filter-count">{{ activeCount }}</span></button>
    <div v-if="filtersOpen" class="tp-filter-panel" @click.stop>
      <div class="tp-filter-head">
        <span>Filter results</span>
        <button v-if="activeCount" class="tp-filter-clear" @click="clearFilters">Clear</button>
      </div>
      <label v-for="ff in filterFields" :key="ff.field" class="tp-filter-row">
        <span class="tp-filter-label">{{ ff.label }}</span>
        <input
          v-if="ff.valueType === 'boolean'"
          type="checkbox"
          :checked="!!effective[ff.field]"
          @change="setValue(ff.field, $event.target.checked ? true : null)"
        />
        <select
          v-else-if="ff.options?.length"
          :value="effective[ff.field] ?? ''"
          @change="setValue(ff.field, $event.target.value || null)"
        >
          <option value="">Any</option>
          <option v-for="o in ff.options" :key="o" :value="o">{{ o }}</option>
        </select>
        <input
          v-else
          type="text"
          :value="effective[ff.field] ?? ''"
          placeholder="Any"
          @input="setValue(ff.field, $event.target.value || null)"
        />
      </label>
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
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import SearchDropdown from './SearchDropdown.vue'
import { useEffectTargets } from '@/composables/useEffectTargets.js'
import { useSfxMeta } from '@/composables/useSfxMeta.js'
import { useApi } from '@/composables/useApi.js'

// Generic target picker — resolves candidates through the backend's shared
// `targetCandidates` resolver (same candidate set the random mode uses) and
// renders them via the shared SearchDropdown. Every entity picker in the GM
// panel should route through this instead of fetching its own data.
//
// **Filters.** The backend describes which candidate fields can narrow a kind
// (`targetFilterFields`: field / label / valueType / kinds / options), and this
// picker offers them behind the ⚙ button — so a picker gets facet filtering
// without its caller building the UI. Selections merge over the `filter` prop
// (caller-set filters win nothing: local selections take precedence for the
// same field) and are sent with every candidate lookup. New fields appear here
// automatically as the backend adds them.
const props = defineProps({
  modelValue: { type: [String, Array], default: '' },
  kind: { type: String, required: true },
  scope: { type: String, default: '' },
  filter: { type: Object, default: null },
  entityId: { type: String, default: '' },
  action: { type: String, default: '' },
  placeholder: { type: String, default: 'Choose target…' },
  allowRandom: { type: Boolean, default: false },
  /** Show the ⚙ facet popout. Callers that build their own filter UI (the
      effect form, the target wizard) set this false so filters appear once. */
  allowFilters: { type: Boolean, default: true },
  clearable: { type: Boolean, default: true },
  excludeIds: { type: Array, default: () => [] },
  /** Pick several: the picks become chips and `modelValue` is a list. The
      caller stores one as a scalar (`==`) and several as a list (`in`). */
  multiple: { type: Boolean, default: false },
  /** How a candidate becomes the *stored* value. A universe field holds the
      world's handle (`earth`), not its entity id (`universe-earth`), so the
      caller supplies the mapping; everything else stores the id. */
  optionToValue: { type: Function, default: null },
})

const emit = defineEmits(['update:modelValue', 'select', 'update:filter'])

const { candidates, fetchTargets } = useEffectTargets()
const { load: loadSfxMeta, targetFilterFields } = useSfxMeta()
const { graphql } = useApi()

// A saved value whose candidate isn't in the loaded set would otherwise render
// as a raw id. The backend resolves the name through the same resolver the card
// text uses — so the picker shows "Beast", never "trait-2081905".
function toValue(opt) {
  return props.optionToValue ? (props.optionToValue(opt) || '') : (opt?.id || '')
}

const picked = computed(() => {
  const v = props.modelValue
  return Array.isArray(v) ? v.filter(Boolean) : (v ? [v] : [])
})

const resolvedLabels = ref({})
watch([() => props.modelValue, candidates], async ([value, list]) => {
  const values = Array.isArray(value) ? value.filter(Boolean) : (value ? [value] : [])
  const known = new Set((list || []).map((c) => toValue(c)))
  const unknown = values.filter((v) => !known.has(v))
  if (!unknown.length) {
    resolvedLabels.value = {}
    return
  }
  try {
    const data = await graphql(
      `query($ids: [ID!]!) { targetLabels(ids: $ids) { id name } }`,
      { ids: unknown },
    )
    const names = {}
    for (const row of (data?.targetLabels || [])) names[row.id] = row.name
    resolvedLabels.value = names
  } catch (e) { /* the raw value stays as the last resort */ }
})

const resolvedLabel = computed(() =>
  props.multiple ? '' : (resolvedLabels.value[props.modelValue] || ''))

function labelFor(value) {
  const hit = (candidates.value || []).find((c) => toValue(c) === value)
  return hit?.name || resolvedLabels.value[value] || value
}

// In chip/append mode the dropdown must not offer what is already picked. It
// excludes by candidate id, so the picked *values* are mapped back.
const excludeCandidates = computed(() => {
  if (!props.multiple) return props.excludeIds
  const chosen = new Set(picked.value)
  return [...props.excludeIds,
          ...(candidates.value || []).filter((c) => chosen.has(toValue(c))).map((c) => c.id)]
})

function remove(value) {
  emit('update:modelValue', picked.value.filter((v) => v !== value))
}

// Fields the backend says can narrow this kind.
const filterFields = computed(() =>
  targetFilterFields.value.filter((ff) => !ff.kinds?.length || ff.kinds.includes(props.kind))
)

const localFilter = ref({})
const filtersOpen = ref(false)

// Caller-set filter first, then whatever the user picked here.
const effective = computed(() => {
  const merged = { ...(props.filter || {}) }
  for (const [k, v] of Object.entries(localFilter.value)) {
    if (v === null || v === undefined || v === '') delete merged[k]
    else merged[k] = v
  }
  return merged
})

const activeCount = computed(() => Object.keys(effective.value).length)

function setValue(field, value) {
  localFilter.value = { ...localFilter.value, [field]: value }
  emit('update:filter', effective.value)
}

function clearFilters() {
  localFilter.value = {}
  emit('update:filter', effective.value)
}

// The 🎲 button never picks an id the caller explicitly excluded.
const randomCandidates = computed(() =>
  candidates.value.filter((c) => !props.excludeIds.includes(c.id))
)

function pick(opt) {
  const value = toValue(opt)
  if (props.multiple) {
    // The dropdown hides what is already chosen, so this is an append; a
    // repeat (from the dice button) would be a no-op rather than a duplicate.
    const next = picked.value.includes(value)
      ? picked.value.filter((v) => v !== value)
      : [...picked.value, value]
    emit('update:modelValue', next)
  } else {
    emit('update:modelValue', value)
  }
  emit('select', opt)
}

function clear() {
  emit('update:modelValue', props.multiple ? [] : '')
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
    activeCount.value ? effective.value : null,
  )
}

function onDocumentClick(e) {
  if (!filtersOpen.value) return
  if (e.target.closest && e.target.closest('.tp-root')) return
  filtersOpen.value = false
}

onMounted(() => {
  loadSfxMeta()
  load()
  document.addEventListener('click', onDocumentClick, true)
})
onBeforeUnmount(() => document.removeEventListener('click', onDocumentClick, true))

watch(() => [props.kind, props.scope, props.entityId, props.action, props.filter], load)
watch(effective, load)
</script>

<style scoped>
.tp-root { position: relative; display: flex; align-items: center; gap: 4px; width: 100%; }
/* Chip/append mode: the picks take their own row above the dropdown. */
.tp-multi { flex-wrap: wrap; }
.tp-chips { flex-basis: 100%; display: flex; flex-wrap: wrap; gap: 4px; }
.tp-chip {
  display: inline-flex; align-items: center; gap: 4px; padding: 1px 4px 1px 6px;
  background: var(--overlay-8); border: 1px solid var(--overlay-12);
  border-radius: var(--radius-xs); font-size: 10px; color: var(--text);
}
.tp-chip-x {
  border: 0; background: none; padding: 0 2px; cursor: pointer;
  color: var(--text-dim); font-size: 11px; line-height: 1;
}
.tp-chip-x:hover { color: var(--accent); }
.tp-input { flex: 1; min-width: 0; }
/* The results are an inline list now, so the field can be far taller than these
   buttons; `align-self` keeps them on the field's line instead of floating in
   the middle of the list. When the list is closed the row is the buttons' own
   height, so this changes nothing. */
.tp-random {
  flex: none; align-self: flex-start; width: 26px; height: 24px; line-height: 1; cursor: pointer;
  background: var(--overlay-6); border: 1px solid var(--overlay-12);
  border-radius: var(--radius-xs); color: var(--text-dim); font-size: 13px;
}
.tp-random:hover:not(:disabled) { color: var(--accent); border-color: var(--accent); }
.tp-random:disabled { opacity: 0.4; cursor: not-allowed; }
/* Result rows are the app's `.entity-row` + `.entity-name` / `.entity-universe`
   shell (assets/gm-panel.css), supplied by SearchDropdown; all this adds is the
   trailing secondary that must not wrap. */
.tp-universe { margin-left: 8px; white-space: nowrap; }

.tp-filter {
  flex: none; align-self: flex-start; position: relative; width: 26px; height: 24px; line-height: 1; cursor: pointer;
  background: var(--overlay-6); border: 1px solid var(--overlay-12);
  border-radius: var(--radius-xs); color: var(--text-dim); font-size: 12px;
}
.tp-filter:hover { color: var(--accent); border-color: var(--accent); }
.tp-filter.active { color: var(--accent); border-color: var(--accent); background: var(--accent-12); }
.tp-filter-count {
  position: absolute; top: -6px; right: -6px; min-width: 13px; height: 13px;
  border-radius: var(--radius-sm); background: var(--accent); color: var(--text-on-accent);
  font-size: 9px; font-weight: 700; line-height: 13px; text-align: center;
}
.tp-filter-panel {
  position: absolute; top: calc(100% + 4px); right: 0; z-index: 40;
  min-width: 210px; padding: 8px; display: flex; flex-direction: column; gap: 6px;
  background: var(--bg-panel); border: 1px solid var(--overlay-12); border-radius: var(--radius-sm);
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.45);
}
.tp-filter-head {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  font-size: 10px; text-transform: uppercase; letter-spacing: 0.6px; color: var(--text-dim);
}
.tp-filter-clear {
  background: none; border: 0; padding: 0; cursor: pointer;
  color: var(--accent); font-size: 10px; text-transform: uppercase; letter-spacing: 0.6px;
}
.tp-filter-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.tp-filter-label { font-size: 11px; color: var(--text-dim); }
.tp-filter-row select, .tp-filter-row input[type="text"] {
  flex: 1; max-width: 120px; padding: 3px 6px; font-size: 11px;
  background: var(--overlay-4); border: 1px solid var(--overlay-12);
  border-radius: var(--radius-xs); color: var(--text);
}
</style>
