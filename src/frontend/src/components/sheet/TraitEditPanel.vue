<template>
  <div class="trait-edit-panel">
    <Button class="set-back" variant="link" @click="$emit('back')">← Back</Button>
    <h4 class="edit-title">{{ displayName(trait.name) }}</h4>

    <!-- What the instance *is*. Changing it repoints the instance at another
         registry trait and leaves everything the instance owns alone — so this
         belongs at the top, above the fields that survive the change. -->
    <div class="edit-field">
      <span class="edit-label">Definition</span>
      <template v-if="canRedeclare">
        <div class="edit-definition">
          <button type="button" class="definition-chip" @click="$emit('toggle-definition-picker')">
            {{ displayName(trait.name) }}
          </button>
          <span v-if="definitionPending" class="edit-definition-note">saving…</span>
        </div>
        <div v-if="showDefinitionPicker" class="definition-dropdown">
          <select
            class="definition-set-filter"
            :value="effectiveTraitsetFilter"
            aria-label="Filter trait definitions by trait set"
            @change="$emit('update:definitionTraitsetFilter', $event.target.value)"
          >
            <option value="">All trait sets</option>
            <option v-for="ts in definitionTraitsets" :key="ts.id" :value="ts.id">{{ ts.name }}</option>
          </select>
          <input
            :value="definitionFilter"
            class="definition-filter"
            type="search"
            placeholder="Filter traits…"
            aria-label="Filter trait definitions"
            @input="$emit('update:definitionFilter', $event.target.value)"
          />
          <button
            v-for="opt in filteredDefinitions"
            :key="opt.id"
            type="button"
            class="definition-option"
            :class="{ selected: opt.id === trait.traitId }"
            @click="pickDefinition(opt)"
          >{{ displayName(opt.name) }}</button>
          <!-- Say which filter is doing the hiding: "nothing matches" is wrong and
               unhelpful when the set filter alone is the reason the list is bare. -->
          <span v-if="!filteredDefinitions.length" class="edit-sfx-none">{{ emptyDefinitionNote }}</span>
        </div>
      </template>
      <!-- A relationship's traits are the substance of the relationship itself,
           so they cannot be redefined — the row is "what this connection holds",
           and pointing it at another trait would rewrite the connection. -->
      <span v-else class="edit-definition-fixed" title="A relationship's own traits cannot be redefined">
        {{ displayName(trait.name) }}
      </span>
    </div>

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
          <div v-if="visibleSfxIds.length" class="edit-sfx">
            <button
              v-for="sfxId in visibleSfxIds"
              :key="sfxId"
              class="sfx-chip"
              :class="{ assigned: sfxIds.includes(sfxId) }"
              @click="$emit('toggle-sfx', sfxId)"
            >{{ sfxId.replace('sfx-', '') }}</button>
          </div>
          <span v-else class="edit-sfx-none">none acquirable here</span>
        </div>
      </template>

      <template #after-fields>
        <div class="edit-field">
          <span class="edit-label">Tags</span>
          <TagInput
            v-model="tagsModel"
            :suggestions="tagSuggestions"
            placeholder="Add a tag…"
            aria-label="Trait instance tags"
          />
          <span v-if="inheritTags.length" class="edit-tags-inherited">
            from the trait: {{ inheritTags.join(', ') }}
          </span>
        </div>
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

        <!-- Image (B200 slice 2) — this instance's own picture. It is stored on
             the setting's rung of the ladder, so it **overrides the registry
             trait's** for whichever roles it carries: inheritance is the empty
             case, not a copy. -->
        <div class="edit-field">
          <span class="edit-label">Image</span>
          <ImageGallery
            :images="instanceImages"
            :selected-id="openedImageId"
            empty="Inherits the definition's picture."
            @open="openInstanceImage"
          />
          <div class="edit-image-actions">
            <ImageUpload
              owner-kind="trait"
              :owner-id="trait.traitId"
              :variant-id="trait.id"
              :universe="trait.universe || ''"
              :label="instanceImages.length ? 'Upload another' : 'Upload an override'"
              @uploaded="onInstanceImageChanged"
            />
            <span v-if="instanceImages.length" class="edit-image-hint">
              the first picture takes every role, so it overrides at once
            </span>
          </div>
          <!-- The trait's own pictures, as a pool this instance can draw from:
               the trait carries the canonical art, and an instance picks which
               of it is its own rather than uploading another copy by hand. -->
          <div v-if="definitionImages.length" class="edit-image-picks">
            <span class="edit-image-hint">or take one of the trait's own:</span>
            <ImageGallery
              :images="definitionImages"
              empty=""
              :draggable="false"
              @open="useDefinitionImage"
            />
          </div>
          <span v-if="imagesError" class="edit-image-error">{{ imagesError }}</span>
          <span v-if="pickError" class="edit-image-error">{{ pickError }}</span>
          <!-- The shared viewer, rendered **inline**: this panel is mounted both
               inside a GM panel and directly by the player app, and only the
               former has a panel stack to push a child panel onto. -->
          <div v-if="openedImageId" class="edit-image-viewer">
            <Button variant="link" size="sm" @click="openedImageId = ''">← Done with this picture</Button>
            <ImageViewer
              owner-kind="trait"
              :owner-id="trait.traitId"
              :image-id="openedImageId"
              :image="openedImageRecord"
              @close="openedImageId = ''"
              @deleted="onInstanceImageChanged()"
              @refresh="onInstanceImageChanged()"
            />
          </div>
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
import { computed, ref } from 'vue'
import Button from '@/components/ui/Button.vue'
import TagInput from '@/components/ui/TagInput.vue'
import TraitInstanceEditor from '@/components/ui/TraitInstanceEditor.vue'
import { copyImage, useImageGallery } from '@/composables/useImageGallery.js'
import ImageGallery from '@/components/image/ImageGallery.vue'
import ImageUpload from '@/components/image/ImageUpload.vue'
import ImageViewer from '@/components/gm/ImageViewer.vue'

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
  /**
   * The instance's possible SFX whose acquire gate holds right now.
   * `null` = not answered yet — then the full possible list is shown, because a
   * pending (or failed) query must not hide chips. The attach enforces the gate
   * server-side regardless.
   */
  /**
   * The instance's own tags (B116) — editable here. The registry trait's tags
   * are authoring, not instance state, and are only shown as context.
   */
  tags: { type: Array, default: () => [] },
  /** Read-only: tags inherited from the registry trait, shown dimmed. */
  inheritTags: { type: Array, default: () => [] },
  tagSuggestions: { type: Array, default: () => [] },
  acquirableSfxIds: { type: Array, default: null },
  /**
   * Every definition this instance could become — already scoped to the
   * entity's current universe and filtered by the container rule, so the list
   * only ever offers changes the write path accepts. `null` = not loaded yet;
   * the sheet fetches it the first time the picker is opened.
   */
  definitionOptions: { type: Array, default: null },
  /** False for a relationship's own traits, which carry the connection itself. */
  canRedeclare: { type: Boolean, default: true },
  /** True while the repoint mutation is in flight. */
  definitionPending: { type: Boolean, default: false },
  /**
   * Whether the definition list is open, and its filter text.
   *
   * These are the *sheet's* state, not the panel's, for the same reason
   * `showProjectionPicker` lives in `useTraitEditor`: this panel is re-created
   * when the sheet re-renders, so anything held locally here is lost the moment
   * the option list arrives. Owning it in the panel made the first click on the
   * chip open the list and then silently wipe it — the sheet's update landed,
   * the panel was replaced, and the dropdown never appeared.
   */
  showDefinitionPicker: { type: Boolean, default: false },
  definitionFilter: { type: String, default: '' },
  /**
   * The trait sets the candidate definitions live in — `[{ id, name }]`, already
   * narrowed to sets that actually hold a candidate, so the filter never offers a
   * set that would come back empty. Empty until the list is fetched.
   */
  definitionTraitsets: { type: Array, default: () => [] },
  /**
   * The chosen trait set, or `null` for "wherever this instance already lives".
   *
   * `null` rather than the id so the default is *derived*: the picker then opens
   * on the instance's own set without anything having to keep a stored id in step
   * with the edited trait, which is the class of bug that broke this picker in the
   * first place.
   */
  definitionTraitsetFilter: { type: String, default: null },
})

