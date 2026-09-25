<template>
  <div class="image-viewer">
    <MediaImage :src="imageType === 'animated' && animatedSrc ? animatedSrc : src" class="viewer-media" :alt="alt" />

    <div class="animate-section" v-if="imageType !== 'animated'">
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
      <div class="bg-remove-row" v-if="imageType !== 'cutout'">
        <Button class="bg-btn" :loading="bgBusy" :disabled="bgBusy || !!localBgJob" @click="onRemoveBgClick" variant="neutral">
          <span class="btn-label">{{ bgLabel }}</span>
        </Button>
      </div>
    </div>
    <div class="role-assign">
      <label class="role-check" title="Use as background"><input type="checkbox" :checked="hasRole('background')" @change="toggleRole('background')" /> BG</label>
      <label class="role-check" title="Use as character sheet portrait"><input type="checkbox" :checked="hasRole('sheet')" @change="toggleRole('sheet')" /> Sheet</label>
      <label class="role-check" title="Use as navigation dot"><input type="checkbox" :checked="hasRole('navdot')" @change="toggleRole('navdot')" /> Nav</label>
    </div>
    <details class="credits-block">
      <summary>Credits &amp; source</summary>
      <ImageCreditsEditor
        :image-id="imageId"
        :credits="fetchedCredits"
        :license="fetchedLicense"
        :credit-text="fetchedCreditText"
        @saved="onCreditsSaved"
      />
    </details>
    <div class="flag-assign">
      <label class="flag-check" title="AI was somewhere in this image's workflow — tick this for art you know involved AI">
        <input type="checkbox" :checked="hasFlag('ai')" @change="toggleFlag('ai')" />
        <span class="flag-pill" :class="{ 'is-on': hasFlag('ai') }">AI</span>
      </label>
      <span
        v-for="f in autoFlags"
        :key="f"
        class="flag-pill is-on is-auto"
        :title="f === 'ai_generated' ? 'Made by the imagen pipeline' : 'Motion made by the animate pipeline'"
      >{{ AUTO_FLAG_LABELS[f] }}</span>
    </div>
    <div class="body-assign">
      <label class="body-label">Body</label>
      <select v-model="imageProjection" class="body-select" @change="onProjectionChange">
        <option value="">Entity (default)</option>
        <option v-for="p in entityProjections" :key="p.id" :value="p.id">{{ projectionLabel(p) }}</option>
      </select>
    </div>
    <div class="image-meta">{{ alt }}<span v-if="fileExt" class="meta-ext"> · {{ fileExt }}</span><span v-if="sizeBytes" class="meta-size"> · {{ formatBytes(sizeBytes) }}</span></div>
    <div v-if="message" class="message">{{ message }}</div>

    <div class="danger-zone">
      <h4>Danger Zone</h4>
      <div class="danger-actions">
        <Button class="delete-btn" :loading="deleting" :disabled="deleting" @click="onDelete" variant="danger" solid>🗑 Delete</Button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import ImageCreditsEditor from '@/components/ImageCreditsEditor.vue'
import MediaImage from '@/components/MediaImage.vue'
import Button from '@/components/ui/Button.vue'

const props = defineProps({
  src: { type: String, required: true },
  alt: { type: String, default: '' },
  entityId: { type: String, default: '' },
  imageId: { type: String, default: '' },
  imageType: { type: String, default: '' },
  animateJob: { type: Object, default: null },
  animatedSrc: { type: String, default: '' },
  // Both are passed by the opener and were previously undeclared, so the size
  // never rendered and the tags relied on a fetch that only ran on mount.
  roles: { type: Array, default: () => [] },
  sizeBytes: { type: Number, default: 0 },
})

const emit = defineEmits(['close', 'deleted', 'refresh'])
const animating = ref(false)

const activeSrc = computed(() => props.imageType === 'animated' && props.animatedSrc ? props.animatedSrc : props.src)
const fileExt = computed(() => { const m = activeSrc.value.match(/\.(\w+)(\?|$)/); return m ? m[1] : '' })

