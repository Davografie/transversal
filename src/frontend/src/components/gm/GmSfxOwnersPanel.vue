<template>
  <div class="owners-panel">
    <!-- Owner type selector -->
    <div class="type-chips">
      <button
        v-for="t in OWNER_TYPES"
        :key="t.value"
        type="button"
        class="type-chip"
        :class="{ active: activeType === t.value }"
        :title="t.hint"
        @click="selectType(t.value)"
      >{{ t.label }}</button>
    </div>

    <!-- Owner instances for the active type -->
    <input v-model="search" class="filter-input" placeholder="Filter owners…" />

    <div v-if="loading" class="empty">Loading…</div>
    <div v-else-if="filteredOwners.length === 0" class="empty">No owners of this type</div>
    <div v-else class="owner-list">
      <div
        v-for="o in filteredOwners"
        :key="o.ownerId"
        class="owner-row"
        :class="{ selected: isSelected(o) }"
        @click="toggleOwner(o)"
      >
        <span class="pick-icon">{{ isSelected(o) ? '✓' : '+' }}</span>
        <span class="owner-label">{{ o.label }}</span>
        <span class="owner-count">{{ (o.sfxIds || []).length }}</span>
      </div>
    </div>

    <!-- Selected owners -->
    <div v-if="selected.length" class="selected-section">
      <span class="section-label">Selected owners</span>
      <div class="selected-chips">
        <span v-for="o in selected" :key="o.ownerType + ':' + o.ownerId" class="selected-chip">
          {{ o.label }}
          <button class="chip-x" @click.stop="removeSelected(o)">✕</button>
        </span>
      </div>
    </div>

    <!-- Shared SFX (intersection) -->
    <div class="shared-section">
      <div class="shared-head">
        <span class="section-label">Shared SFX ({{ sharedSfxIds.length }})</span>
        <button class="ps-add-btn" :disabled="selected.length === 0" @click="openPicker">+ Add SFX</button>
      </div>
      <div v-if="selected.length === 0" class="empty">Select one or more owners to manage their shared SFX</div>
      <div v-else-if="sharedSfx.length === 0" class="empty">No SFX shared by all selected owners</div>
      <div v-else class="sfx-list">
        <div v-for="s in sharedSfx" :key="s.id" class="sfx-row">
          <span class="sfx-name">{{ s.name }}</span>
          <span class="sfx-trigger">{{ s.trigger || '' }}</span>
          <button class="row-del-btn" @click="removeSfx(s.id)" title="Remove from all selected">✕</button>
        </div>
      </div>
    </div>

    <div v-if="error" class="error-msg">{{ error }}</div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useSfxOwners } from '@/composables/useSfxOwners.js'
import { useTraitsConfig } from '@/composables/useTraitsConfig.js'
import { usePanel } from '@/composables/usePanel.js'
import GmSfxPickerPanel from '@/components/gm/GmSfxPickerPanel.vue'

const panel = usePanel()
const { OWNER_TYPES, ownersByType, loading, error, fetchOwners, addOwnerSfx, removeOwnerSfx } = useSfxOwners()
const { allSfxs } = useTraitsConfig()

const activeType = ref('TABLE')
const selected = ref([])
const search = ref('')

const owners = computed(() => ownersByType.value[activeType.value] || [])

const filteredOwners = computed(() => {
  const q = search.value.toLowerCase()
  if (!q) return owners.value
  return owners.value.filter(o => (o.label || '').toLowerCase().includes(q))
})

function ownerKey(o) { return `${o.ownerType}:${o.ownerId}` }
function isSelected(o) { return selected.value.some(s => ownerKey(s) === ownerKey(o)) }

function selectType(type) {
  activeType.value = type
  if (!ownersByType.value[type]) fetchOwners(type)
}

function toggleOwner(o) {
  if (isSelected(o)) {
    selected.value = selected.value.filter(s => ownerKey(s) !== ownerKey(o))
  } else {
    selected.value.push({ ...o })
  }
}

function removeSelected(o) {
  selected.value = selected.value.filter(s => ownerKey(s) !== ownerKey(o))
}

// Intersection of every selected owner's sfxIds.
const sharedSfxIds = computed(() => {
  if (selected.value.length === 0) return []
  const sets = selected.value.map(o => new Set(o.sfxIds || []))
  const first = sets[0]
  return [...first].filter(id => sets.every(s => s.has(id)))
})

