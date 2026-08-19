<template>
  <div class="cm-root">
    <div class="cm-title">{{ title }}</div>

    <!-- Step 1: choose an option -->
    <div v-if="phase === 'menu'" class="cm-menu">
      <button
        v-for="opt in options"
        :key="opt.id"
        class="cm-option"
        :class="'cm-side-' + opt.side"
        @click="choose(opt)"
      >
        <span class="cm-label">{{ opt.label }}</span>
        <span v-if="opt.source !== 'base'" class="cm-source">{{ opt.source }}</span>
      </button>
      <div v-if="!options.length && !loading" class="cm-empty">No options available.</div>
      <button class="cm-btn cm-cancel" @click="$emit('close')">Cancel</button>
    </div>

    <!-- Step 2: resolve any choose-targets the chosen option needs -->
    <div v-else-if="phase === 'wizard'" class="cm-wizard">
      <EffectTargetWizard
        :entity-id="entityId"
        :pending-choices="pendingChoices"
        @resolve="finishResolve"
        @cancel="$emit('close')"
      />
    </div>

    <!-- Step 3: done -->
    <div v-else-if="phase === 'done'" class="cm-done">
      <div class="cm-done-title">Applied</div>
      <ul class="cm-applied">
        <li v-for="(s, i) in applied" :key="i">{{ s }}</li>
      </ul>
      <button class="cm-btn cm-primary" @click="$emit('close')">Done</button>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import EffectTargetWizard from './EffectTargetWizard.vue'
import { useConsequences } from '@/composables/useConsequences.js'

const props = defineProps({
  entityId: { type: String, required: true },
  side: { type: String, default: 'player' },
  effectDie: { type: String, default: '' },
  title: { type: String, default: 'Consequences' },
  excludeIds: { type: Array, default: () => [] },
})
const emit = defineEmits(['applied', 'close'])

const { loading, fetchConsequenceOptions, applyOption, resolveEffectTargets } = useConsequences()

const options = ref([])
const phase = ref('menu')
const applied = ref([])
const pendingChoices = ref([])

async function load() {
  phase.value = 'menu'
  const all = await fetchConsequenceOptions(props.entityId, props.side)
  options.value = all.filter(o => !props.excludeIds.includes(o.id))
}

onMounted(load)
watch(() => [props.entityId, props.side, props.excludeIds], load)

async function choose(opt) {
  const result = await applyOption(props.entityId, opt, props.effectDie)
  if (!result) return
  if (result.pendingChoices && result.pendingChoices.length) {
    pendingChoices.value = result.pendingChoices
    phase.value = 'wizard'
  } else {
    applied.value = result.applied || ['(no mechanical effect)']
    phase.value = 'done'
    emit('applied', applied.value)
  }
}

async function finishResolve(resolutions) {
  const result = await resolveEffectTargets(props.entityId, resolutions)
  applied.value = result?.applied || []
  phase.value = 'done'
  emit('applied', applied.value)
}
</script>

<style scoped>
.cm-root { display: flex; flex-direction: column; gap: 8px; padding: 10px; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); border-radius: 6px; }
.cm-title { font-size: 10px; font-weight: 600; color: var(--accent); text-transform: uppercase; letter-spacing: 0.5px; }
.cm-menu { display: flex; flex-direction: column; gap: 4px; }
.cm-option { display: flex; justify-content: space-between; align-items: center; gap: 8px; padding: 7px 9px; border-radius: 4px; cursor: pointer; background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); color: var(--text); font-size: 11px; text-align: left; }
.cm-option:hover { background: rgba(0,200,150,0.1); border-color: var(--accent); }
.cm-label { flex: 1; }
.cm-source { font-size: 8px; color: var(--text-dim); text-transform: uppercase; }
.cm-side-gm { border-left: 2px solid #d44040; }
.cm-side-player { border-left: 2px solid #40b860; }
.cm-empty { font-size: 10px; color: var(--text-dim); }
.cm-done-title { font-size: 10px; color: var(--text-dim); text-transform: uppercase; }
.cm-applied { margin: 0; padding-left: 16px; font-size: 10px; color: var(--text); }
.cm-btn { font-size: 10px; padding: 4px 10px; border-radius: 4px; cursor: pointer; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12); color: var(--text); }
.cm-cancel { color: var(--text-dim); }
.cm-primary { background: var(--success); color: #0a0a0f; border-color: transparent; font-weight: 600; }
</style>
