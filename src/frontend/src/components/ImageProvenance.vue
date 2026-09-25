<template>
  <!--
    Provenance for one image, shown to whoever is looking at it: the AI labels
    and, when the author recorded them, the artwork's credits and its source.

    Read-only on purpose — this is the *disclosure* side of the data. Authoring
    happens in the GM surfaces (`ImageCreditsEditor`).
  -->
  <div v-if="hasAnything" class="img-prov" :class="{ 'is-compact': compact }">
    <div v-if="aiLabels.length" class="img-prov-ai">
      <span
        v-for="label in aiLabels"
        :key="label"
        class="img-prov-badge"
        :title="AI_TITLES[label] || ''"
      >{{ label }}</span>
    </div>

    <p v-if="creditText" class="img-prov-text">{{ creditText }}</p>

    <ul v-else-if="credits.length" class="img-prov-credits">
      <li v-for="(credit, i) in credits" :key="i">
        <span class="img-prov-role">{{ ROLE_LABELS[credit.role] || credit.role }}</span>
        <a
          v-if="credit.url"
          :href="credit.url"
          target="_blank"
          rel="noopener noreferrer"
        >{{ credit.name || credit.url }}</a>
        <span v-else>{{ credit.name }}</span>
      </li>
    </ul>

    <p v-if="license" class="img-prov-license">
      <span class="img-prov-role">Licence</span>
      <a
        v-if="isLink(license)"
        :href="license"
        target="_blank"
        rel="noopener noreferrer"
      >{{ license }}</a>
      <span v-else>{{ license }}</span>
    </p>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  flags: { type: Array, default: () => [] },
  credits: { type: Array, default: () => [] },
  license: { type: String, default: '' },
  creditText: { type: String, default: '' },
  compact: { type: Boolean, default: false },
})

//: Only the labels an image actually carries are shown, so an ordinary upload
//: displays nothing at all rather than a row of empty badges.
const FLAG_LABELS = {
  ai: '[AI]',
  ai_generated: '[AI-generated]',
  ai_animated: '[AI-animated]',
}

const AI_TITLES = {
  '[AI]': 'AI was somewhere in this image’s workflow',
  '[AI-generated]': 'Made by the image generator',
  '[AI-animated]': 'Motion made by the animation generator',
}

const ROLE_LABELS = {
  artist: 'Art by',
  source: 'Source',
  rights: 'Rights',
  publisher: 'Published by',
}

const aiLabels = computed(() =>
  ['ai', 'ai_generated', 'ai_animated']
    .filter(f => (props.flags || []).includes(f))
    .map(f => FLAG_LABELS[f])
)

const hasAnything = computed(() =>
  aiLabels.value.length > 0 || !!props.creditText || !!props.license || props.credits.length > 0
)

function isLink(value) {
  return /^https?:\/\//i.test(value || '')
}
</script>

<style scoped>
.img-prov {
  display: flex; flex-direction: column; gap: 4px;
  font-size: 11px; color: var(--text-dim); text-align: center;
}
.img-prov.is-compact { font-size: 10px; text-align: left; align-items: flex-start; }
.img-prov-ai { display: flex; gap: 4px; justify-content: center; flex-wrap: wrap; }
.img-prov.is-compact .img-prov-ai { justify-content: flex-start; }
.img-prov-badge {
  font-size: 9px; padding: 1px 5px; border-radius: 3px;
  border: 1px solid var(--accent, #6c8cff); color: var(--text);
}
.img-prov-text { margin: 0; font-style: italic; }
.img-prov-credits { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 2px; }
.img-prov-credits li { display: flex; gap: 4px; justify-content: center; }
.img-prov.is-compact .img-prov-credits li { justify-content: flex-start; }
.img-prov-role { opacity: 0.75; }
.img-prov-license { margin: 0; display: flex; gap: 4px; justify-content: center; }
.img-prov.is-compact .img-prov-license { justify-content: flex-start; }
.img-prov a { color: inherit; text-decoration: underline; }
.img-prov a:hover { color: var(--text); }
</style>
