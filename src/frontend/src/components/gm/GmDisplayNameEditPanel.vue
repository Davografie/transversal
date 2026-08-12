<template>
  <div>
    <div class="ps-form">
      <label>Name</label>
      <input v-model="form.name" placeholder="Display name…" />
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
        <button class="row-del-btn" @click="removeRating(ri)" title="Remove rating">✕</button>
        <div v-if="showDiePicker === ri" class="die-options">
          <button
            v-for="d in DICE"
            :key="d"
            class="die-opt"
            @click="addDie(ri, d)"
          >{{ d }}</button>
        </div>
      </div>
      <button class="ps-add-btn" @click="addRating">+ Add Rating</button>
    </div>

    <div v-if="errorMsg" class="error-msg">{{ errorMsg }}</div>
    <div v-if="saving" class="saving-hint">Saving…</div>
  </div>
</template>

<script setup>
import { reactive, ref, computed, watch } from 'vue'
import { useApi } from '@/composables/useApi.js'
import { useTraitsConfig } from '@/composables/useTraitsConfig.js'

const { graphql } = useApi()
const { patchData } = useTraitsConfig()

const props = defineProps({
  allDisplayNames: { type: Array, default: () => [] },
  editIndex: { type: Number, default: null },
  traitId: { type: String, required: true },
})

const emit = defineEmits(['saved', 'deleted'])

const DICE = ['D4', 'D6', 'D8', 'D10', 'D12']

const isNew = computed(() => props.editIndex === null || props.editIndex === undefined)
const saving = ref(false)
const errorMsg = ref('')
const isDirty = ref(false)

// ── Form state ──
const entry = isNew.value ? { name: '', universe: '', ratings: [] } : (props.allDisplayNames[props.editIndex] || { name: '', universe: '', ratings: [] })

const form = reactive({
  name: entry.name || '',
  universe: entry.universe || '',
  ratings: (entry.ratings || []).map(r => [...r]),
})

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
function buildUpdatedList() {
  const list = props.allDisplayNames.map(dn => ({
    name: dn.name || '',
    universe: dn.universe || '',
    ratings: (dn.ratings || []).map(r => [...r]),
  }))
  const newEntry = {
    name: form.name.trim(),
    universe: form.universe || '',
    ratings: form.ratings.filter(r => r.length > 0),
  }
  if (isNew.value) {
    list.push(newEntry)
  } else {
    list[props.editIndex] = newEntry
  }
  return list.filter(dn => dn.name)
}

// ── Auto-save ──
let saveTimer = null
watch([
  () => form.name,
  () => form.universe,
  () => form.ratings.map(r => [...r]),
], () => {
  isDirty.value = true
  clearTimeout(saveTimer)
  saveTimer = setTimeout(() => doSave(), 500)
}, { deep: true })

async function doSave() {
  if (!isDirty.value) return
  saving.value = true
  errorMsg.value = ''
  try {
    const displayNames = buildUpdatedList()
    await graphql(
      `mutation($id: ID!, $input: TraitUpdateInput!) { updateTrait(id: $id, input: $input) { id } }`,
      { id: props.traitId, input: { displayNames } }
    )
    patchData('traits', props.traitId, { displayNames })
    isDirty.value = false
    emit('saved', displayNames)
  } catch (e) {
    errorMsg.value = e?.message || 'Save failed'
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.ps-form { display: flex; flex-direction: column; gap: 6px; }
.ps-form label { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; }
.ps-form input, .ps-form select {
  font-size: 12px; padding: 6px 8px;
  background: rgba(255,255,255,0.06); color: var(--text);
  border: 1px solid rgba(255,255,255,0.1); border-radius: 6px;
  width: 100%; box-sizing: border-box;
}

.empty { font-size: 11px; color: var(--text-dim); padding: 4px 0; }

.rating-row { position: relative; display: flex; align-items: center; gap: 4px; padding: 2px 0; flex-wrap: wrap; }
.rating-dice { display: flex; align-items: center; gap: 3px; font-size: 11px; flex-wrap: wrap; }

.die-chip {
  display: inline-block; padding: 2px 6px; background: rgba(255,255,255,0.1);
  border-radius: 4px; font-size: 11px; font-weight: 600;
}
.die-chip.clickable { cursor: pointer; transition: background 0.1s; }
.die-chip.clickable:hover { background: rgba(212,64,64,0.2); color: var(--danger); }

.add-chip {
  background: rgba(64,136,212,0.12); color: var(--accent); cursor: pointer;
  border: 1px solid rgba(64,136,212,0.2); padding: 1px 7px; font-size: 13px;
  transition: background 0.1s;
}
.add-chip:hover, .add-chip.active { background: var(--accent); color: #fff; }

.die-options {
  display: flex; gap: 3px; width: 100%; margin-top: 4px;
}
.die-opt {
  font-size: 11px; padding: 3px 6px; font-weight: 600;
  background: rgba(255,255,255,0.08); color: var(--text);
  border: 1px solid rgba(255,255,255,0.12); border-radius: 4px; cursor: pointer;
  transition: background 0.1s;
}
.die-opt:hover { background: var(--accent); color: #fff; }

.row-del-btn { font-size: 12px; padding: 2px 6px; background: none; color: var(--text-dim); border: none; cursor: pointer; border-radius: 3px; flex-shrink: 0; }
.row-del-btn:hover { color: var(--danger); background: rgba(212,64,64,0.12); }

.ps-add-btn { font-size: 12px; padding: 6px; margin-top: 4px; background: var(--accent-dim); color: var(--text); border-radius: 6px; border: none; cursor: pointer; width: 100%; }
.ps-add-btn:hover { background: var(--accent); }

.error-msg { font-size: 11px; color: var(--danger); margin-top: 8px; padding: 6px 8px; background: rgba(212,64,64,0.08); border-radius: 4px; }
.saving-hint { font-size: 10px; color: var(--text-dim); text-align: center; margin-top: 6px; }
</style>
