<template>
  <div class="admit-panel">
    <!-- The window this session minted, live from the shared admission state: it
         is closed (here or in the tab) the moment the QR would stop admitting. -->
    <template v-if="live">
      <p class="name-hint">Show this to the table — everyone who scans it can join.</p>

      <img v-if="qr" class="admit-qr" :src="qr" alt="Admission QR code" />

      <div class="admit-link">
        <input
          class="admit-link-input"
          readonly
          :value="url"
          aria-label="Admission link"
          @focus="$event.target.select()"
        />
        <Button variant="neutral" size="sm" @click="$emit('copy', url)">Copy</Button>
      </div>

      <p class="name-hint">This window closes itself at {{ closingAt }}.</p>

      <div class="admit-actions">
        <Button variant="danger" size="sm" :disabled="busy" @click="closeWindow">
          {{ busy ? 'Closing…' : 'Close this window' }}
        </Button>
      </div>
    </template>

    <p v-else class="name-hint">
      That window is closed — nothing can join through it now. Open another from the
      Players tab.
    </p>

    <p v-if="error" class="switch-error">{{ error }}</p>
  </div>
</template>

<script setup>
// The invitation itself, as a child panel of the GM panel: the QR the table scans
// and the link to paste. It is a panel rather than a block in the Players tab for
// two reasons — the QR needs room (a ~220px code inside a ~386px tab is the widest
// thing there and was what pushed the tab into horizontal scroll), and the thing
// you *show* to the table is a surface you open, not chrome left sitting beside the
// roster.
//
// It takes no props: the window it shows is the session's live one, read from the
// same `useAdmission()` state the tab uses. That is what lets it notice a window
// closed from the tab — a props snapshot would keep showing a QR for a token that
// no longer admits.
//
// Not restorable (see `constants/restorablePanels.js`): it renders a live admission
// token, which must never be written to localStorage.
import { computed, ref, watch } from 'vue'
import QRCode from 'qrcode'
import Button from '@/components/ui/Button.vue'
import { usePanel } from '@/composables/usePanel.js'
import { useAdmission, joinUrl } from '@/composables/useAdmission.js'

const emit = defineEmits(['copy'])

const panel = usePanel()
const { joining, busy, error, close } = useAdmission()

const live = computed(() => !!joining.value?.id)
// Same origin, so the cookie the token issues lands where it is read.
const url = computed(() => (joining.value?.token ? joinUrl(joining.value) : ''))

const qr = ref('')
watch(
  url,
  async (value) => {
    // Generated locally. The token is an admission credential and must never be
    // handed to a third-party image service to be rendered.
    qr.value = value ? await QRCode.toDataURL(value, { margin: 1, width: 220 }) : ''
  },
  { immediate: true },
)

const closingAt = computed(() => {
  const d = new Date(joining.value?.expires_at)
  return isNaN(d) ? 'soon' : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
})

async function closeWindow() {
  await close(joining.value.id)
  // A failure leaves the panel up with the error on it, and the window still open —
  // which is the honest state: it can still admit.
  if (!error.value) panel.close()
}
</script>

<style scoped>
.admit-panel {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  width: 100%;
  min-width: 0;
}
.admit-panel .name-hint { max-width: 100%; }
.admit-qr {
  display: block;
  background: #fff;
  padding: 8px;
  border-radius: 6px;
  /* Fits whatever panel it is in — a detached window can be dragged narrow. */
  max-width: 100%;
  height: auto;
}
.admit-link {
  display: flex;
  gap: 6px;
  align-items: center;
  width: 100%;
  min-width: 0;
}
/* `min-width: 0` is what lets a long token ellipsise instead of setting the flex
   row's width and scrolling the panel. (Deliberately not `.settings-name-input`:
   that class is the overlay's 24px name field and carries `!important` sizing this
   panel cannot argue with.) */
.admit-link-input {
  flex: 1 1 auto;
  min-width: 0;
  padding: 5px 8px;
  font-size: 11px;
  text-overflow: ellipsis;
  color: var(--text-dim);
  background: var(--overlay-4);
  border: 1px solid var(--overlay-8);
  border-radius: var(--radius-sm);
}
.admit-actions { display: flex; gap: 6px; }
</style>
