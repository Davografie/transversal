<template>
  <div>
    <div class="sfx-summary">{{ sfxSummary }}</div>
    <!-- Shared form -->
    <div class="ps-form">
      <label>Name</label>
      <input v-model="draft.name" placeholder="SFX name…" />
      <label>Description</label>
      <textarea v-model="draft.description" rows="2" placeholder="What it does…"></textarea>
      <label>Trigger</label>
      <select v-model="draft.trigger">
        <optgroup v-for="g in triggerGroups" :key="g.label" :label="g.label">
          <option v-for="t in g.options" :key="t.value" :value="t.value">{{ t.label }}</option>
        </optgroup>
        <option v-if="!knownTrigger" :value="draft.trigger">{{ draft.trigger }}</option>
      </select>
      <label>Placement</label>
      <select v-model="draft.placement">
        <option :value="null">Auto (from trigger)</option>
        <option value="auto">Auto-fire</option>
        <option value="sheet">Sheet (owner card)</option>
        <option value="menu">Menu (consequence menu)</option>
      </select>
      <label>Source</label>
      <select v-model="draft.source_kind">
        <option :value="null">None</option>
        <option v-for="s in sourceKinds()" :key="s.value" :value="s.value">{{ s.label }}</option>
      </select>
      <div v-if="scopeVariables.length" class="sfx-vars">
        <span class="sfx-vars-label">Available variables:</span>
        <span v-for="v in scopeVariables" :key="v.name" class="sfx-var">{{ '{' + v.name + '}' }}<em class="sfx-var-type">{{ v.type }}</em></span>
      </div>
      <label>Conditions</label>
      <ConditionEditor v-model="draft.conditions" :source-element="sourceElement" />
    </div>

    <!-- Effects: list inline; each effect's form opens in a child panel -->
    <h4 class="ps-section-title">Effects</h4>
    <EffectList
      :model-value="draft.effects"
      @update:model-value="draft.effects = $event"
      @add="openEffectEditor(null)"
      @edit="openEffectEditor"
    />

    <label>Duration (in effect)</label>
    <DurationBuilder v-model="draft.duration" allow-rolls />

    <!-- Status messages -->
    <div v-if="errorMsg" class="error-msg">{{ errorMsg }}</div>
    <div v-if="successMsg" class="success-msg">{{ successMsg }}</div>

    <!-- Validation warnings (live) -->
    <div v-if="validationWarnings.length" class="sfx-warnings">
      <div v-for="w in validationWarnings" :key="w" class="sfx-warning">⚠ {{ w }}</div>
    </div>

    <!-- Action buttons: differ by mode -->
    <button v-if="sfx" class="save-btn save-main" @click="onSave" :disabled="saving">
      {{ saving ? 'Saving…' : (savedAt ? 'Saved ✓' : 'Save now') }}
    </button>
    <button v-else class="save-btn save-main" @click="onCreate" :disabled="saving || !draft.name.trim()">
      {{ saving ? 'Creating…' : 'Create SFX' }}
    </button>

    <div v-if="sfx" class="danger-zone">
      <DangerButton
        label="Delete SFX"
        loading-label="Deleting…"
        :disabled="saving"
        @confirm="onDelete"
      />
    </div>
  </div>
</template>

<script setup>
import { computed, inject, onMounted, ref, watch } from 'vue'
import { useApi } from '@/composables/useApi.js'
import { useTraitsConfig } from '@/composables/useTraitsConfig.js'
import { usePanel } from '@/composables/usePanel.js'
import { useSfxMeta } from '@/composables/useSfxMeta.js'
import { useSfxEdit } from '@/composables/useSfxEdit.js'
import { useTargetCatalog } from '@/composables/useTargetCatalog.js'
import DangerButton from '@/components/gm/DangerButton.vue'
import GmEffectEditPanel from './GmEffectEditPanel.vue'
import EffectList from './EffectList.vue'
import ConditionEditor from './ConditionEditor.vue'
import DurationBuilder from './DurationBuilder.vue'
import { useEffectActions } from '@/composables/useEffectActions.js'

