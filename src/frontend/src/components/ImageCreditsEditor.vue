<template>
  <!--
    Credits editor (GM): who made the artwork and where it came from.
    Self-contained — it PATCHes the image itself and emits `saved`, so any
    surface that already knows an image id can host it.

    **Auto-save** ([[B211]] follow-up): there is no Save button. Every edit is
    written shortly after you stop typing, the way the rest of the panel's fields
    behave, and the status line says so.
  -->
  <div class="credits-editor">
    <div v-for="(row, i) in rows" :key="i" class="credit-row">
      <select v-model="row.role" aria-label="Credit role" @change="onEdit(0)">
        <option v-for="role in ROLES" :key="role.key" :value="role.key">{{ role.label }}</option>
      </select>
      <input v-model="row.name" class="credit-name" placeholder="Name" aria-label="Credit name" @input="onEdit()" />
      <input v-model="row.url" class="credit-url" placeholder="https://…" aria-label="Credit link" @input="onEdit()" />
      <button type="button" class="credit-remove" title="Remove this credit" @click="removeRow(i)">✕</button>
    </div>

    <button type="button" class="credit-add" @click="addRow">＋ add credit</button>

    <label class="credit-field">
      <span>Licence</span>
      <input v-model="license" placeholder="CC BY-SA 4.0, or a licence URL" @input="onEdit()" />
    </label>
    <label class="credit-field">
      <span>Credit line</span>
      <input v-model="creditText" placeholder="exact wording to display, if one is required" @input="onEdit()" />
    </label>

    <div class="credit-status">
      <span v-if="error" class="credit-error">{{ error }}</span>
      <span v-else-if="saving" class="credit-ok">Saving…</span>
      <span v-else-if="savedAt" class="credit-ok">Saved</span>
    </div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps({
  imageId: { type: String, required: true },
  credits: { type: Array, default: () => [] },
  license: { type: String, default: '' },
  creditText: { type: String, default: '' },
})

const emit = defineEmits(['saved'])

//: Mirrors CREDIT_ROLES on the server, which validates them.
const ROLES = [
  { key: 'artist', label: 'Art by' },
  { key: 'source', label: 'Source' },
  { key: 'publisher', label: 'Published by' },
  { key: 'rights', label: 'Rights' },
]

//: How long to wait after the last keystroke before writing. Long enough that a
//: name is one request rather than one per letter, short enough that closing the
//: panel right after typing still saves (the unmount flushes anyway).
const DEBOUNCE_MS = 500

const rows = ref([])
const license = ref('')
const creditText = ref('')
const saving = ref(false)
const error = ref('')
const savedAt = ref(0)

function seed() {
  rows.value = (props.credits || []).map(c => ({ role: c.role || 'artist', name: c.name || '', url: c.url || '' }))
  license.value = props.license || ''
  creditText.value = props.creditText || ''
  error.value = ''
  savedAt.value = 0
}

//: Whether the local state has edits the server has not confirmed. Declared
//: **before** the watchers below, because the first one is `immediate` and runs
//: during setup — reading it from a later `let` is a temporal-dead-zone crash.
let dirty = false
//: Incremented on every edit, so a save that lands after further typing knows not
//: to call the editor clean again.
let editSeq = 0
let timer = null

// The viewer reuses one component instance across images, so follow the picture
// id rather than seeding once — otherwise switching image would show (and then
// save) the previous image's credits.
watch(() => props.imageId, () => { dirty = false; seed() }, { immediate: true })

// Before the first edit, follow the props: the viewer's opener may hand over only
// an id, and the picture's credits arrive with the list a moment later. After an
// edit the local state wins, so a save's own reload cannot clobber what is being
// typed.
watch(() => [props.credits, props.license, props.creditText], () => {
  if (!dirty) seed()
}, { deep: true })

function onEdit(delay = DEBOUNCE_MS) {
  dirty = true
  editSeq += 1
  if (timer) clearTimeout(timer)
  timer = setTimeout(save, delay)
}

function addRow() {
  // Deliberately does **not** save: the server drops blank rows, so writing now
  // would delete the row the user is about to type into. The first keystroke
  // schedules the save; a row left blank is simply nothing to persist.
  rows.value.push({ role: 'artist', name: '', url: '' })
  dirty = true
  editSeq += 1
}

function removeRow(index) {
  rows.value.splice(index, 1)
  onEdit(0)
}

async function save() {
  if (timer) { clearTimeout(timer); timer = null }
  if (!props.imageId) return
  const seq = editSeq
  saving.value = true
  error.value = ''
  try {
    const res = await fetch(`/api/v1/imagen/${encodeURIComponent(props.imageId)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        credits: rows.value,
        license: license.value,
        credit_text: creditText.value,
      }),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(data.detail || `Save failed (${res.status})`)
    savedAt.value = Date.now()
    // Only clean if nothing was typed while this request was in flight.
    if (editSeq === seq) dirty = false
    emit('saved')
  } catch (e) {
    error.value = e?.message || 'Save failed'
  } finally {
    saving.value = false
  }
}

// Closing the panel right after an edit must not lose it.
onBeforeUnmount(() => {
  if (timer) { clearTimeout(timer); timer = null; save() }
})
</script>

<style scoped>
.credits-editor { display: flex; flex-direction: column; gap: 5px; text-align: left; }
.credit-row { display: flex; gap: 4px; align-items: center; }
.credit-row select { font-size: 10px; }
.credit-name { flex: 1 1 40%; min-width: 0; }
.credit-url { flex: 1 1 50%; min-width: 0; }
.credit-row input, .credit-field input { font-size: 10px; padding: 2px 4px; }
.credit-remove {
  border: none; background: none; color: var(--text-dim); cursor: pointer;
  font-size: 11px; padding: 0 3px;
}
.credit-remove:hover { color: var(--danger, #e06c75); }
.credit-add {
  align-self: flex-start; font-size: 10px; padding: 2px 6px;
  border: 1px dashed var(--border); border-radius: 3px;
  background: none; color: var(--text-dim); cursor: pointer;
}
.credit-field { display: flex; flex-direction: column; gap: 2px; font-size: 10px; color: var(--text-dim); }
.credit-status { min-height: 13px; }
.credit-error { font-size: 10px; color: var(--danger, #e06c75); }
.credit-ok { font-size: 10px; color: var(--text-dim); }
</style>