const sharedSfx = computed(() => {
  const byId = new Map(allSfxs.value.map(s => [s.id, s]))
  return sharedSfxIds.value.map(id => byId.get(id) || { id, name: id, trigger: '' })
})

const ownerRefs = computed(() => selected.value.map(o => ({ ownerType: o.ownerType, ownerId: o.ownerId })))

async function openPicker() {
  if (ownerRefs.value.length === 0) return
  panel.open({
    component: GmSfxPickerPanel,
    title: 'Add SFX to selected owners',
    props: { selectedIds: [...sharedSfxIds.value] },
    listeners: {
      'add-sfx': async (id) => { await addOwnerSfx(ownerRefs.value, id) },
      'remove-sfx': async (id) => { await removeOwnerSfx(ownerRefs.value, id) },
    },
  })
}

async function removeSfx(id) {
  await removeOwnerSfx(ownerRefs.value, id)
}

onMounted(() => {
  if (!ownersByType.value[activeType.value]) fetchOwners(activeType.value)
})
</script>

<style scoped>
.owners-panel { display: flex; flex-direction: column; gap: 10px; }

.type-chips { display: flex; flex-wrap: wrap; gap: 4px; }
.type-chip {
  padding: 3px 10px; border-radius: 999px; border: 1px solid var(--text-dim);
  background: transparent; color: var(--text-dim); font-size: 11px; cursor: pointer;
  text-transform: uppercase; letter-spacing: 0.3px;
}
.type-chip.active { border-color: var(--accent); color: var(--accent); background: rgba(64,136,212,0.12); }

.filter-input { width: 100%; font-size: 12px; padding: 6px 8px; box-sizing: border-box;
  background: rgba(255,255,255,0.06); color: var(--text); border: 1px solid rgba(255,255,255,0.1); border-radius: 6px; }

.owner-list { display: flex; flex-direction: column; gap: 2px; max-height: 240px; overflow-y: auto; }
.owner-row { display: flex; align-items: center; gap: 6px; padding: 6px 8px; border-radius: 4px; cursor: pointer; font-size: 12px; background: rgba(255,255,255,0.04); }
.owner-row:hover { background: rgba(255,255,255,0.08); }
.owner-row.selected { background: rgba(64,136,212,0.12); }
.pick-icon { font-weight: 700; font-size: 12px; width: 16px; text-align: center; flex-shrink: 0; }
.owner-row.selected .pick-icon { color: var(--success); }
.owner-label { flex: 1; }
.owner-count { font-size: 10px; color: var(--text-dim); }

.selected-section { display: flex; flex-direction: column; gap: 4px; }
.section-label { font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; }
.selected-chips { display: flex; flex-wrap: wrap; gap: 4px; }
.selected-chip { display: inline-flex; align-items: center; gap: 4px; padding: 3px 8px; border-radius: 999px;
  background: rgba(64,136,212,0.16); color: var(--text); font-size: 11px; }
.chip-x { background: none; border: none; color: var(--text-dim); cursor: pointer; font-size: 11px; padding: 0; }

.shared-section { display: flex; flex-direction: column; gap: 6px; border-top: 1px solid rgba(255,255,255,0.08); padding-top: 8px; }
.shared-head { display: flex; align-items: center; justify-content: space-between; }
.ps-add-btn { background: rgba(255,255,255,0.08); color: var(--text); border: 1px solid rgba(255,255,255,0.15);
  border-radius: 6px; padding: 4px 10px; font-size: 11px; cursor: pointer; }
.ps-add-btn:disabled { opacity: 0.4; cursor: default; }

.sfx-list { display: flex; flex-direction: column; gap: 2px; }
.sfx-row { display: flex; align-items: center; gap: 6px; padding: 6px 8px; border-radius: 4px; font-size: 12px; background: rgba(255,255,255,0.04); }
.sfx-name { flex: 1; font-weight: 500; }
.sfx-trigger { font-size: 10px; color: var(--text-dim); }
.row-del-btn { background: none; border: none; color: var(--text-dim); cursor: pointer; font-size: 12px; padding: 0; }
.row-del-btn:hover { color: var(--danger); }

.empty { font-size: 12px; color: var(--text-dim); padding: 6px 0; }
.error-msg { font-size: 11px; color: var(--danger); background: rgba(212,64,64,0.08); padding: 6px 10px; border-radius: 4px; }
</style>
