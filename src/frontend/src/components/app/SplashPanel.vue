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
           `action`, which is also what tells the two apart. An authored client
           action ([[B132]]) arrives as the same face: a message the engine was
           told to deliver, which may name an action of its own.

       **Front and centre, for every face** (the author, 2026-10-14: *"I expected
       the splash panel to open front and center, but it's more like a glorified
       toast now"*). It used to take the free corner on a desktop and the top
       banner on a phone; the centre is the same place on every layout, which is
       what "a player learns where to look" wanted in the first place. It stays
       **non-modal, with no scrim**: the card is the only thing that takes input,
       so the table behind it is never blocked.

       The shell owns *when*: it decides the dwell (a small change is shorter than
       a course summary), holds a target until it is tapped, and feeds notes in
       order. The splash owns *how*. -->
  <div
    class="sp-root"
    :class="{ 'sp-has-prompt': hasPrompt, 'sp-target-card': !!currentNote?.value }"
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

    <!-- One note at a time, the head of the queue. A plain report is a live region
         (`role="status"`) so a change nobody asked for is announced rather than
         only seen; a **target** is a button instead, because it is meant to be
         pressed. -->
    <TransitionGroup v-if="!hasPrompt && currentNote" name="sp-note" tag="div" class="sp-notes">
      <!-- A wrapper, so a sticky message with nothing to press can carry its own
           ✕ *beside* the control rather than inside it (a button inside a button
           is not a thing). -->
      <div :key="currentNote.id" class="sp-note-wrap">
        <component
          :is="currentNote.action ? 'button' : 'div'"
          class="sp-note"
          :class="{ 'sp-note-action': !!currentNote.action }"
          :type="currentNote.action ? 'button' : undefined"
          :role="currentNote.action ? undefined : 'status'"
          @click="currentNote.action && emit('act', currentNote)"
        >
          <!-- A **target**: the number is the whole point, so it is the biggest thing
               on the surface and it lands with a ring rather than fading in. The head
               is skipped — "your target" over a number that is already labelled is a
               second label for the same thing. -->
          <div v-if="currentNote.value" class="sp-target">
            <span class="sp-target-ring" aria-hidden="true"></span>
            <span class="sp-target-label">{{ currentNote.title }}</span>
            <span class="sp-target-value">{{ currentNote.value }}</span>
          </div>
          <div v-else class="sp-note-head">
            <span class="sp-note-title">{{ currentNote.title }}</span>
            <span class="sp-note-kind">{{ kindLabel }}</span>
          </div>
          <ul v-if="currentNote.lines?.length" class="sp-note-lines">
            <li v-for="(line, i) in currentNote.lines" :key="i" :class="{ 'is-silent': line.silent }">{{ line.text || line }}</li>
          </ul>
          <!-- What is opposing you, as the location's own trait chips ([[B92]]) —
               name, statement, and the face each die actually rolled. Re-using the
               chip is the point: it is the same object the map draws, so the two
               cannot drift apart. -->
          <div v-if="currentNote.chips?.length" class="sp-chips">
            <TraitChip
              v-for="(chip, i) in currentNote.chips"
              :key="i"
              class="sp-chip"
              :style="{ '--sp-chip-delay': `${120 + i * 70}ms` }"
              :trait="chip"
              expanded
            />
          </div>
          <span v-if="currentNote.action" class="sp-note-cue">{{ currentNote.action }}</span>
        </component>
        <!-- A target is dismissed *by* its action, so it needs no Cancel. A sticky
             message with no action has no such way out, and a card that waits for
             ever with no exit is a trap. -->
        <button
          v-if="currentNote.sticky && !currentNote.action"
          class="sp-note-close"
          type="button"
          aria-label="Dismiss"
          @click="emit('dismiss', currentNote)"
        >✕</button>
      </div>
    </TransitionGroup>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import EffectTargetWizard from '@/components/gm/EffectTargetWizard.vue'
import TraitChip from '@/components/location/TraitChip.vue'

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
//     Cancel of its own. A sticky message the engine delivered with *no* action is
//     the one case that does need one ([[B132]]), hence the ✕.
//
// The dwell of a note belongs to the shell; the splash only says which face it is,
// and every face opens in the same place — the middle of the viewport.
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
  /**
   * The note at the head of the queue — the note face, the **target** face when it
   * names an `action`, and an authored client message ([[B132]]).
   * `{ id, title, kind, lines, action?, targetId?, sticky? }`.
   */
  note: { type: Object, default: null },
})
// Captured, not just declared: the template calls `emit(...)`, and a bare
// `defineEmits([...])` leaves it undefined there — every click then throws
// instead of reaching the shell, which reads as "the question will not close".
const emit = defineEmits(['answer', 'leave', 'loop', 'act', 'dismiss'])

const hasPrompt = computed(() => !!props.choices?.length)
const promptEntityId = computed(() => props.choices?.[0]?.entity_id || props.entityId)
const currentNote = computed(() => (hasPrompt.value ? null : props.note))

const KIND_LABELS = { summary: 'resolved', target: 'your target', change: 'changed' }
const kindLabel = computed(() => KIND_LABELS[currentNote.value?.kind] || KIND_LABELS.change)

</script>

<style scoped>
/* Front and centre for every face.
   Deliberately **transform-free**: a transformed ancestor becomes the containing
   block for `position: fixed` descendants, and the wizard's own surface must not
   be re-parented — the trap the landscape dock records. `inset: 0` with
   `margin: auto` centres without one. Above the GM panel viewport (25) so a
   splash is never buried under a panel, below the login/settings overlay (100). */
