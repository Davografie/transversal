<template>
  <div class="image-viewer">
    <MediaImage v-if="record" :src="detailSrc(record)" class="viewer-media" :alt="altText" />

    <!-- Animate is the one action that is entity-only: the endpoint takes an
         entity, and a trait has no motion to generate. Cut out and upscale work
         for either owner, so they sit outside it. -->
    <div v-if="isEntity" class="animate-section">
      <div class="motion-hint-row">
        <input v-if="!statusInfo.cancelling" v-model="motionHint" type="text" placeholder="Motion hint (optional) — e.g. 'hair blowing in wind'" />
        <Button
          class="animate-btn"
          :class="{ cancelling: statusInfo.cancelling }"
          :loading="animating"
          @click="onAnimateClick"
          variant="secondary"
        >
          <span class="btn-label">{{ statusInfo.label }}</span>
          <span v-if="statusInfo.status" class="btn-status">{{ statusInfo.status }}</span>
        </Button>
      </div>
    </div>

    <div v-if="record && !hasRender('animated')" class="action-rows">
      <Button
        v-if="canUpscale(record) || jobFor('upscale')"
        class="bg-btn"
        :loading="busy === 'upscale'"
        :disabled="busy === 'upscale' || !!jobFor('upscale')"
        @click="onUpscale"
        variant="neutral"
      >
        <span class="btn-label">⤢ {{ upscaleLabel }}</span>
      </Button>
      <Button
        v-if="canCutOut(record)"
        class="bg-btn"
        :loading="busy === 'cutout'"
        :disabled="busy === 'cutout' || !!jobFor('remove_bg')"
        @click="onCutOut"
        variant="neutral"
      >
        <span class="btn-label">{{ bgLabel }}</span>
      </Button>
    </div>

    <div class="role-assign">
      <label
        v-for="tag in ROLE_TAGS"
        :key="tag.key"
        class="role-check"
        :title="tag.title"
      >
        <input type="checkbox" :checked="hasRole(tag.key)" @change="toggleRole(tag.key)" />
        {{ tag.label }}
      </label>
    </div>

    <details class="credits-block">
      <summary>Credits &amp; source</summary>
      <ImageCreditsEditor
        :image-id="imageId"
        :credits="record?.credits || []"
        :license="record?.license || ''"
        :credit-text="record?.credit_text || ''"
        @saved="onChanged"
      />
    </details>

    <div class="flag-assign">
      <label class="flag-check" title="AI was somewhere in this picture's workflow — tick this for art you know involved AI">
        <input type="checkbox" :checked="hasFlag(record, 'ai')" @change="toggleFlag('ai')" />
        <span class="flag-pill" :class="{ 'is-on': hasFlag(record, 'ai') }">AI</span>
      </label>
      <span
        v-for="f in autoFlags(record)"
        :key="f"
        class="flag-pill is-on is-auto"
        :title="f === 'ai_generated' ? 'Made by the imagen pipeline' : 'Motion made by the animate pipeline'"
      >{{ AUTO_FLAG_LABELS[f] }}</span>
      <span
        v-if="record && record.can_upscale === false"
        class="flag-pill is-on is-auto"
        title="At the 2048px ceiling — the XLarge tier is real detail"
      >XL</span>
    </div>

    <div v-if="isEntity" class="body-assign">
      <label class="body-label">Body</label>
      <select v-model="imageProjection" class="body-select" @change="onProjectionChange">
        <option value="">Entity (default)</option>
        <option v-for="p in entityProjections" :key="p.id" :value="p.id">{{ projectionLabel(p) }}</option>
      </select>
    </div>

    <div class="image-meta">{{ altText }}<span v-if="fileExt" class="meta-ext"> · {{ fileExt }}</span></div>
    <div v-if="error" class="message message-error">{{ error }}</div>
    <div v-if="message" class="message">{{ message }}</div>

    <div class="danger-zone">
      <h4>Danger Zone</h4>
      <div class="danger-actions">
        <Button class="delete-btn" :loading="busy === 'delete'" :disabled="busy === 'delete'" @click="onDelete" variant="danger" solid>🗑 Delete</Button>
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * The one image viewer ([[B211]]).
 *
 * Before this it was **entity-only** — it fetched an entity's projections and
 * keyed every call by `entityId` — which is exactly why the trait editor grew its
 * own inline editor with a second copy of the role and flag controls. It now takes
 * an owner (`kind` + `id`) and reads the picture out of the gallery list, so
 * there is no second copy of its roles or flags to go stale, and the same control
 * serves an entity, a trait, and anything that owns pictures later.
 */
