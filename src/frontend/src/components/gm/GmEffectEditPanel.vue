<template>
  <div class="geep-root">
    <EffectForm
      :value="editingEffect"
      :variables="scopeVariables"
      :source-element="sourceElement"
      :trigger="draft.trigger"
      :placement="draft.placement"
      :output-variables="outputVariables"
      @save="onSave"
    />

    <!-- A **test run**, for the author: apply this one effect to the entity the GM
         is acting as and say what it did. Firing the rule would run its
         neighbours too and answer a different question; `POST /effects/apply`
         applies the single effect and reports, broadcasting nothing. -->
    <div class="geep-test">
      <Button
        variant="secondary"
        size="sm"
        :loading="running"
        :disabled="running || !actingEntityId || !testEffect"
        :title="actingEntityId
          ? 'Run this effect now, on the entity you are acting as'
          : 'Open a character or a place first — there is nothing to run it on'"
        @click="runEffect"
      >Activate effect</Button>
      <span v-if="report" class="geep-report" :class="{ 'is-error': report.error }">{{ report.text }}</span>
      <span v-else-if="!actingEntityId" class="geep-hint">No current entity to run it on.</span>
    </div>
  </div>
</template>

<script setup>
import { computed, inject, ref, watch } from 'vue'
import Button from '@/components/ui/Button.vue'
import { useApi } from '@/composables/useApi.js'
import EffectForm from './EffectForm.vue'
import { createSfxEdit } from '@/composables/useSfxEdit.js'
import { useSfxMeta } from '@/composables/useSfxMeta.js'
import { useTargetCatalog } from '@/composables/useTargetCatalog.js'

const props = defineProps({
  // Identity only (Rule 6): which effect to edit, or null to add. The effect
  // data itself lives in the shared useSfxEdit draft.
  index: { type: Number, default: null },
})

// The SFX editor provides its instance, so this child edits the same draft as
// its parent panel. A standalone open (none today) falls back to a private
// instance rather than a shared global.
const { draft, scopeVariables } = inject('sfxEdit', null) || createSfxEdit()

// Whom a test run acts on. The GM panel provides the **live perspective** — the
// entity the GM is looking at the world as — which is exactly "the current entity"
// and needs no picker of its own. Absent (a panel opened outside the GM surface),
// the button says so rather than guessing.
const actingEntityId = inject('actingEntityId', null) || computed(() => '')
const { applyEffect } = useApi()
const { load: loadCatalog, sourceKinds, collectVariables } = useTargetCatalog()
loadCatalog()

const editingEffect = computed(() => (props.index === null ? null : (draft.effects[props.index] || null)))

// The SFX's declared source_kind → its catalog element, so the targeting
// wizard can offer `select source` typed against it.
const sourceElement = computed(() => {
  const sk = draft.source_kind
  if (!sk) return ''
  const found = sourceKinds().find(s => s.value === sk)
  return found ? found.element : ''
})

// Typed names available to `select variable` in this effect's paths: the
// activation's own (the trigger's declared variables and the source token), the
// rule's **declared** bound variables (bound before the conditions, so before
// every effect), the SFX's conditions, and the effects *before* the one being
// edited.
const outputVariables = ref({})

function priorEffects() {
  const limit = props.index === null ? draft.effects.length : props.index
  return draft.effects.slice(0, limit)
}

watch(
  () => [draft.effects, draft.conditions, draft.trigger, draft.source_kind, draft.bound_variables, props.index, sourceElement.value],
  async () => {
    outputVariables.value = await collectVariables(
      priorEffects(), sourceElement.value || null, draft.conditions || null,
      draft.trigger || null, draft.source_kind || null,
      draft.bound_variables || null,
    )
  },
  { immediate: true, deep: true },
)

// Write-through: the form emits on every change, so the *first* emit of an add
// appends the effect and every later one replaces it. Nothing is saved from here
// and nothing closes: the SFX composer's own auto-save follows its **whole draft**
// (useSfxEdit), which is the commit point now that the form has no button. That
// also removes the old failure mode where closing before the write settled let the
// parent re-read the list and discard the effect just added.
// A ref, not a plain local: the test-run button reads the effect this panel is
// about, and an added effect only exists in the draft *after* the first emit.
const workingIndex = ref(props.index)

const testEffect = computed(() => {
  const i = workingIndex.value
  return i === null ? null : (draft.effects[i] || null)
})

function onSave(eff) {
  if (workingIndex.value === null) {
    draft.effects = [...draft.effects, eff]
    workingIndex.value = draft.effects.length - 1
  } else {
    const next = [...draft.effects]
    next[workingIndex.value] = eff
    draft.effects = next
  }
}

// ── The test run ─────────────────────────────────────
const running = ref(false)
const report = ref(null)

function describe(body) {
  const did = (body.applied || []).filter(Boolean)
  const parts = [did.length ? did.join(' · ') : 'nothing applied']
  if (body.pending) parts.push(`${body.pending} question${body.pending === 1 ? '' : 's'} it would ask`)
  const at = body.entity?.location_id
  if (at) parts.push(`now at ${at}`)
  return parts.join(' — ')
}

async function runEffect() {
  const effect = testEffect.value
  const entityId = String(actingEntityId.value || '')
  if (!effect || !entityId) return
  running.value = true
  report.value = null
  try {
    const body = await applyEffect(entityId, effect)
    report.value = body
      ? { error: false, text: describe(body) }
      : { error: true, text: 'the run failed — see the console' }
  } finally {
    running.value = false
  }
}
</script>

<style scoped>
.geep-root {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
/* The test run sits under the form, out of the way of authoring. */
.geep-test {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding-top: 6px;
  border-top: 1px dashed var(--overlay-10);
}
.geep-report {
  font-size: 10px;
  color: var(--text-dim);
  flex: 1;
  min-width: 0;
}
.geep-report.is-error { color: var(--danger, #d67); }
.geep-hint { font-size: 10px; color: var(--text-dim); }
</style>
