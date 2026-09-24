import { createApp } from 'vue'
import App from './App.vue'
import './assets/styles.css'
import './assets/gm-panel.css'
import { installAuthGate } from './composables/useAuthGate.js'

// One-line env marker so dev vs prod is unambiguous in the console.
// Dev (vite serve): no service worker, so media runtime caching is disabled.
// Prod (vite build output): service worker registers and caches /media/.
console.log(`[env] ${import.meta.env.DEV ? 'dev (no service worker / no media cache)' : 'prod (service worker / media cache)'}`)

// Before mount, so the very first request is watched: a deployed build's requests
// all pass the nginx perimeter, which 401s without a session cookie.
installAuthGate()

createApp(App).mount('#app')