import { computed, onMounted, ref, watch } from 'vue'
import Button from '@/components/ui/Button.vue'
import ImageCreditsEditor from '@/components/ImageCreditsEditor.vue'
import MediaImage from '@/components/MediaImage.vue'
import { useImageGallery } from '@/composables/useImageGallery.js'
import {
  AUTO_FLAG_LABELS, ROLE_TAGS, autoFlags, canCutOut, canUpscale,
  detailSrc, hasFlag as hasFlagOn,
} from '@/components/image/imageMeta.js'

const props = defineProps({
  ownerKind: { type: String, default: 'entity' },
  ownerId: { type: String, default: '' },
  imageId: { type: String, default: '' },
  //: The opener's list row, so the picture paints before this viewer's own fetch
  //: lands. Everything else is read from the record it fetches.
  image: { type: Object, default: null },
})

const emit = defineEmits(['close', 'deleted', 'refresh'])

const {
  images, error, job, busy, load, toggleRole: setRole, toggleFlag: setFlag,
  assignTo, cutOut, upscale, remove, jobFor,
} = useImageGallery(() => ({ kind: props.ownerKind, id: props.ownerId }))

const record = computed(() => images.value.find(i => i.id === props.imageId) || props.image || null)
const isEntity = computed(() => props.ownerKind === 'entity')
const hasRender = (name) => (record.value?.renders || []).includes(name)
const hasRole = (role) => (record.value?.roles || []).includes(role)
const hasFlag = (flag) => hasFlagOn(record.value, flag)

const message = ref('')
const animating = ref(false)
const motionHint = ref('')

const altText = computed(() => {
  const r = record.value
  if (!r) return ''
  return `${r.image_type} — ${r.width}×${r.height}`
})
const fileExt = computed(() => {
  const m = (detailSrc(record.value) || '').match(/\.(\w+)(\?|$)/)
  return m ? m[1] : ''
})

onMounted(load)

function onChanged() {
  load()
  emit('refresh')
}

async function toggleRole(role) {
  if (!record.value) return
  await setRole(record.value, role)
  onChanged()
}

async function toggleFlag(flag) {
  if (!record.value) return
  await setFlag(record.value, flag)
  onChanged()
}

// ── Body (projection) assignment — the tap-friendly alternative to drag-drop ──
const imageProjection = ref('')
const entityProjections = ref([])

async function fetchProjections() {
  if (!isEntity.value || !props.ownerId) return
  try {
    const r = await fetch('/api/v1/graphql', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: 'query($id: ID!) { entity(id: $id) { projections { id name universe originUniverse } } }',
        variables: { id: props.ownerId },
      }),
    })
    if (r.ok) {
      const data = await r.json()
      entityProjections.value = data.data?.entity?.projections || []
    }
  } catch { /* the picker is optional; the panel is still usable without it */ }
}

onMounted(fetchProjections)

// The record arrives from the opener first and from the fetch a moment later, so
// seed the picker from whichever has it — but never overwrite a choice the user
// has already made in this panel.
watch(record, (r) => {
  if (!imageProjection.value && r?.projection_id) imageProjection.value = r.projection_id
}, { immediate: true })

function projectionLabel(p) {
  const uni = p.universe || p.originUniverse || ''
  const name = p.name || ''
  if (name && uni) return `${name} · ${uni}`
  return name || uni || p.id
}

async function onProjectionChange() {
  await assignTo(props.imageId, imageProjection.value)
  onChanged()
}

// ── Upscale (detail pass) ────────────────────────────
const upscaleLabel = computed(() => {
  if (jobFor('upscale')) return 'Upscaling…'
  return record.value?.upscaled ? 'Upscaled' : 'Upscale'
})

async function onUpscale() {
  message.value = 'Upscaling…'
  const ok = await upscale(props.imageId)
  message.value = ok ? 'Upscaling started — the picture refreshes when it lands' : (error.value || 'Failed')
}

// ── Background removal ───────────────────────────────
const bgLabel = computed(() => (jobFor('remove_bg') ? 'Removing background…' : '🧼 Remove BG'))

async function onCutOut() {
  message.value = 'Removing background…'
  const ok = await cutOut(props.imageId)
  message.value = ok ? 'Background removal started — it appears when it lands' : (error.value || 'Failed')
}

// ── Animate (entity only) ────────────────────────────
const statusInfo = computed(() => {
  const j = jobFor('animate')
  if (!j) return { label: '🎬 Animate', status: '', cancelling: false }
  if (j.status === 'failed') return { label: '🎬 Animate', status: '!', cancelling: false }
  return { label: 'Cancel', status: '✕', cancelling: true }
})

function onAnimateClick() {
  if (statusInfo.value.cancelling) cancelAnimate()
  else startAnimate()
}

