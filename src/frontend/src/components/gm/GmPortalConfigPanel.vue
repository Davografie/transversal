<template>
  <div>
    <div class="portal-head">
      <span class="portal-to">→ {{ link.name }}</span>
      <span class="portal-type">{{ link.transversal_type || 'inapposite' }}</span>
    </div>
    <div class="portal-effects">
      <EffectEditor v-model="effects" :universe="universe" />
    </div>
    <div class="actions">
      <button class="save-btn" :disabled="saving" @click="save">{{ saving ? 'Saving…' : 'Save' }}</button>
      <button class="cancel-btn" @click="panel.close()">Cancel</button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { usePanel } from '@/composables/usePanel.js'
import EffectEditor from './EffectEditor.vue'

const props = defineProps({
  fromId: { type: String, required: true },
  link: { type: Object, required: true },
  universe: { type: String, default: '' },
})

const panel = usePanel()
const effects = ref((props.link.effects || []).map((e) => ({ ...e })))
const saving = ref(false)

async function save() {
  saving.value = true
  try {
    const r = await fetch(`/api/v1/locations/${props.fromId}/edges/${props.link._key}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type: 'transversal', effects: effects.value }),
    })
    if (!r.ok) throw new Error(await r.text())
    props.link.effects = effects.value
    panel.close()
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
  background: rgba(255, 255, 255, 0.04);
}
.portal-effects {
  margin-bottom: 12px;
}
.actions {
  display: flex;
  gap: 6px;
}
.save-btn {
  background: var(--success);
  color: #0a0a0f;
  font-weight: 600;
  padding: 6px 14px;
  border-radius: 6px;
  border: none;
  cursor: pointer;
  font-size: 12px;
}
.save-btn:disabled {
  opacity: 0.5;
  cursor: default;
}
.cancel-btn {
  padding: 6px 14px;
  border-radius: 6px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.03);
  color: var(--text);
  cursor: pointer;
  font-size: 12px;
}
.cancel-btn:hover {
  background: rgba(255, 255, 255, 0.06);
}
</style>