.sp-root {
  position: fixed;
  inset: 0;
  margin: auto;
  z-index: 30;
  width: min(420px, calc(100vw - 32px));
  height: fit-content;
  max-height: min(70dvh, 560px);
  overflow-y: auto;
  padding: 12px;
  /* The one surface. Opaque enough to be read over a bright location photo, which
     the wizard's own 2%-overlay inset cannot be. */
  background: var(--bg-panel-solid);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: 0 12px 32px var(--shadow);
}

/* A target's card is edged in the accent and glows: it is the one face that is
   asking for attention rather than reporting. */
.sp-target-card {
  border-color: color-mix(in srgb, var(--accent) 55%, var(--border));
  box-shadow:
    0 12px 32px var(--shadow),
    0 0 0 1px color-mix(in srgb, var(--accent) 35%, transparent),
    0 0 34px color-mix(in srgb, var(--accent) 22%, transparent);
}

/* A note is a banner, not a card: it sits in the same place but does not need the
   prompt's room, and it reads as transient. */
.sp-notes { display: flex; flex-direction: column; }
.sp-note-wrap { position: relative; display: flex; flex-direction: column; }
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

/* A sticky message with nothing to press carries its own way out, in the corner
   of the card. */
.sp-note-close {
  position: absolute;
  top: -6px;
  right: -6px;
  width: 20px;
  height: 20px;
  padding: 0;
  border: 1px solid var(--border-soft);
  border-radius: var(--radius-xs);
  background: var(--bg-panel-raised);
  color: var(--text-dim);
  font-size: 10px;
  line-height: 1;
  cursor: pointer;
}
.sp-note-close:hover { color: var(--text); border-color: var(--border); }

/* ── The target: the loudest thing the surface ever draws ────────────────────
   A target is the number you are about to be measured against, so it is stated
   rather than reported: oversized, glowing, and it *lands* — a ring punches out
   from behind it as it pops in. The drama is on descendants, never on `.sp-root`
   (a transformed ancestor would re-parent every `position: fixed` inside it), and
   all of it is off under `prefers-reduced-motion`. */
.sp-target {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 8px 0 4px;
}
.sp-target-label {
  font-size: 9px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.22em;
  color: var(--text-dim);
}
/* A wash behind the number, so the eye lands there before anything else. */
.sp-target::before {
  content: '';
  position: absolute;
  inset: -10px -28px;
  background: radial-gradient(ellipse at center,
    color-mix(in srgb, var(--accent) 24%, transparent) 0%,
    transparent 72%);
  pointer-events: none;
}
.sp-target-value {
  font-size: 76px;
  font-weight: 800;
  line-height: 1;
  letter-spacing: -0.02em;
  color: var(--accent);
  font-variant-numeric: tabular-nums;
  text-shadow:
    0 0 2px color-mix(in srgb, var(--accent) 90%, transparent),
    0 0 26px color-mix(in srgb, var(--accent) 70%, transparent),
    0 0 64px color-mix(in srgb, var(--accent) 45%, transparent),
    0 3px 0 rgba(0, 0, 0, 0.4);
  /* Lands, then breathes: the pop is the arrival, the glow is the menace. */
  animation:
    sp-target-pop 0.5s cubic-bezier(0.2, 1.5, 0.4, 1) both,
    sp-target-glow 2.6s ease-in-out 0.5s infinite;
}
@keyframes sp-target-glow {
  0%, 100% { filter: brightness(1); }
  50%      { filter: brightness(1.2); }
}
/* The ring is decoration, so it is out of the flow and never eats a press. */
.sp-target-ring {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 96px;
  height: 96px;
  margin: -48px 0 0 -48px;
  border: 2px solid var(--accent);
  border-radius: 50%;
  pointer-events: none;
  animation: sp-target-ring 0.75s ease-out both;
}
@keyframes sp-target-pop {
  0%   { transform: scale(0.5); opacity: 0; }
  60%  { transform: scale(1.08); opacity: 1; }
  100% { transform: scale(1); opacity: 1; }
}
@keyframes sp-target-ring {
  0%   { transform: scale(0.25); opacity: 0.85; }
  100% { transform: scale(2.1); opacity: 0; }
}

/* The trait chips, staggered in behind the number: the number lands, then what is
   opposing you arrives one trait at a time. */
.sp-chips {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  margin-top: 2px;
}
.sp-chip {
  animation: sp-chip-in 0.35s ease-out both;
  animation-delay: var(--sp-chip-delay, 120ms);
}
@keyframes sp-chip-in {
  from { transform: translateY(-4px); opacity: 0; }
  to   { transform: translateY(0); opacity: 1; }
}
/* Decorative here, not a control: the chip is the map's, and on the map it is
   clickable. The card around it is the thing you press. */
.sp-chip :deep(.trait-chip) { cursor: inherit; }

@media (prefers-reduced-motion: reduce) {
  .sp-target-value, .sp-target-ring, .sp-chip { animation: none; }
  .sp-target-ring { display: none; }
}

/* Arrival and departure only — the dwell belongs to the shell, which decides how
   long a note lives (and gives a target none). */
.sp-note-enter-active, .sp-note-leave-active { transition: opacity 0.2s ease, transform 0.2s ease; }
.sp-note-enter-from, .sp-note-leave-to { opacity: 0; transform: translateY(4px); }

@media (prefers-reduced-motion: reduce) {
  .sp-note-enter-active, .sp-note-leave-active { transition: none; }
}
</style>
