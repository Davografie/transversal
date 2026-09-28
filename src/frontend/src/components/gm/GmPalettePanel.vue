<template>
  <div class="gp-root">
    <div class="gp-pick">
      <label class="gp-label">Universe</label>
      <SearchDropdown
        :options="universeOptions"
        :model-value="key"
        value-key="key"
        label-key="name"
        placeholder="Choose a universe…"
        @select="(o) => select(o.key)"
      />
    </div>

    <p v-if="loading" class="gp-hint">Loading universes…</p>
    <p v-else-if="!key" class="gp-hint">Pick a universe to give it its own look.</p>
    <template v-else>
      <p class="gp-hint">
        A palette repaints the chrome — accent, surfaces, borders and type. Anything left
        blank keeps the app's own value. Changes preview live; <strong>Save</strong> keeps
        them. The map, the GM canvas and the dice never follow a palette.
      </p>

      <div v-for="theme in PALETTE_THEMES" :key="theme" class="gp-section">
        <div class="gp-section-head">
          <span class="gp-section-title">{{ theme === 'dark' ? 'Dark theme' : 'Light theme' }}</span>
          <span v-if="unsetCount(theme)" class="gp-unset">{{ unsetCount(theme) }} unset</span>
        </div>

        <div v-for="group in GROUPS" :key="group.title" class="gp-group">
          <div class="gp-group-title">{{ group.title }}</div>
          <div v-for="knob in group.knobs" :key="knob" class="gp-row" :class="{ 'is-warn': warningFor(theme, knob) }">
            <input
              class="gp-swatch"
              type="color"
              :value="hexOf(theme, knob)"
              :title="`Pick ${knob}`"
              :aria-label="`${group.title} ${knob}`"
              @input="setKnob(theme, knob, $event.target.value)"
            />
            <span class="gp-knob">{{ knob }}</span>
            <input
              class="gp-value"
              type="text"
              spellcheck="false"
              :value="valueOf(theme, knob)"
              :placeholder="`default`"
              @input="setKnob(theme, knob, $event.target.value)"
            />
            <Button
              v-if="valueOf(theme, knob)"
              class="gp-clear"
              variant="ghost"
              size="icon"
              :title="`Unset ${knob} (use the app's value)`"
              @click="setKnob(theme, knob, '')"
            >×</Button>
            <span v-if="warningFor(theme, knob)" class="gp-warn">
              {{ warningFor(theme, knob).ratio.toFixed(1) }}:1 on {{ warningFor(theme, knob).against }} — below the 3:1 floor
            </span>
          </div>
        </div>
      </div>

      <div class="gp-section">
        <div class="gp-section-head"><span class="gp-section-title">Type &amp; shape</span></div>
        <div class="gp-row">
          <span class="gp-knob gp-knob-wide">font.ui</span>
          <input class="gp-value gp-value-wide" type="text" spellcheck="false" placeholder="font stack, e.g. Georgia, serif"
                 :value="form.font?.ui || ''" @input="setFont('ui', $event.target.value)" />
        </div>
        <div class="gp-row">
          <span class="gp-knob gp-knob-wide">font.display</span>
          <input class="gp-value gp-value-wide" type="text" spellcheck="false" placeholder="defaults to font.ui"
                 :value="form.font?.display || ''" @input="setFont('display', $event.target.value)" />
        </div>
        <div class="gp-row">
          <span class="gp-knob gp-knob-wide">radius</span>
          <input class="gp-value" type="text" spellcheck="false" placeholder="e.g. 0px"
                 :value="form.radius || ''" @input="setRadius($event.target.value)" />
          <span class="gp-hint-inline">one value; the smaller steps derive from it</span>
        </div>
      </div>

      <div class="gp-actions">
        <Button variant="success" solid :loading="saving" :disabled="!dirty" @click="save">
          {{ saving ? 'Saving…' : 'Save' }}
        </Button>
        <Button variant="neutral" :disabled="!dirty || saving" @click="revert">Revert</Button>
        <Button variant="danger-ghost" :disabled="saving || !hasPalette" @click="clear">Clear</Button>
      </div>
      <p v-if="error" class="gp-error">{{ error }}</p>
      <p v-else-if="saved" class="gp-saved">{{ saved }}</p>
    </template>
  </div>
</template>

<script setup>
import { computed, onUnmounted, ref, watch } from 'vue'
import Button from '@/components/ui/Button.vue'
import SearchDropdown from '@/components/ui/SearchDropdown.vue'
import { useApi } from '@/composables/useApi.js'
import { KNOWN_KNOBS, THEMES as PALETTE_THEMES, cleanPalette, paletteContrastWarnings } from '@/assets/universePalette.js'
import { setPalettePreview } from '@/composables/useUniverseTheme.js'

