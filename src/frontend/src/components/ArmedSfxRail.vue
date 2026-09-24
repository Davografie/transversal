<template>
  <div v-if="cards.length" class="armed-sfx-rail" aria-label="Active SFX">
    <div class="armed-sfx-rail__heading">Active</div>
    <button
      v-for="sfx in cards"
      :key="sfx.id"
      class="armed-sfx-card"
      :class="{ 'armed-sfx-card--open': expandedId === sfx.id }"
      :title="sfx.description || sfx.name"
      @click.stop="expandedId = expandedId === sfx.id ? null : sfx.id"
    >
      <span class="armed-sfx-card__pulse" aria-hidden="true"></span>
      <span class="armed-sfx-card__name">{{ sfx.name }}</span>
      <span v-if="expandedId !== sfx.id" class="armed-sfx-card__hint">
        {{ shortHint(sfx) }}
      </span>

      <div v-if="expandedId === sfx.id" class="armed-sfx-card__detail">
        <p v-if="sfx.description" class="armed-sfx-card__desc">{{ sfx.description }}</p>
        <dl class="armed-sfx-card__meta">
          <div v-if="sfx.trigger" class="armed-sfx-card__meta-row">
            <dt>Trigger</dt>
            <dd>{{ labelize(sfx.trigger) }}</dd>
          </div>
          <div v-if="sfx.armingScope" class="armed-sfx-card__meta-row">
            <dt>Listens to</dt>
            <dd>{{ labelize(sfx.armingScope) }}</dd>
          </div>
          <div v-if="durationLabel(sfx)" class="armed-sfx-card__meta-row">
            <dt>Duration</dt>
            <dd>{{ durationLabel(sfx) }}</dd>
          </div>
          <div v-if="sourceLabel(sfx)" class="armed-sfx-card__meta-row">
            <dt>Source</dt>
            <dd>{{ sourceLabel(sfx) }}</dd>
          </div>
        </dl>

        <div v-if="sfx.activation?.bindings?.length" class="armed-sfx-card__bound">
          <div class="armed-sfx-card__bound-head">Bound</div>
          <ul class="armed-sfx-card__bindings">
            <li v-for="b in sfx.activation.bindings" :key="b.name" class="armed-sfx-card__binding">
              <span class="armed-sfx-card__binding-name">{{ '{' + b.name + '}' }}</span>
              <span class="armed-sfx-card__binding-value">{{ b.summary }}</span>
            </li>
          </ul>
        </div>

        <ul v-if="sfx.effects?.length" class="armed-sfx-card__effects">
          <li v-for="(fx, i) in sfx.effects" :key="i" class="armed-sfx-card__effect">
            <span class="armed-sfx-card__effect-timing">{{ labelize(fx.timing) }}</span>
            <span class="armed-sfx-card__effect-body">{{ effectLine(fx) }}</span>
          </li>
        </ul>
      </div>
    </button>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useApi } from '../composables/useApi.js'
import { formatTimers } from '../composables/useScheduledEvents.js'

const props = defineProps({
  entityId: { type: String, default: '' },
  phase: { type: String, default: 'adding' },
  refreshKey: { type: Number, default: 0 },
})

const { graphql } = useApi()

const active = ref([])   // what this activation holds: source + bound names
const catalog = ref({}) // sfxId → the authored definition (description, trigger, duration, effects)
const expandedId = ref(null)
let refreshTimer = null

// A card is the definition plus what *this* activation holds — two queries
// because a definition is authored once, while a source and its bound variables
// exist only while the rule is running in this process.
const cards = computed(() => active.value
  .map((a) => ({ ...(catalog.value[a.sfxId] || {}), ...a, id: a.sfxId, activation: a }))
  .filter((c) => c.name))

