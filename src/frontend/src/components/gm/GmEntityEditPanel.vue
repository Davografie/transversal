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
    <div v-if="form.type === 'LOCATION' || form.type === 'GMC' || form.type === 'FACTION'" class="canvas-open-row">
      <Button class="section-btn" variant="neutral" @click="openCanvas">🗺 Open in Canvas</Button>
      <Button
        v-if="form.type === 'LOCATION'"
        class="section-btn"
        variant="neutral"
        :loading="goingToLocation"
        @click="goToThisLocation"
      >📍 Go to this location</Button>
      <span v-if="goError" class="go-error">{{ goError }}</span>
    </div>
    <div v-if="hasSheet" class="section-buttons">
      <Button class="section-btn" variant="neutral" @click="openSheet">{{ sheetLabel }}</Button>
    </div>
    <div class="image-gallery">
      <div class="gallery-header">
        <h4>Images</h4>
        <div class="gallery-actions">
          <ImageUpload
            owner-kind="entity"
            :owner-id="props.entityId"
            @uploaded="loadImages"
          />
          <button class="imagen-btn" :class="{ cancelling: imagenStatus.cancelling }" @click="onImagenClick()">
            <span class="btn-label">{{ imagenStatus.label }}</span>
            <span v-if="imagenStatus.status" class="btn-status">{{ imagenStatus.status }}</span>
          </button>
          <label
            v-if="supportsSurroundings"
            class="ancestors-toggle"
            :class="{ saving: savingAncestors }"
            :title="surroundingsTitle"
          >
            <input
              type="checkbox"
              :checked="promptIncludeAncestors"
              :disabled="savingAncestors"
              @change="onToggleAncestors"
            />
            Surroundings
          </label>
        </div>
      </div>
      <ImageGallery
        :images="entityImages"
        :selected-id="openedImageId"
        zone-class="entity-gallery-drop"
        :drop-active="dropTarget === '__entity__'"
        empty="No entity images yet — upload or generate one."
        @open="openImage"
        @dragstart="dragStart"
        @dragend="dragEnd"
        @touchstart="touchStart"
        @dragover.prevent="dragOver"
        @dragleave="onZoneDragLeave"
        @drop.prevent="drop"
      />
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
            <MediaImage v-if="projectionThumb(p)" :src="projectionThumb(p).path_animated || projectionThumb(p).path_large" class="proj-thumb" :alt="p.originUniverse" />
            <span v-else class="proj-thumb proj-thumb-empty">🖼</span>
            <span class="proj-name">{{ p.name || form?.name }}</span>
            <span class="proj-universe">{{ universeName(p.originUniverse) }}<template v-if="p.universe !== p.originUniverse"> → {{ universeName(p.universe) }}</template></span>
            <span class="proj-type" :class="{ active: p.id === currentProjection }">{{ p.transversalType.toLowerCase() }}<template v-if="p.id === currentProjection"> · active</template></span>
            <Button class="proj-imagen" variant="ghost" size="sm" :class="{ cancelling: projectionGenBusy(p) }" :title="projectionGenBusy(p) ? 'Cancel generation' : 'Generate image for this body'" @click.stop="onImagenClick(p.id)">{{ projectionGenBusy(p) ? '✕' : '🖼' }}</Button>
            <Button class="proj-remove" variant="danger-ghost" size="sm" @click.stop="removeProjection(p.id)" title="Remove projection">✕</Button>
          </div>
          <ImageGallery
            v-if="projectionImages(p).length"
            class="projection-gallery"
            :images="projectionImages(p)"
            :selected-id="openedImageId"
            empty=""
            @open="openImage"
            @dragstart="dragStart"
            @dragend="dragEnd"
            @touchstart="touchStart"
          />
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
          <!-- Remove the link (the route drops its reverse edge too). Two-step
               like the danger button, sized for a row; one row arms at a time. -->
          <Button
            class="tie-remove"
            :variant="armedTie === link._key ? 'danger' : 'danger-ghost'"
            :active="armedTie === link._key"
            size="sm"
            :loading="tieBusy === link._key"
            :title="armedTie === link._key ? `Confirm: remove the transversal link to ${link.name}` : `Remove the transversal link to ${link.name}`"
            @click.stop="removeTransversalLink(link)"
          >{{ armedTie === link._key ? '✓?' : '✕' }}</Button>
        </div>
      </div>
      <div v-if="transversalNote" class="members-note">{{ transversalNote }}</div>
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
    <!-- What happens when someone walks in ([[B8]]). A place's arrival rules are
         spent the moment they fire — they are never *held* by an occupant — so no
         other surface lists them, and from the place itself there was no answer to
         "what does walking in here do?". Rule names come from the shared SFX list,
         so the whole section costs one read. -->
    <div v-if="form.type === 'LOCATION' && arrivalRules.length" class="arrival-section">
      <div class="gallery-header">
        <h4>Fires on arrival</h4>
      </div>
      <div v-for="group in arrivalRules" :key="group.locationId" class="arrival-group">
        <!-- A rule may come from a parent place; say which, rather than implying
             this room owns it. The place itself needs no label. -->
        <div v-if="group.locationId !== entityId" class="arrival-from">
          from {{ group.locationName }}
        </div>
        <button
          v-for="sid in group.sfxIds"
          :key="sid"
          type="button"
          class="arrival-rule"
          :title="sid"
          @click="openArrivalRule(sid)"
        >{{ sfxName(sid) }}</button>
      </div>
    </div>
    <div v-if="form.type === 'FACTION'" class="members-section">
      <div class="gallery-header">
        <h4>Members</h4>
      </div>
      <div v-if="!members.length" class="gallery-empty">No members yet.</div>
      <div v-else class="members-list">
        <div v-for="m in members" :key="m.id" class="member-row" :class="{ self: m.id === actingEntityId }" @click="openMemberPanel(m)">
          <span class="entity-type-badge" :class="'type-' + m.type">{{ m.type }}</span>
          <span class="member-name">{{ m.name }}</span>
          <!-- The role is the tie's own statement, so it is edited where it is
               read; an unset role needs a region of its own to click. -->
          <FactionRoleCell
            :role="m.role || ''"
            :busy="roleBusy === m.id"
            :title="`Edit ${m.name}'s role in this faction`"
            @save="(next) => saveMemberRole(m, next)"
          />
          <span v-if="m.rank" class="member-rank">{{ m.rank }}</span>
          <!-- Two-step like the danger button, sized for a row (DangerButton is
               full-width by design). One row arms at a time. -->
          <Button
            class="tie-remove"
            :variant="armedTie === m.id ? 'danger' : 'danger-ghost'"
            :active="armedTie === m.id"
            size="sm"
            :loading="tieBusy === m.id"
            :title="armedTie === m.id ? `Confirm: remove ${m.name} from this faction` : `Kick ${m.name} from this faction`"
            @click.stop="kickMember(m)"
          >{{ armedTie === m.id ? '✓?' : '✕' }}</Button>
        </div>
      </div>
      <!-- The tie is member → faction, and the member is whoever the GM is
           acting as: one gesture to claim a slot, one to give it up. -->
      <div v-if="canHoldMembership" class="members-action">
        <Button v-if="actingMembership" variant="neutral" :loading="memberBusy" :title="`Remove the membership tie ${acting.name} → ${form.name}`" @click="leaveFaction">
          Leave as {{ acting.name }}
        </Button>
        <Button v-else variant="secondary" :loading="memberBusy" :title="`Create the membership tie ${acting.name} → ${form.name}`" @click="joinFaction">
          Join as {{ acting.name }}
        </Button>
      </div>
      <div v-if="memberNote" class="members-note">{{ memberNote }}</div>
    </div>
    <div v-if="isOccupant" class="factions-section">
      <div class="gallery-header">
        <h4>Factions</h4>
      </div>
      <div v-if="!entityFactions.length" class="gallery-empty">Not in a faction yet.</div>
      <div v-else class="factions-list">
        <div v-for="f in entityFactions" :key="f.id" class="faction-row" @click="openFactionPanel(f)">
          <span class="entity-type-badge type-FACTION">FAC</span>
          <span class="faction-name">{{ f.name }}</span>
          <FactionRoleCell
            :role="f.role || ''"
            :busy="factionRoleBusy === f.id"
            :title="`Edit ${form.name}'s role in ${f.name}`"
            @save="(next) => saveEntityRole(f, next)"
          />
          <span v-if="f.rank" class="member-rank">{{ f.rank }}</span>
          <Button
            class="tie-remove"
            :variant="armedTie === f.id ? 'danger' : 'danger-ghost'"
            :active="armedTie === f.id"
            size="sm"
            :loading="tieBusy === f.id"
            :title="armedTie === f.id ? `Confirm: leave ${f.name}` : `Leave ${f.name}`"
            @click.stop="leaveEntityFaction(f)"
          >{{ armedTie === f.id ? '✓?' : '✕' }}</Button>
        </div>
      </div>
      <div v-if="factionNote" class="members-note">{{ factionNote }}</div>
    </div>
    <div v-if="form.type === 'UNIVERSE'" class="section-buttons">
      <Button class="section-btn" variant="neutral" @click="openLoraConfig">🖼 LoRA Configuration</Button>
      <Button class="section-btn" variant="neutral" @click="openPalettePanel">🎨 Universe Style</Button>
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
import { ref, computed, watch, nextTick, onMounted, onUnmounted, inject } from 'vue'
import { useApi } from '@/composables/useApi.js'
import { useEntityCrud, createEntityCrud } from '@/composables/useEntityCrud.js'
import { useTraitsConfig } from '@/composables/useTraitsConfig.js'
import CharacterSheet from '@/components/CharacterSheet.vue'
// A member's panel is another instance of this component, opened as this panel's
// child (referenced at click time, so the module cycle resolves).
import GmEntityEditPanel from '@/components/gm/GmEntityEditPanel.vue'
import { useFactionRoles } from '@/composables/useFactionRoles.js'
import FactionRoleCell from '@/components/gm/FactionRoleCell.vue'
import { useLifePaths } from '@/composables/useLifePaths.js'
import { useUniverseNames } from '@/composables/useUniverseNames.js'
import { usePanel } from '@/composables/usePanel.js'
import { usePanelBus } from '@/composables/usePanelBus.js'
import { useTransversalLinks } from '@/composables/useTransversalLinks.js'
import { useDragDrop } from '@/composables/useDragDrop.js'
import { useImageGallery } from '@/composables/useImageGallery.js'
import ImageGallery from '@/components/image/ImageGallery.vue'
import ImageUpload from '@/components/image/ImageUpload.vue'
import Button from '@/components/ui/Button.vue'
import GmEntityForm from '@/components/gm/GmEntityForm.vue'
import ImageViewer from '@/components/gm/ImageViewer.vue'
import GmLoRAConfigPanel from '@/components/gm/GmLoRAConfigPanel.vue'
import GmPalettePanel from '@/components/gm/GmPalettePanel.vue'
import GmRollTablesPanel from '@/components/gm/GmRollTablesPanel.vue'
import GmSfxEditPanel from '@/components/gm/GmSfxEditPanel.vue'
import GmProjectionEditPanel from '@/components/gm/GmProjectionEditPanel.vue'
import GmPortalConfigPanel from '@/components/gm/GmPortalConfigPanel.vue'
import TargetPicker from '@/components/ui/TargetPicker.vue'
import DangerButton from '@/components/ui/DangerButton.vue'
import MediaImage from '@/components/MediaImage.vue'

