<template>
  <div>
    <div class="panel-top">
      <div class="panel-top-left">
        <span v-if="agencyHolder" class="agency-line" :title="agencyTitle">
          Agency: {{ agencyHolder.playerName }}<template v-if="!agencyHolder.main"> · support</template>
        </span>
      </div>
      <div class="panel-top-actions">
        <Button
          v-if="(form.type === 'CHARACTER' || form.type === 'GMC') && entityId !== currentEntityId"
          class="assume-btn"
          variant="secondary"
          size="sm"
          title="Act as this character"
          @click="assumeCharacter"
        >🎭 Assume</Button>
        <Button
          v-if="canImportToLocation"
          class="import-btn"
          variant="neutral"
          size="sm"
          :loading="importing"
          title="Move this entity to your current location"
          @click="importToLocation"
        >📥 Import to Location</Button>
      </div>
    </div>
    <GmEntityForm
      v-model="form"
      :entity-id="entityId"
    />
    <div v-if="form.type === 'LOCATION' || form.type === 'GMC'" class="canvas-open-row">
      <Button class="section-btn" variant="neutral" @click="openCanvas">🗺 Open in Canvas</Button>
      <Button v-if="form.type === 'LOCATION'" class="section-btn" variant="neutral" @click="emit('go-to-location')">📍 Go to this location</Button>
    </div>
    <div class="image-gallery">
      <div class="gallery-header">
        <h4>Images</h4>
        <div class="gallery-actions">
          <label class="upload-btn">
            📤 Upload
            <input type="file" accept="image/*" @change="onUpload" hidden />
          </label>
          <button class="imagen-btn" :class="{ cancelling: imagenStatus.cancelling }" @click="onImagenClick()">
            <span class="btn-label">{{ imagenStatus.label }}</span>
            <span v-if="imagenStatus.status" class="btn-status">{{ imagenStatus.status }}</span>
          </button>
        </div>
      </div>
      <div v-if="!entityImages.length" class="gallery-empty">No entity images yet — upload or generate one.</div>
      <div v-else class="gallery-grid entity-gallery-drop" :class="{ 'drag-over': dropTarget === '__entity__' }" @dragover.prevent="dragOver" @dragleave="onZoneDragLeave" @drop.prevent="drop">
        <div
          v-for="img in entityImages"
          :key="img.id"
          class="gallery-item"
          :data-img-path="img.path_animated || img.path_large"
          draggable="true"
          @contextmenu.prevent
          @dragstart="dragStart($event, img.id)"
          @dragend="dragEnd"
          @touchstart="touchStart($event, img.id)"
          @click="openImage(img)"
        >
          <MediaImage :src="img.image_type === 'animated' ? img.path_animated : img.path_large" class="gallery-thumb" :alt="img.image_type" lazy />
          <span class="gallery-label">
            {{ img.image_type }} — {{ formatSize(img.size_bytes) }}
            <span v-if="img.universe_label" class="universe-badge">{{ img.universe_label }}</span>
            <span v-for="r in img.roles" :key="r" class="role-badge">{{ r }}</span>
          </span>
        </div>
      </div>
    </div>
    <div v-if="isOccupant" class="projections-section">
      <div class="gallery-header">
        <h4>Projections</h4>
      </div>
      <div v-if="!projections.length" class="gallery-empty">No projections yet.</div>
      <div v-else class="projection-list">
        <!-- The projection is the container: its header row and its images live
             in the same box, and the whole box is the drop zone — so an image
             dropped on the header, on the images or between them all land on
             this projection. -->
        <div
          v-for="p in sortedProjections"
          :key="p.id"
          class="projection-block"
          :class="{ 'drag-over': dropTarget === p.id }"
          :data-projection-id="p.id"
          @dragover.prevent="dragOver"
          @dragleave="onZoneDragLeave"
          @drop.prevent="drop"
        >
          <div class="projection-row" @click="openProjectionEditor(p)">
            <MediaImage v-if="projectionThumb(p)" :src="projectionThumb(p).image_type === 'animated' ? projectionThumb(p).path_animated : projectionThumb(p).path_large" class="proj-thumb" :alt="p.originUniverse" />
            <span v-else class="proj-thumb proj-thumb-empty">🖼</span>
            <span class="proj-name">{{ p.name || form?.name }}</span>
            <span class="proj-universe">{{ universeName(p.originUniverse) }}<template v-if="p.universe !== p.originUniverse"> → {{ universeName(p.universe) }}</template></span>
            <span class="proj-type" :class="{ active: p.id === currentProjection }">{{ p.transversalType.toLowerCase() }}<template v-if="p.id === currentProjection"> · active</template></span>
            <Button class="proj-imagen" variant="ghost" size="sm" :class="{ cancelling: projectionGenBusy(p) }" :title="projectionGenBusy(p) ? 'Cancel generation' : 'Generate image for this body'" @click.stop="onImagenClick(p.id)">{{ projectionGenBusy(p) ? '✕' : '🖼' }}</Button>
            <Button class="proj-remove" variant="danger-ghost" size="sm" @click.stop="removeProjection(p.id)" title="Remove projection">✕</Button>
          </div>
          <div v-if="projectionImages(p).length" class="gallery-grid projection-gallery">
            <div
              v-for="img in projectionImages(p)"
              :key="img.id"
              class="gallery-item"
              :data-img-path="img.path_animated || img.path_large"
              draggable="true"
              @contextmenu.prevent
              @dragstart="dragStart($event, img.id)"
              @dragend="dragEnd"
              @touchstart="touchStart($event, img.id)"
              @click="openImage(img)"
            >
              <MediaImage :src="img.image_type === 'animated' ? img.path_animated : img.path_large" class="gallery-thumb" :alt="img.image_type" lazy />
              <span class="gallery-label">
                {{ img.image_type }} — {{ formatSize(img.size_bytes) }}
                <span v-for="r in img.roles" :key="r" class="role-badge">{{ r }}</span>
              </span>
            </div>
          </div>
        </div>
      </div>
      <div class="projection-universe">
        <select v-model="newProjUniverse" class="proj-universe-select" title="Universe for the new projection — filters the locations below" @change="onNewProjUniverseChange">
          <option v-for="u in universeOptions" :key="u.value" :value="u.value">{{ u.label }}</option>
        </select>
      </div>
      <div class="projection-add">
        <TargetPicker v-model="newProjLocationId" kind="location" :scope="newProjUniverse ? `universe:${newProjUniverse}` : ''" placeholder="Search location…" class="proj-picker" @select="onLocationSelect" />
        <select v-model="newProjType" class="proj-type-select">
          <option value="NATIVE">native</option>
          <option value="CONSCIOUSNESS">consciousness</option>
          <option value="INAPPOSITE">inapposite</option>
        </select>
        <Button class="section-btn proj-add-btn" variant="neutral" @click="addProjectionLocal">+ Add</Button>
      </div>
    </div>
    <div v-if="form.type === 'LOCATION'" class="transversal-links">
      <div class="gallery-header">
        <h4>Transversal Links</h4>
      </div>
      <div v-if="!transversalLinks.length" class="gallery-empty">No transversal links yet.</div>
      <div v-else class="transversal-list">
        <div v-for="link in transversalLinks" :key="link._key" class="transversal-row">
          <span class="transversal-name">{{ link.name }}</span>
          <Button class="transversal-effects" variant="neutral" size="sm" :active="(link.effects || []).length > 0" title="Edit portal effects" @click="openPortalConfig(link)">
            ⚙{{ (link.effects || []).length || '' }}
          </Button>
          <Button class="transversal-toggle" variant="neutral" size="sm" :class="link.transversal_type || 'inapposite'" @click="toggleLinkType(link)">
            {{ link.transversal_type || 'inapposite' }}
          </Button>
        </div>
      </div>
      <div class="transversal-add">
        <TargetPicker v-model="newTransversalLocationId" kind="location" placeholder="Add link to location…" class="proj-picker" @select="onTransversalLocationSelect" />
        <Button class="section-btn proj-add-btn" variant="neutral" @click="createTransversalLinkLocal">+ Add</Button>
      </div>
    </div>
    <div v-if="form.type === 'LOCATION' || form.type === 'UNIVERSE'" class="zones-section">
      <div class="gallery-header">
        <h4>Zones</h4>
      </div>
      <div v-if="!zones.length" class="gallery-empty">No sub-locations yet.</div>
      <div v-else class="zones-list">
        <div v-for="z in zones" :key="z.id" class="zone-row">
          <span class="zone-name">{{ z.name }}</span>
        </div>
      </div>
      <div class="zones-add">
        <input v-model="newZoneName" class="zone-input" placeholder="New sub-location name…" @keyup.enter="createZone" />
        <Button class="section-btn zone-add-btn" variant="neutral" :loading="creatingZone" :disabled="!newZoneName.trim() || creatingZone" @click="createZone">
          {{ creatingZone ? '…' : '+ Add' }}
        </Button>
      </div>
    </div>
    <div v-if="form.type === 'UNIVERSE'" class="section-buttons">
      <Button class="section-btn" variant="neutral" @click="openLoraConfig">🖼 LoRA Configuration</Button>
      <Button class="section-btn" variant="neutral" @click="openRollTables">🎲 Roll Tables</Button>
    </div>
    <div class="danger-zone">
      <h4>Danger Zone</h4>
      <div class="danger-actions">
        <Button
          class="publish-btn"
          :variant="form.unpublished ? 'neutral' : 'success'"
          size="sm"
          :title="form.unpublished ? 'Publish — make visible to players' : 'Unpublish — GM-only again'"
          @click="form.unpublished = !form.unpublished"
        >{{ form.unpublished ? '⬆ Publish' : '⬇ Unpublish' }}</Button>
        <DangerButton
          label="Delete"
          @confirm="onDeleteConfirmed"
        />
        <DangerButton
          v-if="form.type === 'LOCATION'"
          label="Prune"
          @confirm="onPruneConfirmed"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, inject } from 'vue'
