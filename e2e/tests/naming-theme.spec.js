// The Naming theme dropdown on a universe's editor (B82).
//
// The regression this exists for: the select shipped with **exactly one option**,
// "Default ()". The list is fetched on demand, and the fetch was gated on
// `onMounted(isUniverse)` — but the GM panel mounts the form *before* the entity it
// edits has loaded, so at mount `local.type` was still undefined, the gate was
// false, and the themes were never asked for. Every node-level check passed: the
// query is fine, the composable is fine, the template is fine. Only a browser
// notices that the options never arrived.
//
// So this spec asserts the *populated* dropdown, and the default option's label.

import { test, expect } from '@playwright/test'
import { gql } from '../helpers/sheet.js'
import { asArchitect } from '../helpers/arrange.js'
import { establishSession } from '../helpers/session.js'

const KAEL = 'character-kael-drift-e555ccde'
const DESKTOP = { width: 1280, height: 950 }

// Opening the GM panel stack is the slow part (it mounts the entity list).
test.setTimeout(60000)

let character

test.beforeAll(async ({ request }) => {
  const { players } = await gql(request, `query { players { id name agency { entityId main } } }`)
  const owner = players.find((p) => (p.agency || []).some((a) => a.entityId === KAEL && a.main))
  if (!owner) throw new Error(`no player mains ${KAEL} — cannot reach the testing character`)
  character = { playerId: owner.id, playerName: owner.name, entityId: KAEL }
})

/** The universe a GM reaches first in Prep, and the entity id it opens. */
async function openUniverseEditor(page) {
  await page.unroute('**/api/v1/players/**')
  await asArchitect(page)
  await page.setViewportSize(DESKTOP)
  await page.goto('/')
  await page.evaluate(([pid, pname, eid]) => {
    localStorage.setItem('playerId', pid)
    localStorage.setItem('playerName', pname)
    localStorage.setItem('entityId', eid)
  }, [character.playerId, character.playerName, character.entityId])
  await establishSession(page)
  await page.goto('/')
  await page.locator('.name-entry.panel').first().waitFor({ state: 'hidden', timeout: 20000 })

  // The panel mounts its own list on open, so wait for the chrome before driving it.
  await page.locator('.gm-toggle').click()
  await page.locator('.mode-tabs').waitFor({ state: 'visible', timeout: 20000 })
  await page.locator('.mode-tabs button', { hasText: 'Prep' }).click()
  const row = page.locator('.entity-row.tree-row', { hasText: 'Earth' }).first()
  await row.waitFor({ state: 'visible', timeout: 20000 })
  await row.click()
}

test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: 'ignoreErrors' })
})

test('the universe editor offers every theme, not just the default', async ({ page }) => {
  const problems = []
  page.on('pageerror', (e) => problems.push('uncaught: ' + String(e)))
  page.on('console', (m) => { if (m.type() === 'error' && /\[Vue warn\]/.test(m.text())) problems.push(m.text()) })

  await openUniverseEditor(page)

  // Located by its label rather than a class: this spec has to run against the
  // tree *before* the fix as well as after it (that is the red check), and the
  // class hook was added with the fix.
  const select = page.locator('label:has-text("Naming theme") + select')
  await expect(select).toBeVisible({ timeout: 20000 })

  // The bug: one option. A loaded list is the whole point of the control.
  const options = select.locator('option')
  await expect.poll(async () => options.count(), { timeout: 20000 }).toBeGreaterThan(1)

  // Real themes, by label — read from the backend, so this is the API's list too.
  await expect(select.locator('option', { hasText: 'Chinese' })).toHaveCount(1)
  await expect(select.locator('option', { hasText: 'Fantasy' })).toHaveCount(1)
  await expect(select.locator('option', { hasText: 'Alien' })).toHaveCount(1)

  // The default option names the theme it means, and never the empty parentheses
  // the first cut showed while the list was in flight.
  const first = await options.first().textContent()
  expect(first).toMatch(/^Default \(.+\)$/)

  expect(problems, problems.join('\n')).toEqual([])
})

test('picking a theme is what the panel would save', async ({ page }) => {
  // Stubbed: a universe's theme is live content and a run must not rewrite it.
  const writes = []
  await page.route('**/api/v1/graphql', async (route) => {
    const body = route.request().postData() || ''
    if (body.includes('updateEntity') && body.includes('namingTheme')) {
      const input = JSON.parse(body).variables?.input
      writes.push(input)
      return route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify({
          data: {
            updateEntity: {
              id: input.id, name: 'Earth', namingTheme: input.namingTheme,
              razmerit: 0, currentUniverse: 'earth', currentLocation: null,
              hidden: false, unpublished: false, supportEligible: false,
              starterLocation: false, loraConfig: null, promptSteering: '',
            },
          },
        }),
      })
    }
    return route.continue()
  })

  await openUniverseEditor(page)
  const select = page.locator('label:has-text("Naming theme") + select')
  await expect(select).toBeVisible({ timeout: 20000 })
  await expect.poll(async () => select.locator('option').count(), { timeout: 20000 })
    .toBeGreaterThan(1)

  await select.selectOption({ label: 'Chinese' })

  // The write carries the theme, which is the whole round trip: the dropdown read
  // the list from the API and what it stores comes back as `namingTheme`.
  //
  // Polled on the **value**, not on the count: the panel autosaves on a 600ms
  // debounce, so an earlier write can land first and a count-based poll would read
  // that one and fail on a correct build.
  await expect.poll(
    () => writes.map((w) => w.namingTheme).at(-1),
    { timeout: 20000 },
  ).toBe('chinese')
})
