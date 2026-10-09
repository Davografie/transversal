<template>
  <div class="play-overview">
    <div class="gm-shortcuts">
      <Button class="shortcut-btn beat-btn" variant="neutral" @click="$emit('next-beat')">◆ Next Beat</Button>
      <Button class="shortcut-btn scene-btn" variant="neutral" @click="$emit('advance-scene')">◈ Scene</Button>
      <Button v-if="!inSession" class="shortcut-btn session-btn" variant="neutral" title="Start the session" @click="$emit('start-session')">▶ Start</Button>
      <Button v-else class="shortcut-btn session-btn" variant="danger" title="End the session" @click="$emit('end-session')">■ End</Button>
    </div>

    <!-- The rules that live on the GM, when the host has them to offer. A slot
         rather than a prop because only one of the two hosts (the sheet) can
         resolve a card's state and activation; the panel's Play tab is not a
         place a rule is pressed, and an empty slot is how it says so. -->
    <slot name="rules" />

    <GmTroupeOverview
      :current-location-id="currentLocationId"
      :current-location-name="currentLocationName"
      @go-to-location="$emit('go-to-location', $event)"
    />
    <GmSceneSummary
      :entities="sceneEntitiesHere"
      :parents="sceneParentGroups"
      :zones="sceneZoneGroups"
      @inspect="$emit('inspect', $event)"
    />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import Button from '@/components/ui/Button.vue'
import GmSceneSummary from '@/components/gm/GmSceneSummary.vue'
import GmTroupeOverview from '@/components/gm/GmTroupeOverview.vue'
import { useSceneOverview } from '@/composables/useSceneOverview.js'

// The Play surface, in one place, because it has two hosts: the GM panel's Play
// tab (the workspace it was built in) and the roaming GM's character sheet (where
// the author moved it — the panels keep Prep, the sheet carries play). The four
// shortcuts are thin wrappers that emit up, so each host routes them to the same
// app action it always did.
const props = defineProps({
  currentLocationId: { type: String, default: '' },
  currentLocationName: { type: String, default: '' },
  // The whole entity roster, as the host already holds it. The composable owns
  // the scene shape; the host owns the fetch, so the two cannot disagree about
  // *what* is in the scene — only about where the list came from.
  entities: { type: Array, default: () => [] },
  locationTree: { type: Array, default: () => [] },
  inSession: { type: Boolean, default: false },
})

defineEmits(['next-beat', 'advance-scene', 'start-session', 'end-session', 'go-to-location', 'inspect'])

const { sceneEntitiesHere, sceneParentGroups, sceneZoneGroups } = useSceneOverview({
  entities: computed(() => props.entities),
  locationTree: computed(() => props.locationTree),
  currentLocationId: computed(() => props.currentLocationId),
})
</script>

<style scoped>
.play-overview { display: flex; flex-direction: column; }

.gm-shortcuts { display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: 8px; }
.gm-shortcuts .shortcut-btn { flex: 1; padding: 8px 6px; font-size: 11px; white-space: nowrap; }
/* Per-action border hues (the primitive owns fill/hover/radius). */
.gm-shortcuts .beat-btn { border-color: var(--accent-32); }
.gm-shortcuts .beat-btn:hover { border-color: var(--accent); }
.gm-shortcuts .scene-btn { border-color: var(--success-32); }
.gm-shortcuts .scene-btn:hover { border-color: var(--success); }
.gm-shortcuts .session-btn { border-color: var(--warn-32); }
.gm-shortcuts .session-btn:hover { border-color: var(--warn); }
</style>