import { useApi } from '@/composables/useApi.js'
import { useEntityCrud, createEntityCrud } from '@/composables/useEntityCrud.js'
import { useTraitsConfig } from '@/composables/useTraitsConfig.js'
import { useLifePaths } from '@/composables/useLifePaths.js'
import { useUniverseNames } from '@/composables/useUniverseNames.js'
import { usePanel } from '@/composables/usePanel.js'
import { usePanelBus } from '@/composables/usePanelBus.js'
import { useTransversalLinks } from '@/composables/useTransversalLinks.js'
import { useDragDrop } from '@/composables/useDragDrop.js'
import Button from '@/components/ui/Button.vue'
import GmEntityForm from '@/components/gm/GmEntityForm.vue'
import ImageViewer from '@/components/gm/ImageViewer.vue'
import GmLoRAConfigPanel from '@/components/gm/GmLoRAConfigPanel.vue'
import GmRollTablesPanel from '@/components/gm/GmRollTablesPanel.vue'
import GmProjectionEditPanel from '@/components/gm/GmProjectionEditPanel.vue'
import GmPortalConfigPanel from '@/components/gm/GmPortalConfigPanel.vue'
import TargetPicker from '@/components/ui/TargetPicker.vue'
import DangerButton from '@/components/ui/DangerButton.vue'
import MediaImage from '@/components/MediaImage.vue'

