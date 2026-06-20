<template>
  <div>
    <label>Name</label><input v-model="form.name" autofocus />
    <label>Type</label><select v-model="form.type"><option v-for="t in entityTypes" :key="t" :value="t">{{ t }}</option></select>
    <label>Universe</label><select v-model="form.universe"><option v-for="u in universes" :key="u.key" :value="u.key">{{ u.name }}</option></select>
    <label>Location</label><select v-model="form.location"><option value="">-- None --</option><option v-for="l in locationEntities" :key="l.id" :value="l.id">{{ l.name }}</option></select>
    <label>Razmerit</label><input v-model.number="form.razmerit" type="number" />
    <button class="save-btn" @click="onSubmit" :disabled="saving || !form.name.trim()">{{ saving ? 'Creating…' : 'Create' }}</button>
  </div>
</template>

<script setup>
import { reactive } from 'vue'

defineProps({
  universes: { type: Array, default: () => [] },
  locationEntities: { type: Array, default: () => [] },
  saving: { type: Boolean, default: false },
  entityTypes: { type: Array, default: () => ['CHARACTER', 'LOCATION', 'GMC', 'FACTION', 'ASSET'] },
})

const emit = defineEmits(['create'])

const initForm = () => ({ name: '', type: 'CHARACTER', universe: 'earth', location: '', razmerit: 0 })
const form = reactive(initForm())

function onSubmit() {
  emit('create', { ...form })
  Object.assign(form, initForm())
}
</script>

<style scoped>
label { font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; display: block; margin-top: 8px; }
input, select { font-size: 13px; padding: 6px 10px; width: 100%; box-sizing: border-box; }
.save-btn { background: var(--success); color: #0a0a0f; font-weight: 600; margin-top: 8px; padding: 8px; border-radius: 6px; border: none; cursor: pointer; width: 100%; }
.save-btn:disabled { opacity: 0.5; cursor: default; }
</style>