// The authoring half of per-universe styling ([[UI-UX Design#The universe
// palette]]): the palette is data on the universe entity, and this is the only
// surface that writes it. It is a *dedicated panel* rather than a block inside
// the universe's entity editor, because a universe's look is a cross-cutting
// concern like traitsets or SFX — a GM looks for it in Prep's tools, not by
// hunting for the universe entity first.
//
// Three rules it keeps in step with the runtime:
//   * **blank means unset.** The runtime *omits* a knob to keep the app's value,
//     so `cleanPalette` drops empty fields rather than writing `""`;
//   * **no second source of truth for the mapping** — `paletteVars` is still the
//     only knob → token table, and this panel never names a CSS property;
//   * **live preview through the one writer.** `setPalettePreview` hands the
//     in-progress palette to `useUniverseTheme`, which owns `:root`; the panel
//     itself touches no styles.
const props = defineProps({
  /** The universe in play — the panel opens on it, and can switch. */
  universe: { type: String, default: '' },
})

const { graphql } = useApi()
const universes = ref([])
const key = ref(props.universe || '')
const form = ref({})
const loading = ref(true)
const saving = ref(false)
const dirty = ref(false)
const saved = ref('')
const error = ref('')

const universeOptions = computed(() =>
  universes.value
    .map((u) => ({ key: u.currentUniverse, name: u.name }))
    .filter((u) => u.key)
    .sort((a, b) => a.name.localeCompare(b.name))
)

// The vocabulary, grouped the way a person thinks about it rather than the way
// the tokens are named. `KNOWN_KNOBS.color` is the same list the mapper knows, so
// a knob can never be authored here that the runtime would ignore.
const GROUPS = [
  { title: 'Accent', knobs: ['accent', 'accentDim', 'accentActive'] },
  { title: 'Surfaces', knobs: ['bgDeep', 'bgOverlay', 'bgPanel', 'bgPanelSolid', 'bgPanelRaised'] },
  { title: 'Text', knobs: ['text', 'textDim'] },
  { title: 'Borders', knobs: ['border', 'borderSoft', 'borderStrong'] },
].map((g) => ({ ...g, knobs: g.knobs.filter((k) => KNOWN_KNOBS.color.includes(k)) }))

const current = computed(() => universes.value.find((u) => u.currentUniverse === key.value) || null)
const hasPalette = computed(() => Object.keys(form.value?.dark || {}).length > 0 || Object.keys(form.value?.light || {}).length > 0)

const valueOf = (theme, knob) => form.value?.[theme]?.[knob] || ''
const warningFor = (theme, knob) => warnings.value[theme]?.find((w) => w.knob === knob) || null
const unsetCount = (theme) => GROUPS.reduce((n, g) => n + g.knobs.filter((k) => !valueOf(theme, k)).length, 0)

// A colour input cannot show `rgba(...)` or a missing value, so it shows the
// opaque hex it can parse and otherwise a neutral chip; the **text field is the
// value**, which is what lets translucent surfaces be authored at all.
const hexOf = (theme, knob) => {
  const v = valueOf(theme, knob)
  const m = v.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i)
  if (m) return m[1].length === 3 ? '#' + m[1].split('').map((c) => c + c).join('') : v
  const rgba = v.match(/rgba?\(([^)]+)\)/i)
  if (rgba) {
    const [r, g, b] = rgba[1].split(',').map((s) => Math.round(parseFloat(s)))
    if ([r, g, b].every((n) => Number.isFinite(n))) {
      return '#' + [r, g, b].map((n) => Math.max(0, Math.min(255, n)).toString(16).padStart(2, '0')).join('')
    }
  }
  return '#808080'
}

const warnings = computed(() => Object.fromEntries(
  PALETTE_THEMES.map((t) => [t, paletteContrastWarnings(form.value, t)]),
))

// Dirty is set by an *edit*, not by the form changing: adopting a stored palette
// (open, Revert, switching universe) rewrites the whole object, and a watcher
// could not tell that apart from a keystroke — the panel opened claiming unsaved
// work.
function setKnob(theme, knob, value) {
  form.value = { ...form.value, [theme]: { ...(form.value[theme] || {}), [knob]: value } }
  dirty.value = true
}
function setFont(slot, value) {
  form.value = { ...form.value, font: { ...(form.value.font || {}), [slot]: value } }
  dirty.value = true
}
function setRadius(value) {
  form.value = { ...form.value, radius: value }
  dirty.value = true
}

async function loadUniverses() {
  loading.value = true
  const data = await graphql(`{ entities(type: UNIVERSE) { id name currentUniverse palette } }`)
  universes.value = data?.entities || []
  if (!key.value || !universes.value.some((u) => u.currentUniverse === key.value)) {
    key.value = universes.value[0]?.currentUniverse || ''
  }
  loading.value = false
}

