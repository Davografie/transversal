<template>
  <!-- Support characters you have agency over; disabled while their main is away -->
  <div v-if="supportCharacters.length" class="settings-section">
    <label class="settings-label">Support characters</label>
    <div class="char-list support-list">
      <button
        v-for="sc in supportCharacters"
        :key="sc.entity.id"
        class="char-chip support-chip"
        :class="{ 'support-unavailable': !sc.mainActive, 'support-current': sc.entity.id === activeId }"
        :disabled="!sc.mainActive"
        @click="$emit('assume', sc)"
      >
        <MediaImage v-if="sc.entity.sheetPortrait" :src="sc.entity.sheetPortrait" class="char-portrait" alt="" />
        <span v-else class="char-portrait char-portrait-fallback">{{ (sc.entity.name || sc.entity.id).charAt(0) }}</span>
        <span class="char-chip-meta">
          <span class="char-chip-name">{{ sc.entity.name || sc.entity.id }}</span>
          <span class="char-chip-location support-main">supports {{ sc.main?.name || '—' }}</span>
        </span>
        <span v-if="sc.mainActive" class="support-available-dot" title="Available">●</span>
      </button>
    </div>
    <p v-if="!supportCharacters.some(sc => sc.mainActive)" class="support-hint">No support characters are available right now — their mains are inactive.</p>
  </div>

  <!-- Create-from-scratch support for another player's active main (players only) -->
  <div v-if="!gmMode" class="settings-section">
    <label class="settings-label">Create support character</label>
    <template v-if="otherMains.length">
      <div class="other-mains-list">
        <div v-for="a in otherMains" :key="a.playerId" class="other-main-row">
          <MediaImage v-if="a.main?.sheetPortrait" :src="a.main.sheetPortrait" class="char-portrait" alt="" />
          <span v-else class="char-portrait char-portrait-fallback">{{ (a.main?.name || a.playerId).charAt(0) }}</span>
          <span class="char-chip-meta">
            <span class="char-chip-name">{{ a.main?.name || a.playerId }}</span>
            <span class="char-chip-location">{{ a.playerName || a.playerId }}</span>
          </span>
          <button class="support-create-btn support-create-inline" :title="'Create a support character for ' + (a.main?.name || a.playerId)" @click="$emit('create-support', a.main.id)">＋ support</button>
        </div>
      </div>
    </template>
    <p v-else class="support-hint">No other mains are active right now to support.</p>
  </div>
</template>

<script setup>
import MediaImage from '@/components/MediaImage.vue'

// The support-character half of the settings overlay: the SCs you can assume
// (unavailable while their main is away) and the create-from-scratch list of
// other players' active mains. Assuming and creating are the app's actions.
defineProps({
  /** [{ entity, main, mainActive }] — the SCs this player has agency over. */
  supportCharacters: { type: Array, default: () => [] },
  /** [{ playerId, playerName, main }] — other players' active mains. */
  otherMains: { type: Array, default: () => [] },
  activeId: { type: String, default: null },
  gmMode: { type: Boolean, default: false },
})

defineEmits(['assume', 'create-support'])
</script>
