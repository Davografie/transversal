import { createApp } from 'vue'
import App from './App.vue'
import PortalView from './components/PortalView.vue'
import './assets/styles.css'
import './assets/gm-panel.css'
import { installAuthGate } from './composables/useAuthGate.js'

// One-line env marker so dev vs prod is unambiguous in the console.
// Dev (vite serve): no service worker, so media runtime caching is disabled.
// Prod (vite build output): service worker registers and caches /media/.
console.log(`[env] ${import.meta.env.DEV ? 'dev (no service worker / no media cache)' : 'prod (service worker / media cache)'}`)

// A new service worker should take effect **without asking the visitor to know about
// hard refresh** (B88). `autoUpdate` installs and activates it, but the page in front of
// them was rendered by the old one — so when control changes under a page that was
// already controlled, reload once. Guarded on `hadController` so a first install (which
// also fires this) does not reload a page that was never stale.
const hadController = !!navigator.serviceWorker?.controller
navigator.serviceWorker?.addEventListener('controllerchange', () => {
  if (hadController) window.location.reload()
})

// Two surfaces, one bundle. `/portal` is the **apex** page — sign in, and your
// campaigns — and it mounts instead of the game, for two reasons that matter:
//
// - it must render *without* a campaign session, which is exactly the state the
//   auth gate treats as "the perimeter refused us"; and
// - it calls the account tier, whose 401 is a legitimate answer ("not signed in"),
//   not a sealed door.
//
// The path is the whole test, so dev (`/portal` on any host) and production (the
// apex rewrites `/` here) behave identically. Campaign hosts keep the game.
if (window.location.pathname.startsWith('/portal')) {
  createApp(PortalView).mount('#app')
} else {
  // Before mount, so the very first request is watched: a deployed build's requests
  // all pass the nginx perimeter, which 401s without a session cookie.
  installAuthGate()
  createApp(App).mount('#app')
}
