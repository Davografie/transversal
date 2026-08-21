import { createApp } from 'vue'
import App from './App.vue'
import './assets/styles.css'
import './assets/gm-panel.css'

// One-line env marker so dev vs prod is unambiguous in the console.
// Dev (vite serve): no service worker, so media runtime caching is disabled.
// Prod (vite build output): service worker registers and caches /media/.
console.log(`[env] ${import.meta.env.DEV ? 'dev (no service worker / no media cache)' : 'prod (service worker / media cache)'}`)

createApp(App).mount('#app')
