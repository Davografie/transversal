<template>
  <div class="lpl-root">
    <p class="lpl-hint">Life paths available in this universe. Click one for full details.</p>
    <div v-if="!paths.length" class="lpl-empty">No life paths seeded.</div>
    <button v-for="lp in paths" :key="lp.id" class="lpl-path-btn" @click="openDetail(lp)">
      <span class="lpl-name">{{ lp.name }}</span>
      
    </button>
    <button v-if="open" class="lpl-add-btn" @click="addNew">＋ Add life path</button>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useApi } from '@/composables/useApi.js'
import GmLifePathDetailPanel from './GmLifePathDetailPanel.vue'
import GmLifePathEditPanel from './GmLifePathEditPanel.vue'

const props = defineProps({
  universe: { type: String, default: '' },
  open: { type: Function, default: null },
  close: { type: Function, default: null },
})

const { graphql } = useApi()
const paths = ref([])
let autoOpenId = null

async function fetchPaths(e) {
  if (!props.universe) return
  try {
    const data = await graphql(`query($u: String!) { lifePaths(universe: $u) { id name universe description qualification { traitId difficulty mustBeAtLocation draft } discovery { atLocation knowsEntity possessesTrait hasTraitRating hasRelationship } curriculum { traitId createAt stepUp } survival { traitIds difficulty termPenaltyAfter mishaps } events { description effect } advancement { traitIds difficulty ranks { number name benefits } } musterOut { perTermBenefits atRanks } } }`, { u: props.universe })
    paths.value = data?.lifePaths || []
    console.log('[paths] fetchPaths result:', paths.value.length, 'paths')
    // Auto-open detail panel for newly created paths
    if (autoOpenId && props.open) {
      const lp = paths.value.find(p => p.id === autoOpenId)
      if (lp) openDetail(lp)
      autoOpenId = null
    }
  } catch {}
}

onMounted(() => {
  fetchPaths()
  window.addEventListener('lifepath-saved', (e) => {
    if (e.detail?.isNew) autoOpenId = e.detail.id
    fetchPaths()
  })
})
onUnmounted(() => window.removeEventListener('lifepath-saved', fetchPaths))

function openDetail(lp) {
  if (!props.open) return
  props.open({
    component: GmLifePathDetailPanel,
    title: lp.name,
    props: { lp, open: props.open, close: props.close },
  })
}

function addNew() {
  if (!props.open) return
  const blank = { id: '', name: '', description: '', universe: props.universe }
  props.open({
    component: GmLifePathEditPanel,
    title: 'New Life Path',
    props: { lp: blank, section: '_root' },
  })
}
</script>

<style scoped>
.lpl-root { padding: 0; }
.lpl-hint { font-size: 10px; color: var(--text-dim); margin: 0 0 8px 0; }
.lpl-empty { font-size: 10px; color: var(--text-dim); padding: 12px 0; text-align: center; }
.lpl-path-btn {
  display: flex; align-items: center; gap: 8px; width: 100%;
  background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.06);
  border-radius: 4px; padding: 8px 10px; margin-bottom: 4px;
  cursor: pointer; text-align: left;
  color: var(--text);
}
.lpl-path-btn:hover { border-color: rgba(0,200,150,0.3); background: rgba(0,200,150,0.05); }
.lpl-path-btn:last-child { margin-bottom: 0; }
.lpl-name { font-weight: 600; font-size: 12px; }
.lpl-type { font-size: 9px; color: var(--text-dim); text-transform: uppercase; background: rgba(255,255,255,0.06); padding: 1px 5px; border-radius: 3px; margin-left: auto; }
.lpl-add-btn {
  width: 100%; margin-top: 8px; font-size: 11px; padding: 6px 0;
  background: rgba(0,200,150,0.08); border: 1px dashed rgba(0,200,150,0.25);
  border-radius: 4px; color: var(--accent); cursor: pointer;
}
.lpl-add-btn:hover { background: rgba(0,200,150,0.14); }
</style>