function formatBytes(bytes) {
  if (!bytes || bytes === 0) return ''
  return bytes < 1024 ? `${bytes} B` : bytes < 1048576 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1048576).toFixed(1)} MB`
}
const deleting = ref(false)
const message = ref('')
const motionHint = ref('')
const fetchedRoles = ref([])
// Provenance labels — separate from roles: not unique, and nothing strips
// siblings, so several images of one owner can carry AI at once.
const fetchedFlags = ref([])
// Credits + licence for this image — the citation half, independent of roles.
const fetchedCredits = ref([])
const fetchedLicense = ref('')
const fetchedCreditText = ref('')

//: Machine-set labels are shown, never editable: the pipelines own them.
const AUTO_FLAG_LABELS = { ai_generated: 'AI-generated', ai_animated: 'AI-animated' }

const autoFlags = computed(() => fetchedFlags.value.filter(f => f in AUTO_FLAG_LABELS))

function hasFlag(f) { return fetchedFlags.value.includes(f) }

async function toggleFlag(f) {
  const current = fetchedFlags.value
  const next = current.includes(f) ? current.filter(x => x !== f) : [...current, f]
  fetchedFlags.value = next
  try {
    await fetch(`/api/v1/imagen/${props.imageId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ flags: next }),
    })
    emit('refresh')
  } catch {}
}

function onCreditsSaved() {
  // Re-read so the panel reflects exactly what the server stored.
  fetchRoles()
  emit('refresh')
}

async function fetchRoles() {
  const entityId = props.entityId
  const imageId = props.imageId
  if (!entityId || !imageId) return
  try {
    const r = await fetch(`/api/v1/imagen/${entityId}`)
    if (r.ok) {
      const data = await r.json()
      if (imageId !== props.imageId) return   // the viewer moved on while in flight
      const img = (data.images || []).find(i => i.id === imageId)
      if (img) {
        fetchedRoles.value = img.roles || []
        fetchedFlags.value = img.flags || []
        fetchedCredits.value = img.credits || []
        fetchedLicense.value = img.license || ''
        fetchedCreditText.value = img.credit_text || ''
      }
    }
  } catch {}
}

// Body (projection) assignment — the tap-friendly alternative to drag-and-drop.
const imageProjection = ref('')
const entityProjections = ref([])

async function fetchEntityProjections() {
  if (!props.entityId) return
  try {
    const r = await fetch('/api/v1/graphql', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: `query($id: ID!) { entity(id: $id) { projections { id name universe originUniverse } } }`,
        variables: { id: props.entityId },
      }),
    })
    if (r.ok) {
      const data = await r.json()
      entityProjections.value = data.data?.entity?.projections || []
    }
  } catch {}
}

async function fetchImageProjection() {
  const entityId = props.entityId
  const imageId = props.imageId
  if (!entityId || !imageId) return
  try {
    const r = await fetch(`/api/v1/imagen/${entityId}`)
    if (r.ok) {
      const data = await r.json()
      if (imageId !== props.imageId) return   // the viewer moved on while in flight
      const img = (data.images || []).find(i => i.id === imageId)
      if (img) imageProjection.value = img.projection_id || ''
    }
  } catch {}
}

// Re-opening the viewer on another image replaces its props but reuses this
// component instance, so mount-only fetches left the previous image's tags
// (BG/Sheet/Nav) and body on screen — and a tag toggle would have written that
// stale list back. Follow the props instead, seeding the tags from the opener's
// `roles` so there is no stale window at all.
watch(() => [props.entityId, props.imageId], () => {
  fetchedRoles.value = [...(props.roles || [])]
  imageProjection.value = ''
  fetchEntityProjections()
  fetchRoles()
  fetchImageProjection()
}, { immediate: true })

function projectionLabel(p) {
  const uni = p.universe || p.originUniverse || ''
  const name = p.name || ''
  if (name && uni) return `${name} · ${uni}`
  return name || uni || p.id
}

async function onProjectionChange() {
  try {
    await fetch(`/api/v1/imagen/${props.imageId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ projection_id: imageProjection.value || null }),
    })
    emit('refresh')
  } catch {}
}

function hasRole(r) { return fetchedRoles.value.includes(r) }
async function toggleRole(r) {
  const current = fetchedRoles.value
  const next = current.includes(r) ? current.filter(x => x !== r) : [...current, r]
  fetchedRoles.value = next
  try {
    await fetch(`/api/v1/imagen/${props.imageId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ roles: next }),
    })
    emit('refresh')
  } catch {}
}

// Independent job polling — Panel system props are static on open
const localJob = ref(null)
const localBgJob = ref(null)
let _pollTimer = null

async function pollOwnJob() {
  if (!props.entityId) return
  try {
    const r = await fetch('/api/v1/imagen/jobs')
    if (r.ok) {
      const jobs = (await r.json()).jobs || {}
      const j = jobs[props.entityId]
      localJob.value = (j && j.type === 'animate') ? j : null
      localBgJob.value = (j && j.type === 'remove_bg') ? j : null
    }
  } catch {}
}

