<template>
  <div :class="embedded ? 'rtm-in-panel' : 'rtm-overlay'" @click.self="!embedded && $emit('close')">
    <div class="rtm-root" :class="{ 'rtm-embedded': embedded }">
      <div class="rtm-title">{{ title }}</div>

      <!-- Step 1: pick an entry -->
      <div v-if="phase === 'menu'" class="rtm-menu">
        <ChoiceTable
          :rows="entries"
          :scheme="scheme"
          stagger
          allow-random
          :random-label="mode === 'create-support' ? 'Roll an archetype' : 'Roll'"
          empty-text="No entries in this table."
          @pick="(e, i) => choose(e, i + 1)"
          @close="$emit('close')"
        />
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
        <Button variant="success" solid size="sm" @click="$emit('close')">Done</Button>
      </div>

      <div v-if="error" class="rtm-error">{{ error }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import EffectTargetWizard from './EffectTargetWizard.vue'
import ChoiceTable from '@/components/ui/ChoiceTable.vue'
import Button from '@/components/ui/Button.vue'
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
  /**
   * Hosted **inside a panel** rather than floated over the app. The character
   * sheet is the container there — the same slot its question wizard and its
   * life-path choice table take — so the scrim and the fixed frame go, and the
   * table fills the panel instead of covering the screen. Opt-in because two
   * hosts mount this: the sheet (embedded) and `App.vue`'s support-character
   * flow (an overlay, where it really is a modal in front of everything).
   */
  embedded: { type: Boolean, default: false },
})
const emit = defineEmits(['applied', 'close'])

const { loading, fetchTable, applyEntry, createSupport, resolveEffectTargets } = useRollTableMenu()
const { load: loadActions } = useEffectActions()

const entries = ref([])
const scheme = ref('')
const phase = ref('menu')
const applied = ref([])
const pendingChoices = ref([])
const error = ref('')

async function load() {
  phase.value = 'menu'
  error.value = ''
  await loadActions()
  const table = await fetchTable(props.tableId)
  scheme.value = table?.scheme || ''
  // Shaped for the shared choice table: it renders the row (its key comes from
  // the table's `scheme`, its conditions and effects are phrased by the shared
  // resolver), while *this* decides what a row means — an unaffordable entry is
  // locked and says so, and `weight` makes the 🎲 weighted when the table
  // carries weights.
  //
  // The entry's own `conditions` are rendered as declarations ("if …"), and
  // deliberately do **not** lock the row: whether they hold is resolved by the
  // backend at apply time ([[B179]] — a roll falls back, a deliberate pick is
  // refused *by name*), so a client-side guess would either hide a row the
  // server would accept or offer one it will refuse.
  entries.value = (table?.entries || []).map((e) => {
    const cost = (e.costEffects || []).reduce((sum, c) => {
      if (c.type === 'transfer_razmerit' && c.action === 'spend') {
        return sum + (parseInt(c.result, 10) || 0)
      }
      return sum
    }, 0)
    const affordable = cost <= (props.entityRazmerit || 0)
    return {
      label: e.label,
      description: e.description,
      weight: e.weight || 0,
      minValue: e.minValue,
      maxValue: e.maxValue,
      tier: e.tier,
      conditions: e.conditions || [],
      effects: e.effects || [],
      costEffects: e.costEffects || [],
      locked: !affordable,
      why: affordable ? '' : `needs ${cost} razmerit`,
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
.rtm-overlay { position: fixed; inset: 0; z-index: 500; display: flex; align-items: center; justify-content: center; background: var(--scrim); padding: 12px; }
/* Inside a panel the panel *is* the frame: no scrim, no fixed box, no card of its
   own — the shape `EffectTargetWizard`'s `embedded` takes, for the same reason. */
.rtm-in-panel { display: flex; flex-direction: column; min-height: 0; flex: 1; }
.rtm-embedded { width: 100%; max-height: none; padding: 0; background: transparent; border: 0; border-radius: 0; }
.rtm-root { width: min(560px, 96vw); max-height: min(86vh, 720px); overflow: auto; display: flex; flex-direction: column; gap: 8px; padding: 12px; background: var(--bg-panel-solid); border: 1px solid var(--overlay-10); border-radius: var(--radius); }
.rtm-title { font-size: 10px; font-weight: 600; color: var(--accent); text-transform: uppercase; letter-spacing: 0.5px; }
.rtm-menu { display: flex; flex-direction: column; gap: 4px; }
/* The entry rows, their key column, conditions, effects, cost treatment and the
   actions now come from ui/ChoiceTable — see [[UI-UX Design#Choice table]]. */
.rtm-done-title { font-size: 10px; color: var(--text-dim); text-transform: uppercase; }
.rtm-applied { margin: 0; padding-left: 16px; font-size: 11px; color: var(--text); }
.rtm-error { font-size: 11px; color: var(--danger-bright); }
</style>
