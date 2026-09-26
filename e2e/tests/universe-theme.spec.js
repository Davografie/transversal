// Per-universe styling — the universe in play repaints the app's tokens.
//
// The palette itself is content (asserted for shape and contrast in
// `src/api/tests/test_universe_palettes.py`, and for the knob → token mapping in
// `scripts/check-universe-theme.mjs`). What only a browser can show is the
// **wiring**, and its failures are all silent: the palette never reaching
// `:root`, the wrong half of it in the wrong theme, or yesterday's universe
// surviving a walk into the next one.
//
// So this spec reads the palettes from the API and asserts the applied values
// against them — never against hard-coded colours, which would break the day a
// GM edits Earth's palette.

import { test, expect } from '@playwright/test'
import { gql } from '../helpers/sheet.js'

const KAEL = 'character-kael-drift-e555ccde'
const SCREENSHOTS = process.env.PALETTE_SHOTS || ''   // a directory, for a visual pass

let character
let palettes
test.beforeAll(async ({ request }) => {
  const { players } = await gql(request, `query { players { id name agency { entityId main } } }`)
  const owner = players.find((p) => (p.agency || []).some((a) => a.entityId === KAEL && a.main))
  if (!owner) throw new Error(`no player mains ${KAEL} — cannot reach the testing character`)
  character = { playerId: owner.id, playerName: owner.name, entityId: KAEL }

  const data = await gql(request, `{ entities(type: UNIVERSE) { currentUniverse palette } }`)
  palettes = Object.fromEntries(
    data.entities.filter((u) => u.palette).map((u) => [u.currentUniverse, JSON.parse(u.palette)]),
  )
  // Which universe is in play is the app's answer, not this spec's assumption —
  // Kael can be standing anywhere, and the fixture suite moves him.
  const { entity } = await gql(request, `query($id: ID!) { entity(id: $id) { currentUniverse } }`, { id: KAEL })
  character.universe = entity.currentUniverse
  if (!palettes[character.universe]) {
    throw new Error(`the universe in play (${character.universe}) has no palette on its entity`)
  }
})

const cssVar = (page, name) =>
  page.evaluate((n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim(), name)
const appliedUniverse = (page) => page.evaluate(() => document.documentElement.dataset.universe || null)

/** Seed the testing identity and load, with the palette the API really serves. */
async function load(page, { size = { width: 1280, height: 950 }, palette = null } = {}) {
  await page.setViewportSize(size)
  // Pin the starting theme. Playwright's default emulation is *light*, so a
  // case that means to start dark would otherwise measure the light half — and
  // the flip case would pass without ever flipping.
  await page.emulateMedia({ colorScheme: 'dark' })
  if (palette) {
    // Swap the universe entity's palette over the wire: the app's own parser,
    // mapping and clearing are still what runs — only the authored content is
    // synthetic, so this cannot drift from what a real palette would do.
    await page.route('**/api/v1/graphql', async (route) => {
      const response = await route.fetch()
      const json = await response.json()
      for (const u of json?.data?.entities || []) {
        if (u.palette) u.palette = JSON.stringify(palette)
      }
      await route.fulfill({ response, json })
    })
  }
  await page.goto('/')
  await page.evaluate(([pid, pname, eid]) => {
    localStorage.setItem('playerId', pid)
    localStorage.setItem('playerName', pname)
    localStorage.setItem('entityId', eid)
  }, [character.playerId, character.playerName, character.entityId])
  await page.goto('/')
  // `.stage` is a bare positioning div with no box of its own, so it is
  // "hidden" to Playwright forever — attached is the honest wait; the palette
  // assertions below poll for the values, which is the real readiness signal.
  await page.waitForSelector('.stage', { state: 'attached' })
}

test('the universe in play paints its palette on :root, in the theme in play', async ({ page }) => {
  await load(page)
  await expect.poll(() => appliedUniverse(page)).toBe(character.universe)

  const palette = palettes[character.universe]
  for (const [knob, cssVarName] of [['accent', '--accent'], ['bgDeep', '--bg-deep'], ['text', '--text']]) {
    expect(await cssVar(page, cssVarName)).toBe(palette.dark[knob])
  }
  // Type is the half that must reach real elements, not just the root: form
  // controls do not inherit the page font, and that was a real gap.
  const stack = palette.font?.ui
  if (stack) {
    expect(await cssVar(page, '--font-ui')).toBe(stack)
    const button = page.locator('button').first()
    expect(await button.evaluate((el) => getComputedStyle(el).fontFamily)).toContain(stack.split(',')[0].replace(/['"]/g, ''))
  }
  if (SCREENSHOTS) await page.screenshot({ path: `${SCREENSHOTS}/palette-dark.png`, fullPage: false })
})

test('a live theme flip repaints the other half — no reload', async ({ page }) => {
  await load(page)
  await expect.poll(() => appliedUniverse(page)).toBe(character.universe)
  const palette = palettes[character.universe]
  // Dark first, so the flip below is a flip and not a no-op.
  await expect.poll(() => cssVar(page, '--accent')).toBe(palette.dark.accent)
  // A reload would re-run setup and hide a broken watcher, so leave a mark.
  await page.evaluate(() => { window.__notReloaded = true })

  await page.emulateMedia({ colorScheme: 'light' })

  await expect.poll(() => cssVar(page, '--accent')).toBe(palette.light.accent)
  expect(await cssVar(page, '--bg-deep')).toBe(palette.light.bgDeep)
  expect(await page.evaluate(() => window.__notReloaded === true)).toBe(true)
  if (SCREENSHOTS) await page.screenshot({ path: `${SCREENSHOTS}/palette-light.png`, fullPage: false })
})

test('a different universe clears what the last one set', async ({ page }) => {
  // Deliberately not the real Three Realms values: this case is about the
  // *clearing*, and a synthetic palette cannot be mistaken for live content.
  const synthetic = {
    font: { ui: 'Georgia, serif' },
    radius: '0px',
    dark: { accent: '#4fc79a', bgDeep: '#0a1210', text: '#e2ece4' },
  }
  await load(page, { palette: synthetic })
  await expect.poll(() => cssVar(page, '--accent')).toBe('#4fc79a')
  expect(await cssVar(page, '--radius')).toBe('0px')

  // Now the dark-only trap: in light, the synthetic palette has no light group,
  // so every dark colour it painted must be gone — not left behind inline.
  await page.emulateMedia({ colorScheme: 'light' })
  await expect.poll(() => cssVar(page, '--accent')).not.toBe('#4fc79a')
  expect(await cssVar(page, '--bg-deep')).not.toBe('#0a1210')
  // …while the theme-independent half stays, because type and shape are not
  // per-theme and a light/dark flip must not change them.
  expect(await cssVar(page, '--radius')).toBe('0px')
  expect(await cssVar(page, '--font-ui')).toBe('Georgia, serif')
  if (SCREENSHOTS) await page.screenshot({ path: `${SCREENSHOTS}/palette-synthetic-light.png`, fullPage: false })

  // The app keeps polling while the page is open, so the stub outlives the
  // assertions; leaving it in flight makes the *next* teardown fail with a
  // route error that has nothing to do with the test.
  await page.unrouteAll({ behavior: 'ignoreErrors' })
})
