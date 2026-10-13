<template>
  <div class="inst-panel">
    <p class="inst-summary">
      <strong>{{ instances.length }}</strong> instance{{ instances.length === 1 ? '' : 's' }} of
      <strong>{{ props.traitName || 'this trait' }}</strong>
      <span v-if="counts.entity"> · {{ counts.entity }} on entities</span>
      <span v-if="counts.projection"> · {{ counts.projection }} on bodies</span>
      <span v-if="counts.relationship"> · {{ counts.relationship }} on relationships</span>
      <span v-if="counts.traitsetting"> · {{ counts.traitsetting }} as sub-traits</span>
    </p>

    <input v-model="filters.q" class="filter-input" placeholder="Filter by owner, statement, note, tag…" />

    <div class="filter-grid">
      <select v-model="filters.kind" class="filter-select">
        <option value="">Anywhere</option>
        <option v-for="k in HOST_KINDS" :key="k" :value="k">{{ hostKindLabel(k) }}</option>
      </select>
      <select v-model="filters.ratingType" class="filter-select">
        <option value="">Any rating</option>
        <option value="STATIC">Static</option>
        <option value="RESOURCE">Resource</option>
        <option value="CHALLENGE">Challenge</option>
        <option value="EMPTY">Empty</option>
      </select>
      <select v-model="filters.die" class="filter-select">
        <option value="">Any die</option>
        <option v-for="d in DICE" :key="d" :value="d">{{ d.toLowerCase() }}</option>
      </select>
      <select v-model="filters.enabled" class="filter-select">
        <option value="">Enabled or not</option>
        <option value="yes">Enabled</option>
        <option value="no">Disabled</option>
      </select>
      <select v-model="filters.polarity" class="filter-select">
        <option value="">Any polarity</option>
        <option value="POSITIVE">Positive</option>
        <option value="NEGATIVE">Negative</option>
      </select>
    </div>

    <div class="select-bar">
      <Button type="button" variant="secondary" size="sm" @click="toggleAllMatching">
        <span class="select-all-pick" :class="{ selected: allMatchingSelected }">{{ allMatchingSelected ? '✓' : '+' }}</span>
        <span>All matching ({{ shown.length }})</span>
      </Button>
      <span class="selected-count">{{ selectedIds.length }} selected</span>
    </div>

    <p v-if="error" class="switch-error">{{ error }}</p>
    <p v-if="loadError" class="switch-error">{{ loadError }}</p>

    <GmList
      :items="shown"
      item-key="id"
      selectable
      :selected-ids="selectedIds"
      :loading="loading"
      empty-text="No instances match the current filters"
      @toggle="onToggle"
    >
      <template #item="{ item: t }">
        <div class="inst-row">
          <div class="inst-host">
            <span class="host-kind" :class="'kind-' + (t.host?.kind || 'entity')">{{ hostKindLabel(t.host?.kind) }}</span>
            <span class="host-name">{{ hostLine(t.host) }}</span>
            <span v-if="hostTypeBadge(t.host)" class="host-type">{{ hostTypeBadge(t.host) }}</span>
            <span v-if="hostDetail(t.host)" class="host-detail">{{ hostDetail(t.host) }}</span>
          </div>
          <div class="inst-meta">
            <span class="die-badge" :class="'die-' + (t.dice?.[0] || 'none').toLowerCase()">{{ t.dice?.length ? t.dice.join('+') : '—' }}</span>
            <span class="rating-badge" :class="'rt-' + (t.ratingType || 'static').toLowerCase()">{{ ratingLabel(t.ratingType) }}</span>
            <span class="polarity-badge" :class="'pol-' + (t.polarity || 'positive').toLowerCase()">{{ polarityLabel(t.polarity) }}</span>
            <span v-if="!t.enabled" class="off-badge">disabled</span>
          </div>
          <span v-if="t.statement" class="inst-statement">{{ t.statement }}</span>
        </div>
      </template>
    </GmList>

    <div class="batch-actions">
      <h4 class="ps-section-title">Apply to {{ selectedIds.length }} selected</h4>
      <div class="action-row">
        <label>Rating type</label>
        <select v-model="apply.ratingType">
          <option value="">— no change —</option>
          <option value="STATIC">Static</option><option value="RESOURCE">Resource</option>
          <option value="CHALLENGE">Challenge</option><option value="EMPTY">Empty</option>
        </select>
      </div>
      <div class="action-row">
        <label>Dice</label>
        <select v-model="apply.dice">
          <option value="">— no change —</option>
          <option v-for="d in DICE" :key="d" :value="d">{{ d.toLowerCase() }}</option>
          <option value="CLEAR">clear (no dice)</option>
        </select>
      </div>
      <div class="action-row">
        <label>Polarity</label>
        <select v-model="apply.polarity">
          <option value="">— no change —</option>
          <option value="POSITIVE">Positive</option>
          <option value="NEGATIVE">Negative</option>
        </select>
      </div>
      <div class="action-row">
        <label>Enabled</label>
        <select v-model="apply.enabled">
          <option value="">— no change —</option>
          <option value="yes">Enable</option>
          <option value="no">Disable</option>
        </select>
      </div>
      <Button class="ps-add-btn" :loading="applying" :disabled="applying || !selectedIds.length" @click="applyBatch" variant="secondary" block>
        {{ applying ? 'Applying…' : `Apply to ${selectedIds.length} selected` }}
      </Button>

      <!-- Two-step, like ending a player's session: this is the one action here
           that cannot be undone by editing the row again. -->
      <Button v-if="!confirmingRemove" variant="danger" block :disabled="applying || !selectedIds.length" @click="confirmingRemove = true">
        Remove {{ selectedIds.length }} selected…
      </Button>
      <Button v-else variant="danger" solid block :loading="removing" :disabled="removing" @click="removeSelected">
        {{ removing ? 'Removing…' : `Really remove ${selectedIds.length}?` }}
      </Button>

      <p v-if="status" class="status" :class="{ 'status-err': statusIsError }">{{ status }}</p>
    </div>
  </div>
