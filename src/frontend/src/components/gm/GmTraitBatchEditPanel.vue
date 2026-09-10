<template>
  <div class="batch-panel">
    <input v-model="search" class="filter-input" placeholder="Filter traits by name or id…" />

    <div class="filter-grid">
      <select v-model="traitsetId" class="filter-select">
        <option value="">All traitsets</option>
        <option v-for="ts in traitsets" :key="ts.id" :value="ts.id">{{ ts.name }}</option>
      </select>
      <select v-model="ratingType" class="filter-select">
        <option value="">Any rating</option>
        <option value="STATIC">Static</option>
        <option value="RESOURCE">Resource</option>
        <option value="CHALLENGE">Challenge</option>
        <option value="EMPTY">Empty</option>
      </select>
      <select v-model="dieType" class="filter-select">
        <option value="">Any die</option>
        <option value="D4">d4</option><option value="D6">d6</option><option value="D8">d8</option><option value="D10">d10</option><option value="D12">d12</option>
      </select>
      <select v-model="ego" class="filter-select">
        <option value="">Any flag</option>
        <option value="ego">Ego</option>
        <option value="morph">Morph</option>
      </select>
    </div>

    <div class="select-bar">
      <button type="button" class="select-all" @click="toggleAllMatching">
        <span class="select-all-pick" :class="{ selected: allMatchingSelected }">{{ allMatchingSelected ? '✓' : '+' }}</span>
        <span>All matching ({{ filtered.length }})</span>
      </button>
      <span class="selected-count">{{ selectedIds.length }} selected</span>
    </div>

    <GmList
      :items="filtered"
      item-key="id"
      selectable
      :selected-ids="selectedIds"
      :loading="loading"
      empty-text="No traits match the current filters"
      :row-class="(t) => (t._flash ? 'patch-flash' : '')"
      @toggle="onToggle"
    >
      <template #item="{ item: t }">
        <span class="entity-name">{{ t.name }}</span>
        <span class="die-badge" :class="'die-' + (t.defaultDieType || 'd6').toLowerCase()">{{ t.defaultDieType || '—' }}</span>
        <span class="rating-badge" :class="'rt-' + (t.defaultRatingType || 'static').toLowerCase()">{{ ratingLabel(t.defaultRatingType) }}</span>
        <span class="ego-badge" :class="{ 'is-ego': t.defaultEgo }">{{ t.defaultEgo ? 'ego' : 'morph' }}</span>
        <span class="polarity-badge" :class="'pol-' + (t.polarity || 'inherit').toLowerCase()">{{ polarityLabel(t.polarity) }}</span>
        <span class="entity-universe">{{ t.traitsetName }}</span>
      </template>
    </GmList>

    <div class="batch-actions">
      <h4 class="ps-section-title">Apply to {{ selectedIds.length }} selected</h4>
      <div class="action-row">
        <label>Die type</label>
        <select v-model="applyDieType">
          <option value="">— no change —</option>
          <option value="D4">d4</option><option value="D6">d6</option><option value="D8">d8</option><option value="D10">d10</option><option value="D12">d12</option>
        </select>
      </div>
      <div class="action-row">
        <label>Rating type</label>
        <select v-model="applyRatingType">
          <option value="">— no change —</option>
          <option value="STATIC">Static</option><option value="RESOURCE">Resource</option><option value="CHALLENGE">Challenge</option><option value="EMPTY">Empty</option>
        </select>
      </div>
      <div class="action-row">
        <label>Ego / morph</label>
        <select v-model="applyEgo">
          <option value="">— no change —</option>
          <option value="ego">ego</option>
          <option value="morph">morph</option>
        </select>
      </div>
      <div class="action-row">
        <label>Polarity</label>
        <select v-model="applyPolarity">
          <option value="">— no change —</option>
          <option value="POSITIVE">Positive</option>
          <option value="NEGATIVE">Negative</option>
          <option value="CLEAR">Inherit traitset</option>
        </select>
      </div>
      <Button class="ps-add-btn" :loading="applying" :disabled="applying || selectedIds.length === 0" @click="applyBatch" variant="secondary" block>
        {{ applying ? 'Applying…' : `Apply to ${selectedIds.length} selected` }}
      </Button>
      <p v-if="status" class="status" :class="{ 'status-err': statusIsError }">{{ status }}</p>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, onMounted } from 'vue'
import { useTraitsConfig } from '@/composables/useTraitsConfig.js'
import GmList from '@/components/ui/GmList.vue'
import Button from '@/components/ui/Button.vue'

const props = defineProps({
  initialTraitsetId: { type: String, default: '' },
})

const { traitsets, loading, fetchTraitsConfig, batchUpdateTraits } = useTraitsConfig()

// ── Selection state ──────────────────────────────────
const selectedIds = ref([])
const selectedSet = computed(() => new Set(selectedIds.value))

function toggle(id) {
  const next = new Set(selectedIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selectedIds.value = [...next]
}

function onToggle(t) { toggle(t.id) }

// ── Filters ──────────────────────────────────────────
const search = ref('')
const traitsetId = ref(props.initialTraitsetId || '')
const ratingType = ref('')
const dieType = ref('')
const ego = ref('')

const allTraits = computed(() => {
  const out = []
  for (const ts of traitsets.value) {
    for (const t of (ts.traits || [])) {
      out.push({ ...t, traitsetName: ts.name, traitsetId: t.traitsetId || ts.id })
    }
  }
  return out
})

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  return allTraits.value.filter((t) => {
    if (traitsetId.value && t.traitsetId !== traitsetId.value) return false
    if (ratingType.value && t.defaultRatingType !== ratingType.value) return false
    if (dieType.value && t.defaultDieType !== dieType.value) return false
    if (ego.value === 'ego' && !t.defaultEgo) return false
    if (ego.value === 'morph' && t.defaultEgo) return false
    if (q && !(t.name || '').toLowerCase().includes(q) && !(t.id || '').toLowerCase().includes(q)) return false
    return true
  })
})