const panel = usePanel()
const bus = usePanelBus()
const { graphql, error: apiError } = useApi()

// ── Composables: shared state with GmPanel ──────────
// This panel's own editor state, keyed to props.entityId. The shared instance
// would let a second open entity panel overwrite this one's form — and this one
// would overwrite it back.
const editor = createEntityCrud()
const { form, selected, onImagen: doImagen, onCancel: doCancel, imagenJob, projections, currentProjection, addProjection, removeProjection, selectEntity } = editor
// Genuinely global: the GM panel's entity list, and the delete that clears the
// shared selection.
const { deleteEntity, fetchEntities } = useEntityCrud()
const { traitNameMap, traitsets, allSfxs, fetchTraitsConfig } = useTraitsConfig()
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
    if (to.kind === 'entity') assignTo(from, null)
    else if (to.kind === 'projection' && to.id) assignTo(from, to.id)
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

const emit = defineEmits(['image-open', 'go-to-location'])

// The owner's pictures and every action that changes them — one implementation,
// shared with the trait editor and the viewer ([[B211]]).
const { images, job, load: loadImages, assignTo } = useImageGallery(
  () => ({ kind: 'entity', id: props.entityId })
)

// This panel owns its editor state (createEntityCrud): it loads its entity on
// mount and re-loads whenever it becomes the active tab again, so it follows
// edits made in its sub-panels and never shows whichever entity was selected
// last.
const panelActive = inject('panelActive', computed(() => true))
watch(panelActive, (active) => {
  if (active && props.entityId) selectEntity({ id: props.entityId })
  // A roster can move while this panel sits behind another one (a join from a
  // sibling faction panel, say), so re-read it on the way back to the front.
  if (active && form.value?.type === 'FACTION') loadMembers()
  if (active && isOccupant.value) loadEntityFactions()
}, { immediate: true })

