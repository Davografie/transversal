<template>
  <!-- The **activation splash** ([[B229]]): the one place a player looks when the
       engine did something they did not ask for. Three faces, one surface, because
       the author's rule is that the splash *is* where engine-initiated prompts
       appear — so a question, a "here is what changed", and a "here is what you
       are up against" must not be three different corners of the screen.

         * **prompt** — a choice the engine raised (an automatic rule, a routed
           question, a branch from [[B5]]). It **stays until it is interacted
           with**: answered, or left by its own Cancel.
         * **note** — what an activation did, and why an effect did nothing
           ([[B236]]'s note per effect). It **fades**, and a queue of them is not
           a stack of dialogs: one at a time, each brief.
         * **target** — a number the player is about to act on (a difficulty set
           for where they are). It **waits for the tap**, because the tap is the
           point: the splash is the notice and the way through to the sheet, and a
           report that faded before it was read would lose both. It carries
           `action`, which is also what tells the two apart.

       The shell owns *when*: it decides the dwell (a small change is shorter than
       a course summary), holds a target until it is tapped, and feeds notes in
       order. The splash owns *how*. -->
  <div
    class="sp-root"
    :class="{ 'sp-has-prompt': hasPrompt }"
    role="region"
    :aria-label="hasPrompt ? 'A rule is asking for a choice' : 'What changed'"
  >
    <div v-if="hasPrompt" class="sp-prompt">
      <EffectTargetWizard
        :entity-id="promptEntityId"
        :pending-choices="choices"
        :title="promptTitle"
        @resolve="(r) => emit('answer', r)"
        @cancel="emit('leave')"
        @run-loop="(c) => emit('loop', c)"
      />
    </div>

    <!-- One note at a time, the head of the queue. `role="status"` so a change
         nobody asked for is announced rather than only seen. A **target** is a
         button instead: it is meant to be pressed, so it is not a live region. -->
    <TransitionGroup v-if="!hasPrompt && currentNote" name="sp-note" tag="div" class="sp-notes">
      <component
        :is="currentNote.action ? 'button' : 'div'"
        :key="currentNote.id"
        class="sp-note"
        :class="{ 'sp-note-action': !!currentNote.action }"
        :type="currentNote.action ? 'button' : undefined"
        :role="currentNote.action ? undefined : 'status'"
        @click="currentNote.action && emit('act', currentNote)"
      >
        <div class="sp-note-head">
          <span class="sp-note-title">{{ currentNote.title }}</span>
          <span class="sp-note-kind">{{ kindLabel }}</span>
        </div>
        <ul v-if="currentNote.lines?.length" class="sp-note-lines">
          <li v-for="(line, i) in currentNote.lines" :key="i" :class="{ 'is-silent': line.silent }">{{ line.text || line }}</li>
        </ul>
        <span v-if="currentNote.action" class="sp-note-cue">{{ currentNote.action }}</span>
      </component>
    </TransitionGroup>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import EffectTargetWizard from '@/components/gm/EffectTargetWizard.vue'

// The shape rules, which are different on purpose:
//
//   * **A prompt is non-modal, has no scrim, and never dismisses itself.** The
//     change that raised the question is the context for answering it, a parked
//     question must not block play, and the only ways out are answering it or the
//     wizard's own Cancel (which writes nothing — the branch is parked server-side
//     and recoverable). No timer exists here at all.
//   * **A note always fades**, because it is a report, not a decision. It is never
//     interactive, never covered by a scrim, and never blocks anything.
//   * **A target waits for its tap** and is the one interactive note. It is still
//     non-modal and scrim-less — it names one action (`action`), not a decision —
//     and it is dismissible *by* doing that action, which is why it needs no
//     Cancel of its own.
//
// The dwell of a note belongs to the shell; the splash only says which face it is.
// Neither moves: the splash is fixed to the same corner so a player learns where
// to look, and on touch the bands already own the drag gestures.
// Captured, not just declared — the script reads `props.…` and the template's
// computeds are built from it, so a bare `defineProps({…})` throws on the first
// render (`props is not defined`). The sibling of the `emit` trap below.
const props = defineProps({
  /** The pending choice, if any — the prompt face. */
  choices: { type: Array, default: () => [] },
  // The entity the *question* belongs to, which is not always the acting one: a
  // routed question ([[B229]] item 4) is aimed at a chosen entity.
  entityId: { type: String, default: '' },
  promptTitle: { type: String, default: 'A rule needs a choice' },
  /** The note at the head of the queue — the note face, or the target face when
   *  it names an `action`. `{ id, title, kind, lines, action? }`. */
  note: { type: Object, default: null },
})
// Captured, not just declared: the template calls `emit(...)`, and a bare
// `defineEmits([...])` leaves it undefined there — every click then throws
// instead of reaching the shell, which reads as "the question will not close".
const emit = defineEmits(['answer', 'leave', 'loop', 'act'])

const hasPrompt = computed(() => !!props.choices?.length)
const promptEntityId = computed(() => props.choices?.[0]?.entity_id || props.entityId)
const currentNote = computed(() => (hasPrompt.value ? null : props.note))

const KIND_LABELS = { summary: 'resolved', target: 'your target', change: 'changed' }
const kindLabel = computed(() => KIND_LABELS[currentNote.value?.kind] || KIND_LABELS.change)

</script>

<style scoped>
/* Bottom-right on a desktop: the sheet docks left, the roller sits bottom-centre
   and the ✨ rail owns the left edge, so this is the one free corner. Above the GM
   panel viewport (25) so a splash is never buried under a panel, below the
   login/settings overlay (100). */
.sp-root {
  position: fixed;
  right: 16px;
  bottom: 16px;
  z-index: 30;
  width: min(340px, calc(100vw - 24px));
  max-height: min(70dvh, 560px);
  overflow-y: auto;
  padding: 10px;
  /* The one surface. Opaque enough to be read over a bright location photo, which
     the wizard's own 2%-overlay inset cannot be. */
  background: var(--bg-panel-solid);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: 0 8px 24px var(--shadow);
}

/* A note is a banner, not a card: it sits in the same corner but does not need
   the prompt's room, and it reads as transient. */
.sp-notes { display: flex; flex-direction: column; }
.sp-note { display: flex; flex-direction: column; gap: 4px; }
.sp-note-head { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; }
.sp-note-title { font-size: 11px; font-weight: 700; color: var(--accent); }
.sp-note-kind {
  font-size: 8px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-dim);
}
.sp-note-lines { margin: 0; padding-left: 14px; display: flex; flex-direction: column; gap: 2px; }
.sp-note-lines li { font-size: 10px; line-height: 1.4; color: var(--text); }
/* An effect that did nothing says so in its own voice: it is the whole point of
   the splash (a refusal used to be indistinguishable from a success). */