const panel = usePanel()
const bus = usePanelBus()
const { graphql } = useApi()

// ── Composables: shared state with GmPanel ──────────
// This panel's own editor state, keyed to props.entityId. The shared instance
// would let a second open entity panel overwrite this one's form — and this one
// would overwrite it back.
const editor = createEntityCrud()
const { form, selected, uploadBgImage, onImagen: doImagen, onCancel: doCancel, imagenJob, projections, currentProjection, addProjection, removeProjection, selectEntity } = editor
// Genuinely global: the GM panel's entity list, and the delete that clears the
// shared selection.
const { deleteEntity, fetchEntities } = useEntityCrud()
const { traitNameMap } = useTraitsConfig()
const { fetchLifePaths } = useLifePaths()
const { name: universeName, options: universeOptions, load: loadUniverseNames } = useUniverseNames()
loadUniverseNames()

// ── Who holds agency over this entity ────────────────
// Straight from the agency edge (Entity.agency), so it answers for a main whose
// player is offline as well as for a support character — no "who is playing
// right now" proxy.
const agencyHolder = computed(() => {
  const a = selected.value?.agency
  if (!a) return null
  return { playerName: a.playerName || a.playerId, main: !!a.main }
})

const agencyTitle = computed(() => {
  if (!agencyHolder.value) return ''
  return agencyHolder.value.main
    ? `Main character of ${agencyHolder.value.playerName}`
    : `Support character of ${agencyHolder.value.playerName}`
})

const isOccupant = computed(() => ['CHARACTER', 'GMC', 'ASSET'].includes(form.value?.type))