function adopt() {
  const u = current.value
  try {
    form.value = u?.palette ? JSON.parse(u.palette) : {}
  } catch {
    form.value = {}
    error.value = 'This universe\'s stored palette is not valid JSON — Clear replaces it.'
  }
  dirty.value = false
  saved.value = ''
}

// The list is loaded once; switching universe only re-reads the palette it already
// carries. It used to refetch and adopt twice, which could land *after* a keystroke
// and silently replace what the GM had typed.
function select(next) {
  key.value = next
  adopt()
}

function revert() {
  adopt()
  error.value = ''
}

async function save() {
  const u = current.value
  if (!u) {
    // Never a silent no-op: a Save that does nothing is indistinguishable from a
    // Save that worked, and the GM's next click is a lost edit.
    error.value = 'The universe list is still loading — nothing was saved.'
    return
  }
  saving.value = true
  error.value = ''
  saved.value = ''
  try {
    const clean = cleanPalette(form.value)
    const payload = JSON.stringify(clean)
    const res = await graphql(
      `mutation($input: UpdateEntityInput!) { updateEntity(input: $input) { id palette } }`,
      { input: { id: u.id, palette: payload } },
    )
    if (!res) throw new Error('save failed')
    u.palette = payload
    dirty.value = false
    setPalettePreview(null)   // the stored value is what the runtime now paints
    saved.value = 'Saved.'
  } catch (e) {
    error.value = e?.message || 'Could not save the palette.'
  } finally {
    saving.value = false
  }
}

async function clear() {
  const u = current.value
  if (!u) return
  saving.value = true
  error.value = ''
  saved.value = ''
  try {
    // `""` is the resolver's "clear it" — the universe goes back to the app's
    // own look, and `backfill_universe_palettes.py` can put an example back.
    const res = await graphql(
      `mutation($input: UpdateEntityInput!) { updateEntity(input: $input) { id palette } }`,
      { input: { id: u.id, palette: '' } },
    )
    if (!res) throw new Error('clear failed')
    u.palette = null
    form.value = {}
    dirty.value = false
    setPalettePreview(null)
    saved.value = 'Cleared — this universe uses the app\'s default look again.'
  } catch (e) {
    error.value = e?.message || 'Could not clear the palette.'
  } finally {
    saving.value = false
  }
}

// Preview follows the form, not the save: a GM picking a colour sees the chrome
// change (the composable is still the only writer of `:root`).
watch(form, (v) => setPalettePreview(key.value, v), { deep: true })
// Leaving the panel must release the preview, or an unsaved experiment keeps
// painting after the panel is gone.
onUnmounted(() => setPalettePreview(null))

// Adopt only once the list is in: an editable form populated from a list that is
// still arriving is a form whose contents can be overwritten mid-edit.
loadUniverses().then(adopt)
</script>

<style scoped>
/* Two columns of knobs where there is room: four groups × five rows is a long
   scroll on one. */
.gp-root { display: flex; flex-direction: column; gap: 10px; font-size: 11px; color: var(--text); }
.gp-pick { display: flex; flex-direction: column; gap: 4px; }
.gp-label { font-size: 9px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-dim); }
.gp-hint { font-size: 10px; color: var(--text-dim); line-height: 1.45; }
.gp-hint-inline { font-size: 9px; color: var(--text-dim); }

.gp-section { display: flex; flex-direction: column; gap: 6px; border-top: 1px solid var(--border-soft); padding-top: 8px; }
.gp-section-head { display: flex; justify-content: space-between; align-items: baseline; }
.gp-section-title { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: var(--accent); }
.gp-unset { font-size: 9px; color: var(--text-dim); }

.gp-group { display: flex; flex-direction: column; gap: 3px; }
.gp-group-title { font-size: 9px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-dim); }

.gp-row { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.gp-swatch {
  flex: none; width: 22px; height: 22px; padding: 0; border: 1px solid var(--border);
  border-radius: var(--radius-xs); background: none; cursor: pointer;
}
.gp-knob { flex: none; width: 84px; font-family: monospace; font-size: 10px; color: var(--text-dim); }
.gp-knob-wide { width: 88px; }
.gp-value {
  flex: 1; min-width: 90px; font-family: monospace; font-size: 10px;
  padding: 3px 6px; background: var(--overlay-6); color: var(--text);
  border: 1px solid var(--border); border-radius: var(--radius-xs);
}
.gp-value-wide { min-width: 140px; }
.gp-clear { flex: none; }
.gp-row.is-warn .gp-value { border-color: var(--danger); }

/* The floor, in the row it applies to — an authored palette can be unreadable,
   and the warning is where the value is, not in a summary line. */
.gp-warn { flex-basis: 100%; font-size: 9px; color: var(--danger-bright); }

.gp-actions { display: flex; gap: 6px; align-items: center; }
.gp-error { font-size: 10px; color: var(--danger-bright); }
.gp-saved { font-size: 10px; color: var(--success); }
</style>
