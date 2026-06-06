<template>
  <div class="trait-editor">
    <h4 class="traits-heading">Traits</h4>
    <div v-if="traits?.length" class="trait-list">
      <div v-for="ts in traits" :key="ts.id" class="trait-row">
        <span class="trait-name">{{ ts.name }}</span>
        <span class="trait-die" :class="'die-' + ts.dieType.toLowerCase()">{{ ts.dieType }}</span>
        <span v-if="ts.ego" class="trait-ego">ego</span>
        <button class="trait-remove" @click="$emit('remove-trait', ts.id)">×</button>
      </div>
    </div>
    <div v-else class="empty">No traits assigned</div>

    <div class="add-trait">
      <select v-model="newTraitId" @change="onTraitSelected">
        <option value="">-- Add trait --</option>
        <option v-for="t in availableTraits" :key="t.id" :value="t.id">
          {{ t.name }} ({{ t.defaultDieType }})
        </option>
      </select>
      <div v-if="newTraitId" class="add-trait-detail">
        <label>Die</label>
        <select v-model="dieType">
          <option v-for="d in dieTypes" :key="d" :value="d">{{ d }}</option>
        </select>
        <label>Rating</label>
        <input v-model="rating" placeholder="d8" />
        <label>Statement</label>
        <input v-model="statement" placeholder="Distinction statement…" />
        <button @click="emitAdd" :disabled="adding">Add</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({
  traits: { type: Array, default: () => [] },
  availableTraits: { type: Array, default: () => [] },
  adding: { type: Boolean, default: false },
  dieTypes: { type: Array, default: () => ['d4', 'd6', 'd8', 'd10', 'd12'] },
})

const emit = defineEmits(['add-trait', 'remove-trait'])

const newTraitId = ref('')
const dieType = ref('d6')
const rating = ref('')
const statement = ref('')

function onTraitSelected() {
  const t = props.availableTraits.find(t => t.id === newTraitId.value)
  if (t) { dieType.value = t.defaultDieType.toLowerCase(); rating.value = t.defaultDieType.toLowerCase() }
}

function emitAdd() {
  const t = props.availableTraits.find(t => t.id === newTraitId.value)
  emit('add-trait', { traitId: newTraitId.value, traitsetId: t?.traitsetId || '', dieType: dieType.value.toUpperCase(), rating: rating.value || dieType.value, statement: statement.value })
  newTraitId.value = ''; dieType.value = 'd6'; rating.value = ''; statement.value = ''
}
</script>

<style scoped>
.traits-heading {
  font-size: 12px; color: var(--text-dim); text-transform: uppercase;
  letter-spacing: 1px; margin-top: 12px; padding-top: 8px;
  border-top: 1px solid rgba(255,255,255,0.08);
}
.trait-list { display: flex; flex-direction: column; gap: 4px; }
.trait-row {
  display: flex; align-items: center; gap: 6px;
  padding: 4px 8px; background: rgba(255,255,255,0.04); border-radius: 4px; font-size: 12px;
}
.trait-name { flex: 1; font-weight: 500; }
.trait-die { font-weight: 700; font-size: 11px; }
.die-d4  { color: #e88830; } .die-d6  { color: #e0e0e0; } .die-d8  { color: #d44040; }
.die-d10 { color: #4088d4; } .die-d12 { color: #40b860; }
.trait-ego {
  font-size: 9px; background: var(--accent-dim); color: var(--accent);
  padding: 1px 5px; border-radius: 3px; text-transform: uppercase;
}
.trait-remove { font-size: 14px; padding: 2px 6px; background: none; color: var(--danger); border-radius: 4px; }
.trait-remove:hover { background: rgba(212,64,64,0.15); }

.add-trait { margin-top: 8px; }
.add-trait select { width: 100%; font-size: 12px; }
.add-trait-detail {
  display: flex; flex-direction: column; gap: 6px; margin-top: 8px; padding: 8px;
  background: rgba(255,255,255,0.03); border-radius: 6px;
}
.add-trait-detail label { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; }
.add-trait-detail input, .add-trait-detail select { font-size: 12px; padding: 6px 10px; }
.add-trait-detail button { font-size: 12px; padding: 6px; }

.empty { font-size: 12px; color: var(--text-dim); padding: 12px 0; text-align: center; }
</style>
