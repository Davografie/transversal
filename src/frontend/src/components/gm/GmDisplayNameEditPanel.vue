<template>
  <div>
    <div class="ps-form">
      <label>Name</label>
      <input ref="nameInput" v-model="form.name" placeholder="Display name…" />
      <label>Universe</label>
      <select v-model="form.universe">
        <option value="">-- pick --</option>
        <option value="earth">Earth</option>
        <option value="three_realms">Three Realms</option>
        <option value="*">* (any)</option>
      </select>

      <label>Ratings</label>
      <div v-if="form.ratings.length === 0" class="empty">No ratings — matches any dice</div>
      <div v-for="(rating, ri) in form.ratings" :key="ri" class="rating-row">
        <span class="rating-dice">
          <span
            v-for="(d, di) in rating"
            :key="di"
            class="die-chip clickable"
            @click="removeDie(ri, di)"
            title="Click to remove"
          >{{ d }}</span>
          <button
            class="die-chip add-chip"
            :class="{ active: showDiePicker === ri }"
            @click="showDiePicker = showDiePicker === ri ? null : ri"
          >+</button>
        </span>
        <Button class="row-del-btn" @click="removeRating(ri)" title="Remove rating" variant="danger-ghost" size="sm">✕</Button>
        <div v-if="showDiePicker === ri" class="die-options">
          <button
            v-for="d in DICE"
            :key="d"
            class="die-opt"
            @click="addDie(ri, d)"
          >{{ d }}</button>
        </div>
      </div>
      <Button class="ps-add-btn" @click="addRating" variant="secondary" block>+ Add Rating</Button>
    </div>

    <div v-if="errorMsg" class="error-msg">{{ errorMsg }}</div>
    <div v-if="saving" class="saving-hint">Saving…</div>
  </div>
</template>

<script setup>
import { reactive, ref, computed, watch, inject, nextTick } from 'vue'
import { useApi } from '@/composables/useApi.js'
import { useTraitsConfig } from '@/composables/useTraitsConfig.js'
import Button from '@/components/ui/Button.vue'

const { graphql } = useApi()
const { patchData } = useTraitsConfig()

const props = defineProps({
  allDisplayNames: { type: Array, default: () => [] },
  editIndex: { type: Number, default: null },
  traitId: { type: String, required: true },
})

const emit = defineEmits(['saved', 'deleted'])

// The opener hands the *live* display-name list across in the panel spec's
// `context`, because a panel's own `provide` cannot reach its child panels (they
// are rendered by `Panel.vue`, as siblings of the slot outlet — see
// `PanelScope.vue`). Reading the live list rather than the `allDisplayNames`
// prop matters: a prop is captured when the panel opens, so a second entry saved
// from this same panel would rebuild the list from that stale snapshot and drop
// the first. The prop stays as the fallback for a panel opened outside that tree.
const displayNamesDraft = inject('displayNamesDraft', null)
const liveList = () => displayNamesDraft?.value ?? props.allDisplayNames

const DICE = ['D4', 'D6', 'D8', 'D10', 'D12']

const isNew = computed(() => props.editIndex === null || props.editIndex === undefined)
const saving = ref(false)
const errorMsg = ref('')
const isDirty = ref(false)
const nameInput = ref(null)

// ── Form state ──
// Seeded by `seedForm` below. The panel is *reused in place* when the opener
// replaces its spec — add → edit, edit → add, and editing another row all share
// this component with no identity `id` — so the fields cannot be built once here
// and then left alone.
const form = reactive({ name: '', universe: '', ratings: [] })

const showDiePicker = ref(null)  // rating index with open picker, or null

function addRating() {
  form.ratings.push([])
  showDiePicker.value = form.ratings.length - 1
}

function removeRating(ri) {
  form.ratings.splice(ri, 1)
  if (showDiePicker.value === ri) showDiePicker.value = null
}

function addDie(ri, die) {
  form.ratings[ri].push(die)
  showDiePicker.value = null
}

function removeDie(ri, di) {
  form.ratings[ri].splice(di, 1)
  if (form.ratings[ri].length === 0) {
    form.ratings.splice(ri, 1)
  }
}

// ── Build updated list ──
// Pure, so the check script can run it directly rather than restating it.
function mergeDisplayName(list, entry, editIndex) {
  const out = (list || []).map(dn => ({
    name: dn.name || '',
    universe: dn.universe || '',
    ratings: (dn.ratings || []).map(r => [...r]),
  }))
  const next = {
    name: (entry.name || '').trim(),
    universe: entry.universe || '',
    ratings: (entry.ratings || []).filter(r => r.length > 0).map(r => [...r]),
  }
  if (editIndex === null || editIndex === undefined) out.push(next)
  else out[editIndex] = next
  return out.filter(dn => dn.name)
}

function buildUpdatedList() {
  return mergeDisplayName(liveList(), form, props.editIndex)
}