const emit = defineEmits([
  'update:dice', 'update:capacity', 'update:statement', 'update:notes',
  'rating-type', 'change', 'field-blur', 'recover-die',
  'back', 'delete', 'toggle-sfx', 'toggle-ego', 'toggle-polarity',
  'toggle-projection-picker', 'select-projection', 'add-subtrait', 'remove-subtrait',
  'toggle-definition-picker', 'update:definitionFilter', 'change-definition',
  'update:definitionTraitsetFilter', 'image-changed',
])

// ── The instance's own picture ───────────────────────
// Owner is the **registry trait**, rung is the **setting** — the same shape a
// projection has against an entity, and the reason one canonical definition
// picture can serve every instance until an instance wants its own.
const openedImageId = ref('')
const pickError = ref('')
const {
  images: traitImages,
  error: imagesError,
  load: loadInstanceImages,
} = useImageGallery(
  () => ({ kind: 'trait', id: props.trait?.traitId || '', universe: props.trait?.universe || '' }),
  // One read of the trait, and the two lists below are derived from it: this
  // instance's rung, and the definition pictures it may take one from. Two
  // filtered readers would be two fetches and two job pollers for one section.
)

//: This instance's own pictures — the rung is the setting.
const instanceImages = computed(
  () => traitImages.value.filter(i => (i.variant_id || null) === (props.trait?.id || null)),
)
//: The trait's definition pictures — the pool an instance may pick from.
const definitionImages = computed(() => traitImages.value.filter(i => !i.variant_id))