// ── Sub-panel openers ───────────────────────────────
/** The universe's look ([[UI-UX Design#The universe palette]]). It hangs off the
 *  universe entity because that is where the palette lives — the same doorway the
 *  LoRA config and the roll tables use. */
function openPalettePanel() {
  panel.open({
    component: GmPalettePanel,
    title: 'Universe Style',
    badge: 'STYLE',
    // A universe entity's `current_universe` *is* the key the palette is looked
    // up by (the entity ids are separate synthetic keys).
    props: { universe: form.value?.current_universe || '' },
  })
}

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
  } else if (type === 'FACTION') {
    bus.emit('canvas:open-full', { mode: 'faction', entityId: props.entityId })
  }
}

// The sheet needs the shell's inputs — the perspective and the pool/settings/effect
// handlers — to be fully functional, and only a panel can open one (`usePanel` is
// per-Panel context). App provides the spec; this panel opens it in its own stack,
// so a sheet opened here behaves exactly like the main-view one.
const characterSheetSpec = inject('characterSheetSpec', null)

// The sheet shell renders per type (its own profile decides the tabs): occupants,
// factions (roster) and locations (incoming ties). Universe and the pseudo-types
// are left out — they would fall back to the occupant profile, and nothing asked
// for them.
const SHEET_TYPES = ['CHARACTER', 'GMC', 'ASSET', 'FACTION', 'LOCATION']
const hasSheet = computed(() => SHEET_TYPES.includes(form.value?.type))
const SHEET_LABELS = { FACTION: '📄 Faction Sheet', LOCATION: '📄 Location Sheet' }
const sheetLabel = computed(() => SHEET_LABELS[form.value?.type] || '📄 Character Sheet')

