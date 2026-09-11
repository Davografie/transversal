<template>
  <div class="trait-edit-panel">
    <Button class="set-back" variant="link" @click="$emit('back')">← Back</Button>
    <h4 class="edit-title">{{ displayName(trait.name) }}</h4>

    <TraitInstanceEditor
      v-model:dice="diceModel"
      v-model:capacity="capacityModel"
      v-model:statement="statementModel"
      v-model:notes="notesModel"
      :rating-type="ratingType"
      :show-polarity="false"
      :show-statement="trait.statement !== undefined"
      :show-notes="trait.notes !== undefined || !!notes"
      :spent-dice="trait.spentDice || []"
      @update:rating-type="$emit('rating-type', $event)"
      @change="$emit('change', $event)"
      @field-blur="$emit('field-blur', $event)"
      @recover-die="$emit('recover-die', $event)"
    >
      <template #after-dice>
        <div v-if="trait.possibleSfxIds?.length" class="edit-field">
          <span class="edit-label">SFX</span>
          <div class="edit-sfx">
            <button
              v-for="sfxId in trait.possibleSfxIds"
              :key="sfxId"
              class="sfx-chip"
              :class="{ assigned: sfxIds.includes(sfxId) }"
              @click="$emit('toggle-sfx', sfxId)"
            >{{ sfxId.replace('sfx-', '') }}</button>
          </div>
        </div>
      </template>

      <template #after-fields>
        <div class="edit-field">
          <span class="edit-label">Type</span>
          <div class="edit-flags">
            <button
              v-if="trait.fromType !== 'relationship'"
              type="button"
              class="ego-toggle"
              :class="{ 'is-ego': isEgo }"
              @click="$emit('toggle-ego')"
            >{{ isEgo ? 'ego' : 'morph' }}</button>
            <button
              type="button"
              class="polarity-toggle"
              :class="{ 'is-positive': polarity === 'POSITIVE' }"
              @click="$emit('toggle-polarity')"
            >{{ polarity === 'POSITIVE' ? 'positive' : 'negative' }}</button>
          </div>
          <div v-if="!isEgo && trait.fromType !== 'relationship'" class="edit-projection">
            <span class="edit-projection-label">on</span>
            <button type="button" class="projection-chip" @click="$emit('toggle-projection-picker')">{{ projectionName }}</button>
            <div v-if="showProjectionPicker" class="projection-dropdown">
              <button
                v-for="p in projectionOptions"
                :key="p.id"
                type="button"
                class="projection-option"
                :class="{ selected: p.id === projectionId }"
                @click="$emit('select-projection', p)"
              >{{ p.name }}</button>
            </div>
          </div>
        </div>

        <div class="edit-field">
          <span class="edit-label">Sub-traits</span>
          <div v-if="(trait.subTraitSettings || []).length" class="edit-subtraits">
            <div v-for="st in trait.subTraitSettings" :key="st.id" class="edit-subtrait-row">
              <span class="edit-subtrait-name">{{ displayName(st.name) }}</span>
              <span v-if="st.statement" class="edit-subtrait-statement">{{ st.statement }}</span>
              <Button class="edit-subtrait-remove" variant="danger-ghost" size="sm" title="Remove sub-trait" @click="$emit('remove-subtrait', st.id)">✕</Button>
            </div>
          </div>
          <div v-if="subtraits.length" class="edit-subtraits-add">
            <span class="edit-subtrait-add-label">Add:</span>
            <button v-for="opt in subtraits" :key="opt.id" class="edit-subtrait-chip" @click="$emit('add-subtrait', opt.id)">{{ opt.name }}</button>
          </div>
          <span v-else-if="!(trait.possibleSubtraitIds || []).length" class="edit-subtrait-empty">No sub-traits configured for this trait.</span>
        </div>
      </template>

      <template #actions>
        <div class="edit-actions">
          <Button class="edit-done-btn" variant="primary" @click="$emit('back')">Done</Button>
          <Button
            class="edit-delete-btn"
            variant="danger"
            :active="deleteCountdown > 0 && deletingTraitId === trait.id"
            @click="$emit('delete', trait)"
          >
            {{ deleteCountdown > 0 && deletingTraitId === trait.id ? `Cancel (${deleteCountdown})` : 'Delete' }}
          </Button>
        </div>
      </template>
    </TraitInstanceEditor>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import Button from '@/components/ui/Button.vue'
import TraitInstanceEditor from '@/components/ui/TraitInstanceEditor.vue'