onMounted(() => { pollOwnJob(); _pollTimer = setInterval(pollOwnJob, 2000) })
onUnmounted(() => { clearInterval(_pollTimer) })

// When job completes, tell parent to refresh gallery
watch(localJob, (now, prev) => {
  if (prev && !now) emit('refresh')
})
watch(localBgJob, (now, prev) => {
  if (prev && !now) emit('refresh')
})

// Background removal
const bgBusy = ref(false)
const bgLabel = computed(() => localBgJob.value ? 'Removing background…' : '🧼 Remove BG')

async function onRemoveBgClick() {
  if (bgBusy.value || localBgJob.value) return
  bgBusy.value = true
  message.value = 'Removing background…'
  try {
    const r = await fetch(`/api/v1/remove-background/${props.entityId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image_id: props.imageId }),
    })
    const d = await r.json()
    message.value = d.accepted ? 'Background removal started — check gallery when complete' : (d.detail || 'Failed')
  } catch {
    message.value = 'Request failed'
  } finally {
    bgBusy.value = false
  }
}

const statusInfo = computed(() => {
  const j = localJob.value || props.animateJob
  if (!j) return { label: '🎬 Animate', status: '', cancelling: false }
  if (j.status === 'failed') return { label: '🎬 Animate', status: '!', cancelling: false }
  return { label: 'Cancel', status: '✕', cancelling: true }
})

function onAnimateClick() {
  if (statusInfo.value.cancelling) cancelAnimate()
  else startAnimate()
}

async function startAnimate() {
  if (!props.entityId || animating.value) return
  animating.value = true
  message.value = 'Starting animation...'
  try {
    const r = await fetch(`/api/v1/animate/${props.entityId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image_id: props.imageId, motion_hint: motionHint.value }),
    })
    const d = await r.json()
    message.value = d.accepted ? 'Animation started — check gallery when complete' : 'Failed'
  } catch {
    message.value = 'Request failed'
  } finally {
    animating.value = false
  }
}

async function cancelAnimate() {
  if (!props.entityId) return
  try {
    await fetch(`/api/v1/imagen/${props.entityId}/cancel`, { method: 'POST' })
    message.value = 'Cancelled'
  } catch {
    message.value = 'Cancel failed'
  }
}

async function onDelete() {
  if (!props.imageId || deleting.value) return
  deleting.value = true
  try {
    const r = await fetch(`/api/v1/imagen/${props.imageId}`, { method: 'DELETE' })
    if (r.ok) {
      emit('deleted')
      emit('close')
    } else {
      message.value = 'Delete failed'
    }
  } catch {
    message.value = 'Request failed'
  } finally {
    deleting.value = false
  }
}
</script>

<style scoped>
.image-viewer { text-align: center; }
.image-viewer img { max-width: 100%; max-height: 60vh; border-radius: 4px; }
.viewer-video, .viewer-media { max-width: 100%; max-height: 60vh; border-radius: 4px; }

.animate-section { margin-top: 8px; }
.motion-hint-row { display: flex; gap: 6px; align-items: center; }
.motion-hint-row input { flex: 1; font-size: 11px; padding: 4px 8px; border-radius: 4px; border: 1px solid var(--overlay-12); background: var(--overlay-6); color: var(--text); }
/* Split button: label + status segments sit flush, so the button itself keeps
   zero padding/gap and clips the status segment's corners. */
.motion-hint-row .animate-btn { padding: 0; gap: 0; overflow: hidden; white-space: nowrap; }
.motion-hint-row .animate-btn.cancelling { background: var(--danger-strong); color: var(--text-on-accent); }
.animate-btn .btn-label { padding: 4px 8px; }
.animate-btn .btn-status { padding: 4px 8px; background: rgba(0,0,0,0.25); font-weight: 600; }

.bg-remove-row { display: flex; justify-content: center; margin-top: 6px; }
.bg-remove-row .bg-btn { padding: 0; overflow: hidden; white-space: nowrap; }
.bg-btn .btn-label { padding: 4px 8px; }

.role-assign { display: flex; gap: 8px; justify-content: center; margin-top: 6px; }
.section-label { font-size: 10px; color: var(--text-dim); text-transform: uppercase; }
.role-check { font-size: 10px; color: var(--text-dim); cursor: pointer; display: flex; align-items: center; gap: 2px; }
.role-check input { margin: 0; cursor: pointer; }

/* Provenance labels — deliberately unlike the role row, since these do not
   assign the image anywhere. */
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
.meta-size { color: var(--accent); }
.meta-ext { color: var(--text-dim); text-transform: uppercase; }
.message { font-size: 11px; color: var(--accent); margin-top: 6px; }

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
