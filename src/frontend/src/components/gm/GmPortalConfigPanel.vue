<template>
  <div>
    <div class="portal-head">
      <span class="portal-to">{{ fromName }} → {{ link.name }}</span>
      <span class="portal-type">{{ link.transversal_type || 'inapposite' }}</span>
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
    <div class="actions">
      <Button class="save-btn" :loading="saving" :disabled="saving" @click="save" variant="success" solid>{{ saving ? 'Saving…' : 'Save' }}</Button>
      <button class="cancel-btn" @click="panel.close()">Cancel</button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { usePanel } from '@/composables/usePanel.js'
import EffectEditor from './EffectEditor.vue'
import Button from '@/components/ui/Button.vue'

const props = defineProps({
  fromId: { type: String, required: true },
  fromName: { type: String, default: '' },
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
  background: var(--overlay-4);
}
.portal-effects {
  margin-bottom: 12px;
}
.actions {
  display: flex;
  gap: 6px;
}
.cancel-btn {
  padding: 6px 14px;
  border-radius: 6px;
  border: 1px solid var(--overlay-10);
  background: var(--overlay-2);
  color: var(--text);
  cursor: pointer;
  font-size: 12px;
}
.cancel-btn:hover {
  background: var(--overlay-6);
}
</style>