async function startAnimate() {
  if (!props.ownerId || animating.value) return
  animating.value = true
  message.value = 'Starting animation...'
  try {
    const r = await fetch(`/api/v1/animate/${props.ownerId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image_id: props.imageId, motion_hint: motionHint.value }),
    })
    const d = await r.json().catch(() => ({}))
    message.value = d.accepted ? 'Animation started — it appears when it lands' : 'Failed'
  } catch {
    message.value = 'Request failed'
  } finally {
    animating.value = false
  }
}

async function cancelAnimate() {
  if (!props.ownerId) return
  try {
    await fetch(`/api/v1/imagen/${props.ownerId}/cancel`, { method: 'POST' })
    message.value = 'Cancelled'
  } catch {
    message.value = 'Cancel failed'
  }
}

async function onDelete() {
  const ok = await remove(props.imageId)
  if (ok) {
    emit('deleted')
    emit('close')
  } else {
    message.value = error.value || 'Delete failed'
  }
}
</script>

<style scoped>
.image-viewer { text-align: center; }
.image-viewer img { max-width: 100%; max-height: 60vh; border-radius: 4px; }
.viewer-media { max-width: 100%; max-height: 60vh; border-radius: 4px; }

.animate-section { margin-top: 8px; }
.motion-hint-row { display: flex; gap: 6px; align-items: center; }
.motion-hint-row input { flex: 1; font-size: 11px; padding: 4px 8px; border-radius: 4px; border: 1px solid var(--overlay-12); background: var(--overlay-6); color: var(--text); }
/* Split button: label + status segments sit flush, so the button itself keeps
   zero padding/gap and clips the status segment's corners. */
.motion-hint-row .animate-btn { padding: 0; gap: 0; overflow: hidden; white-space: nowrap; }
.motion-hint-row .animate-btn.cancelling { background: var(--danger-strong); color: var(--text-on-accent); }
.animate-btn .btn-label { padding: 4px 8px; }
.animate-btn .btn-status { padding: 4px 8px; background: rgba(0, 0, 0, 0.25); font-weight: 600; }

.action-rows { display: flex; gap: 6px; justify-content: center; margin-top: 6px; flex-wrap: wrap; }
.action-rows .bg-btn { padding: 0; overflow: hidden; white-space: nowrap; }
.bg-btn .btn-label { padding: 4px 8px; }

.role-assign { display: flex; gap: 8px; justify-content: center; margin-top: 6px; }
.role-check { font-size: 10px; color: var(--text-dim); cursor: pointer; display: flex; align-items: center; gap: 2px; }
.role-check input { margin: 0; cursor: pointer; }

/* Provenance labels — deliberately unlike the role row, since these do not
   assign the picture anywhere. */
.credits-block { margin-top: 6px; font-size: 10px; color: var(--text-dim); }
.credits-block summary { cursor: pointer; }
.credits-block[open] summary { margin-bottom: 5px; }
.flag-assign { display: flex; gap: 6px; justify-content: center; align-items: center; margin-top: 4px; flex-wrap: wrap; }
.flag-check { display: flex; align-items: center; gap: 3px; cursor: pointer; }
.flag-check input { margin: 0; cursor: pointer; }
.flag-pill {
  font-size: 9px; padding: 1px 5px; border-radius: 3px; letter-spacing: 0.02em;
  border: 1px solid var(--border); color: var(--text-dim); opacity: 0.65;
}
.flag-pill.is-on { opacity: 1; color: var(--text); border-color: var(--accent, #6c8cff); }
.flag-pill.is-auto { cursor: default; }

.body-assign { display: flex; gap: 6px; justify-content: center; align-items: center; margin-top: 4px; }
.body-label { font-size: 9px; color: var(--text-dim); text-transform: uppercase; }
.body-select { font-size: 10px; padding: 2px 6px; border-radius: 3px; border: 1px solid var(--overlay-10); background: var(--overlay-4); color: var(--text); }

.image-meta { font-size: 10px; color: var(--text-dim); margin-top: 6px; }
.meta-ext { color: var(--text-dim); text-transform: uppercase; }
.message { font-size: 11px; color: var(--accent); margin-top: 6px; }
.message-error { color: var(--danger-soft, #e07a7a); }

.danger-zone {
  margin-top: 12px; padding: 10px;
  border: 1px solid var(--danger-20); border-radius: 6px;
  background: var(--danger-8); text-align: left;
}
.danger-zone h4 {
  font-size: 10px; color: var(--danger-soft); text-transform: uppercase; letter-spacing: 1px;
  margin: 0 0 8px 0;
}
.danger-actions { display: flex; gap: 6px; }
</style>
