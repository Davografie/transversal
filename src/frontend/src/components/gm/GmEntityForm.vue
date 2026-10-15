<template>
  <div class="entity-form">
    <label>Name</label>
    <div class="name-row">
      <input v-model="local.name" @input="emitUpdate" />
      <Button
        variant="neutral"
        :loading="naming"
        :title="isUniverse
          ? `Generate a name in this world's theme${themeName ? ` (${themeName})` : ''}`
          : 'Generate a name in this entity\'s universe theme'"
        @click="onGenerateName"
      >🎲</Button>
    </div>

    <!-- Universe, Location, and Parent Location are managed by drag-and-drop in the tree view. -->

    <!-- B82: a world names the theme its people are named in. Read from the backend
         so a theme added there appears here without a frontend change, and a
         dropdown so an unknown theme cannot be typed. -->
    <template v-if="isUniverse">
      <label>Naming theme</label>
      <select class="naming-theme" :value="local.naming_theme || ''" @change="onThemeChange">
        <option value="">{{ defaultOptionLabel }}</option>
        <option v-for="t in themes" :key="t.key" :value="t.key">{{ t.label }}</option>
      </select>
      <p class="hint">Names generated in this universe sound like this.</p>
    </template>

    <!-- Razmerit: only CHARACTER, GMC, FACTION -->
    <template v-if="showRazmerit">
      <label>Razmerit</label>
      <input v-model.number="local.razmerit" type="number" @input="emitUpdate" />
    </template>

    <label>
      <input :checked="local.hidden" type="checkbox" @change="onToggleBool('hidden', $event)" />
      Hidden
    </label>

    <!-- B86: a GMC flagged here may be taken over by a player as a support character -->
    <template v-if="local.type === 'GMC'">
      <label title="A player may take this GMC over as their support character">
        <input :checked="local.support_eligible" type="checkbox" @change="onToggleBool('support_eligible', $event)" />
        Available for take-over
      </label>
    </template>

    <template v-if="local.type === 'LOCATION'">
      <label>
        <input :checked="local.starter_location" type="checkbox" @change="onToggleBool('starter_location', $event)" />
        Starter Location
      </label>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { hasRazmerit } from '@/constants/entityTypes.js'
import { useNaming } from '@/composables/useNaming.js'
import Button from '@/components/ui/Button.vue'

const props = defineProps({
  modelValue: { type: Object, default: () => ({}) },
  entityId: { type: String, default: null },
})

const emit = defineEmits(['update:modelValue'])

const local = ref({ ...props.modelValue })

watch(() => props.modelValue, (v) => { local.value = { ...v } }, { deep: true })

function emitUpdate() {
  emit('update:modelValue', { ...local.value })
}

// Boolean checkboxes: read the DOM state explicitly and emit in one step,
// avoiding the v-model + @change ordering ambiguity.
function onToggleBool(field, e) {
  local.value = { ...local.value, [field]: e.target.checked }
  emit('update:modelValue', { ...local.value })
}

// ── Field visibility by entity type ──────────────────
// The rule itself lives in `constants/entityTypes.js`, shared with the create
// panel, so the two doors cannot disagree about which types are rated.
const showRazmerit = computed(() => hasRazmerit(local.value.type))

// ── Naming (B82) ─────────────────────────────────────
const { themes, defaultTheme, loadThemes, generateName } = useNaming()
const naming = ref(false)

const isUniverse = computed(() => local.value.type === 'UNIVERSE')

// A universe names its own theme; anything else is named *by* its universe. The
// distinction matters for the button: opening a universe and pressing 🎲 should use
// the theme you are choosing on this very form, not the one it currently has.
const namingUniverse = computed(() => (isUniverse.value ? '' : (local.value.current_universe || '')))

const themeName = computed(
  () => themes.value.find((t) => t.key === (local.value.naming_theme || ''))?.label || '',
)
const defaultThemeLabel = computed(
  () => themes.value.find((t) => t.key === defaultTheme.value)?.label || defaultTheme.value,
)
// Reads "Default (Modern / Earth)" once loaded and plain "Default" before that —
// the first cut rendered the empty parentheses "Default ()" while the list was in
// flight, which is also what a failed fetch would have left on screen.
const defaultOptionLabel = computed(
  () => (defaultThemeLabel.value ? `Default (${defaultThemeLabel.value})` : 'Default'),
)

// A **watch, not `onMounted`**: the panel mounts this form before the entity it
// edits has loaded, so at mount `local.type` is still undefined, the check was
// false, and the themes were never fetched — the dropdown rendered with no options
// ("Default ()"). Watching the condition itself covers both orders, and `immediate`
// covers a form that is already a universe when it mounts.
watch(isUniverse, (v) => { if (v) loadThemes() }, { immediate: true })

async function onGenerateName() {
  naming.value = true
  try {
    const name = await generateName({
      theme: isUniverse.value ? (local.value.naming_theme || '') : '',
      universe: namingUniverse.value,
    })
    // Only the name changes: an empty result (a dead network) must not clear a name
    // the GM already typed.
    if (name) {
      local.value = { ...local.value, name }
      emitUpdate()
    }
  } finally {
    naming.value = false
  }
}

function onThemeChange(e) {
  local.value = { ...local.value, naming_theme: e.target.value }
  emitUpdate()
}
</script>

<style scoped>
.entity-form { display: flex; flex-direction: column; gap: 8px; }
.entity-form label {
  font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px;
}
.entity-form input, .entity-form select { font-size: 13px; padding: 6px 10px; }
/* The generate button sits beside the field it fills rather than under it, so the
   form does not reflow when it appears — the same shape the sheet's name row uses. */
.name-row { display: flex; gap: 6px; align-items: center; }
.name-row input { flex: 1; min-width: 0; }
.hint { margin: 0; font-size: 11px; color: var(--text-dim); }

</style>