function labelize(str) {
  if (!str) return ''
  return String(str)
    .replace(/^sfx-/, '')
    .replace(/[_-]+/g, ' ')
    .toLowerCase()  // GraphQL enums arrive screaming (IMMEDIATE, ON_ROLL)
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

function shortHint(sfx) {
  const parts = []
  if (sfx.trigger && sfx.trigger !== 'manual') parts.push(labelize(sfx.trigger))
  const duration = durationLabel(sfx)
  if (duration) parts.push(duration)
  return parts.join(' · ')
}

function durationLabel(sfx) {
  return formatTimers(sfx.duration?.timers, sfx.duration?.combine)
}

// Where the rule was activated from — the instance it lives on, named where the
// repository can, falling back to the declared kind.
function sourceLabel(sfx) {
  const a = sfx.activation
  if (!a) return ''
  return a.sourceName || (a.sourceKind ? labelize(a.sourceKind) : '')
}

function effectLine(fx) {
  const parts = [fx.type, fx.action].filter(Boolean)
  const target = fx.target || fx.entity
  if (target) parts.push(target)
  if (fx.result) parts.push(`→ ${fx.result}`)
  return parts.map(labelize).join(' · ')
}

async function loadCatalog() {
  try {
    const data = await graphql(
      `query {
        sfxs {
          id name description trigger placement armingScope
          duration { timers { event remaining } combine }
          effects { timing type action target entity result }
        }
      }`,
    )
    const map = {}
    for (const s of data?.sfxs || []) {
      map[s.id] = { ...s, armingScope: s.armingScope }
    }
    catalog.value = map
  } catch (e) {
    console.error('[ArmedSfxRail] catalog', e)
  }
}

async function loadActive() {
  const id = props.entityId
  if (!id) { active.value = []; return }
  try {
    const data = await graphql(
      `query($id: ID!) {
        activeSfx(entityId: $id) {
          sfxId name sourceKind sourceId sourceName
          bindings { name element cardinality summary }
        }
      }`,
      { id },
    )
    active.value = data?.activeSfx || []
  } catch (e) {
    console.error('[ArmedSfxRail] activeSfx', e)
  }
}

function scheduleRefresh() {
  clearTimeout(refreshTimer)
  refreshTimer = setTimeout(async () => {
    if (!Object.keys(catalog.value).length) await loadCatalog()
    await loadActive()
  }, 120)
}

watch(
  () => [props.entityId, props.phase, props.refreshKey],
  () => scheduleRefresh(),
  { immediate: true },
)
</script>

<style scoped>
.armed-sfx-rail {
  position: fixed;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
  /* One below the GM panel layer (`.panel-viewport` 25 / `.gm-toggle` 26): this
     rail is sheet chrome, so a panel the GM has opened must be able to cover it.
     At 30 it floated *over* every GM panel, which is what looked wrong. It stays
     above the centred page overlays (LocationViewer 22, PoolDiceRing 23) so the
     left edge keeps reading while they are up. */
  z-index: 24;
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-width: 220px;
  max-height: 70dvh;
  overflow-y: auto;
  pointer-events: auto;
}

.armed-sfx-rail__heading {
  font-size: 10px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--text-dim, #8890a0);
  padding-left: 8px;
  margin-bottom: 2px;
}

.armed-sfx-card {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  text-align: left;
  background: var(--overlay-8, rgba(255, 255, 255, 0.06));
  border: 1px solid var(--overlay-12, rgba(255, 255, 255, 0.12));
  border-radius: 10px;
  padding: 8px 10px;
  color: var(--text, #e8eaf0);
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease;
}

.armed-sfx-card:hover,
.armed-sfx-card--open {
  background: var(--overlay-14, rgba(255, 255, 255, 0.14));
  border-color: var(--accent, rgba(140, 200, 255, 0.5));
}

.armed-sfx-card__pulse {
  position: absolute;
  left: -4px;
  top: 50%;
  transform: translateY(-50%);
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent, #7dd3fc);
  box-shadow: 0 0 8px var(--accent, #7dd3fc);
  animation: armed-pulse 2.4s ease-in-out infinite;
}

@keyframes armed-pulse {
  0%, 100% { opacity: 0.9; }
  50% { opacity: 0.3; }
}

.armed-sfx-card__name {
  font-weight: 600;
  font-size: 13px;
  line-height: 1.2;
  padding-left: 6px;
}

.armed-sfx-card__hint {
  font-size: 11px;
  color: var(--text-dim, #8890a0);
  padding-left: 6px;
}

.armed-sfx-card__detail {
  margin-top: 4px;
  padding-top: 6px;
  border-top: 1px solid var(--overlay-12, rgba(255, 255, 255, 0.12));
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 100%;
}

.armed-sfx-card__desc {
  font-size: 12px;
  color: var(--text, #e8eaf0);
  margin: 0;
}

.armed-sfx-card__meta {
  display: flex;
  flex-direction: column;
  gap: 3px;
  margin: 0;
}

.armed-sfx-card__meta-row {
  display: flex;
  gap: 6px;
  font-size: 11px;
}

.armed-sfx-card__meta-row dt {
  color: var(--text-dim, #8890a0);
  flex: 0 0 auto;
}

.armed-sfx-card__meta-row dd {
  margin: 0;
  color: var(--text, #e8eaf0);
}

.armed-sfx-card__bound {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.armed-sfx-card__bound-head {
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-dim, #8890a0);
}

.armed-sfx-card__bindings {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.armed-sfx-card__binding {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 11px;
}

.armed-sfx-card__binding-name {
  color: var(--accent, #7dd3fc);
  font-family: var(--font-mono, monospace);
}

.armed-sfx-card__binding-value {
  color: var(--text, #e8eaf0);
  text-align: right;
}

.armed-sfx-card__effects {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.armed-sfx-card__effect {
  font-size: 11px;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.armed-sfx-card__effect-timing {
  color: var(--accent, #7dd3fc);
  text-transform: uppercase;
  font-size: 10px;
  letter-spacing: 0.06em;
}

.armed-sfx-card__effect-body {
  color: var(--text, #e8eaf0);
}

@media (max-width: 820px) {
  .armed-sfx-rail {
    left: 6px;
    max-width: 150px;
    max-height: 52dvh;
  }
  .armed-sfx-card__name {
    font-size: 12px;
  }
}
</style>