const { graphql } = useApi()
const panel = usePanel()
const { traitNameMap, traitsets, allSfxs, fetchTraitsConfig } = useTraitsConfig()
const {
  draft, saving, errorMsg, successMsg, savedAt, validationWarnings, scopeVariables,
  open, reset, save, create, remove,
} = useSfxEdit()

const props = defineProps({
  sfx: { type: Object, default: null },
})

const emit = defineEmits(['sfx-created', 'sfx-updated', 'sfx-deleted'])

// Initialize the shared draft synchronously (no empty-state flash). The
// composable's sync-flush watchers ignore this via `_suppressEdits`.
open(props.sfx)

// The draft is a module-level singleton shared across every open SFX panel. When
// this panel becomes the active tab again, reload it from the freshest copy of
// its SFX — otherwise it keeps showing whichever sibling was opened last.
const panelActive = inject('panelActive', computed(() => true))
watch(panelActive, (active) => {
  if (!active) return
  const fresh = allSfxs.value.find((s) => s.id === props.sfx?.id) || props.sfx
  open(fresh)
})

const { load: loadSfxMeta, triggers } = useSfxMeta()
loadSfxMeta()

const { load: loadCatalog, sourceKinds } = useTargetCatalog()
loadCatalog()

// The SFX's declared source_kind → its catalog element, so a targeting-path
// condition can offer `select source` typed against it.
const sourceElement = computed(() => {
  const sk = draft.source_kind
  if (!sk) return ''
  const found = sourceKinds().find(s => s.value === sk)
  return found ? found.element : ''
})

const { load: loadActions, summarize: summarizeEffect } = useEffectActions()
loadActions()

onMounted(() => {
  if (!traitsets.value.length) fetchTraitsConfig()
  loadEntityNames()
})

// Backend trigger vocabulary grouped into Dice Pool / Manual / Auto-fire. A
// legacy value not in the vocabulary is still offered so saving never drops it.
const triggerGroups = computed(() => {
  const byGroup = { dicepool: [], manual: [], auto: [] }
  for (const t of triggers.value) {
    ;(byGroup[t.group] || (byGroup[t.group] = [])).push(t)
  }
  return [
    { label: 'Dice Pool', options: byGroup.dicepool },
    { label: 'Manual', options: byGroup.manual },
    { label: 'Auto-fire', options: byGroup.auto },
  ]
})
const knownTrigger = computed(() => !draft.trigger || triggers.value.some(t => t.value === draft.trigger))

// ── Plain-English summary ────────────────────────────

function triggerPhrase(trigger) {
  const t = triggers.value.find(t => t.value === trigger)
  return t?.label || trigger || 'Manual'
}

function conditionPhrase(c) {
  if (!c || !c.type) return ''
  switch (c.type) {
    case 'ALWAYS': return ''
    case 'NARRATIVE': return c.narrative || ''
    case 'UNPLACED': return 'unplaced'
    case 'AT_LOCATION': return `at ${c.target}`
    case 'HAS_TRAIT': return `has ${c.target}`
    case 'HAS_TRAIT_IN_TRAITSET': return `has a trait in ${c.target}`
    case 'HAS_RELATIONSHIP': return `related to ${c.target}`
    case 'TRAIT_RATING': return `${c.target} ≥ ${c.value}`
    case 'IN_UNIVERSE': return `in ${c.target}`
    default: return `${c.type}`
  }
}

const entityNames = ref({})

async function loadEntityNames() {
  try {
    const data = await graphql(`query { entities { id name } }`)
    const m = {}
    for (const e of (data?.entities || [])) m[e.id] = e.name
    entityNames.value = m
  } catch { /* summary stays id-based on failure */ }
}

