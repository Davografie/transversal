<template>
  <div>
    <div class="portal-head">
      <span class="portal-to">{{ fromName }} → {{ link.name }}</span>
      <span class="portal-type">{{ link.transversal_type || 'inapposite' }}</span>
      <!-- No Save button (the convention since B211), so the one thing a button
           used to tell you — that the write happened — is a line of text. -->
      <span v-if="saving" class="portal-save-msg">Saving…</span>
      <span v-else-if="savedAt" class="portal-save-msg is-saved">Saved</span>
    </div>
    <!-- One effect at a time, in a **child panel** — the shape every other effect
         list uses (the SFX editor, a roll-table row, a life-path step): an effect
         is a stacked builder of unbounded height, and the list has to stay in
         view while one is edited. -->
    <div class="portal-effects">
      <EffectList
        :model-value="draft.effects"
        :editing-index="editingEffectIndex"
        @update:model-value="draft.effects = $event"
        @add="openEffectEditor(null)"
        @edit="openEffectEditor"
      />
    </div>
  </div>
</template>

<script setup>
// The portal's effects, authored in place.
//
// This was the last authoring panel with a manual Save, and the save *was* the
// close: `save()` POSTed and then called `panel.close()`. The author asked for
// auto-save here like everywhere else (2026-10-17 — the request came through
// [[effects]]), so there is no button left to press and nothing closes the panel
// for you. Its effect list also moved into a child panel, which is what the rest
// of the app does; the inline form it used before was the last of those too.
import { ref, reactive, watch, onUnmounted } from 'vue'
import { usePanel } from '@/composables/usePanel.js'
import EffectList from './EffectList.vue'
import GmDraftEffectPanel from './GmDraftEffectPanel.vue'

const props = defineProps({
  fromId: { type: String, required: true },
  fromName: { type: String, default: '' },
  link: { type: Object, required: true },
  universe: { type: String, default: '' },
})

// The draft is seeded **before** the watcher is registered, so this initial copy
// is not an edit. Nothing re-seeds it afterwards: the draft belongs to the panel,
// and each write keeps the parent's copy in step instead (below). It is a plain
// object with `effects` because that is the contract `GmDraftEffectPanel` reads —
// it is deliberately draft-agnostic, so any owner can hand it the thing to edit.
const panel = usePanel()
const draft = reactive({ effects: (props.link.effects || []).map((e) => ({ ...e })) })
const editingEffectIndex = ref(null)
const saving = ref(false)
const savedAt = ref(null)

/** Edit one effect of the list, in a child panel. */
function openEffectEditor(index) {
  editingEffectIndex.value = index
  panel.open({
    component: GmDraftEffectPanel,
    title: index === null ? 'Add effect' : 'Edit effect',
    props: {
      index,
      universe: props.universe,
      // The destination travels with the form: it is what lets the targeting
      // wizard offer portal-relative targets, exactly as the old inline editor's
      // four props did.
      portalDestination: props.link.name,
      portalTargetType: props.link.type,
      portalUniverse: props.link.current_universe,
      portalRootId: props.link.type === 'location' ? props.link._key : '',
    },
    // The draft travels as a live reference through the spec's `context` — a panel
    // cannot `provide` to its own child panels. The child writes effects into it;
    // this panel's auto-save is the commit point.
    context: { rowDraft: draft },
  })
}

// ── Auto-save ───────────────────────────────────────
// Three things this has to get right, all of them learned elsewhere — the long
// form of the reasoning is in `GmRollTableEditPanel`'s auto-save block:
//   * the **whole draft** is watched, not a list of field names. A list is a
//     promise to keep in step with the document; it falls behind, and a field
//     that silently never saves reads as "auto-save is broken".
//   * a pending write is **flushed on close**. With the button gone, closing
//     inside the debounce window would drop the last edit silently, which is
//     exactly the trap this change is about.
//   * the parent's `link.effects` is updated by every write, so the summary it
//     draws cannot go stale while the GM works — the old code only did that on
//     the way out.
let _saveTimer = null

function scheduleSave() {
  savedAt.value = null
  clearTimeout(_saveTimer)
  _saveTimer = setTimeout(() => { save() }, 700)
}

watch(draft, scheduleSave, { deep: true, flush: 'sync' })

onUnmounted(() => {
  // The flush: an edit made in the last 700ms still reaches the server.
  if (_saveTimer) {
    clearTimeout(_saveTimer)
    _saveTimer = null
    save()
  }
})

async function save() {
  saving.value = true
  try {
    const r = await fetch(`/api/v1/locations/${props.fromId}/edges/${props.link._key}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      // The endpoint **patches** what it is given — `effects` is written only when
      // present, and the write is mirrored onto the reverse edge — so this touches
      // nothing else on the document. `type` is the edge's identity for that
      // lookup, not a field being rewritten.
      body: JSON.stringify({ type: 'transversal', effects: draft.effects }),
    })
    if (!r.ok) throw new Error(await r.text())
    props.link.effects = draft.effects
    savedAt.value = Date.now()
  } catch (e) {
    console.error('[portal-effects] save failed', e)
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.portal-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 10px;
  font-size: 12px;
}
.portal-to {
  color: var(--text);
  font-weight: 600;
}
.portal-type {
  font-size: 10px;
  text-transform: uppercase;
  color: var(--text-dim);
  padding: 1px 6px;
  border-radius: 3px;
  background: var(--overlay-4);
}
.portal-save-msg {
  font-size: 10px;
  color: var(--text-dim);
}
.portal-save-msg.is-saved {
  color: var(--success, #40b860);
}
.portal-effects {
  margin-bottom: 12px;
}
</style>
