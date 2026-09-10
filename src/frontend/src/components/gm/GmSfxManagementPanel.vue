<template>
  <div class="mgmt-panel">
    <!-- Search + create -->
    <div class="top-row">
      <input v-model="search" class="filter-input" placeholder="Search SFX…" />
      <button type="button" class="new-btn" @click="newSfx">+ New SFX</button>
    </div>

    <!-- Primitive filters -->
    <div class="filter-row">
      <select v-model="fTrigger" class="filter-select">
        <option value="">All triggers</option>
        <optgroup v-for="g in triggerGroups" :key="g.name" :label="g.name">
          <option v-for="t in g.items" :key="t.value" :value="t.value">{{ t.label }}</option>
        </optgroup>
      </select>
      <select v-model="fCondition" class="filter-select">
        <option value="">All conditions</option>
        <option v-for="c in conditionTypes" :key="c.value" :value="c.value">{{ c.label }}</option>
      </select>
      <select v-model="fAction" class="filter-select">
        <option value="">All actions</option>
        <optgroup v-for="g in actionGroups" :key="g.name" :label="g.name">
          <option v-for="a in g.actions" :key="a.actionId" :value="a.effectType + ':' + a.effectAction">{{ a.label }}</option>
        </optgroup>
      </select>
    </div>

    <!-- Owner filter -->
    <div class="filter-row">
      <select v-model="ownerType" class="filter-select" @change="onOwnerTypeChange">
        <option value="">No owner filter</option>
        <option v-for="t in OWNER_TYPES" :key="t.value" :value="t.value">{{ t.label }}</option>
      </select>
      <select v-if="ownerType" v-model="ownerId" class="filter-select">
        <option value="">-- pick owner --</option>
        <option v-for="o in ownersOfType" :key="o.ownerId" :value="o.ownerId">{{ o.label }}</option>
      </select>
      <button v-if="ownerRef" type="button" class="add-btn" @click="openPicker">+ Add SFX</button>
    </div>

    <!-- SFX list -->
    <GmList
      :items="filteredSfxs"
      item-key="id"
      :loading="loading"
      empty-text="No SFX match"
      max-height="380px"
      @click="openSfx"
    >
      <template #item="{ item: s }">
        <span class="sfx-name">{{ s.name }}</span>
        <span class="sfx-trigger">{{ triggerLabel(s.trigger) }}</span>
        <button v-if="ownerRef" type="button" class="row-del" title="Remove from owner" @click.stop="removeSfx(s.id)">✕</button>
      </template>
    </GmList>
    <div class="count">Showing {{ filteredSfxs.length }} of {{ allSfxs.length }} SFX</div>

    <div v-if="error" class="error-msg">{{ error }}</div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useTraitsConfig } from '@/composables/useTraitsConfig.js'
import { useSfxMeta } from '@/composables/useSfxMeta.js'
import { useEffectActions } from '@/composables/useEffectActions.js'
import { useSfxOwners } from '@/composables/useSfxOwners.js'
import { usePanel } from '@/composables/usePanel.js'
import GmList from '@/components/ui/GmList.vue'
import GmSfxEditPanel from './GmSfxEditPanel.vue'
import GmSfxPickerPanel from './GmSfxPickerPanel.vue'

const panel = usePanel()
const { allSfxs, fetchTraitsConfig } = useTraitsConfig()
const { load: loadSfxMeta, triggers, conditionTypes } = useSfxMeta()
const { load: loadActions, actions: effectActions } = useEffectActions()
const { OWNER_TYPES, ownersByType, loading, error, fetchOwners, addOwnerSfx, removeOwnerSfx } = useSfxOwners()

const search = ref('')
const fTrigger = ref('')
const fCondition = ref('')
const fAction = ref('')
const ownerType = ref('')
const ownerId = ref('')

onMounted(() => {
  if (!allSfxs.value.length) fetchTraitsConfig()
  loadSfxMeta()
  loadActions()
})

const triggerGroups = computed(() => {
  const groups = {}
  for (const t of triggers.value) {
    const g = t.group || 'auto'
    if (!groups[g]) groups[g] = []
    groups[g].push(t)
  }
  return Object.entries(groups).map(([name, items]) => ({ name, items }))
})

const actionGroups = computed(() => {
  const groups = {}
  for (const a of effectActions.value) {
    const g = a.group || 'Other'
    if (!groups[g]) groups[g] = []
    groups[g].push(a)
  }
  return Object.entries(groups).map(([name, actions]) => ({ name, actions }))
})

