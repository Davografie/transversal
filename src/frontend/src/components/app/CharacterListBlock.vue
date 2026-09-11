<template>
  <!-- Your characters: skeletons while loading, chips once known -->
  <div v-if="loading" class="settings-section">
    <label class="settings-label">Your characters</label>
    <div class="char-list">
      <div v-for="n in 3" :key="n" class="char-chip char-chip-skeleton" aria-hidden="true">
        <span class="char-portrait char-skeleton-pulse"></span>
        <span class="char-chip-meta">
          <span class="char-skeleton-line char-skeleton-pulse char-skeleton-line-name"></span>
          <span class="char-skeleton-line char-skeleton-pulse char-skeleton-line-location"></span>
        </span>
      </div>
    </div>
  </div>

  <div v-else-if="entities.length" class="settings-section">
    <label class="settings-label">Your characters</label>
    <div class="char-list">
      <button
        v-for="e in entities"
        :key="e.id"
        class="char-chip"
        :class="{ active: activeId === e.id }"
        @click="$emit('select', e)"
        @contextmenu.prevent="$emit('reveal', e.id)"
        @touchstart="$emit('touch-start', e.id)"
        @touchmove="$emit('touch-cancel')"
        @touchend="$emit('touch-end')"
        @touchcancel="$emit('touch-cancel')"
      >
        <MediaImage v-if="e.sheetPortrait" :src="e.sheetPortrait" class="char-portrait" alt="" />
        <span v-else class="char-portrait char-portrait-fallback">{{ (e.name || e.id).charAt(0) }}</span>
        <span class="char-chip-meta">
          <span class="char-chip-name">{{ e.name || e.id }} <span v-if="e.main" class="main-badge">MAIN</span></span>
          <span v-if="locationLabel(e)" class="char-chip-location">{{ locationLabel(e) }}</span>
        </span>
        <span class="main-toggle" :class="{ on: e.main }" :title="e.main ? 'Unset as main' : 'Set as main'" @click.stop="$emit('toggle-main', e)">★</span>
        <span class="char-release-btn" :class="{ revealed: revealedReleaseId === e.id }" title="Relinquish agency" @click.stop="$emit('release', e)">✕</span>
      </button>
    </div>
    <div class="char-create-row">
      <template v-if="showNewChar">
        <input
          :value="newCharName"
          placeholder="Name…"
          class="char-name-input"
          @input="$emit('update:newCharName', $event.target.value)"
          @keyup.enter="$emit('create')"
        />
        <button class="char-create-btn" :disabled="!newCharName.trim() || creating" @click="$emit('create')">✓</button>
      </template>
      <button v-else class="new-char-toggle" @click="$emit('update:showNewChar', true)">+ New character</button>
    </div>
    <p v-if="error" class="switch-error">{{ error }}</p>
  </div>

  <div v-else class="settings-section settings-empty">
    <p class="settings-empty-title">No characters yet</p>
    <p class="settings-empty-hint">Create a new character or find one below to claim agency.</p>
    <template v-if="showNewChar">
      <div class="switch-row">
        <input
          :value="newCharName"
          placeholder="Character name…"
          @input="$emit('update:newCharName', $event.target.value)"
          @keyup.enter="$emit('create')"
        />
        <button :disabled="!newCharName.trim() || creating" @click="$emit('create')">+</button>
      </div>
    </template>
    <button v-else class="new-char-toggle" @click="$emit('update:showNewChar', true)">+ New character</button>
    <p v-if="error" class="switch-error">{{ error }}</p>
  </div>
</template>

<script setup>
import MediaImage from '@/components/MediaImage.vue'

// The player's own characters in the settings overlay — skeletons, chips with
// portrait / MAIN badge / location, the set-as-main star and the long-press
// relinquish affordance, plus the create row (and its empty-state twin).
//
// The chip's click, reveal-on-long-press and release actions are the app's
// (see usePlayerCharacters), so they come back out as events; `locationLabel`
// resolves the location subtitle.
defineProps({
  entities: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  /** The entity currently being played (chip highlight). */
  activeId: { type: String, default: null },
  /** The chip whose ✕ has been revealed by long-press / right-click. */
  revealedReleaseId: { type: String, default: null },
  locationLabel: { type: Function, default: () => '' },
  showNewChar: { type: Boolean, default: false },
  newCharName: { type: String, default: '' },
  creating: { type: Boolean, default: false },
  error: { type: String, default: '' },
})

defineEmits([
  'select', 'reveal', 'release', 'toggle-main',
  'touch-start', 'touch-cancel', 'touch-end',
  'update:showNewChar', 'update:newCharName', 'create',
])
</script>