function resolveName(id) {
  if (!id) return id
  if (traitNameMap.value[id]) return traitNameMap.value[id]
  if (entityNames.value[id]) return entityNames.value[id]
  return id
}

const sfxSummary = computed(() => {
  let out = triggerPhrase(draft.trigger)
  const conds = (draft.conditions || []).map(conditionPhrase).filter(Boolean)
  if (conds.length) out += ` · if ${conds.join(', ')}`
  const effs = (draft.effects || []).map((e) => summarizeEffect(e, resolveName)).filter(Boolean)
  if (effs.length) out += ` → ${effs.join(' then ')}`
  return out
})

// ── Child panel + mutations (delegated to the composable) ──

function openEffectEditor(index) {
  panel.open({
    component: GmEffectEditPanel,
    title: index == null ? 'Add effect' : 'Edit effect',
    props: { index },
  })
}

async function onSave() {
  const ok = await save()
  if (!ok) return
  emit('sfx-updated', {
    id: props.sfx.id, name: draft.name, trigger: draft.trigger,
    description: draft.description, conditions: [...draft.conditions], duration: draft.duration, effects: [...draft.effects],
    source_kind: draft.source_kind, placement: draft.placement,
  })
}

async function onCreate() {
  const id = await create()
  if (!id) return
  emit('sfx-created', {
    id, name: draft.name.trim(), trigger: draft.trigger,
    description: draft.description, conditions: [...draft.conditions], duration: draft.duration, effects: [...draft.effects],
    source_kind: draft.source_kind, placement: draft.placement,
  })
  setTimeout(() => { panel.close() }, 600)
  reset()
  setTimeout(() => { successMsg.value = '' }, 8000)
}

async function onDelete() {
  if (!(await remove())) return
  emit('sfx-deleted', props.sfx.id)
  panel.close()
}
</script>

<style scoped>
.ps-form input, .ps-form select, .ps-form textarea {
  font-size: 12px; padding: 6px 8px;
  background: var(--overlay-6); color: var(--text);
  border: 1px solid var(--overlay-10); border-radius: 6px;
  font-family: inherit; width: 100%; box-sizing: border-box;
}
.ps-form textarea { resize: vertical; min-height: 48px; }

.sfx-summary { font-size: 11px; color: var(--accent); font-family: monospace; background: var(--accent-8); border: 1px solid var(--accent-dim); border-radius: 4px; padding: 6px 8px; margin-bottom: 8px; line-height: 1.4; }
.sfx-warnings { margin-top: 10px; display: flex; flex-direction: column; gap: 4px; }
.sfx-warning { font-size: 11px; color: var(--warn-soft); background: var(--warn-12); border: 1px solid var(--warn-32); border-radius: 4px; padding: 5px 8px; font-family: monospace; }
.sfx-vars { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; margin-top: 2px; }
.sfx-vars-label { font-size: 9px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; }
.sfx-var { font-size: 10px; font-family: monospace; padding: 2px 6px; background: var(--accent-12); border: 1px solid var(--accent-dim); border-radius: 4px; color: var(--accent); }
.sfx-var-type { font-style: normal; font-family: inherit; font-size: 8px; color: var(--text-dim); margin-left: 3px; }
.hint { text-transform: none; letter-spacing: 0; color: var(--text-dim); font-size: 9px; }
.save-btn { background: var(--success); color: var(--text-invert); font-weight: 600; padding: 6px 12px; border-radius: 6px; border: none; cursor: pointer; font-size: 12px; }
.save-btn:disabled { opacity: 0.5; cursor: default; }
.save-main { margin-top: 10px; width: 100%; }
.error-msg { font-size: 11px; color: var(--danger); background: var(--danger-8); padding: 6px 10px; border-radius: 4px; margin-top: 8px; }
.success-msg { font-size: 11px; color: var(--success); background: var(--success-8); padding: 6px 10px; border-radius: 4px; margin-top: 8px; }
</style>