function triggerLabel(value) {
  return triggers.value.find(t => t.value === value)?.label || value || ''
}

const ownersOfType = computed(() => ownersByType.value[ownerType.value] || [])

const ownerRef = computed(() => {
  if (!ownerType.value || !ownerId.value) return null
  const o = ownersOfType.value.find(x => x.ownerId === ownerId.value)
  return o ? { ownerType: ownerType.value, ownerId: o.ownerId, label: o.label, sfxIds: o.sfxIds || [] } : null
})

function onOwnerTypeChange() {
  ownerId.value = ''
  if (ownerType.value && !ownersByType.value[ownerType.value]) fetchOwners(ownerType.value)
}

const filteredSfxs = computed(() => {
  const q = search.value.toLowerCase()
  let list = allSfxs.value || []
  if (q) list = list.filter(s => (s.name || '').toLowerCase().includes(q) || (s.description || '').toLowerCase().includes(q))
  if (fTrigger.value) list = list.filter(s => s.trigger === fTrigger.value)
  if (fCondition.value) list = list.filter(s => (s.conditions || []).some(c => c.type === fCondition.value))
  if (fAction.value) {
    const [t, a] = fAction.value.split(':')
    list = list.filter(s => (s.effects || []).some(e => e.type === t && e.action === a))
  }
  if (ownerRef.value) {
    const owned = new Set(ownerRef.value.sfxIds)
    list = list.filter(s => owned.has(s.id))
  }
  return list
})

function openSfx(sfx) {
  panel.open({ component: GmSfxEditPanel, title: sfx.name || 'Edit SFX', id: sfx.id, props: { sfx }, listeners: {} })
}

function newSfx() {
  panel.open({
    component: GmSfxEditPanel,
    title: 'New SFX',
    props: { sfx: null },
    listeners: { 'sfx-created': () => { fetchTraitsConfig() } },
  })
}

async function openPicker() {
  if (!ownerRef.value) return
  const ref = { ownerType: ownerRef.value.ownerType, ownerId: ownerRef.value.ownerId }
  panel.open({
    component: GmSfxPickerPanel,
    title: 'Add SFX to ' + (ownerRef.value.label || 'owner'),
    props: { selectedIds: [...ownerRef.value.sfxIds] },
    listeners: {
      'add-sfx': async (id) => { await addOwnerSfx([ref], id) },
      'remove-sfx': async (id) => { await removeOwnerSfx([ref], id) },
    },
  })
}

async function removeSfx(id) {
  if (!ownerRef.value) return
  await removeOwnerSfx([{ ownerType: ownerRef.value.ownerType, ownerId: ownerRef.value.ownerId }], id)
}
</script>

<style scoped>
.mgmt-panel { display: flex; flex-direction: column; gap: 8px; }
.filter-input { width: 100%; font-size: 12px; padding: 6px 8px; box-sizing: border-box;
  background: var(--overlay-6); color: var(--text); border: 1px solid var(--overlay-10); border-radius: 6px; }
.top-row { display: flex; gap: 6px; }
.top-row .filter-input { flex: 1; min-width: 0; }
.new-btn { flex: none; background: var(--success); color: var(--text-invert); font-weight: 600; border: none; border-radius: 6px; padding: 6px 12px; font-size: 11px; cursor: pointer; }
.filter-row { display: flex; gap: 4px; flex-wrap: wrap; }
.filter-select { flex: 1; min-width: 110px; font-size: 11px; padding: 5px 6px;
  background: var(--overlay-6); color: var(--text); border: 1px solid var(--overlay-10); border-radius: 6px; }
.add-btn { background: var(--accent-16); color: var(--accent); border: 1px solid var(--accent-dim);
  border-radius: 6px; padding: 5px 10px; font-size: 11px; cursor: pointer; }
.sfx-name { flex: 1; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sfx-trigger { font-size: 9px; color: var(--text-dim); white-space: nowrap; }
.row-del { background: none; border: none; color: var(--danger); cursor: pointer; font-size: 12px; padding: 0 2px; }
.count { font-size: 10px; color: var(--text-dim); }
.error-msg { font-size: 11px; color: var(--danger); background: var(--danger-8); padding: 6px 10px; border-radius: 4px; }
</style>
