import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { defineConfig, devices } from '@playwright/test'

// SEC-3: the suite obtains *real* sessions, so it needs the architect key. Read it
// from the repo's `.env` when the environment does not already carry it, so
// `npm test` works without a preamble. An explicit ARCHITECT_TOKEN still wins,
// which is what a run against a remote (tailnet) server needs — its key is not
// necessarily the one in a local checkout.
const repoEnv = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '.env')
if (fs.existsSync(repoEnv)) {
  for (const line of fs.readFileSync(repoEnv, 'utf8').split('\n')) {
    const m = line.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$/)
    if (m && !process.env[m[1]]) {
      process.env[m[1]] = m[2].replace(/^["']|["']$/g, '')
    }
  }
}

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

  // Serial, because this suite drives a *live* backend rather than a fixture.
  // Two workers opening the same player's same character collide over the shared
  // session: tests that pass one at a time fail two at a time, in both engines.
  // The whole suite is a few seconds either way, so the parallelism buys nothing.
  fullyParallel: false,
  workers: 1,

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