async function useDefinitionImage(img) {
  if (!img || !props.trait) return
  pickError.value = ''
  try {
    await copyImage({
      imageId: img.id,
      ownerKind: 'trait',
      ownerId: props.trait.traitId,
      variantId: props.trait.id,
    })
    onInstanceImageChanged()
  } catch (e) {
    pickError.value = e?.message || 'Could not use that picture'
  }
}

const openedImageRecord = computed(
  () => instanceImages.value.find(i => i.id === openedImageId.value) || null,
)

function openInstanceImage(img) {
  openedImageId.value = img.id
}

function onInstanceImageChanged() {
  loadInstanceImages()
  // The row's picture comes from the sheet's own query (`sheetImage` on the
  // setting), which this panel does not own — so the sheet has to re-read for the
  // change to show on the row behind it.
  emit('image-changed')
}

/** The set actually being filtered on: the chosen one, else the instance's own. */
const effectiveTraitsetFilter = computed(
  () => props.definitionTraitsetFilter ?? props.trait.traitsetId ?? '',
)

const filteredDefinitions = computed(() => {
  const set = effectiveTraitsetFilter.value
  const opts = (props.definitionOptions || []).filter(o => !set || o.traitsetId === set)
  const q = props.definitionFilter.trim().toLowerCase()
  const matched = q
    ? opts.filter(o => String(o.name || '').toLowerCase().includes(q))
    : opts
  // Alphabetical by the *label*, not the raw name: the list is read top-down and
  // the label is what the eye is scanning, and the two can differ because the
  // label capitalises and strips underscores. Case-insensitive, so `Fire Blade`
  // and `fire blade` do not sort into separate runs.
  return [...matched].sort((a, b) =>
    definitionLabel(a).localeCompare(definitionLabel(b), undefined, { sensitivity: 'base' }))
})

const emptyDefinitionNote = computed(() => {
  const named = props.definitionTraitsets.some(ts => ts.id === effectiveTraitsetFilter.value)
  if (named) return 'Nothing else in this trait set — try “All trait sets”.'
  return 'No trait matches.'
})

function pickDefinition(opt) {
  if (opt.id === props.trait.traitId) return
  // The picker's open state belongs to the sheet, so closing it is the sheet's
  // job too (`changeDefinition` does it) — the panel only reports the choice.
  emit('change-definition', opt.id)
}