// ── Import to the GM's current location ─────────────
// Same heuristics as the tree drop (GmPanel.onMoveEntity): when a projection
// lives in the target location's universe it is assumed and moved there — the
// active projection is the most recently touched one, so it wins; without one,
// the current projection makes an inapposite jump. GmPanel provides the
// location live, since a panel's props freeze at open time.
// Provided by App, live (the stack is mounted there). The prop is the open-time
// fallback for a panel opened outside that tree.
const gmLocationId = inject('gmCurrentLocationId', null) || computed(() => props.currentLocationId || '')
const importing = ref(false)
const canImportToLocation = computed(() =>
  isOccupant.value && !!gmLocationId.value && form.value?.current_location !== gmLocationId.value
)

async function importToLocation() {
  const target = gmLocationId.value
  if (!props.entityId || !target || importing.value) return
  importing.value = true
  try {
    const q = await graphql(
      `query($id: ID!) { entity(id: $id) { projections { id universe originUniverse } } }`,
      { id: props.entityId }
    )
    const projs = q?.entity?.projections || []
    const loc = await graphql(`query($id: ID!) { entity(id: $id) { currentUniverse } }`, { id: target })
    const targetUniverse = loc?.entity?.currentUniverse || ''
    const inUniverse = projs.filter((p) => p.universe === targetUniverse || p.originUniverse === targetUniverse)
    const proj = inUniverse.find((p) => p.id === currentProjection.value) || inUniverse[0] || null
    if (proj) {
      await graphql(
        `mutation($entityId: ID!, $projectionId: ID!, $location: ID) { activateProjection(entityId: $entityId, projectionId: $projectionId, location: $location) { id } }`,
        { entityId: props.entityId, projectionId: proj.id, location: target }
      )
    } else {
      await graphql(
        `mutation($entityId: ID!, $location: ID!) { inappositeTravel(entityId: $entityId, location: $location) { id } }`,
        { entityId: props.entityId, location: target }
      )
    }
    await fetchEntities()
    await selectEntity({ id: props.entityId })
  } catch (e) {
    console.error('importToLocation:', e)
  } finally {
    importing.value = false
  }
}
const newProjLocationId = ref('')
const newProjLocation = ref(null)
const newProjType = ref('NATIVE')
// The new projection's universe: an explicit first choice, which also scopes the
// location picker (a location in another universe makes a body in that universe).
// Defaults to where the entity is now, so the common case is one click.
const newProjUniverse = ref('')
watch(() => form.value?.current_universe, (u) => {
  if (u && !newProjUniverse.value) newProjUniverse.value = u
}, { immediate: true })

function onLocationSelect(loc) {
  newProjLocation.value = loc
}

// A pick made under another universe must not survive the switch.
function onNewProjUniverseChange() {
  newProjLocationId.value = ''
  newProjLocation.value = null
}

async function addProjectionLocal() {
  const loc = newProjLocation.value
  if (!loc || !loc.universe) return
  await addProjection(loc.universe, newProjType.value, loc.id)
  newProjLocationId.value = ''
  newProjLocation.value = null
}

// ── Image → projection drag-and-drop (HTML5 + touch longpress) ──

// Static projection order, regardless of update time: the native body first,
// then the active one, then the rest by their origin universe's name. Without
// this the list followed whatever order the server (or the last patch) left
// behind, so an edited projection appeared to jump.
const sortedProjections = computed(() => {
  const rank = (p) => (p.transversalType === 'NATIVE' ? 0 : p.id === currentProjection.value ? 1 : 2)
  return [...(projections.value || [])].sort((a, b) => {
    const byRank = rank(a) - rank(b)
    if (byRank) return byRank
    const ua = (universeName(a.originUniverse) || a.originUniverse || '').toLowerCase()
    const ub = (universeName(b.originUniverse) || b.originUniverse || '').toLowerCase()
    return ua.localeCompare(ub) || String(a.id).localeCompare(String(b.id))
  })
})

// Entity-level vs projection-scoped images (ownership is ``projection_id``).
const entityImages = computed(() => images.value.filter(i => !i.projection_id))
function projectionImages(p) { return images.value.filter(i => i.projection_id === p.id) }
function projectionThumb(p) {
  const list = projectionImages(p)
  return list.find(i => (i.roles || []).includes('sheet'))
    || list.find(i => (i.roles || []).includes('background'))
    || list[0] || null
}

