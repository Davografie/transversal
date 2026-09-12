<template>
  <div>
    <div class="sfx-summary">{{ sfxSummary }}</div>
    <!-- Where this rule is attached, when the caller knows. Manage SFX knows (its
         owner filter picked it); the editor alone never does — and since the
         attachment lives on another screen, that fact is invisible here. -->
    <div v-if="owner" class="sfx-owner-line">
      <span class="sfx-owner-where">Lives on</span>
      <span class="sfx-owner-name">{{ owner.label || owner.ownerId }}</span>
      <span v-if="ownerTypeLabel" class="sfx-owner-type">{{ ownerTypeLabel }}</span>
      <span v-if="ownerReaches" class="sfx-owner-reach">→ {{ ownerReaches }}</span>
    </div>
    <!-- Shared form. The headings are the questions a rule answers, in dependency
         order: what it lives on decides the words available below it, what
         starts it decides when it fires, and the rest follow from those two. -->
    <div class="ps-form">
      <label>Name</label>
      <input v-model="draft.name" placeholder="SFX name…" />
      <label>Description</label>
      <textarea v-model="draft.description" rows="2" placeholder="Flavour text…"></textarea>

      <h5 class="sfx-slot">Lives on</h5>
      <label>Source</label>
      <select v-model="draft.source_kind">
        <option :value="null">None</option>
        <option v-for="s in sourceKinds()" :key="s.value" :value="s.value">{{ s.label }}</option>
      </select>
      <div v-if="scopeVariables.length" class="sfx-vars">
        <span class="sfx-vars-label">Available variables:</span>
        <span v-for="v in scopeVariables" :key="v.name" class="sfx-var">{{ '{' + v.name + '}' }}<em class="sfx-var-type">{{ v.type }}</em></span>
      </div>

      <h5 class="sfx-slot">What starts it</h5>
      <label>Trigger</label>
      <select v-model="draft.trigger">
        <optgroup v-for="g in triggerGroups" :key="g.label" :label="g.label">
          <option v-for="t in g.options" :key="t.value" :value="t.value">{{ t.label }}</option>
        </optgroup>
        <option v-if="!knownTrigger" :value="draft.trigger">{{ draft.trigger }}</option>
      </select>
      <!-- Placement used to sit here. The menu is a trigger now, so there is
           nothing left for the field to say; a stored value is shown rather
           than silently dropped, and rides along on save untouched. -->
      <p v-if="storedPlacement" class="hint">
        Carries a stored placement of <em>{{ draft.placement }}</em>.
      </p>

      <!-- Only meaningful when part of the rule *waits* for a roll: the scope says
           whose rolls feed that waiting part. With nothing waiting there is no
           answer to give, so the field is out of the way (same condition as the
           armed window below). -->
      <template v-if="hasDeferredEffects">
        <h5 class="sfx-slot">Who it's about</h5>
        <label>Listens to</label>
        <select v-model="draft.arming_scope">
          <option :value="null">From the trigger — {{ derivedArmingScope }}</option>
          <option value="self">Self (whoever activated it)</option>
          <option value="global">Global (everyone's rolls)</option>
          <option value="listener_spec">A targeting path</option>
          <!-- Never strand a stored value (see the placement note above). -->
          <option v-if="unknownArmingScope" :value="draft.arming_scope">{{ draft.arming_scope }} (stored)</option>
        </select>
        <p class="hint">Whose rolls feed the part of this rule that waits.</p>
        <div v-if="draft.arming_scope === 'listener_spec'" class="sfx-listener">
          <TargetSpecBuilder v-model="draft.listener_spec" :destination="{ element: 'entity' }" :source-element="sourceElement" />
          <p class="hint">Resolve which entities this SFX listens to (e.g. <em>select self → navigate relationships → filter type == curse_bind → navigate target</em>). Resolved once, when the rule arms.</p>
        </div>
      </template>
      <!-- Where this may be *taken*, not where it works. Seeded at the thing
           being unlocked, so `select source` is the trait instance (or entity)
           the rule is being attached to. Empty = acquirable anywhere. -->
      <h5 class="sfx-slot">Where it may be learned</h5>
      <label>Acquire path <span class="hint-inline">(optional)</span></label>
      <div class="sfx-listener">
        <!-- No destination hint: "who may take this" is not a fixed type — it ends
             wherever the author means (an entity, a trait instance, …). -->
        <TargetSpecBuilder v-model="draft.acquire_spec" :source-element="sourceElement" />
        <p class="hint">Where this rule may be <em>learned</em> — leaving the place afterwards does not take it away (a condition would). E.g. <em>select source → navigate entity → filter current_location == Azure Dawn</em>.</p>
      </div>
      <h5 class="sfx-slot">When it applies</h5>
      <label>Conditions</label>
      <ConditionEditor v-model="draft.conditions" :source-element="sourceElement" :available-keys="availableKeys" />
    </div>

    <!-- Effects: list inline; each effect's form opens in a child panel -->
    <h4 class="ps-section-title">What it does</h4>
    <EffectList
      :model-value="draft.effects"
      @update:model-value="draft.effects = $event"
      @add="openEffectEditor(null)"
      @edit="openEffectEditor"
    />

    <!-- Armed window: only meaningful when the SFX has delayed effects. -->
    <div v-if="hasDeferredEffects" class="sfx-duration">
      <h4 class="ps-section-title">How long it's held</h4>
      <label>Armed for (listening window)</label>
      <DurationBuilder v-model="draft.duration" allow-rolls />
      <p class="hint">How long this SFX stays armed before its delayed effects fire and it drops. Only affects <em>On roll / On result / On contest</em> effects — immediate effects fire once regardless. This is <strong>not</strong> an undo timer; each effect's own duration governs when a change reverts.</p>
    </div>

    <!-- Status messages -->
    <div v-if="errorMsg" class="error-msg">{{ errorMsg }}</div>
    <div v-if="successMsg" class="success-msg">{{ successMsg }}</div>

    <!-- Validation warnings (live) -->
    <div v-if="validationWarnings.length" class="sfx-warnings">
      <div v-for="w in validationWarnings" :key="w" class="sfx-warning">⚠ {{ w }}</div>
    </div>

    <!-- Action buttons: differ by mode -->
    <Button v-if="sfx" class="save-btn save-main" @click="onSave" :loading="saving" :disabled="saving" variant="success" solid>
      {{ saving ? 'Saving…' : (savedAt ? 'Saved ✓' : 'Save now') }}
    </Button>
    <Button v-else class="save-btn save-main" @click="onCreate" :loading="saving" :disabled="saving || !draft.name.trim()" variant="success" solid>
      {{ saving ? 'Creating…' : 'Create SFX' }}
    </Button>

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
import { computed, inject, onMounted, provide, ref, watch } from 'vue'
import { useApi } from '@/composables/useApi.js'
import { useTraitsConfig } from '@/composables/useTraitsConfig.js'
import { usePanel } from '@/composables/usePanel.js'
import { useSfxMeta } from '@/composables/useSfxMeta.js'
import { createSfxEdit } from '@/composables/useSfxEdit.js'
import { useTargetCatalog } from '@/composables/useTargetCatalog.js'
import DangerButton from '@/components/ui/DangerButton.vue'
import GmEffectEditPanel from './GmEffectEditPanel.vue'
import EffectList from './EffectList.vue'
import ConditionEditor from './ConditionEditor.vue'
import DurationBuilder from './DurationBuilder.vue'
import TargetSpecBuilder from './TargetSpecBuilder.vue'
import { useEffectActions } from '@/composables/useEffectActions.js'
import Button from '@/components/ui/Button.vue'

const { graphql } = useApi()
const panel = usePanel()
const { traitNameMap, traitsets, allSfxs, fetchTraitsConfig } = useTraitsConfig()
// One editor state per panel; the effect-edit child panel injects this same
// instance so the pair shares a single draft (and two open editors do not).
const sfxEdit = createSfxEdit()
provide('sfxEdit', sfxEdit)
const {
  draft, saving, errorMsg, successMsg, savedAt, validationWarnings, scopeVariables, cardText,
  open, reset, save, create, remove,
} = sfxEdit

const props = defineProps({
  sfx: { type: Object, default: null },
  /**
   * Where this SFX is attached: `{ ownerType, ownerId, label }`. Supplied by
   * whoever opened the panel *and knows* — Manage SFX does, because its owner
   * filter picked the thing. The editor alone never knows, which is why the
   * attachment has been an invisible fact on this screen.
   */
  owner: { type: Object, default: null },
})

// "LOCATION" reads as "location" in a sentence; the raw enum is for the picker.
const ownerTypeLabel = computed(() =>
  String(props.owner?.ownerType || '').toLowerCase().replace(/_/g, ' '))

// A place's rules are the one case where "lives on" and "who it's about" come
// apart: the place owns the rule, and it reaches whoever is inside it. Worth
// saying out loud, since this screen otherwise implies the owner is the answer.
const ownerReaches = computed(() =>
  String(props.owner?.ownerType || '').toUpperCase() === 'LOCATION'
    ? 'reaches everyone inside it'
    : '')

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

// Placement's only live value is `menu` (the consequence menu, validation, and
// the context-key map read it). `sheet`/`auto` were choices nothing consumed, so
// they are no longer offered — but a stored one must still render, or opening
// and saving a rule would silently rewrite it.
const unknownPlacement = computed(() => !!draft.placement)

// Placement is no longer authored here — the menu is a trigger. A rule saved
// before the change keeps whatever it holds; showing it beats rewriting it.
const storedPlacement = unknownPlacement

// Mirror of `derive_arming_scope` (domain/traits.py): every trigger listens to
// the entity that activated it, except a session-start passive, which watches
// everyone. Shown resolved rather than as "auto", so the empty option says where
// it lands instead of naming a value the author has to translate.
const derivedArmingScope = computed(() =>
  (draft.trigger || '') === 'on_session_start' ? 'global' : 'self')

const ARMING_SCOPES = ['self', 'global', 'listener_spec']
const unknownArmingScope = computed(() =>
  !!draft.arming_scope && !ARMING_SCOPES.includes(draft.arming_scope))

// A condition that reads the fire-time context can only be offered where the
// point supplies it. The keys come from the backend capability map (shared with
// `validate_sfx`), not from a list kept in step by hand.
const { contextKeysFor } = useSfxMeta()
const availableKeys = ref(null)
watch(
  () => [draft.trigger, draft.placement],
  async () => {
    availableKeys.value = await contextKeysFor(draft.trigger, draft.placement, '')
  },
  { immediate: true },
)

// Deferred (roll/outcome-timed) effect timings — the only effects the SFX-level
// armed window applies to. Immediate effects fire once at trigger time.
const DEFERRED_EFFECT_TIMINGS = ['ON_ROLL', 'ON_SET', 'ON_RESULT', 'ON_CONTEST_WIN', 'ON_CONTEST_LOSS', 'ON_SUCCESS', 'ON_FAILURE']
const hasDeferredEffects = computed(() =>
  (draft.effects || []).some(e => DEFERRED_EFFECT_TIMINGS.includes(e.timing))
)

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

// Derived rules text. The backend owns the phrasing (so the editor, the player
// sheet, the canvas and MCP all say the same thing); the local summary is only
// a fallback for when the query fails.
const sfxSummary = computed(() => {
  if (cardText.value) return cardText.value
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
    // The effect editor lives in a *child panel*, which cannot inject this
    // panel's provide — hand the shared draft across in the spec's context.
    context: { sfxEdit },
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
.hint-inline { opacity: 0.6; font-weight: 400; }
.ps-form input, .ps-form select, .ps-form textarea {
  font-size: 12px; padding: 6px 8px;
  background: var(--overlay-6); color: var(--text);
  border: 1px solid var(--overlay-10); border-radius: 6px;
  font-family: inherit; width: 100%; box-sizing: border-box;
}
.ps-form textarea { resize: vertical; min-height: 48px; }

.sfx-owner-line {
  display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px;
  font-size: 11px; padding: 5px 8px; margin-bottom: 8px;
  border: 1px solid var(--overlay-8); border-radius: 4px; background: var(--overlay-2);
}
.sfx-owner-where, .sfx-owner-type {
  font-size: 9px; color: var(--text-dim);
  text-transform: uppercase; letter-spacing: 0.5px;
}
.sfx-owner-name { color: var(--text); }
/* The seven questions this panel answers. Deliberately *not* uppercase like the
   field labels: a group heading should read as a sentence, and the fields under
   it are the machinery answering it. */
.sfx-slot {
  font-size: 12px; font-weight: 600; letter-spacing: 0;
  text-transform: none; color: var(--text); opacity: 0.85;
  margin: 14px 0 0; padding-top: 8px;
  border-top: 1px solid var(--overlay-8);
}
.sfx-summary { font-size: 11px; color: var(--accent); font-family: monospace; background: var(--accent-8); border: 1px solid var(--accent-dim); border-radius: 4px; padding: 6px 8px; margin-bottom: 8px; line-height: 1.4; }
.sfx-warnings { margin-top: 10px; display: flex; flex-direction: column; gap: 4px; }
.sfx-warning { font-size: 11px; color: var(--warn-soft); background: var(--warn-12); border: 1px solid var(--warn-32); border-radius: 4px; padding: 5px 8px; font-family: monospace; }
.sfx-vars { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; margin-top: 2px; }
.sfx-vars-label { font-size: 9px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; }
.sfx-var { font-size: 10px; font-family: monospace; padding: 2px 6px; background: var(--accent-12); border: 1px solid var(--accent-dim); border-radius: 4px; color: var(--accent); }
.sfx-var-type { font-style: normal; font-family: inherit; font-size: 8px; color: var(--text-dim); margin-left: 3px; }
.hint { text-transform: none; letter-spacing: 0; color: var(--text-dim); font-size: 9px; }
.save-main { margin-top: 10px; width: 100%; }
.error-msg { font-size: 11px; color: var(--danger); background: var(--danger-8); padding: 6px 10px; border-radius: 4px; margin-top: 8px; }
.success-msg { font-size: 11px; color: var(--success); background: var(--success-8); padding: 6px 10px; border-radius: 4px; margin-top: 8px; }
</style>