function openSheet() {
  const spec = characterSheetSpec?.(props.entityId)
  if (!spec) return
  panel.open({
    component: CharacterSheet,
    title: spec.title,
    id: props.entityId,
    badge: 'SHEET',
    props: spec.props,
    listeners: spec.listeners,
  })
}

// Going somewhere is a request that can fail, so it is awaited rather than fired
// at the bus: the button spins until App reports arrival (or why it could not).
// The emit stays as the fallback for a panel opened outside App's tree, where
// there is nobody to await — it just cannot report progress.
const goToLocation = inject('goToLocation', null)
const goingToLocation = ref(false)
const goError = ref('')

async function goToThisLocation() {
  const locId = props.entityId
  if (!locId || goingToLocation.value) return
  if (!goToLocation) { emit('go-to-location'); return }
  goingToLocation.value = true
  goError.value = ''
  try {
    const res = await goToLocation(locId)
    if (res && !res.ok) goError.value = res.error || 'Could not go to that location.'
  } finally {
    goingToLocation.value = false
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
const { toggleTransversalType, createTransversalLink, deleteTransversalLink } = useTransversalLinks()
const newTransversalLocationId = ref('')
const newTransversalLocation = ref(null)
const transversalNote = ref('')

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

async function removeTransversalLink(link) {
  // Two-step, like the other row removals: first click arms, second confirms
  // inside the same 3s window.
  if (!armOrConfirm(link._key)) return
  tieBusy.value = link._key
  transversalNote.value = ''
  try {
    // `link._key` is the destination location's id — a `transversal` entry in the
    // navigate payload is the target document, which is also why the type toggle
    // passes it as the `toId`.
    await deleteTransversalLink(props.entityId, link._key)
    await loadTransversalLinks()
  } catch (e) {
    transversalNote.value = e?.message || 'Could not remove that link.'
  } finally {
    tieBusy.value = ''
  }
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
  if (id && type === 'LOCATION') loadArrivalRules()
}, { immediate: true })

// ── Rules that fire on arrival (B8) ─────────────────
// The rules a place *spends* on whoever walks in. They are never held, so the
// sheet's place-rules strip leaves them out and nothing else showed them either;
// a GM looking at the place is the one reader who wants exactly these.
const arrivalRules = ref([])

async function loadArrivalRules() {
  arrivalRules.value = []
  if (!props.entityId) return
  try {
    const data = await graphql(
      `query($id: ID!) { arrivalSfxRules(locationId: $id) { locationId locationName sfxIds } }`,
      { id: props.entityId })
    arrivalRules.value = data?.arrivalSfxRules || []
    // Names live in the shared SFX list; load it only when there is something to
    // name, so a place with no arrival rules costs nothing.
    if (arrivalRules.value.length && !allSfxs.value.length) fetchTraitsConfig()
  } catch { arrivalRules.value = [] }
}

// Names come from the shared SFX list the panel already holds — one read for the
// section, and a rule the list has not caught up with falls back to its id rather
// than rendering blank.
function sfxName(id) {
  return allSfxs.value.find((s) => s.id === id)?.name || id
}

function openArrivalRule(sfxId) {
  const sfx = allSfxs.value.find((s) => s.id === sfxId) || null
  panel.open({
    component: GmSfxEditPanel,
    title: sfx?.name || 'Edit SFX',
    id: sfxId,
    badge: 'SFX',
    props: {
      sfx,
      // The place is the owner, so the editor shows where the rule lives.
      owner: { ownerType: 'LOCATION', ownerId: props.entityId, label: form.value?.name || '' },
    },
    listeners: {},
  })
}

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

// ── Members (faction entities) ──────────────────────
// The roster read and the membership tie are both backend-platform's; the panel
// owns the gesture. A roster entry is a `membership` (or roster-trait `relation`)
// tie pointing member → faction, and the member here is whoever the GM is acting
// as.
const members = ref([])
const acting = ref(null)            // the acting entity: { id, name, type }
const memberBusy = ref(false)
const memberNote = ref('')
// Who may hold a membership — the same set the backend validates against.
const HOLDER_TYPES = ['CHARACTER', 'GMC', 'ASSET']
const canHoldMembership = computed(() => !!acting.value && HOLDER_TYPES.includes(acting.value.type))
// Live from App (see the provide there): a panel's spec props are frozen when it
// opens, so the acting entity has to arrive as provided state for the gesture to
// follow a perspective switch without reopening the panel. As with
// `gmCurrentLocationId`, the inject wins outright — an empty one means free-roam,
// and must not resurrect the id the panel happened to open with.
const actingEntityId = inject('actingEntityId', null) || computed(() => props.currentEntityId || '')
const actingMembership = computed(() => members.value.find(m => m.id === actingEntityId.value) || null)

// ── Roles (the tie's own statement) ─────────────────
// The role lives on the membership tie and is written through the shared
// `useFactionRoles`, which both this panel and the entity panel's faction list
// use. Here it is the member's role in *this* faction.
const roleBusy = ref('')
const { setRole, removeMembership, factionsFor } = useFactionRoles()

// Patch the one row instead of re-reading the roster: a role edit must not blank
// the list under the GM's cursor, and the rows have to stay put to be edited one
// after another. The setting's id comes back with the write, so the row's next
// edit skips the tie lookup as well.
async function saveMemberRole(m, next) {
  roleBusy.value = m.id
  try {
    const res = await setRole({ memberId: m.id, factionId: props.entityId, statement: next, settingId: m.settingId || '' })
    if (!res.ok) { memberNote.value = res.error; return }
    memberNote.value = ''
    const row = members.value.find(x => x.id === m.id)
    if (row) {
      row.role = next || null
      row.settingId = res.settingId
    }
  } finally {
    // Only if no further edit has claimed the busy flag in the meantime — rows
    // are edited back to back and a write may still be in flight.
    if (roleBusy.value === m.id) roleBusy.value = ''
  }
}

// The member's own panel opens as a **child of this one**, so the two sit side by
// side in the chain and the faction stays in view (the canvas:inspect route the
// member rows used before made it a sibling of the faction panel, which put the
// roster off screen). It gets the entity panel's two listeners, built for this
// member rather than for whatever the GM panel has selected — a child panel must
// not move the GM panel's selection.
function openMemberPanel(m) {
  if (!m?.id) return
  panel.open({
    component: GmEntityEditPanel,
    title: m.name || 'Edit Entity',
    id: m.id,
    badge: String(m.type || '').toUpperCase(),
    props: {
      entityId: m.id,
      currentEntityId: actingEntityId.value,
      currentLocationId: gmLocationId.value || props.currentLocationId,
    },
    listeners: {
      'image-open': (img) => openMemberImage(m, img),
      'go-to-location': () => bus.emit('switch-view-location', m.id),
    },
  })
}

// The entity panel's image gallery hands the image up; the viewer is a panel of
// its own (the same spec the GM panel builds, for this member).
function openMemberImage(m, img) {
  panel.open({
    component: ImageViewer,
    title: img.id,
    badge: (img.renders || []).includes('animated') ? 'ANIMATED' : 'IMAGE',
    props: { ownerKind: 'entity', ownerId: m.id, imageId: img.id, image: img },
    listeners: {},
  })
}

async function loadMembers() {
  members.value = []
  acting.value = null
  memberNote.value = ''
  if (!props.entityId) return
  const wanted = actingEntityId.value
  const [roster, me] = await Promise.all([
    graphql(`query($id: ID!) { factionMembers(factionId: $id) { id name type role rank } }`, { id: props.entityId }),
    wanted ? graphql(`query($id: ID!) { entity(id: $id) { id name type } }`, { id: wanted }) : null,
  ])
  // A response that is missing rather than empty is a failed read; say so once
  // rather than rendering an empty roster as if the faction had no members.
  if (!roster) { memberNote.value = apiError.value || 'Could not load the roster.'; return }
  members.value = roster.factionMembers || []
  acting.value = me?.entity || null
}

// ── Leaving / being removed ─────────────────────────
// Both directions drop the same tie (member → faction), so both go through
// `removeMembership`, and both confirm the same way the danger button does — arm
// on the first click, commit on the second within the same 3s window — but sized
// for a row, since `DangerButton` is full-width by design. One row arms at a time.
const tieBusy = ref('')
const armedTie = ref('')
const RELATION_TIE_NOTE = 'That roster slot is a relation tie, not a membership — edit or remove it from the relationship editor.'
let armedTimer = null

function clearArmed() {
  if (armedTimer) { clearTimeout(armedTimer); armedTimer = null }
  armedTie.value = ''
}

// true when this click is the confirmation
function armOrConfirm(id) {
  if (armedTie.value === id) { clearArmed(); return true }
  clearArmed()
  armedTie.value = id
  armedTimer = setTimeout(() => { armedTie.value = '' }, 3000)
  return false
}

// The row goes without a re-read: the write already says what happened, and a
// relation-tie slot stays put with the note explaining why.
async function dropTie(memberId, factionId, removeId, list, note) {
  tieBusy.value = memberId
  try {
    const res = await removeMembership({ memberId, factionId })
    if (!res.ok) { note.value = res.error; return }
    if (res.nothingRemoved) { note.value = RELATION_TIE_NOTE; return }
    note.value = ''
    list.value = list.value.filter(x => x.id !== removeId)
  } finally {
    tieBusy.value = ''
  }
}

async function kickMember(m) {
  if (!armOrConfirm(m.id)) return
  await dropTie(m.id, props.entityId, m.id, members, memberNote)
}

async function leaveEntityFaction(f) {
  if (!armOrConfirm(f.id)) return
  await dropTie(props.entityId, f.id, f.id, entityFactions, factionNote)
}

async function joinFaction() {
  if (!canHoldMembership.value || memberBusy.value) return
  memberBusy.value = true
  try {
    const res = await graphql(
      `mutation($input: CreateRelationshipInput!) { createRelationship(input: $input) { id } }`,
      { input: { fromEntityId: actingEntityId.value, toEntityId: props.entityId, type: 'membership' } },
    )
    // Read the reason before the reload below: every call clears the api error
    // ref on the way in, so a stale message cannot survive it.
    const failure = res ? '' : (apiError.value || 'Could not add the membership.')
    await loadMembers()
    if (failure) memberNote.value = failure
  } finally {
    memberBusy.value = false
  }
}

async function leaveFaction() {
  if (memberBusy.value) return
  memberBusy.value = true
  try {
    const res = await removeMembership({ memberId: actingEntityId.value, factionId: props.entityId })
    if (!res.ok) { memberNote.value = res.error; return }
    if (res.nothingRemoved) { memberNote.value = RELATION_TIE_NOTE; return }
    memberNote.value = ''
    members.value = members.value.filter(m => m.id !== actingEntityId.value)
  } finally {
    memberBusy.value = false
  }
}

watch(() => [props.entityId, form.value?.type, actingEntityId.value], ([id, type]) => {
  if (id && type === 'FACTION') loadMembers()
}, { immediate: true })

// ── The entity's own factions ───────────────────────
// The inverse of the Members section: which factions this entity is on the roster
// of, with the role it holds there. `factionsFor` owns the read (and the reason it
// costs one confirmation per tied faction — see that composable).
const entityFactions = ref([])
const factionNote = ref('')
const factionRoleBusy = ref('')

async function loadEntityFactions() {
  entityFactions.value = []
  factionNote.value = ''
  if (!props.entityId) return
  const { factions, error } = await factionsFor(props.entityId)
  entityFactions.value = factions
  if (error) factionNote.value = error
}

async function saveEntityRole(f, next) {
  factionRoleBusy.value = f.id
  try {
    const res = await setRole({ memberId: props.entityId, factionId: f.id, statement: next, settingId: f.settingId || '' })
    if (!res.ok) { factionNote.value = res.error; return }
    factionNote.value = ''
    // Same as the roster rows: the write already tells us the result, so the list
    // must not be re-read under the GM.
    const row = entityFactions.value.find(x => x.id === f.id)
    if (row) {
      row.role = next || null
      row.settingId = res.settingId
    }
  } finally {
    if (factionRoleBusy.value === f.id) factionRoleBusy.value = ''
  }
}

// The same channel the canvas uses to open an entity panel — the GM panel owns
// that spec, and a faction's panel is where its roster (the Members section) is.
function openFactionPanel(f) {
  if (f?.id) bus.emit('canvas:inspect', f.id)
}

watch(() => [props.entityId, form.value?.type], ([id, type]) => {
  if (id && isOccupant.value) loadEntityFactions()
}, { immediate: true })

// ── Imagen ──────────────────────────────────────────
// The job registry is polled by `useImageGallery`, keyed by this owner, so the
// button and the gallery read the same fact ([[B211]]).
const imagenStatus = computed(() => {
  const j = job.value || imagenJob.value
  if (!j) return { label: '🖼 Imagen', status: '', cancelling: false }
  if (j.status === 'failed') return { label: '🖼 Imagen', status: '!', cancelling: false }
  return { label: 'Cancel', status: '✕', cancelling: true }
})

const genTarget = ref(null)  // projection id (or '' for entity) of the active generation

// ── Surroundings: describe where this thing is? ──────────────────────
// For a LOCATION the sub-locations ("zones") always go into the prompt; the
// ancestor chain is the optional part — surroundings make an exterior read
// right and are usually noise for an interior. For a GMC or asset the whole
// chain is optional: it describes the place they are in and its surroundings,
// which v1 also gave npc/asset prompts. Characters are deliberately excluded —
// a PC is generated wherever the player wants, not where the soul sits.
// Stored as `Entity.prompt_include_ancestors`; it survives a form save because
// that mutation only sends the fields it names.
const SURROUNDINGS_TYPES = ['LOCATION', 'GMC', 'ASSET']
const supportsSurroundings = computed(() => SURROUNDINGS_TYPES.includes(form.value?.type))
const surroundingsTitle = computed(() =>
  form.value?.type === 'LOCATION'
    ? "Also describe this location's ancestors in the image prompt — the surrounding geography. Good for exteriors; usually noise for interiors. Sub-locations are always described."
    : "Also describe where this is — the place they are in, and its surroundings."
)
const promptIncludeAncestors = ref(false)
const savingAncestors = ref(false)

async function fetchPromptIncludeAncestors() {
  if (!props.entityId || !supportsSurroundings.value) {
    promptIncludeAncestors.value = false
    return
  }
  const result = await graphql(
    `query($id: ID!) { entity(id: $id) { id promptIncludeAncestors } }`,
    { id: props.entityId }
  )
  if (result?.entity) {
    promptIncludeAncestors.value = !!result.entity.promptIncludeAncestors
  }
}

async function onToggleAncestors(event) {
  const next = event.target.checked
  const previous = promptIncludeAncestors.value
  promptIncludeAncestors.value = next   // optimistic; the checkbox is controlled by this ref
  savingAncestors.value = true
  const result = await graphql(
    `mutation($input: UpdateEntityInput!) {
      updateEntity(input: $input) { id promptIncludeAncestors }
    }`,
    { input: { id: props.entityId, promptIncludeAncestors: next } }
  )
  if (result?.updateEntity) {
    promptIncludeAncestors.value = !!result.updateEntity.promptIncludeAncestors
  } else {
    promptIncludeAncestors.value = previous   // revert; `apiError` carries the reason
  }
  savingAncestors.value = false
}

watch(() => [props.entityId, form.value?.type], fetchPromptIncludeAncestors, { immediate: true })

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

// Refresh the gallery when a job completes
watch(job, (now, prev) => {
  if (prev && !now) genTarget.value = null
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
    badge: (img.renders || []).includes('animated') ? 'ANIMATED' : 'IMAGE',
    // The viewer is owner-aware and reads the record itself, so the opener hands
    // over an owner and an id rather than a cartful of copied fields ([[B211]]).
    props: { ownerKind: 'entity', ownerId: props.entityId, imageId: img.id, image: img },
    listeners: {
      'close': () => { openedImageId.value = null },
      'refresh': () => { loadImages() },
      'deleted': () => { loadImages(); openedImageId.value = null },
    },
  })
}

