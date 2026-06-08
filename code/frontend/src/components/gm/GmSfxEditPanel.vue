<template>
  <div>
    <div class="ps-form">
      <label>Name</label>
      <input v-model="form.name" />
      <label>Trigger</label>
      <select v-model="form.trigger">
        <option value="">--</option>
        <option value="on_roll">On Roll</option>
        <option value="on_effect">On Effect</option>
        <option value="passive">Passive</option>
        <option value="manual">Manual</option>
      </select>
      <label>Description</label>
      <textarea v-model="form.description" rows="3"></textarea>
      <button class="save-btn" @click="$emit('save', form)" :disabled="saving">{{ saving ? 'Saving…' : 'Save' }}</button>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'

const props = defineProps({
  sfx: { type: Object, default: null },
})

const emit = defineEmits(['save', 'close'])
const saving = ref(false)

const form = reactive({
  name: props.sfx?.name || '',
  trigger: props.sfx?.trigger || '',
  description: props.sfx?.description || '',
})
</script>

<style scoped>
.ps-form { display: flex; flex-direction: column; gap: 6px; }
.ps-form label { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; }
.ps-form input, .ps-form select, .ps-form textarea { font-size: 12px; padding: 6px 8px; }
.save-btn { background: var(--success) !important; color: #0a0a0f !important; font-weight: 600; margin-top: 4px; padding: 8px; border-radius: 6px; border: none; cursor: pointer; }
</style>
