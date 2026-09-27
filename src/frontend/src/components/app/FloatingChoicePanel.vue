<template>
  <!-- The floating host for an **automatic** rule's question ([[B230]]).
       A state change or a timer nobody pressed raises a choice with nowhere its
       reader is looking, so it asks here.

       Layout only, in the sense that matters: this wrapper positions the panel
       and draws *the one* surface it needs, and the wizard inside keeps its own
       inset (`.etw-root`). It deliberately does **not** add a second card with
       its own token set — that is the mistake the sheet host made, and it is why
       the same table rendered differently there. -->
  <div
    class="fcp-root"
    role="region"
    aria-label="A rule is asking for a choice"
  >
    <EffectTargetWizard
      :entity-id="entityId"
      :pending-choices="choices"
      :title="title"
      @resolve="(r) => emit('answer', r)"
      @cancel="emit('leave')"
      @run-loop="(c) => emit('loop', c)"
    />
  </div>
</template>

<script setup>
import EffectTargetWizard from '@/components/gm/EffectTargetWizard.vue'

// A choice the player did not ask for. Three rules decide the shape:
//
//   * **Non-modal, and no scrim.** The change that raised the question is the
//     context for answering it — dimming the table would hide the very thing
//     being asked about — and a parked question must not block play.
//   * **It never dismisses itself.** There is no timer and no auto-close; the
//     only ways out are answering it or the wizard's own Cancel, which writes
//     nothing (the branch stays parked server-side and is recoverable).
//   * **It does not move.** Fixed to the same corner every time rather than
//     dragged: a question should be where you last saw it, and on touch the
//     bands already own the drag gestures. If it proves to be in the way over a
//     map, the follow-up is a corner snap, not free dragging.
defineProps({
  choices: { type: Array, default: () => [] },
  // The entity the *question* belongs to, which is not always the acting one — a
  // GM receives an entity's automatic question without acting as it.
  entityId: { type: String, required: true },
  title: { type: String, default: 'A rule needs a choice' },
})
// Captured, not just declared: the template calls `emit(...)`, and a bare
// `defineEmits([...])` leaves it undefined there — every click then throws
// instead of reaching the shell, which reads as "the question will not close".
const emit = defineEmits(['answer', 'leave', 'loop'])
</script>

<style scoped>
/* Bottom-right on a desktop: the sheet docks left, the roller sits bottom-centre
   and the ✨ rail owns the left edge, so this is the one free corner. Above the
   GM panel viewport (25) so a question is never buried under a panel, below the
   login/settings overlay (100). */
.fcp-root {
  position: fixed;
  right: 16px;
  bottom: 16px;
  z-index: 30;
  width: min(340px, calc(100vw - 24px));
  max-height: min(70dvh, 560px);
  overflow-y: auto;
  padding: 10px;
  /* The one surface. Opaque enough to be read over a bright location photo,
     which the wizard's own 2%-overlay inset cannot be. */
  background: var(--bg-panel-solid);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: 0 8px 24px var(--shadow);
}

/* The band stack owns the bottom of a phone, so the panel takes the top there
   and spans the width — the one place a floating panel becomes a banner. */
@media (max-width: 820px) {
  .fcp-root {
    top: calc(env(safe-area-inset-top, 0px) + 8px);
    right: 12px;
    bottom: auto;
    left: 12px;
    width: auto;
    max-height: 52dvh;
  }
}
</style>