let offLifepathSaved = null
onMounted(() => {
  offLifepathSaved = bus.on('lifepath-saved', () => {
    if (form.value?.type === 'UNIVERSE') fetchLifePaths(form.value.current_universe || props.entityId)
  })
})
onUnmounted(() => { if (offLifepathSaved) offLifepathSaved() })
defineExpose({ refresh: loadImages })
</script>

<style scoped>
.imagen-btn { background: var(--violet); color: var(--text-on-accent); font-size: 11px; padding: 0; border-radius: 4px; border: none; cursor: pointer; display: inline-flex; overflow: hidden; }
.imagen-btn.cancelling { background: var(--danger-strong); }
.imagen-btn .btn-label { padding: 4px 8px; }
.imagen-btn .btn-status { padding: 4px 8px; background: rgba(0,0,0,0.25); font-weight: 600; }
.ancestors-toggle { display: inline-flex; align-items: center; gap: 4px; font-size: 11px; color: var(--text-dim); cursor: pointer; user-select: none; white-space: nowrap; }
.ancestors-toggle input { margin: 0; cursor: pointer; accent-color: var(--violet); }
.ancestors-toggle.saving { opacity: 0.6; }

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
.gallery-empty { font-size: 10px; color: var(--text-dim); padding: 12px 0; text-align: center; }