// v-model proxies onto the parent's draft refs.
const diceModel = computed({ get: () => props.dice, set: (v) => emit('update:dice', v) })
const capacityModel = computed({ get: () => props.capacity, set: (v) => emit('update:capacity', v) })
const statementModel = computed({ get: () => props.statement, set: (v) => emit('update:statement', v) })
const notesModel = computed({ get: () => props.notes, set: (v) => emit('update:notes', v) })
// TagInput drives a v-model; the editor persists on the same path as the other
// fields, so the setter writes the draft and then asks the sheet to save.
const tagsModel = computed({
  get: () => props.tags,
  set: (v) => { emit('update:tags', v); emit('change', 'tags') },
})

/**
 * What the chip list shows: rules acquirable here, plus anything already
 * assigned. An attached rule has to stay visible after its acquire gate stops
 * holding, or it could never be toggled off from the sheet.
 */
const visibleSfxIds = computed(() => {
  const possible = props.trait.possibleSfxIds || []
  if (props.acquirableSfxIds == null) return possible
  const acquirable = new Set(props.acquirableSfxIds)
  const assigned = new Set(props.sfxIds || [])
  return possible.filter((id) => acquirable.has(id) || assigned.has(id))
})

function displayName(name) {
  return name
    .split('_')
    .map(w => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

/** The text a definition option shows — the same string the list is sorted on. */
function definitionLabel(opt) {
  return displayName(String(opt?.name || ''))
}
</script>

<style scoped>
.trait-edit-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 4px 0 8px;
}
.edit-image-actions { display: flex; align-items: center; gap: 8px; margin-top: 6px; flex-wrap: wrap; }
.edit-image-hint { font-size: 10px; color: var(--text-dim); }
.edit-image-error { font-size: 10px; color: var(--danger, #e06c75); }
.edit-image-picks { margin-top: 8px; display: flex; flex-direction: column; gap: 4px; }
.edit-image-viewer { margin-top: 8px; border-top: 1px solid var(--overlay-12); padding-top: 6px; }

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
/* The definition chip reads like the projection chip below it, because both are
   "what this instance currently is/points at" and both open a picker. */
.edit-definition {
  display: flex;
  align-items: center;
  gap: 8px;
}
.edit-definition-note {
  font-size: 10px;
  color: var(--text-dim);
  font-style: italic;
}
.edit-definition-fixed {
  font-size: 12px;
  color: var(--text-dim);
  cursor: not-allowed;
}
.definition-chip {
  padding: 4px 12px;
  border-radius: 999px;
  border: 1px solid var(--accent-dim);
  background: var(--accent-12);
  color: var(--accent);
  font-size: 12px;
  cursor: pointer;
}
.definition-chip:hover {
  border-color: var(--accent);
}
.definition-dropdown {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-top: 6px;
  max-height: 220px;
  overflow-y: auto;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px;
}
.definition-set-filter {
  margin-bottom: 4px;
  padding: 5px 8px;
  border-radius: 4px;
  border: 1px solid var(--overlay-10);
  background: var(--overlay-4);
  color: var(--text);
  font-size: 12px;
}
.definition-filter {
  margin-bottom: 4px;
  padding: 5px 8px;
  border-radius: 4px;
  border: 1px solid var(--overlay-10);
  background: var(--overlay-4);
  color: var(--text);
  font-size: 12px;
}
.definition-option {
  display: block;
  width: 100%;
  padding: 5px 8px;
  background: transparent;
  border: none;
  border-radius: 4px;
  color: var(--text);
  font-size: 12px;
  text-align: left;
  cursor: pointer;
}
.definition-option:hover {
  background: var(--bg-hover);
}
.definition-option.selected {
  color: var(--accent);
  background: var(--accent-12);
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
/* Shown only when every possible rule is gated out — better than the field
   silently vanishing, which reads as a bug. */
.edit-sfx-none {
  font-size: 11px;
  color: var(--text-dim);
  font-style: italic;
}
/* Registry tags are inherited, not editable here — dimmed so they read as
   context rather than as something the instance carries of its own. */
.edit-tags-inherited {
  display: block;
  margin-top: 4px;
  font-size: 10px;
  color: var(--text-dim);
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