// The sheet's full-panel trait editor: a header, the shared rating editor, and
// the sheet-specific extras (SFX chips, ego/morph + projection, sub-traits,
// Done/Delete). Fully controlled — it emits every interaction and the sheet
// owns the draft state and persistence.
const props = defineProps({
  /** The trait being edited (from the sheet's trait sets / profile list). */
  trait: { type: Object, required: true },
  dice: { type: Array, default: () => [] },
  capacity: { type: Array, default: () => [] },
  ratingType: { type: String, default: 'STATIC' },
  polarity: { type: String, default: null },
  statement: { type: String, default: '' },
  notes: { type: String, default: '' },
  sfxIds: { type: Array, default: () => [] },
  isEgo: { type: Boolean, default: true },
  projectionId: { type: String, default: null },
  projectionName: { type: String, default: '' },
  /** Already resolved to display names: [{ id, name }]. */
  projectionOptions: { type: Array, default: () => [] },
  /** Sub-trait candidates not yet assigned: [{ id, name }]. */
  subtraits: { type: Array, default: () => [] },
  showProjectionPicker: { type: Boolean, default: false },
  deleteCountdown: { type: Number, default: 0 },
  deletingTraitId: { type: String, default: null },
})

const emit = defineEmits([
  'update:dice', 'update:capacity', 'update:statement', 'update:notes',
  'rating-type', 'change', 'field-blur', 'recover-die',
  'back', 'delete', 'toggle-sfx', 'toggle-ego', 'toggle-polarity',
  'toggle-projection-picker', 'select-projection', 'add-subtrait', 'remove-subtrait',
])

// v-model proxies onto the parent's draft refs.
const diceModel = computed({ get: () => props.dice, set: (v) => emit('update:dice', v) })
const capacityModel = computed({ get: () => props.capacity, set: (v) => emit('update:capacity', v) })
const statementModel = computed({ get: () => props.statement, set: (v) => emit('update:statement', v) })
const notesModel = computed({ get: () => props.notes, set: (v) => emit('update:notes', v) })

function displayName(name) {
  return name
    .split('_')
    .map(w => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}
</script>

<style scoped>
.trait-edit-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 4px 0 8px;
}
.edit-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.edit-label {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.6px;
}
.edit-flags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  align-items: center;
}
.edit-title {
  margin: 0 0 2px;
  font-size: 14px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--text);
}
.edit-sfx {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}
.sfx-chip {
  font-size: 10px;
  padding: 3px 8px;
  border-radius: 4px;
  border: 1px solid var(--overlay-10);
  background: var(--overlay-4);
  color: var(--text-dim);
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s, color 0.15s;
}
.sfx-chip:hover {
  border-color: var(--overlay-20);
  color: var(--text);
}
.sfx-chip.assigned {
  background: var(--accent-dim);
  border-color: var(--accent);
  color: var(--accent);
}
.edit-subtraits {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.edit-subtrait-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  padding: 3px 8px;
  border-radius: 4px;
  border: 1px solid var(--overlay-10);
  background: var(--overlay-4);
}
.edit-subtraits-add {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
  margin-top: 4px;
}
.edit-subtrait-chip {
  font-size: 10px;
  padding: 3px 8px;
  border-radius: 4px;
  border: 1px solid var(--overlay-10);
  background: var(--overlay-4);
  color: var(--text-dim);
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s, color 0.15s;
}
.edit-subtrait-chip:hover {
  border-color: var(--accent);
  color: var(--accent);
}
.edit-actions {
  display: flex;
  gap: 6px;
  margin-top: 4px;
  padding-top: 12px;
  border-top: 1px solid var(--overlay-8);
}
.ego-toggle {
  padding: 3px 12px;
  border-radius: 999px;
  border: 1px solid var(--text-dim);
  background: transparent;
  color: var(--text-dim);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  cursor: pointer;
}
.ego-toggle.is-ego {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--overlay-6);
}
.polarity-toggle {
  padding: 3px 12px;
  border-radius: 999px;
  border: 1px solid var(--text-dim);
  background: transparent;
  color: var(--text-dim);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  cursor: pointer;
}
.polarity-toggle.is-positive {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--overlay-6);
}
.edit-projection {
  display: flex;
  align-items: center;
  gap: 6px;
  position: relative;
}
.edit-projection-label {
  font-size: 10px;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.projection-chip {
  padding: 3px 10px;
  border-radius: 999px;
  border: 1px solid var(--accent-dim);
  background: var(--accent-12);
  color: var(--accent);
  font-size: 11px;
  cursor: pointer;
}
.projection-chip:hover {
  border-color: var(--accent);
}
.projection-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  z-index: 20;
  margin-top: 4px;
  min-width: 160px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 6px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.4);
  overflow: hidden;
}
.projection-option {
  display: block;
  width: 100%;
  padding: 6px 10px;
  background: transparent;
  border: none;
  color: var(--text);
  font-size: 12px;
  text-align: left;
  cursor: pointer;
}
.projection-option:hover {
  background: var(--bg-hover);
}
.projection-option.selected {
  color: var(--accent);
  background: var(--accent-12);
}
.edit-subtrait-name { font-weight: 500; }
.edit-subtrait-statement { font-size: 11px; opacity: 0.7; flex: 1; }
.edit-subtrait-add-label { font-size: 11px; color: var(--text-dim); }
.edit-subtrait-empty { font-size: 11px; color: var(--text-dim); }
.edit-done-btn { flex: 1; }
.edit-delete-btn { flex: 1; }
.edit-subtrait-remove { margin-left: auto;
    flex-shrink: 0; }
</style>
