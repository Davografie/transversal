<template>
  <div>
    <input v-model="search" class="filter-input" placeholder="Filter SFXs…" />

    <GmList
      :items="offered"
      item-key="id"
      selectable
      :selected-ids="selectedIds"
      empty-text="No SFXs match"
      @toggle="onToggle"
    >
      <template #item="{ item: s }">
        <span class="entity-name">{{ s.name }}</span>
        <span class="entity-universe">{{ s.trigger || '' }}</span>
      </template>
    </GmList>

    <!-- Shown, not offered: the rule declares a home elsewhere. -->
    <div v-if="blocked.length" class="blocked">
      <div class="blocked-title">Can't go here</div>
      <div v-for="s in blocked" :key="s.id" class="blocked-row">
        <span class="blocked-name">{{ s.name }}</span>
        <span class="blocked-why">{{ blockedReason(s) }}</span>
      </div>
    </div>

    <Button class="ps-add-btn" @click="onNewSfx" variant="secondary" block>+ New SFX</Button>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useTraitsConfig } from '@/composables/useTraitsConfig.js'
import { usePanel } from '@/composables/usePanel.js'
import GmList from '@/components/ui/GmList.vue'
import GmSfxEditPanel from '@/components/gm/GmSfxEditPanel.vue'
import Button from '@/components/ui/Button.vue'

const panel = usePanel()
const { allSfxs, fetchTraitsConfig, patchData } = useTraitsConfig()

const props = defineProps({
  selectedIds: { type: Array, default: () => [] },
  // Where this SFX is being attached. Rules whose declared source doesn't belong
  // on that surface are listed but not offered: the backend would refuse them,
  // and a silent refusal is worse than a visible "not this one".
  ownerType: { type: String, default: '' },
})

// Author-facing words for the surfaces (mirrors the backend's own labels).
const SURFACE_LABELS = {
  table: 'the Table (everyone)',
  gm: 'the GM bucket',
  entity: 'an entity',
  location: 'a location',
  projection: 'a projection',
  trait: 'a trait definition',
  trait_instance: 'a trait instance',
  trait_set: 'a trait set instance',
}

const emit = defineEmits(['add-sfx', 'remove-sfx'])

const offered = computed(() => filtered.value.filter(fits))
const blocked = computed(() => filtered.value.filter((s) => !fits(s)))

const search = ref('')

// Compatible when we don't know the target, the rule declares no surfaces (it can
// live anywhere), or it lists this one.
function fits(s) {
  if (!props.ownerType) return true
  const surfaces = s.ownerSurfaces || []
  return !surfaces.length || surfaces.includes(props.ownerType)
}

function blockedReason(s) {
  const surface = (s.ownerSurfaces || [])[0] || ''
  return `belongs on ${SURFACE_LABELS[surface] || surface}`
}

const filtered = computed(() => {
  const q = search.value.toLowerCase()
  if (!q) return allSfxs.value
  return allSfxs.value.filter(s =>
    s.name.toLowerCase().includes(q) ||
    (s.trigger || '').toLowerCase().includes(q) ||
    (s.description || '').toLowerCase().includes(q)
  )
})

function toggleSfx(id) {
  if (props.selectedIds.includes(id)) {
    emit('remove-sfx', id)
  } else {
    emit('add-sfx', id)
  }
}

function onToggle(s) { toggleSfx(s.id) }

function onNewSfx() {
  panel.open({
    component: GmSfxEditPanel,
    title: 'New SFX',
    badge: 'SFX',
    props: { sfx: null },
    listeners: {
      'sfx-created': (created) => {
        emit('add-sfx', created.id)
        panel.close()
      },
    },
  })
}
</script>

<style scoped>
.blocked {
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px dashed var(--border, #3a3a3a);
  opacity: 0.65;
}
.blocked-title {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 4px;
}
.blocked-row {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 11px;
  padding: 2px 0;
}
.blocked-why { font-style: italic; }

.filter-input { width: 100%; font-size: 12px; padding: 6px 8px; margin-bottom: 8px; box-sizing: border-box;
  background: var(--overlay-6); color: var(--text); border: 1px solid var(--overlay-10); border-radius: 6px; }


</style>