</template>

<script setup>
// Every instance of one trait definition, wherever it hangs, with the bulk edits
// a migration cleanup needs. The read is the API's `traitInstances`; the host
// wording and the filter predicate are `utils/traitInstanceHost.js` (pure, and
// what `check-trait-instances.mjs` runs).
import { computed, onMounted, reactive, ref } from 'vue'
import { useTraitInstances } from '@/composables/useTraitInstances.js'
import {
  HOST_KINDS, hostDetail, hostKindLabel, hostLine, hostTypeBadge, instanceMatches, kindCounts, sortInstances,
} from '@/utils/traitInstanceHost.js'
import GmList from '@/components/ui/GmList.vue'
import Button from '@/components/ui/Button.vue'

const props = defineProps({
  traitId: { type: String, required: true },
  traitName: { type: String, default: '' },
})

const DICE = ['D4', 'D6', 'D8', 'D10', 'D12']

const { instances, loading, error: loadError, fetchInstances, updateInstances, removeInstances } = useTraitInstances()

const selectedIds = ref([])
const selectedSet = computed(() => new Set(selectedIds.value))

const filters = reactive({ q: '', kind: '', ratingType: '', die: '', enabled: '', polarity: '' })

const shown = computed(() =>
  sortInstances(instances.value.filter((t) => instanceMatches(t, filters))),
)
const counts = computed(() => kindCounts(instances.value))

const allMatchingSelected = computed(() =>
  shown.value.length > 0 && shown.value.every((t) => selectedSet.value.has(t.id)),
)

function onToggle(t) {
  const next = new Set(selectedIds.value)
  if (next.has(t.id)) next.delete(t.id)
  else next.add(t.id)
  selectedIds.value = [...next]
}

function toggleAllMatching() {
  const next = new Set(selectedIds.value)
  if (allMatchingSelected.value) shown.value.forEach((t) => next.delete(t.id))
  else shown.value.forEach((t) => next.add(t.id))
  selectedIds.value = [...next]
}

function ratingLabel(rt) {
  if (!rt) return 'static'
  return rt.charAt(0) + rt.slice(1).toLowerCase()
}

function polarityLabel(p) {
  return p === 'NEGATIVE' ? 'neg' : 'pos'
}

// ── Bulk edits ───────────────────────────────────────
const apply = reactive({ ratingType: '', dice: '', polarity: '', enabled: '' })
const applying = ref(false)
const removing = ref(false)
const confirmingRemove = ref(false)
const status = ref('')

const statusIsError = computed(() => /fail|could not|choose/i.test(status.value))

function buildChanges() {
  const changes = {}
  if (apply.ratingType) changes.ratingType = apply.ratingType
  if (apply.dice === 'CLEAR') changes.dice = []
  else if (apply.dice) changes.dice = [apply.dice]
  if (apply.polarity) changes.polarity = apply.polarity
  if (apply.enabled) changes.enabled = apply.enabled === 'yes'
  return changes
}