.section-buttons {
  margin-top: 12px; display: flex; gap: 6px;
}
.canvas-open-row { margin-top: 12px; display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.go-error { font-size: 10px; color: var(--danger-soft); }

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
.arrival-section { margin-top: 12px; }
.arrival-group { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; margin-bottom: 4px; }
/* A rule inherited from a parent place, said rather than implied. */
.arrival-from { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; }
.arrival-rule { font-size: 11px; padding: 3px 8px; border: 1px solid var(--overlay-10); border-radius: 4px; background: var(--overlay-2); color: var(--text); cursor: pointer; text-align: left; }
.arrival-rule:hover { background: var(--overlay-4); border-color: var(--accent); }
.members-section { margin-top: 12px; }
.members-list { display: flex; flex-direction: column; gap: 4px; }
.member-row { display: flex; align-items: center; gap: 8px; padding: 6px 8px; border: 1px solid var(--overlay-8); border-radius: 4px; background: var(--overlay-2); cursor: pointer; }
.member-row:hover { background: var(--overlay-4); }
.member-row.self { border-color: var(--accent); }
.member-name { flex: 1; font-size: 12px; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.factions-section { margin-top: 12px; }
.factions-list { display: flex; flex-direction: column; gap: 4px; }
.faction-row { display: flex; align-items: center; gap: 8px; padding: 6px 8px; border: 1px solid var(--overlay-8); border-radius: 4px; background: var(--overlay-2); cursor: pointer; }
.faction-row:hover { background: var(--overlay-4); }
.faction-name { flex: 1; font-size: 12px; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.member-rank { font-size: 10px; text-transform: uppercase; color: var(--text-dim); padding: 1px 6px; border-radius: 3px; background: var(--overlay-4); }
.members-action { display: flex; gap: 6px; margin-top: 8px; }
/* Compact stand-in for DangerButton in a row: same two-step confirm. */
.tie-remove { flex: 0 0 auto; padding: 1px 6px; font-size: 11px; }
.members-action .btn { flex: 1; }
.members-note { font-size: 10px; color: var(--text-dim); margin-top: 6px; }
</style>