function entrySignature() {
  return JSON.stringify([form.name, form.universe, form.ratings])
}

// ── Auto-save ──
let saveTimer = null
// Set while `seedForm` writes the form, so seeding does not look like a new edit
// and schedule a save (which would also make the empty add form write itself).
let suppressWatch = false

// Load the form from the entry the spec now points at: blank for an add, the
// entry at `editIndex` for an edit. Runs at setup and again when the spec changes
// identity, because a reused instance would otherwise keep the previous entry in
// its fields — editing a row after adding would save the added text into it, and
// adding after an edit would append the edited text a second time.
function seedForm() {
  const source = isNew.value
    ? { name: '', universe: '', ratings: [] }
    : (liveList()[props.editIndex] || { name: '', universe: '', ratings: [] })
  suppressWatch = true
  form.name = source.name || ''
  form.universe = source.universe || ''
  form.ratings = (source.ratings || []).map(r => [...r])
  showDiePicker.value = null
  isDirty.value = false
  clearTimeout(saveTimer)
  nextTick(() => { suppressWatch = false })
}

seedForm()

// Keyed on the spec's *identity*, not its content: a re-open with the same index
// (pressing `+ Add Display Name` twice) is left alone, so in-progress typing is
// never thrown away.
watch([() => props.editIndex, () => props.traitId], seedForm)

watch([
  () => form.name,
  () => form.universe,
  () => form.ratings.map(r => [...r]),
], () => {
  if (suppressWatch) return
  isDirty.value = true
  clearTimeout(saveTimer)
  saveTimer = setTimeout(() => doSave(), 500)
}, { deep: true })

// A *new* entry leaves the panel open and ready for the next one: it goes back to
// a blank "Add Display Name" and focuses the name field. The panel is reused in
// place when the same component is opened again (`Panel.openChild` replaces the
// spec and Vue reuses the instance), so without this the next `+ Add Display Name`
// shows the entry that was just saved instead of a fresh form — display names
// could not be added consecutively.
function resetForm() {
  seedForm()
  nextTick(() => nameInput.value?.focus())
}

async function doSave() {
  if (!isDirty.value) return
  saving.value = true
  errorMsg.value = ''
  const wasNew = isNew.value
  const snapshot = entrySignature()
  try {
    const displayNames = buildUpdatedList()
    await graphql(
      `mutation($id: ID!, $input: TraitUpdateInput!) { updateTrait(id: $id, input: $input) { id } }`,
      { id: props.traitId, input: { displayNames } }
    )
    patchData('traits', props.traitId, { displayNames })
    // Typing that landed while this write was in flight is the newer truth: leave
    // it dirty for its own debounce, and never reset the form under it.
    const unchanged = entrySignature() === snapshot
    if (unchanged) isDirty.value = false
    emit('saved', displayNames)
    if (wasNew && unchanged) resetForm()
  } catch (e) {
    errorMsg.value = e?.message || 'Save failed'
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.ps-form input, .ps-form select {
  font-size: 12px; padding: 6px 8px;
  background: var(--overlay-6); color: var(--text);
  border: 1px solid var(--overlay-10); border-radius: 6px;
  width: 100%; box-sizing: border-box;
}

.empty { font-size: 11px; color: var(--text-dim); padding: 4px 0; }

.rating-row { position: relative; display: flex; align-items: center; gap: 4px; padding: 2px 0; flex-wrap: wrap; }
.rating-dice { display: flex; align-items: center; gap: 3px; font-size: 11px; flex-wrap: wrap; }

.die-chip {
  display: inline-block; padding: 2px 6px; background: var(--overlay-10);
  border-radius: 4px; font-size: 11px; font-weight: 600;
}
.die-chip.clickable { cursor: pointer; transition: background 0.1s; }
.die-chip.clickable:hover { background: var(--danger-20); color: var(--danger); }

.add-chip {
  background: var(--accent-12); color: var(--accent); cursor: pointer;
  border: 1px solid var(--accent-20); padding: 1px 7px; font-size: 13px;
  transition: background 0.1s;
}
.add-chip:hover, .add-chip.active { background: var(--accent); color: var(--text-on-accent); }

.die-options {
  display: flex; gap: 3px; width: 100%; margin-top: 4px;
}
.die-opt {
  font-size: 11px; padding: 3px 6px; font-weight: 600;
  background: var(--overlay-8); color: var(--text);
  border: 1px solid var(--overlay-12); border-radius: 4px; cursor: pointer;
  transition: background 0.1s;
}
.die-opt:hover { background: var(--accent); color: var(--text-on-accent); }

.row-del-btn { flex-shrink: 0; }

.ps-add-btn { margin-top: 4px; }

.error-msg { font-size: 11px; color: var(--danger); margin-top: 8px; padding: 6px 8px; background: var(--danger-8); border-radius: 4px; }
.saving-hint { font-size: 10px; color: var(--text-dim); text-align: center; margin-top: 6px; }
</style>