async function assignImage(imageId, projectionId) {
  if (!imageId) return
  try {
    await fetch(`/api/v1/imagen/${imageId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ projection_id: projectionId || null }),
    })
    await loadImages()
  } catch (e) {
    console.error('assignImage:', e)
  }
}

async function onUpload(e) {
  await uploadBgImage(e)
  await loadImages()
  e.target.value = ''
}

const { over, touchStart, dragStart, dragOver, dragLeave, drop, dragEnd } = useDragDrop({
  resolveTarget: (el) => {
    if (!el || !el.closest) return null
    if (el.closest('.entity-gallery-drop')) return { kind: 'entity' }
    // The whole projection container is the target, so a drop on its images (or
    // between them) counts the same as a drop on its header row.
    const block = el.closest('.projection-block')
    return block ? { kind: 'projection', id: block.dataset.projectionId || null } : null
  },
  onCommit: ({ from, to }) => {
    if (!from || !to) return
    if (to.kind === 'entity') assignImage(from, null)
    else if (to.kind === 'projection' && to.id) assignImage(from, to.id)
  },
  makeGhost: (el, t) => {
    const path = el && el.dataset ? el.dataset.imgPath : null
    if (!path) return null
    const ghost = document.createElement('img')
    ghost.src = path
    ghost.style.cssText = 'position:fixed;z-index:100;pointer-events:none;opacity:0.8;width:44px;height:44px;object-fit:cover;border-radius:4px'
    ghost.style.left = (t.clientX - 22) + 'px'
    ghost.style.top = (t.clientY - 22) + 'px'
    return ghost
  },
})

// Visual drop state, derived from the composable's `over` payload.
const dropTarget = computed(() => {
  if (!over.value) return null
  return over.value.kind === 'entity' ? '__entity__' : over.value.id
})

// Moving from a drop zone onto one of its own children (a card's images, say)
// fires dragleave on the parent — that is not leaving the zone, and clearing
// `over` there would blink the highlight off the target the user is over.
function onZoneDragLeave(e) {
  if (e.relatedTarget && e.currentTarget?.contains?.(e.relatedTarget)) return
  dragLeave()
}

const props = defineProps({
  entityId: { type: String, default: null },
  currentEntityId: { type: String, default: '' },
  currentLocationId: { type: String, default: '' },
})

const emit = defineEmits(['switch-to-sheet', 'image-open', 'go-to-location'])

// This panel owns its editor state (createEntityCrud): it loads its entity on
// mount and re-loads whenever it becomes the active tab again, so it follows
// edits made in its sub-panels and never shows whichever entity was selected
// last.
const panelActive = inject('panelActive', computed(() => true))
watch(panelActive, (active) => {
  if (active && props.entityId) selectEntity({ id: props.entityId })
}, { immediate: true })

// ── Sub-panel openers ───────────────────────────────
function openLoraConfig() {
  panel.open({
    component: GmLoRAConfigPanel,
    title: 'LoRA Configuration',
    props: {
      loraConfigJson: form.value.lora_config || '{}',
      promptSteering: form.value.prompt_steering || '',
    },
    listeners: {
      'update:loraConfig': (json) => { form.value = { ...form.value, lora_config: json } },
      'update:promptSteering': (text) => { form.value = { ...form.value, prompt_steering: text } },
    },
  })
}

function openRollTables() {
  const currentUniverse = form.value?.current_universe || props.entityId
  panel.open({
    component: GmRollTablesPanel,
    title: 'Roll Tables',
    props: { universe: currentUniverse },
  })
}

function openCanvas() {
  if (!props.entityId) return
  const type = form.value?.type
  if (type === 'LOCATION') {
    bus.emit('canvas:open-full', { mode: 'location', entityId: props.entityId, scope: 'focus' })
  } else if (type === 'GMC') {
    bus.emit('canvas:open-full', { mode: 'gmc-web', entityId: props.entityId })
  }
}

function assumeCharacter() {
  if (props.entityId) bus.emit('switch-perspective', props.entityId)
}

function openProjectionEditor(p) {
  panel.open({
    component: GmProjectionEditPanel,
    title: `Projection: ${p.originUniverse || p.universe}`,
    id: p.id,
    badge: 'PROJECTION',
    props: { projection: p },
    // The projection editor lives in a *child panel*, which cannot inject this
    // panel's provide — hand the editor instance across in the spec's context
    // (same mechanism the SFX editor uses for its effect panel).
    context: { entityEditor: editor },
  })
}

// Load life paths when editing a universe entity
watch(() => [props.entityId, form.value?.type], ([id, type]) => {
  if (id && type === 'UNIVERSE') fetchLifePaths(form.value.current_universe || props.entityId)
}, { immediate: true })

// ── Transversal links (location entities) ───────────
const transversalLinks = ref([])
const { toggleTransversalType, createTransversalLink } = useTransversalLinks()
const newTransversalLocationId = ref('')
const newTransversalLocation = ref(null)

async function loadTransversalLinks() {
  transversalLinks.value = []
  if (!props.entityId) return
  try {
    const r = await fetch(`/api/v1/locations/${props.entityId}/navigate`)
    if (r.ok) {
      const nav = await r.json()
      transversalLinks.value = nav.transversal || []
    }
  } catch {}
}

function onTransversalLocationSelect(loc) {
  newTransversalLocation.value = loc
}

async function createTransversalLinkLocal() {
  const loc = newTransversalLocation.value
  if (!loc || !loc.id) return
  await createTransversalLink(props.entityId, loc.id)
  newTransversalLocationId.value = ''
  newTransversalLocation.value = null
  await loadTransversalLinks()
}

async function toggleLinkType(link) {
  const next = await toggleTransversalType(props.entityId, link._key, link.transversal_type)
  link.transversal_type = next
}

function openPortalConfig(link) {
  const sourceName = form.value?.name || props.entityId
  panel.open({
    component: GmPortalConfigPanel,
    title: `Portal: ${sourceName} → ${link.name}`,
    props: { fromId: props.entityId, fromName: sourceName, link, universe: form.value?.current_universe || '' },
  })
}

watch(() => [props.entityId, form.value?.type], ([id, type]) => {
  if (id && type === 'LOCATION') loadTransversalLinks()
}, { immediate: true })

// ── Zones (sub-locations) ───────────────────────────
const zones = ref([])
const newZoneName = ref('')
const creatingZone = ref(false)

async function loadZones() {
  zones.value = []
  if (!props.entityId) return
  try {
    if (form.value.type === 'LOCATION') {
      const r = await fetch(`/api/v1/locations/${props.entityId}/navigate`)
      if (r.ok) {
        const nav = await r.json()
        zones.value = (nav.children || []).map(c => ({ id: c._key || c.id, name: c.name }))
      }
    } else if (form.value.type === 'UNIVERSE') {
      const r = await fetch('/api/v1/locations/tree')
      if (r.ok) {
        const tree = await r.json()
        const uni = tree.find(n => n.id === props.entityId)
        zones.value = (uni?.children || []).map(c => ({ id: c.id, name: c.name }))
      }
    }
  } catch {}
}

async function createZone() {
  const name = newZoneName.value.trim()
  if (!name || creatingZone.value) return
  creatingZone.value = true
  try {
    const data = await graphql(
      `mutation($input: CreateEntityInput!) { createEntity(input: $input) { id } }`,
      { input: { name, type: 'LOCATION', universe: form.value.current_universe, location: null, razmerit: 0 } },
    )
    const newId = data?.createEntity?.id
    if (!newId) return
    if (form.value.type === 'LOCATION') {
      await fetch(`/api/v1/locations/${newId}/edges/${props.entityId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: 'super' }),
      })
    }
    newZoneName.value = ''
    await loadZones()
    bus.emit('locations-changed')
  } catch (e) {
    console.error('[zones] create failed', e)
  } finally {
    creatingZone.value = false
  }
}

