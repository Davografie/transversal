import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { VitePWA } from 'vite-plugin-pwa'
import { fileURLToPath, URL } from 'node:url'

// The API the dev server proxies to. `docker run … -e VITE_API_TARGET=…` lets a
// worktree serve its own API container; unset, this is the compose service name.
const API_TARGET = process.env.VITE_API_TARGET || 'http://api:8080'

export default defineConfig({
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) }
  },
  plugins: [
    // `vanilla-colorful` ships custom elements, so the compiler must leave them
    // alone instead of resolving them as Vue components (which logs a warning and
    // renders nothing).
    vue({ template: { compilerOptions: { isCustomElement: (tag) => tag === 'hex-alpha-color-picker' } } }),
    VitePWA({
      registerType: 'autoUpdate',
      manifest: {
        name: 'Transversal',
        short_name: 'Transversal',
        description: 'VTTRPG — traverse the multiverse',
        theme_color: '#0a0a0f',
        background_color: '#0a0a0f',
        display: 'standalone',
        orientation: 'any',
        icons: [
          { src: '/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icon-512.png', sizes: '512x512', type: 'image/png' }
        ]
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2}'],
        // Routes the **server** owns must never be answered by the app shell.
        // Workbox's navigation fallback (`createHandlerBoundToURL('index.html')`)
        // otherwise swallows any full-page navigation in scope — including a
        // browser opening an emailed link: it loaded the SPA *at* the API URL, the
        // API call never happened, and the game's own requests 401'd behind it
        // ("unauthorized", account still unverified). `/enter` is the architect and
        // passage entry; `/api/` and `/media/` are proxied by nginx.
        navigateFallbackDenylist: [/^\/api\//, /^\/media\//, /^\/enter/],
        runtimeCaching: [
          {
            // Static image variants — cache-first, generous cap.
            urlPattern: /\/media\/imagen\/.*/,
            handler: 'CacheFirst',
            options: {
              cacheName: 'media-imagen',
              cacheableResponse: { statuses: [0, 200] },
              expiration: { maxEntries: 300, maxAgeSeconds: 60 * 60 * 24 * 30 }
            }
          },
          {
            // Animated video loops — cache-first, small cap (videos are large).
            urlPattern: /\/media\/animated\/.*/,
            handler: 'CacheFirst',
            options: {
              cacheName: 'media-animated',
              cacheableResponse: { statuses: [0, 200] },
              expiration: { maxEntries: 30, maxAgeSeconds: 60 * 60 * 24 * 30 }
            }
          }
        ]
      }
    })
  ],
  server: {
    // Vite rejects requests whose Host header it does not recognise (protecting
    // against DNS rebinding). Without this, reaching the dev server over the
    // tailnet returns "Blocked request. This host is not allowed." List the
    // tailnet names explicitly rather than `allowedHosts: true`, which would
    // disable the fence for every host.
    //
    // Host-based, so this one entry covers every dev port — :3000 and the role
    // worktree servers on :3002+ (scripts/dev-worktree.sh).
    allowedHosts: ['ptdave', 'ptdave.ts.transversal.app'],
    proxy: {
      // Default: the compose service. `VITE_API_TARGET` points a worktree dev
      // server at its own API container instead (a worktree's API changes are
      // not in `tv2_api`), which is the only way to exercise a backend change
      // against a browser without touching the :3000 tree.
      '/api': API_TARGET,
      '/media': API_TARGET,
      // SEC-3: in production the nginx edge serves `/enter` and *rewrites* it to
      // the API route. The dev server has no nginx, so without this a passage link
      // falls through to the SPA, returns index.html and sets no session — which is
      // indistinguishable from a bad token. Same origin as the app, so the cookie
      // lands where the app reads it.
      '/enter': {
        target: API_TARGET,
        rewrite: (path) => path.replace(/^\/enter/, '/api/v1/auth/enter'),
      }
    }
  }
})
