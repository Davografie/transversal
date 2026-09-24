<template>
  <!-- The login overlay's shell (`.name-entry`), one layer above it: whichever
       screen was about to render is useless while the archive refuses everything,
       so this sits over the whole app rather than inside the login flow. -->
  <div class="name-entry unauthorized-entry">
    <div class="name-entry-scroll">
      <h3>The way is sealed</h3>
      <p class="name-hint">
        You reached the Transversal, but the archive behind it turned every request away.
      </p>
      <p class="unauthorized-why">
        <strong>Unauthorized.</strong> This device has no valid passage token — the magic
        link you came through has expired, or was never used here.
      </p>
      <p class="name-hint">
        Ask an architect for a fresh link and open it. It looks like
        <code>/enter?t=…</code>, and signs this device in for a month.
      </p>
      <button class="continue-btn" @click="retry">Try again</button>
    </div>
  </div>
</template>

<script setup>
// Shown when the perimeter answered 401 — see composables/useAuthGate.js. There is
// nothing to offer but an explanation: no in-app login can fix a missing cookie,
// only opening a magic link can. "Try again" is for the case where the link was
// opened in this browser since the page loaded.
function retry() {
  window.location.reload()
}
</script>

<style scoped>
.unauthorized-entry { z-index: 200; }
.unauthorized-why {
  max-width: 320px; text-align: center; font-size: 13px; line-height: 1.5;
  color: var(--text);
}
.unauthorized-why strong { color: var(--warn); }
code { font-family: monospace; font-size: 12px; color: var(--text-dim); }
</style>
