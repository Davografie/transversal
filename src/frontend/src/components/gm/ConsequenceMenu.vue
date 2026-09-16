<template>
  <div class="cm-root">
    <div class="cm-title">{{ title }}</div>

    <!-- Step 1: choose an option -->
    <div v-if="phase === 'menu'" class="cm-menu">
      <EntryPicker
        :options="pickerOptions"
        :loading="loading"
        empty-text="No options available."
        @pick="choose"
        @close="$emit('close')"
      />
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
import { ref, computed, watch, onMounted } from 'vue'
import EffectTargetWizard from './EffectTargetWizard.vue'
import EntryPicker from '@/components/ui/EntryPicker.vue'
import { useConsequences } from '@/composables/useConsequences.js'

const props = defineProps({
  entityId: { type: String, required: true },
  side: { type: String, default: 'player' },
  menuContext: { type: String, default: 'test_success' },
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

// Shaped for the shared entry picker: the gm/player side becomes the row's tone
// edge, and the option's origin reads as a trailing hint when it is not base.
const pickerOptions = computed(() => options.value.map(o => ({
  id: o.id,
  label: o.label,
  hint: o.source && o.source !== 'base' ? o.source : '',
  tone: o.side === 'gm' ? 'gm' : 'player',
})))

async function load() {
  phase.value = 'menu'
  const all = await fetchConsequenceOptions(props.entityId, props.side, props.menuContext)
  options.value = all.filter(o => !props.excludeIds.includes(o.id))
}

onMounted(load)
watch(() => [props.entityId, props.side, props.menuContext, props.excludeIds], load)

async function choose(opt) {
  const result = await applyOption(props.entityId, opt, props.effectDie)
  if (!result) return
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
.cm-root { display: flex; flex-direction: column; gap: 8px; padding: 10px; background: var(--overlay-2); border: 1px solid var(--overlay-8); border-radius: 6px; }
.cm-title { font-size: 10px; font-weight: 600; color: var(--accent); text-transform: uppercase; letter-spacing: 0.5px; }
.cm-menu { display: flex; flex-direction: column; gap: 4px; }
/* The rows, their gm/player edges and the cancel button now come from
   ui/EntryPicker — see [[UI-UX Design#Entry picker]]. */
.cm-done-title { font-size: 10px; color: var(--text-dim); text-transform: uppercase; }
.cm-applied { margin: 0; padding-left: 16px; font-size: 10px; color: var(--text); }
.cm-btn { font-size: 10px; padding: 4px 10px; border-radius: 4px; cursor: pointer; background: var(--overlay-6); border: 1px solid var(--overlay-12); color: var(--text); }
.cm-primary { background: var(--success); color: var(--text-invert); border-color: transparent; font-weight: 600; }
</style>