watch(() => [props.entityId, form.value?.type], ([id, type]) => {
  if (id && (type === 'LOCATION' || type === 'UNIVERSE')) loadZones()
}, { immediate: true })

// ── Imagen ──────────────────────────────────────────
const localImagenJob = ref(null)
let _jobPollTimer = null

async function pollOwnJob() {
  if (!props.entityId) return
  try {
    const r = await fetch('/api/v1/imagen/jobs')
    if (r.ok) {
      const jobs = (await r.json()).jobs || {}
      localImagenJob.value = jobs[props.entityId] || null
    }
  } catch {}
}

const imagenStatus = computed(() => {
  const j = localImagenJob.value || imagenJob.value
  if (!j) return { label: '🖼 Imagen', status: '', cancelling: false }
  if (j.status === 'failed') return { label: '🖼 Imagen', status: '!', cancelling: false }
  return { label: 'Cancel', status: '✕', cancelling: true }
})

const genTarget = ref(null)  // projection id (or '' for entity) of the active generation

function onImagenClick(projectionId = '') {
  if (imagenStatus.value.cancelling) {
    doCancel()
    genTarget.value = null
    return
  }
  genTarget.value = projectionId
  doImagen(projectionId)
}

function projectionGenBusy(p) {
  return genTarget.value === p.id && imagenStatus.value.cancelling
}

// Refresh gallery when a job completes
watch(localImagenJob, (now, prev) => {
  if (prev && !now) { loadImages(); genTarget.value = null }
})