const allMatchingSelected = computed(() =>
  filtered.value.length > 0 && filtered.value.every((t) => selectedSet.value.has(t.id))
)

function toggleAllMatching() {
  const next = new Set(selectedIds.value)
  if (allMatchingSelected.value) {
    filtered.value.forEach((t) => next.delete(t.id))
  } else {
    filtered.value.forEach((t) => next.add(t.id))
  }
  selectedIds.value = [...next]
}

// ── Batch action state ───────────────────────────────
const applyDieType = ref('')
const applyRatingType = ref('')
const applyEgo = ref('')
const applyPolarity = ref('')
const applying = ref(false)
const status = ref('')

const statusIsError = computed(() =>
  /fail|select|choose/i.test(status.value)
)

function ratingLabel(rt) {
  if (!rt) return 'static'
  return rt.charAt(0) + rt.slice(1).toLowerCase()
}

function polarityLabel(p) {
  if (p === 'POSITIVE') return 'pos'
  if (p === 'NEGATIVE') return 'neg'
  return 'inherit'
}

async function applyBatch() {
  const ids = selectedIds.value
  if (!ids.length) { status.value = 'Select at least one trait.'; return }

  const changes = {}
  if (applyDieType.value) changes.defaultDieType = applyDieType.value
  if (applyRatingType.value) changes.defaultRatingType = applyRatingType.value
  if (applyEgo.value) changes.defaultEgo = applyEgo.value === 'ego'
  if (applyPolarity.value === 'CLEAR') {
    changes.polarity = null
    changes.clearPolarity = true
  } else if (applyPolarity.value) {
    changes.polarity = applyPolarity.value
  }
  if (Object.keys(changes).length === 0) { status.value = 'Choose at least one field to set.'; return }

  applying.value = true
  status.value = ''
  try {
    const { succeeded, failed } = await batchUpdateTraits(ids, changes)
    if (failed.length === 0) {
      status.value = `Updated ${succeeded.length} trait${succeeded.length === 1 ? '' : 's'}.`
    } else {
      status.value = `Updated ${succeeded.length}, failed ${failed.length}.`
    }
  } catch (e) {
    status.value = 'Batch update failed: ' + (e?.message || e)
  } finally {
    applying.value = false
  }
}

onMounted(() => {
  if (traitsets.value.length === 0) fetchTraitsConfig()
})
</script>

<style scoped>
.batch-panel { display: flex; flex-direction: column; gap: 8px; }
.filter-input { width: 100%; font-size: 12px; padding: 6px 8px; box-sizing: border-box; }
.filter-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.filter-select { width: 100%; font-size: 12px; padding: 6px 8px; box-sizing: border-box; }
.select-bar { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.select-all { display: inline-flex; align-items: center; gap: 6px; font-size: 11px; color: var(--text-dim); cursor: pointer; background: none; border: none; padding: 0; }
.select-all-pick { font-weight: 700; font-size: 12px; width: 16px; text-align: center; color: var(--text-dim); }
.select-all-pick.selected { color: var(--success); }
.selected-count { font-size: 11px; color: var(--accent); font-variant-numeric: tabular-nums; }

.die-badge { font-weight: 700; font-size: 11px; min-width: 24px; text-align: center; }
.die-d4 { color: var(--die-d4); }
.die-d6 { color: var(--die-d6); }
.die-d8 { color: var(--die-d8); }
.die-d10 { color: var(--die-d10); }
.die-d12 { color: var(--die-d12); }

.rating-badge {
  font-size: 9px; text-transform: uppercase; padding: 1px 6px;
  border-radius: 3px; font-weight: 600; letter-spacing: 0.3px;
}
.rt-static { background: var(--overlay-12); color: var(--text); }
.rt-resource { background: var(--accent-16); color: var(--accent); }
.rt-challenge { background: var(--danger-12); color: var(--danger); }
.rt-empty { background: transparent; color: var(--text-dim); border: 1px solid var(--text-dim); }

.ego-badge {
  font-size: 9px; text-transform: uppercase; padding: 1px 6px;
  border-radius: 3px; font-weight: 600; color: var(--text-dim);
}
.ego-badge.is-ego { color: var(--accent); }

.polarity-badge {
  font-size: 9px; text-transform: uppercase; padding: 1px 6px;
  border-radius: 3px; font-weight: 600;
}
.pol-positive { background: var(--success-12); color: var(--success); }
.pol-negative { background: var(--danger-12); color: var(--danger); }
.pol-inherit { background: transparent; color: var(--text-dim); border: 1px solid var(--text-dim); }

.batch-actions {
  margin-top: 4px; padding-top: 8px;
  border-top: 1px solid var(--overlay-8);
  display: flex; flex-direction: column; gap: 6px;
}
.action-row { display: flex; flex-direction: column; gap: 3px; }
.action-row label { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; }
.action-row select { width: 100%; font-size: 12px; padding: 6px 8px; box-sizing: border-box; }
.status { font-size: 12px; color: var(--success); margin: 0; }
.status-err { color: var(--danger); }
</style>
