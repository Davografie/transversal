<template>
  <div class="rtm-overlay" @click.self="$emit('close')">
    <div class="rtm-root">
      <div class="rtm-title">{{ title }}</div>

      <!-- Step 1: pick an entry -->
      <div v-if="phase === 'menu'" class="rtm-menu">
        <button
          v-for="(e, i) in entries"
          :key="i"
          class="rtm-option"
          :class="{ 'rtm-unaffordable': !e.affordable }"
          :disabled="!e.affordable"
          @click="choose(e, i + 1)"
        >
          <span class="rtm-label">{{ e.label || ('Entry ' + (i + 1)) }}</span>
          <span v-if="e.description" class="rtm-desc">{{ e.description }}</span>
          <span class="rtm-cost" :class="{ 'rtm-cost-free': !e.costLabel }">{{ e.costLabel || 'free' }}</span>
        </button>
        <div v-if="!entries.length && !loading" class="rtm-empty">No entries in this table.</div>
        <button class="rtm-btn rtm-cancel" @click="$emit('close')">Cancel</button>
      </div>

      <!-- Step 2: resolve choose-targets the entry needs -->
      <div v-else-if="phase === 'wizard'" class="rtm-wizard">
        <EffectTargetWizard
          :entity-id="entityId"
          :pending-choices="pendingChoices"
          @resolve="finishResolve"
          @cancel="$emit('close')"
        />
      </div>

      <!-- Step 3: done -->
      <div v-else-if="phase === 'done'" class="rtm-done">
        <div class="rtm-done-title">{{ mode === 'create-support' ? 'Created' : 'Applied' }}</div>
        <ul class="rtm-applied">
          <li v-for="(s, i) in applied" :key="i">{{ s }}</li>
        </ul>
        <button class="rtm-btn rtm-primary" @click="$emit('close')">Done</button>
      </div>

      <div v-if="error" class="rtm-error">{{ error }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import EffectTargetWizard from './EffectTargetWizard.vue'
import { useRollTableMenu } from '@/composables/useRollTableMenu.js'
import { useEffectActions } from '@/composables/useEffectActions.js'

const props = defineProps({
  entityId: { type: String, required: true },
  tableId: { type: String, required: true },
  title: { type: String, default: 'Roll Table' },
  entityRazmerit: { type: Number, default: 0 },
  mode: { type: String, default: 'apply' },  // 'apply' | 'create-support'
  playerId: { type: String, default: '' },
  mainEntityId: { type: String, default: '' },
})
const emit = defineEmits(['applied', 'close'])

const { loading, fetchTable, applyEntry, createSupport, resolveEffectTargets } = useRollTableMenu()
const { load: loadActions, summarize } = useEffectActions()

const entries = ref([])
const phase = ref('menu')
const applied = ref([])
const pendingChoices = ref([])
const error = ref('')

function razmeritCost(costEffects) {
  return (costEffects || []).reduce((sum, e) => {
    if (e.type === 'transfer_razmerit' && e.action === 'spend') {
      return sum + (parseInt(e.result, 10) || 0)
    }
    return sum
  }, 0)
}

function costLabel(costEffects) {
  const raz = razmeritCost(costEffects)
  if (raz > 0) return `${raz} razmerit`
  const other = (costEffects || []).filter(e => !(e.type === 'transfer_razmerit' && e.action === 'spend'))
  if (other.length) return other.map(e => summarize(e)).join(', ')
  return ''
}

async function load() {
  phase.value = 'menu'
  error.value = ''
  await loadActions()
  const table = await fetchTable(props.tableId)
  entries.value = (table?.entries || []).map((e) => {
    const cost = razmeritCost(e.costEffects)
    return {
      label: e.label,
      description: e.description,
      costEffects: e.costEffects,
      effects: e.effects,
      costLabel: costLabel(e.costEffects),
      affordable: cost <= (props.entityRazmerit || 0),
    }
  })
}

onMounted(load)
watch(() => [props.tableId, props.entityRazmerit], load)

async function choose(entry, index) {
  if (props.mode === 'create-support') {
    const created = await createSupport({
      playerId: props.playerId,
      mainEntityId: props.mainEntityId,
      tableId: props.tableId,
      index,
    })
    if (!created) { error.value = 'Failed to create support character.'; return }
    applied.value = [`Created ${created.name}`]
    phase.value = 'done'
    emit('applied', applied.value)
    return
  }

  const result = await applyEntry(props.entityId, props.tableId, index)
  if (!result) { error.value = 'Failed to apply entry.'; return }
  const structured = (result.structured || []).map((c, i) => ({ ...c, index: i, entity_id: props.entityId }))
  const legacy = (result.pendingChoices || []).map((c, i) => ({ ...c, index: i, entity_id: props.entityId }))
  const allChoices = [...structured, ...legacy]
  if (allChoices.length) {
    pendingChoices.value = allChoices
    phase.value = 'wizard'
  } else {
    applied.value = result.applied || ['(no mechanical effect)']
    phase.value = 'done'
    emit('applied', applied.value)
  }
}

async function finishResolve(resolutions) {
  const clean = (resolutions || []).map(({ entity_id, ...rest }) => rest)
  const result = await resolveEffectTargets(props.entityId, clean)
  applied.value = result?.applied || []
  phase.value = 'done'
  emit('applied', applied.value)
}
</script>

<style scoped>
.rtm-overlay { position: fixed; inset: 0; z-index: 500; display: flex; align-items: center; justify-content: center; background: rgba(0,0,0,0.5); }
.rtm-root { width: min(360px, 90vw); max-height: 80vh; overflow: auto; display: flex; flex-direction: column; gap: 8px; padding: 10px; background: #12121a; border: 1px solid rgba(255,255,255,0.1); border-radius: 8px; }
.rtm-title { font-size: 10px; font-weight: 600; color: var(--accent); text-transform: uppercase; letter-spacing: 0.5px; }
.rtm-menu { display: flex; flex-direction: column; gap: 4px; }
.rtm-option { display: flex; flex-direction: column; align-items: flex-start; gap: 2px; padding: 8px 10px; border-radius: 5px; cursor: pointer; background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); color: var(--text); font-size: 12px; text-align: left; }
.rtm-option:hover:not(:disabled) { background: rgba(0,200,150,0.1); border-color: var(--accent); }
.rtm-option:disabled { opacity: 0.45; cursor: not-allowed; }
.rtm-label { font-weight: 600; }
.rtm-desc { font-size: 10px; color: var(--text-dim); }
.rtm-cost { align-self: flex-end; font-size: 10px; color: #e0a030; font-weight: 600; }
.rtm-cost-free { color: var(--text-dim); font-weight: 400; }
.rtm-empty { font-size: 11px; color: var(--text-dim); }
.rtm-done-title { font-size: 10px; color: var(--text-dim); text-transform: uppercase; }
.rtm-applied { margin: 0; padding-left: 16px; font-size: 11px; color: var(--text); }
.rtm-error { font-size: 11px; color: #ff6b6b; }
.rtm-btn { font-size: 11px; padding: 5px 12px; border-radius: 5px; cursor: pointer; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12); color: var(--text); }
.rtm-cancel { color: var(--text-dim); }
.rtm-primary { background: var(--success); color: #0a0a0f; border-color: transparent; font-weight: 600; }
</style>