// ── Delete / prune (two-click confirm handled by DangerButton) ──
async function onDeleteConfirmed() {
  await deleteEntity(props.entityId)
  bus.emit('locations-changed')
  panel.close()
}

async function onPruneConfirmed() {
  await deleteEntity(props.entityId, true)
  bus.emit('locations-changed')
  panel.close()
}

function formatSize(bytes) {
  if (!bytes || bytes === 0) return ''
  return bytes < 1024 ? `${bytes} B` : bytes < 1048576 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1048576).toFixed(1)} MB`
}

// ── Image gallery (panel-specific) ──────────────────
const openedImageId = ref(null)

function openImage(img) {
  if (openedImageId.value === img.id) {
    panel.closeChild(); openedImageId.value = null
    return
  }
  openedImageId.value = img.id
  panel.open({
    component: ImageViewer,
    title: img.id,
    badge: img.image_type === 'animated' ? 'ANIMATED' : 'IMAGE',
    props: { src: img.path_animated || img.path_large, animatedSrc: img.path_animated, alt: img.image_type + ' — ' + img.width + '×' + img.height, entityId: props.entityId, imageId: img.id, imageType: img.image_type, roles: img.roles || [], sizeBytes: img.size_bytes },
    listeners: {
      'close': () => { openedImageId.value = null },
      'refresh': () => { loadImages() },
      'deleted': () => { loadImages(); openedImageId.value = null },
    },
  })
}

const images = ref([])

async function loadImages() {
  if (!props.entityId) return
  try {
    const r = await fetch(`/api/v1/imagen/${props.entityId}`)
    if (r.ok) { const d = await r.json(); images.value = d.images || [] }
  } catch {}
}

watch(() => props.entityId, loadImages, { immediate: true })
onMounted(() => { pollOwnJob(); _jobPollTimer = setInterval(pollOwnJob, 2000) })
let offLifepathSaved = null
onMounted(() => {
  offLifepathSaved = bus.on('lifepath-saved', () => {
    if (form.value?.type === 'UNIVERSE') fetchLifePaths(form.value.current_universe || props.entityId)
  })
})
onUnmounted(() => { clearInterval(_jobPollTimer); if (offLifepathSaved) offLifepathSaved() })
defineExpose({ refresh: loadImages })
</script>

<style scoped>
.imagen-btn { background: var(--violet); color: var(--text-on-accent); font-size: 11px; padding: 0; border-radius: 4px; border: none; cursor: pointer; display: inline-flex; overflow: hidden; }
.imagen-btn.cancelling { background: var(--danger-strong); }
.imagen-btn .btn-label { padding: 4px 8px; }
.imagen-btn .btn-status { padding: 4px 8px; background: rgba(0,0,0,0.25); font-weight: 600; }

.panel-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.panel-top-left { display: flex; align-items: center; gap: 6px; min-width: 0; }
.panel-top-actions { display: flex; align-items: center; gap: 6px; }
.danger-zone {
  margin-top: 12px; padding: 10px;
  border: 1px solid var(--danger-20); border-radius: 6px;
  background: var(--danger-8);
}
.danger-zone h4 {
  font-size: 10px; color: var(--danger-soft); text-transform: uppercase; letter-spacing: 1px;
  margin: 0 0 8px 0;
}
.danger-actions { display: flex; gap: 6px; }
.danger-actions :deep(.danger-button) { flex: 1; width: auto; }

.image-gallery { margin-top: 12px; }
.gallery-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.gallery-header h4 { font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; margin: 0; }
.gallery-actions { display: flex; gap: 6px; align-items: center; }
.upload-btn {
  font-size: 11px; padding: 4px 8px; cursor: pointer; display: inline-flex; align-items: center;
  background: var(--accent-dim); color: var(--text); border-radius: 4px; border: none;
}
.gallery-empty { font-size: 10px; color: var(--text-dim); padding: 12px 0; text-align: center; }
.gallery-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(100px, 1fr)); gap: 6px; }
.gallery-item { display: block; border: 1px solid var(--overlay-8); border-radius: 4px; overflow: hidden; cursor: pointer; -webkit-touch-callout: none; -webkit-user-select: none; user-select: none; }
.gallery-item img { width: 100%; height: auto; display: block; -webkit-user-drag: none; }
.gallery-thumb, .gallery-thumb-video { width: 100%; height: auto; display: block; }
.gallery-label { display: block; font-size: 9px; color: var(--text-dim); text-align: center; padding: 2px 4px; background: rgba(0,0,0,0.3); }
.universe-badge { display: inline-block; font-size: 7px; background: var(--resource-32); color: var(--violet-pale); padding: 0 3px; border-radius: 2px; margin-left: 3px; }
.role-badge { display: inline-block; font-size: 7px; background: var(--warn-32); color: var(--gold); padding: 0 3px; border-radius: 2px; margin-left: 2px; text-transform: uppercase; }

.section-buttons {
  margin-top: 12px; display: flex; gap: 6px;
}
.canvas-open-row { margin-top: 12px; display: flex; gap: 6px; }
.section-btn { flex: 1; }
.section-count { font-size: 10px; color: var(--text-dim); margin-left: 4px; }

.agency-line {
  font-size: 11px; color: var(--text-dim); margin-left: 8px;
}
.agency-line::before { content: '·'; margin-right: 6px; }

.projections-section { margin-top: 12px; }
.projection-list { display: flex; flex-direction: column; gap: 8px; }
/* One card per projection: the header row is the card's top, its images sit
   inside the same border, and the accent highlight (drag-over) is the card's. */
.projection-block { border: 1px solid var(--overlay-8); border-radius: 6px; background: var(--overlay-2); overflow: hidden; }
.projection-row { display: flex; align-items: center; gap: 8px; padding: 6px 8px; border-bottom: 1px solid var(--overlay-8); }
.projection-row:last-child { border-bottom: none; }
.proj-name { flex: 1; font-size: 12px; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.proj-universe { font-size: 11px; color: var(--text-dim); }
.proj-type { font-size: 10px; text-transform: uppercase; color: var(--text-dim); padding: 1px 6px; border-radius: 3px; background: var(--overlay-4); }
.proj-type.active { color: var(--accent-pale); background: var(--accent-16); }
.proj-imagen.cancelling { color: var(--danger-strong); }
.projection-add { display: flex; gap: 6px; margin-top: 8px; }
.projection-universe { display: flex; margin-top: 8px; }
.proj-universe-select { flex: 1; min-width: 0; padding: 6px; border: 1px solid var(--overlay-8); border-radius: 4px; background: var(--bg-input); color: var(--text); font-size: 12px; }
.proj-input { flex: 1; padding: 6px 8px; border: 1px solid var(--overlay-8); border-radius: 4px; background: var(--bg-input); color: var(--text); font-size: 12px; }
.proj-type-select { padding: 6px; border: 1px solid var(--overlay-8); border-radius: 4px; background: var(--bg-input); color: var(--text); font-size: 12px; }
.section-btn.proj-add-btn { flex: 0 0 auto; padding: 6px 10px; }
.proj-picker { flex: 1; min-width: 0; }
.proj-thumb { width: 32px; height: 32px; object-fit: cover; border-radius: 4px; border: 1px solid var(--overlay-12); flex: 0 0 auto; }
.proj-thumb-empty { display: flex; align-items: center; justify-content: center; font-size: 14px; color: var(--text-dim); background: var(--overlay-4); }
.projection-block.drag-over { border-color: var(--accent); background: var(--accent-12); }
.projection-gallery { padding: 6px; }
.entity-gallery-drop.drag-over { outline: 2px dashed var(--accent); outline-offset: 2px; }
.transversal-links { margin-top: 12px; }
.transversal-list { display: flex; flex-direction: column; gap: 4px; }
.transversal-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 6px 8px; border: 1px solid var(--overlay-8); border-radius: 4px; background: var(--overlay-2); }
.transversal-name { font-size: 12px; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.transversal-list .inapposite { background: rgba(139,92,246,0.18); color: var(--violet-pale); }
.transversal-list .consciousness { background: var(--warn-20); color: var(--gold); }
.transversal-add { display: flex; gap: 6px; margin-top: 8px; }
.zones-section { margin-top: 12px; }
.zones-list { display: flex; flex-direction: column; gap: 4px; }
.zone-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 6px 8px; border: 1px solid var(--overlay-8); border-radius: 4px; background: var(--overlay-2); }
.zone-name { font-size: 12px; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.zones-add { display: flex; gap: 6px; margin-top: 8px; }
.zone-input { flex: 1; padding: 6px 8px; border: 1px solid var(--overlay-8); border-radius: 4px; background: var(--bg-input); color: var(--text); font-size: 12px; }
.section-btn.zone-add-btn { flex: 0 0 auto; padding: 6px 10px; }
</style>
