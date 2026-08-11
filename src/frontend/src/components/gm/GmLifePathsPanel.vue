<template>
  <div class="lpl-root">
    <p class="lpl-hint">Life paths available in this universe. Click one for full details.</p>
    <div v-if="!paths.length" class="lpl-empty">No life paths seeded.</div>
    <button v-for="lp in paths" :key="lp.id" class="lpl-path-btn" @click="openDetail(lp)">
      <span class="lpl-name">{{ lp.name }}</span>
      <span class="lpl-type">{{ lp.type }}</span>
    </button>
  </div>
</template>

<script setup>
import GmLifePathDetailPanel from './GmLifePathDetailPanel.vue'

const props = defineProps({
  paths: { type: Array, default: () => [] },
  traitNameMap: { type: Object, default: () => ({}) },
  open: { type: Function, default: null },
})

function openDetail(lp) {
  if (!props.open) return
  props.open({
    component: GmLifePathDetailPanel,
    title: lp.name,
    props: { lp, traitNameMap: props.traitNameMap },
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
</style>