.sp-note-lines li.is-silent { color: var(--text-dim); font-style: italic; }

/* The target face: the same card, made pressable. A `button` so the press is
   reachable by keyboard and announced as actionable, with the browser's own
   button chrome reset rather than restyled away. */
.sp-note-action {
  width: 100%;
  text-align: left;
  font: inherit;
  color: inherit;
  background: none;
  border: 0;
  padding: 0;
  cursor: pointer;
}
.sp-note-action:hover .sp-note-cue,
.sp-note-action:focus-visible .sp-note-cue { color: var(--accent); }
.sp-note-action:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; border-radius: 4px; }
/* The way through, since the card itself is the control — without a cue the
   press is not discoverable. */
.sp-note-cue {
  font-size: 10px;
  color: var(--text-dim);
  text-decoration: underline;
  text-underline-offset: 2px;
}

/* Arrival and departure only — the dwell belongs to the shell, which decides how
   long a note lives. */
.sp-note-enter-active, .sp-note-leave-active { transition: opacity 0.2s ease, transform 0.2s ease; }
.sp-note-enter-from, .sp-note-leave-to { opacity: 0; transform: translateY(4px); }

/* The band stack owns the bottom of a phone, so the splash takes the top there
   and spans the width — the one place a floating panel becomes a banner. */
@media (max-width: 820px) {
  .sp-root {
    top: calc(env(safe-area-inset-top, 0px) + 8px);
    right: 12px;
    bottom: auto;
    left: 12px;
    width: auto;
    max-height: 52dvh;
  }
}

@media (prefers-reduced-motion: reduce) {
  .sp-note-enter-active, .sp-note-leave-active { transition: none; }
}
</style>