async function applyBatch() {
  if (!selectedIds.value.length) { status.value = 'Select at least one instance.'; return }
  const changes = buildChanges()
  if (Object.keys(changes).length === 0) { status.value = 'Choose at least one field to set.'; return }

  applying.value = true
  status.value = ''
  const ids = [...selectedIds.value]
  try {
    const { succeeded, failed } = await updateInstances(ids, changes)
    status.value = failed.length
      ? `Changed ${succeeded.length}, failed ${failed.length}.`
      : `Changed ${succeeded.length} instance${succeeded.length === 1 ? '' : 's'}.`
    if (succeeded.length) selectedIds.value = failed
    await fetchInstances(props.traitId)
  } catch (e) {
    status.value = 'Batch update failed: ' + (e?.message || e)
  } finally {
    applying.value = false
  }
}

async function removeSelected() {
  const ids = [...selectedIds.value]
  removing.value = true
  status.value = ''
  try {
    const { succeeded, failed } = await removeInstances(ids)
    status.value = failed.length
      ? `Removed ${succeeded.length}, failed ${failed.length}.`
      : `Removed ${succeeded.length} instance${succeeded.length === 1 ? '' : 's'}.`
    selectedIds.value = failed
    confirmingRemove.value = false
    await fetchInstances(props.traitId)
  } catch (e) {
    status.value = 'Remove failed: ' + (e?.message || e)
  } finally {
    removing.value = false
  }
}

onMounted(() => fetchInstances(props.traitId))
</script>

<style scoped>
.inst-panel { display: flex; flex-direction: column; gap: 8px; }
.inst-summary { margin: 0; font-size: 11px; color: var(--text-dim); }
.inst-summary strong { color: var(--text); }

.filter-input { width: 100%; font-size: 12px; padding: 6px 8px; box-sizing: border-box; }
.filter-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.filter-select { width: 100%; font-size: 12px; padding: 6px 8px; box-sizing: border-box; }

.select-bar { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.select-all-pick { font-weight: 700; font-size: 12px; width: 16px; text-align: center; color: var(--text-dim); }
.select-all-pick.selected { color: var(--success); }
.selected-count { font-size: 11px; color: var(--accent); font-variant-numeric: tabular-nums; }

/* The host is the row's headline — it is what the list exists to answer. */
.inst-row { display: flex; flex-direction: column; gap: 2px; width: 100%; min-width: 0; }
.inst-host { display: flex; align-items: baseline; gap: 5px; flex-wrap: wrap; min-width: 0; }
.host-kind {
  flex: 0 0 auto; font-size: 8px; text-transform: uppercase; letter-spacing: 0.4px;
  padding: 1px 4px; border-radius: 3px; color: var(--text-dim); background: var(--overlay-8);
}
.host-kind.kind-projection { color: var(--accent-pale); background: var(--accent-16); }
.host-kind.kind-relationship { color: var(--success); background: var(--success-12); }
.host-kind.kind-traitsetting { color: var(--warn, var(--text-dim)); background: var(--overlay-12); }
.host-name { font-size: 12px; color: var(--text); }
.host-type { font-size: 9px; text-transform: uppercase; letter-spacing: 0.4px; color: var(--text-dim); }
.host-detail { font-size: 10px; color: var(--text-dim); }

.inst-meta { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.die-badge { font-weight: 700; font-size: 11px; min-width: 24px; }
.die-d4 { color: var(--die-d4); } .die-d6 { color: var(--die-d6); } .die-d8 { color: var(--die-d8); }
.die-d10 { color: var(--die-d10); } .die-d12 { color: var(--die-d12); }
.die-none { color: var(--text-dim); }

.rating-badge { font-size: 9px; text-transform: uppercase; padding: 1px 6px; border-radius: 3px; font-weight: 600; letter-spacing: 0.3px; }
.rt-static { background: var(--overlay-12); color: var(--text); }
.rt-resource { background: var(--accent-16); color: var(--accent); }
.rt-challenge { background: var(--danger-12); color: var(--danger); }
.rt-empty { background: transparent; color: var(--text-dim); border: 1px solid var(--text-dim); }

.polarity-badge { font-size: 9px; text-transform: uppercase; padding: 1px 6px; border-radius: 3px; font-weight: 600; }
.pol-positive { background: var(--success-12); color: var(--success); }
.pol-negative { background: var(--danger-12); color: var(--danger); }
.off-badge { font-size: 9px; text-transform: uppercase; color: var(--danger); border: 1px solid var(--danger-20); border-radius: 3px; padding: 1px 5px; }

.inst-statement { font-size: 11px; color: var(--text-dim); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.batch-actions {
  margin-top: 4px; padding-top: 8px; border-top: 1px solid var(--overlay-8);
  display: flex; flex-direction: column; gap: 6px;
}
.action-row { display: flex; flex-direction: column; gap: 3px; }
.action-row label { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; }
.action-row select { width: 100%; font-size: 12px; padding: 6px 8px; box-sizing: border-box; }
.status { font-size: 12px; color: var(--success); margin: 0; }
.status-err { color: var(--danger); }
</style>
