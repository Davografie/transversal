<template>
  <div class="lpd-root">
    <div v-if="open" class="lpd-header lpd-clickable" @click="openEdit('_root')">
      <span class="lpd-name">{{ lpRef.name }} ✎</span>
    </div>
    <div v-else class="lpd-header">
      <span class="lpd-name">{{ lpRef.name }}</span>
      
    </div>
    <p class="lpd-desc">{{ lpRef.description }}</p>
    <p v-if="open" class="lpd-edit-hint">Click a section header to edit the section, or a row to edit just that item.</p>

    <!-- Qualification -->
    <div v-if="lpRef.qualification" class="lpd-subsection">
      <span class="lpd-subtitle lpd-clickable" @click="openEdit('qualification')">Qualification ✎</span>
      <span class="lpd-detail">Roll {{ tName(lpRef.qualification.traitId) }} vs {{ lpRef.qualification.difficulty }}</span>
      <span v-if="lpRef.qualification.mustBeAtLocation" class="lpd-detail">📍 Must be at {{ lpRef.qualification.mustBeAtLocation }}</span>
      <span v-if="lpRef.qualification.draft" class="lpd-detail">📋 Drafts to {{ lpRef.qualification.draft }}</span>
    </div>
    <div v-else class="lpd-subsection">
      <span class="lpd-subtitle lpd-clickable" @click="openEdit('qualification')">Qualification ✎</span>
      <span class="lpd-detail">None required — always available</span>
    </div>

    <!-- Discovery -->
    <div v-if="discoveryRows.length" class="lpd-subsection">
      <span class="lpd-subtitle">Discovery</span>
      <table class="lpd-table">
        <thead><tr><th>Condition</th><th>Value</th></tr></thead>
        <tbody>
          <tr v-for="(row, i) in discoveryRows" :key="i" class="lpd-row-clickable" @click="openEdit('discovery', i)">
            <td>{{ row.typeLabel }}</td>
            <td>{{ row.valueLabel }}</td>
          </tr>
        </tbody>
      </table>
      <button v-if="open" class="lpd-add-btn" @click="openEdit('discovery', null, true)">＋ Add</button>
    </div>
    <div v-else class="lpd-subsection">
      <span class="lpd-subtitle lpd-clickable" @click="openEdit('discovery', null, true)">Discovery ✎</span>
      <span class="lpd-detail">None — visible to all characters</span>
    </div>

    <!-- Curriculum -->
    <div class="lpd-subsection">
      <span class="lpd-subtitle lpd-clickable" @click="openEdit('curriculum')">Curriculum ✎</span>
      <div v-if="lpRef.curriculum?.length">
      <table class="lpd-table">
        <thead><tr><th>Trait</th><th>Create At</th><th>Step Up</th></tr></thead>
        <tbody>
          <tr v-for="(c, i) in lpRef.curriculum" :key="c.traitId" class="lpd-row-clickable" @click="openEdit('curriculum', i)">
            <td>{{ tName(c.traitId) }}</td>
            <td>{{ c.createAt }}</td>
            <td>{{ c.stepUp ? '✅' : '—' }}</td>
          </tr>
        </tbody>
      </table>
      </div>
      <span v-else class="lpd-detail">No curriculum items</span>
      <button v-if="open" class="lpd-add-btn" @click="openEdit('curriculum', null, true)">＋ Add</button>
    </div>

    <!-- Survival -->
    <div v-if="lpRef.survival" class="lpd-subsection">
      <span class="lpd-subtitle lpd-clickable" @click="openEdit('survival')">Survival ✎</span>
      <span class="lpd-detail">Roll {{ tNames(lpRef.survival.traitIds) }} vs {{ lpRef.survival.difficulty }}</span>
      <span v-if="lpRef.survival.termPenaltyAfter" class="lpd-detail">📈 +1 difficulty every {{ lpRef.survival.termPenaltyAfter }} terms</span>
    </div>
    <div v-else class="lpd-subsection">
      <span class="lpd-subtitle lpd-clickable" @click="openEdit('survival')">Survival ✎</span>
      <span class="lpd-detail">No survival roll defined</span>
    </div>

    <!-- Events -->
    <div class="lpd-subsection">
      <span class="lpd-subtitle lpd-clickable" @click="openEdit('events')">Events ✎</span>
      <div v-if="lpRef.events?.length">
      <table class="lpd-table">
        <thead><tr><th>#</th><th>Description</th></tr></thead>
        <tbody>
          <tr v-for="(e, i) in lpRef.events" :key="i" class="lpd-row-clickable" @click="openEdit('events', i)">
            <td class="lpd-num">{{ i + 1 }}</td>
            <td>{{ e.description }}</td>
          </tr>
        </tbody>
      </table>
      </div>
      <span v-else class="lpd-detail">No events defined</span>
      <button v-if="open" class="lpd-add-btn" @click="openEdit('events', null, true)">＋ Add</button>
    </div>

    <!-- Advancement -->
    <div v-if="lpRef.advancement" class="lpd-subsection">
      <span class="lpd-subtitle lpd-clickable" @click="openEdit('advancement')">Advancement ✎</span>
      <span class="lpd-detail">Roll {{ tNames(lpRef.advancement.traitIds) }} vs {{ lpRef.advancement.difficulty }}</span>
      <div v-if="lpRef.advancement.ranks?.length">
        <span class="lpd-subsubtitle">Ranks</span>
        <table class="lpd-table">
          <thead><tr><th>#</th><th>Name</th><th>Benefits</th></tr></thead>
          <tbody>
            <tr v-for="(r, i) in lpRef.advancement.ranks" :key="r.number" class="lpd-row-clickable" @click="openEdit('advancement', i)">
              <td class="lpd-num">{{ r.number }}</td>
              <td>{{ r.name }}</td>
              <td>{{ (r.benefits || []).map(b => b.type || b).join(', ') || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <span v-else class="lpd-detail">No ranks defined</span>
      <button v-if="open" class="lpd-add-btn" @click="openEdit('advancement', null, true)">＋ Add</button>
    </div>
    <div v-else class="lpd-subsection">
      <span class="lpd-subtitle lpd-clickable" @click="openEdit('advancement')">Advancement ✎</span>
      <span class="lpd-detail">No advancement ladder</span>
    </div>

    <!-- Mishaps -->
    <div v-if="lpRef.survival" class="lpd-subsection">
      <span class="lpd-subtitle lpd-clickable" @click="openEdit('mishap')">Mishaps ✎</span>
      <div v-if="lpRef.survival.mishaps?.length">
      <table class="lpd-table">
        <thead><tr><th>#</th><th>Description</th><th class="lpd-mo-col">Musters Out</th></tr></thead>
        <tbody>
          <tr v-for="(m, i) in lpRef.survival.mishaps" :key="i" class="lpd-row-clickable" @click="openEdit('mishap', i)">
            <td class="lpd-num">{{ i + 1 }}</td>
            <td>{{ m.description || m }}</td>
            <td class="lpd-mo-col">{{ m.must_muster_out ? '🏁' : '—' }}</td>
          </tr>
        </tbody>
      </table>
      </div>
      <span v-else class="lpd-detail">No mishaps defined</span>
      <button v-if="open" class="lpd-add-btn" @click="openEdit('mishap', null, true)">＋ Add</button>
    </div>

    <!-- Muster Out -->
    <div v-if="lpRef.musterOut" class="lpd-subsection">
      <span class="lpd-subtitle lpd-clickable" @click="openEdit('muster')">Muster Out ✎</span>
      <div v-if="lpRef.musterOut.perTermBenefits?.length">
        <span class="lpd-subsubtitle">Per Term</span>
        <table class="lpd-table">
          <thead><tr><th>Type</th><th>Amount</th></tr></thead>
          <tbody>
            <tr v-for="(b, i) in lpRef.musterOut.perTermBenefits" :key="i">
              <td>{{ b.type || b }}</td>
              <td>{{ b.amount || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="lpRef.musterOut.atRanks && Object.keys(lpRef.musterOut.atRanks).length">
        <span class="lpd-subsubtitle">At Ranks</span>
        <table class="lpd-table">
          <thead><tr><th>Rank</th><th>Benefits</th></tr></thead>
          <tbody>
            <tr v-for="(benefits, rank) in lpRef.musterOut.atRanks" :key="rank">
              <td class="lpd-num">{{ rank }}</td>
              <td>{{ (benefits || []).map(b => `${b.type || b} ${b.amount || ''}`).join(', ') }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
    <div v-else class="lpd-subsection">
      <span class="lpd-subtitle lpd-clickable" @click="openEdit('muster')">Muster Out ✎</span>
      <span class="lpd-detail">No muster-out benefits defined</span>
    </div>
    <DangerButton v-if="open" label="Delete life path" @confirm="onDeleteConfirmed" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useApi } from '@/composables/useApi.js'
import { useTraitsConfig } from '@/composables/useTraitsConfig.js'
import GmLifePathEditPanel from './GmLifePathEditPanel.vue'
import DangerButton from '@/components/gm/DangerButton.vue'

const { traitNameMap } = useTraitsConfig()

const props = defineProps({
  lp: { type: Object, required: true },
  open: { type: Function, default: null },
  close: { type: Function, default: null },
})

const { graphql } = useApi()
const emit = defineEmits(['close'])
const lpRef = ref(props.lp)
const entityNameMap = ref({})

onMounted(async () => {
  try {
    const data = await graphql(`{ entities { id name } }`)
    if (data?.entities) {
      data.entities.forEach(e => { entityNameMap.value[e.id] = e.name })
    }
  } catch {}
})

async function refreshLp() {
  try {
    const data = await graphql(`{ lifePaths { id name universe description qualification { traitId difficulty mustBeAtLocation draft } discovery { atLocation knowsEntity possessesTrait hasTraitRating hasRelationship } curriculum { traitId createAt stepUp } survival { traitIds difficulty termPenaltyAfter mishaps } events { description effect } advancement { traitIds difficulty ranks { number name benefits } } musterOut { perTermBenefits atRanks } } }`)
    const match = (data?.lifePaths || []).find(lp => lp.id === lpRef.value.id)
    if (match) lpRef.value = match
  } catch {}
}

onMounted(() => window.addEventListener('lifepath-saved', refreshLp))
onUnmounted(() => window.removeEventListener('lifepath-saved', refreshLp))

function onDeleteConfirmed() {
  graphql(`mutation($id:ID!){deleteLifePath(id:$id)}`, { id: lpRef.value.id })
  window.dispatchEvent(new CustomEvent('lifepath-saved', { detail: { id: lpRef.value.id, universe: lpRef.value.universe } }))
  emit('close')
}

const discoveryRows = computed(() => {
  const rows = []
  const d = lpRef.value.discovery
  if (!d) return rows
  for (const loc of (d.atLocation || [])) {
    rows.push({ type: 'atLocation', typeLabel: '📍 Location', value: loc, valueLabel: tName(loc) })
  }
  for (const ent of (d.knowsEntity || [])) {
    rows.push({ type: 'knowsEntity', typeLabel: '👤 Knows', value: ent, valueLabel: tName(ent) })
  }
  for (const trait of (d.possessesTrait || [])) {
    rows.push({ type: 'possessesTrait', typeLabel: '🎯 Has trait', value: trait, valueLabel: tName(trait) })
  }
  for (const [trait, die] of Object.entries(d.hasTraitRating || {})) {
    rows.push({ type: 'hasTraitRating', typeLabel: `⭐ Rating ≥ ${die}`, value: trait, die, valueLabel: tName(trait) })
  }
  for (const rel of (d.hasRelationship || [])) {
    rows.push({ type: 'hasRelationship', typeLabel: '🔗 Relationship', value: rel, valueLabel: tName(rel) })
  }
  return rows
})

function openEdit(section, itemIndex = null, addNew = false) {
  if (!props.open) return
  props.open({ component: GmLifePathEditPanel, title: `Edit ${section} — ${lpRef.value.name}`, props: { lp: lpRef.value, section, itemIndex, addNew } })
}

function tName(id) {
  if (!id) return '—'
  return traitNameMap.value[id] || entityNameMap.value[id] || id.replace(/^trait-/, '').replace(/[-_]\w{4}$/, '').replace(/[-_]/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

function tNames(ids) {
  return (ids || []).map(tName).join(', ') || '—'
}
</script>

<style scoped>
.lpd-root { padding: 0; }
.lpd-header { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.lpd-name { font-weight: 600; font-size: 14px; }
.lpd-type { font-size: 9px; color: var(--text-dim); text-transform: uppercase; background: rgba(255,255,255,0.06); padding: 1px 5px; border-radius: 3px; }
.lpd-desc { font-size: 11px; color: var(--text-dim); margin: 0 0 8px 0; }
.lpd-subsection { margin-top: 8px; }
.lpd-subtitle { display: block; font-size: 9px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 2px; }
.lpd-subsubtitle { display: block; font-size: 8px; color: var(--text-dim); text-transform: uppercase; margin: 4px 0 2px; }
.lpd-detail { display: block; font-size: 10px; color: var(--text-dim); line-height: 1.5; }
.lpd-table { width: 100%; border-collapse: collapse; margin: 4px 0 6px; font-size: 10px; }
.lpd-table th { text-align: left; padding: 2px 6px; border-bottom: 1px solid rgba(255,255,255,0.06); color: var(--text-dim); font-size: 8px; text-transform: uppercase; }
.lpd-table td { padding: 2px 6px; border-bottom: 1px solid rgba(255,255,255,0.03); color: var(--text); }
.lpd-num { width: 24px; text-align: center; color: var(--text-dim); }
.lpd-mo-col { width: 56px; text-align: center; }
.lpd-clickable { cursor: pointer; }
.lpd-clickable:hover { color: var(--accent); }
.lpd-row-clickable { cursor: pointer; }
.lpd-row-clickable:hover { background: rgba(255,255,255,0.04); }
.lpd-edit-hint { font-size: 9px; color: var(--text-dim); margin: 0 0 4px 0; }
.lpd-add-btn { font-size: 9px; padding: 2px 8px; cursor: pointer; background: rgba(255,255,255,0.04); color: var(--text-dim); border: 1px solid rgba(255,255,255,0.06); border-radius: 3px; margin-top: 2px; }
.lpd-add-btn:hover { background: rgba(255,255,255,0.08); color: var(--text); }
</style>
