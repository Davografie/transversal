<template>
  <!-- SEC-3 admission, as the Players tab's controls. The invitation itself — the
       QR and the link — opens as a **child panel** (`GmAdmissionPanel`): a ~220px
       code is the widest thing this tab would ever hold, and showing the table is
       not the same act as managing the roster. What stays here is the switch and
       the open list, because that is the owner's sight and off-switch. -->
  <div class="admit-block">
    <label class="settings-label">Admission</label>

    <p class="admit-hint">One window admits the whole table — show them the code.</p>

    <Button v-if="!joining" variant="success" solid block :disabled="busy" @click="$emit('open')">
      Admit players
    </Button>
    <Button v-else variant="neutral" block @click="$emit('show')">Show the invitation</Button>

    <template v-if="windows.length">
      <label class="settings-label">Open now ({{ windows.length }})</label>
      <div class="char-list">
        <button
          v-for="w in windows"
          :key="w.id"
          class="char-item"
          :disabled="busy"
          @click="$emit('close', w.id)"
        >{{ closingAt(w) }} — close</button>
      </div>
      <!-- Architect-only server-side. Gated on the server's role, not on the
           client's gmMode: SEC-3 means the server decides, and offering an action
           it will refuse is how a UI teaches people to distrust its buttons. -->
      <Button v-if="canCloseAll" variant="danger" block :disabled="busy" @click="$emit('close-all')">
        Close all windows
      </Button>
    </template>

    <p v-if="error" class="switch-error">{{ error }}</p>
  </div>
</template>

<script setup>
import Button from '@/components/ui/Button.vue'

// Presentation only: the composable owns the calls, and the invitation panel owns
// the QR. The window rows are labelled by when they lapse rather than by token id —
// an id means nothing to the person deciding whether to close it.
defineProps({
  windows: { type: Array, default: () => [] },
  /** The window this session just minted, if it is still open. */
  joining: { type: Object, default: null },
  busy: { type: Boolean, default: false },
  error: { type: String, default: '' },
  canCloseAll: { type: Boolean, default: false },
})

defineEmits(['open', 'show', 'close', 'close-all'])

function closingAt(w) {
  const d = new Date(w?.expires_at)
  return isNaN(d) ? 'open' : `until ${d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
}
</script>

<style scoped>
/* The tab is ~386px wide inside the GM panel's scrolling zone. Nothing here
   carries a width of its own, so nothing can push that zone into a horizontal
   scroll; the shared `.settings-section` (min(520px, 100vw - 32px)) belongs to the
   settings overlay and must not be used here. */
.admit-block {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 6px;
  width: 100%;
  min-width: 0;
}
.admit-hint {
  margin: 0;
  font-size: 11px;
  line-height: 1.4;
  color: var(--text-dim);
}
.admit-block .char-list { justify-content: flex-start; }
</style>
