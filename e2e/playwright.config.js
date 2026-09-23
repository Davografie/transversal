import { defineConfig, devices } from '@playwright/test'

// Where the app under test lives.
//
//   localhost:3000        the canonical dev server (release-build), on this machine
//   http://ptdave:3000    the same server over the tailnet, from a remote machine
//
// Vite only answers hostnames listed in `server.allowedHosts`, so a tailnet run
// needs `ptdave` in src/frontend/vite.config.js. See docs/Technical/Private
// Access Runbook.md.
const baseURL = process.env.E2E_BASE_URL || 'http://localhost:3000'

export default defineConfig({
  testDir: './tests',
  timeout: 30_000,
  expect: { timeout: 10_000 },
  reporter: [['list']],

  use: {
    baseURL,
    // Keep evidence when something fails — a screenshot is usually the fastest
    // way to see what actually rendered.
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },

  // Two engines on purpose: a second rendering engine catches problems that are
  // specific to one of them. Run a single one with --project=chromium|firefox.
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
  ],
})
