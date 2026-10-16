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
    <div class="portal-effects">
      <EffectEditor
        v-model="effects"
        :universe="universe"
        :portal-destination="link.name"
        :portal-target-type="link.type"
        :portal-universe="link.current_universe"
        :portal-root-id="link.type === 'location' ? link._key : ''"
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
// for you.
import { ref, watch, onUnmounted } from 'vue'
import EffectEditor from './EffectEditor.vue'

const props = defineProps({
  fromId: { type: String, required: true },
  fromName: { type: String, default: '' },
  link: { type: Object, required: true },
  universe: { type: String, default: '' },
})

// The draft is seeded **before** the watcher is registered, so this initial copy
// is not an edit. Nothing re-seeds it afterwards: the draft belongs to the panel,
// and each write keeps the parent's copy in step instead (below).
const effects = ref((props.link.effects || []).map((e) => ({ ...e })))
const saving = ref(false)
const savedAt = ref(null)

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

watch(effects, scheduleSave, { deep: true, flush: 'sync' })

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
      body: JSON.stringify({ type: 'transversal', effects: effects.value }),
    })
    if (!r.ok) throw new Error(await r.text())
    props.link.effects = effects.value
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
