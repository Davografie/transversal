import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { VitePWA } from 'vite-plugin-pwa'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) }
  },
  plugins: [
    vue(),
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
      '/api': 'http://api:8080',
      '/media': 'http://api:8080'
    }
  }
})
