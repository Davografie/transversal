import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { VitePWA } from 'vite-plugin-pwa'
import { fileURLToPath, URL } from 'node:url'

// The API the dev server proxies to. `docker run … -e VITE_API_TARGET=…` lets a
// worktree serve its own API container; unset, this is the compose service name.
const API_TARGET = process.env.VITE_API_TARGET || 'http://api:8080'

// Which campaign the dev server opens ([[B305]]). A campaign is chosen by the **Host**
// the API sees (`<slug>.<base-domain>`), so the proxy is the only place a dev server can
// set it — and that is deliberate rather than incidental: a client able to *name* its own
// campaign would be a cross-tenant hole, which is exactly what B305 closed. Unset means no
// campaign label, and the default database (the playroom) is served, as before.
const CAMPAIGN_HOST = process.env.VITE_CAMPAIGN_HOST || ''
const campaignHeaders = CAMPAIGN_HOST ? { Host: CAMPAIGN_HOST } : {}

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
        // **`/` must not be answered from the precache at all.** Workbox's default
        // `directoryIndex: 'index.html'` rewrites a request for `/` into
        // `/index.html` and serves the precached shell, and the precache route matches
        // **before** the navigation fallback — so no `navigateFallbackDenylist` entry
        // can reach the root. That is why denying `/` changed nothing: the apex
        // redirects `/` to `/portal`, the redirect never ran, and the SPA booted the
        // game on the apex (no campaign session there → its Unauthorized screen).
        // Verified in workbox's own source that the default is a destructuring default
        // (`directoryIndex = 'index.html'`) and the rewrite is guarded by
        // `if (directoryIndex && …)`, so an explicit null disables it for real.
        directoryIndex: null,
        globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2}'],
        // Routes the **server** owns must never be answered by the app shell.
        // Workbox's navigation fallback (`createHandlerBoundToURL('index.html')`)
        // otherwise swallows any full-page navigation in scope — including a
        // browser opening an emailed link: it loaded the SPA *at* the API URL, the
        // API call never happened, and the game's own requests 401'd behind it
        // ("unauthorized", account still unverified). `/enter` is the architect and
        // passage entry; `/api/` and `/media/` are proxied by nginx.
        //
        // `/` is here for the same reason and was the one that got missed: the apex
        // **redirects** it to `/portal`, and a worker answering that navigation from
        // cache means the redirect never happens — the browser boots the *game* on
        // the apex, which has no campaign session there, and shows its Unauthorized
        // screen instead of the portal. Denying it costs nothing on a campaign host,
        // where nginx serves the same shell from `location /` anyway.
        navigateFallbackDenylist: [
          /^\/api\//,
          /^\/media\//,
          /^\/enter/,
          /^\/(\?.*)?$/,
          // `/portal` too, so the **edge's offline page** can be shown when the machine
          // that runs Transversal is switched off. A cached shell would boot the portal
          // against a dead server and report a broken app; letting the network answer
          // means Caddy's page appears instead. The shell is 642 bytes, so always
          // fetching it costs nothing.
          /^\/portal/,
        ],
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
      '/api': { target: API_TARGET, headers: campaignHeaders },
      '/media': { target: API_TARGET, headers: campaignHeaders },
      // SEC-3: in production the nginx edge serves `/enter` and *rewrites* it to
      // the API route. The dev server has no nginx, so without this a passage link
      // falls through to the SPA, returns index.html and sets no session — which is
      // indistinguishable from a bad token. Same origin as the app, so the cookie
      // lands where the app reads it.
      '/enter': {
        target: API_TARGET,
        headers: campaignHeaders,
        rewrite: (path) => path.replace(/^\/enter/, '/api/v1/auth/enter'),
      }
    }
  }
})
