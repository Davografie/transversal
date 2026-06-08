<template>
  <div>
    <div class="ps-form">
      <label>Name</label>
      <input v-model="form.name" />
      <label>Universes</label>
      <ChipInput v-model="form.universes" :options="universeOptions" placeholder="Add universe…" />
      <label>Entity Types</label>
      <ChipInput v-model="form.entityTypes" :options="entityTypeOptions" placeholder="Add type…" />
      <label>Limit</label>
      <input v-model.number="form.limit" type="number" min="1" />
      <button class="save-btn" @click="save" :disabled="saving">{{ saving ? 'Saving…' : 'Save Traitset' }}</button>
    </div>

    <h4 class="ps-section-title">Traits</h4>
    <div class="ps-list">
      <div v-for="t in traits" :key="t.id" class="entity-row"
        :class="{ selected: selectedId === t.id }"
        @click="$emit('select-trait', t)">
        <span class="entity-name">{{ t.name }}</span>
        <span :class="'die-' + (t.defaultDieType||'d6').toLowerCase()" style="font-weight:700;font-size:11px">{{ t.defaultDieType||'d6' }}</span>
      </div>
      <div v-if="traits.length === 0" class="empty">No traits in this set</div>
    </div>
    <button class="ps-add-btn" @click="$emit('add-trait')">+ New Trait</button>
  </div>
</template>

<script setup>
import { reactive, ref, watch } from 'vue'

const props = defineProps({
  traitset: { type: Object, default: null },
  traits: { type: Array, default: () => [] },
  selectedId: { type: String, default: '' },
})

const emit = defineEmits(['save', 'select-trait', 'add-trait', 'close'])
const saving = ref(false)

const form = reactive({
  name: '',
  universes: '',
  entityTypes: '',
  limit: 1,
})

watch(() => props.traitset, (ts) => {
  if (ts) {
    form.name = ts.name || ''
    form.universes = (ts.universes || []).join(', ')
    form.entityTypes = (ts.entity_types || []).join(', ')
    form.limit = ts.limit || 1
  }
}, { immediate: true })

function save() {
  emit('save', {
    id: props.traitset?.id,
    name: form.name,
    universes: form.universes.split(',').map(s => s.trim()).filter(Boolean),
    entityTypes: form.entityTypes.split(',').map(s => s.trim()).filter(Boolean),
    limit: form.limit,
  })
}
</script>

<style scoped>
.ps-form { display: flex; flex-direction: column; gap: 6px; }
.ps-form label { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; }
.ps-form input { font-size: 12px; padding: 6px 8px; }
.save-btn { background: var(--success) !important; color: #0a0a0f !important; font-weight: 600; margin-top: 4px; padding: 8px; border-radius: 6px; border: none; cursor: pointer; }
.ps-section-title { font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 1px; margin-top: 12px; padding-top: 8px; border-top: 1px solid rgba(255,255,255,0.08); }
.ps-list { display: flex; flex-direction: column; gap: 3px; }
.entity-row { display: flex; align-items: center; gap: 6px; padding: 8px 10px; border-radius: 6px; cursor: pointer; background: rgba(255,255,255,0.03); transition: background 0.15s; font-size: 13px; }
.entity-row:hover { background: rgba(255,255,255,0.06); }
.entity-row.selected { background: rgba(64,136,212,0.15); border: 1px solid var(--accent-dim); }
.entity-name { flex: 1; font-weight: 500; }
.empty { font-size: 12px; color: var(--text-dim); padding: 12px 0; text-align: center; }
.ps-add-btn { font-size: 12px; padding: 6px; margin-top: 8px; background: var(--accent-dim); color: var(--text); border-radius: 6px; border: none; cursor: pointer; width: 100%; }
.ps-add-btn:hover { background: var(--accent); }
</style>
