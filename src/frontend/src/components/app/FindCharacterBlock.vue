<template>
  <div class="settings-section">
    <label class="settings-label">Find character</label>
    <div class="search-wrapper find-char-wrapper">
      <input
        :value="search"
        placeholder="Search characters…"
        class="find-char-input"
        @input="$emit('update:search', $event.target.value)"
        @keyup.enter="$emit('enter')"
      />
      <div v-if="search.trim() && (searching || searched)" class="name-suggestions">
        <div v-if="searching" class="char-search-skeleton-list">
          <div v-for="n in 3" :key="n" class="suggestion-item char-search-result char-search-skeleton" aria-hidden="true">
            <span class="char-search-portrait char-skeleton-pulse"></span>
            <span class="char-search-result-meta">
              <span class="char-skeleton-line char-skeleton-pulse char-skeleton-line-name"></span>
              <span class="char-skeleton-line char-skeleton-pulse char-skeleton-line-location"></span>
            </span>
          </div>
        </div>
        <template v-else>
          <button
            v-for="e in results"
            :key="e.id"
            class="suggestion-item char-search-result"
            @mousedown.prevent
            @click="$emit('choose', e)"
          >
            <MediaImage v-if="e.sheetPortrait" :src="e.sheetPortrait" class="char-search-portrait" alt="" />
            <span v-else class="char-search-portrait char-search-portrait-fallback">{{ (e.name || e.id).charAt(0) }}</span>
            <span class="char-search-result-meta">
              <span class="char-search-result-name">{{ e.name || e.id }}</span>
              <span v-if="locationLabel(e)" class="char-search-result-location">{{ locationLabel(e) }}</span>
            </span>
          </button>
          <div v-if="!results.length && !error" class="suggestion-item char-search-empty">No characters found</div>
        </template>
      </div>
    </div>
    <p v-if="error" class="switch-error">{{ error }}</p>
  </div>
</template>

<script setup>
import MediaImage from '@/components/MediaImage.vue'

// "Find character": the debounced search over every character (the sheet owns
// the query and the results, this owns the input + dropdown + skeletons).
// `locationLabel` resolves an entity's location for the result subtitle.
defineProps({
  search: { type: String, default: '' },
  results: { type: Array, default: () => [] },
  searching: { type: Boolean, default: false },
  searched: { type: Boolean, default: false },
  error: { type: String, default: '' },
  locationLabel: { type: Function, default: () => '' },
})

defineEmits(['update:search', 'enter', 'choose'])
</script>
