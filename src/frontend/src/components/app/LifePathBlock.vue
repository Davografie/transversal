<template>
  <!-- A life path a rule has shown to this player ([[B303]]).

       This is the *settings-overlay* home for `client/life_path`, used when the
       player created the character here — the overlay is where the creation
       happened, so it is where the path is put in front of them. A character that
       appeared some other way is shown the path in its own sheet instead
       (`useLifePathIntro` decides which, because only the client knows). -->
  <div class="settings-section lifepath-intro">
    <label class="settings-label">Life path{{ name ? ` — ${name}` : '' }}</label>
    <p class="lifepath-lede">
      A path is open to this character. Take a look, and take a term when you are
      ready — nothing starts until you choose it.
    </p>
    <!-- Bounded height: the wizard embeds as a flex column that scrolls its own
         body, so it needs a parent that will not grow without limit inside the
         overlay's scroll area. -->
    <div class="lifepath-host">
      <LifePathWizard
        :visible="true"
        embedded
        :entity-id="characterId"
        :universe="universe"
        :initial-path-id="lifePathId"
        @close="$emit('dismiss')"
        @updated="$emit('updated')"
      />
    </div>
    <button type="button" class="lifepath-dismiss" @click="$emit('dismiss')">
      Dismiss
    </button>
  </div>
</template>

<script setup>
import LifePathWizard from '@/components/LifePathWizard.vue'

defineProps({
  /** Whose life path this is. The wizard is entity-addressed, nothing more. */
  characterId: { type: String, required: true },
  /** The path the rule named. */
  lifePathId: { type: String, required: true },
  /** Shown in the heading, so the panel says whose new character this is. */
  name: { type: String, default: '' },
  universe: { type: String, default: 'earth' },
})

defineEmits(['dismiss', 'updated'])
</script>

<style scoped>
.lifepath-lede {
  margin: 0 0 10px;
  font-size: 12px;
  line-height: 1.45;
  color: var(--text-dim);
}
.lifepath-host {
  display: flex;
  flex-direction: column;
  max-height: min(52vh, 460px);
  min-height: 0;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--overlay-2);
  overflow: hidden;
}
.lifepath-dismiss {
  margin-top: 8px;
  background: none;
  border: 0;
  padding: 0;
  cursor: pointer;
  font: inherit;
  font-size: 12px;
  color: var(--text-dim);
  text-decoration: underline;
  align-self: flex-start;
}
</style>
