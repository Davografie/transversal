// The GM palette panel — the *authoring* half of per-universe styling.
//
// The palette is data on the universe entity, and this panel is the only surface
// that writes it. What a browser has to prove that a node check cannot: it opens
// on the universe in play, it paints the chrome **while you edit** (through
// `useUniverseTheme`, the one writer of those `:root` properties), and what it
// saves is the cleaned palette — blank fields dropped rather than written as
// empty strings, because an omitted knob is how the runtime falls back.
//
// The save is stubbed. A run must not rewrite a universe's palette: the shipped
// examples are live content, and this spec asserts the *payload* anyway.

import { test, expect } from '@playwright/test'
import { gql } from '../helpers/sheet.js'
import { asArchitect } from '../helpers/arrange.js'

const KAEL = 'character-kael-drift-e555ccde'
const DESKTOP = { width: 1280, height: 950 }

// Opening the GM panel stack is the slow part (it mounts the entity list).
test.setTimeout(60000)

let character
let earth
test.beforeAll(async ({ request }) => {
  const { players } = await gql(request, `query { players { id name agency { entityId main } } }`)
  const owner = players.find((p) => (p.agency || []).some((a) => a.entityId === KAEL && a.main))
  if (!owner) throw new Error(`no player mains ${KAEL} — cannot reach the testing character`)
  character = { playerId: owner.id, playerName: owner.name, entityId: KAEL }
  const { entities } = await gql(request, `{ entities(type: UNIVERSE) { id name currentUniverse palette } }`)
  earth = entities.find((u) => u.currentUniverse === 'earth')
})

/** Record palette writes instead of performing them. */
async function stubSave(page, extras) {
  await page.route('**/api/v1/graphql', async (route) => {
    const body = route.request().postData() || ''
    // Match `updateEntity` without the paren: the query text is
    // `updateEntity(input: $input)`, and a stub that misses writes to the real
    // universe (a palette is live content).
    if (body.includes('updateEntity') && body.includes('palette')) {
      extras.saved = JSON.parse(body).variables?.input
      return route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify({ data: { updateEntity: { id: extras.saved?.id, palette: extras.saved?.palette } } }),
      })
    }
    return route.continue()
  })
}

async function openPanel(page) {
  await page.unroute('**/api/v1/players/**')
  await asArchitect(page)
  await page.setViewportSize(DESKTOP)
  // The palette has two halves and the browser defaults to *light*, so the theme
  // in play has to be pinned or an edit to the dark rows changes nothing on
  // screen and the preview assertion measures the wrong half.
  await page.emulateMedia({ colorScheme: 'dark' })
  await page.goto('/')
  await page.evaluate(([pid, pname, eid]) => {
    localStorage.setItem('playerId', pid)
    localStorage.setItem('playerName', pname)
    localStorage.setItem('entityId', eid)
  }, [character.playerId, character.playerName, character.entityId])
  await page.goto('/')
  await page.locator('.name-entry.panel').first().waitFor({ state: 'hidden', timeout: 20000 })

  // The GM panel mounts its own data on open (the entity list), so wait for the
  // chrome before driving it: a click that races the mount burns the whole test
  // budget and reports as "the button does not exist".
  await page.locator('.gm-toggle').click()
  await page.locator('.mode-tabs').waitFor({ state: 'visible', timeout: 20000 })
  // Prep holds the Places tree (Play shows the scene instead), and the palette is
  // reached the way it *lives*: from the universe entity's own editor.
  await page.locator('.mode-tabs button', { hasText: 'Prep' }).click()
  const row = page.locator('.entity-row.tree-row', { hasText: 'Earth' }).first()
  await row.waitFor({ state: 'visible', timeout: 20000 })
  await row.click()
  const tool = page.locator('.section-btn', { hasText: 'Universe Style' })
  await tool.waitFor({ state: 'visible', timeout: 20000 })
  if (process.env.PALETTE_SHOTS) {
    await page.screenshot({ path: `${process.env.PALETTE_SHOTS}/palette-entity.png` })
  }
  await tool.click()
  await expect(page.locator('.gp-root')).toBeVisible({ timeout: 20000 })
}

const cssVar = (page, name) =>
  page.evaluate((n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim(), name)

test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: 'ignoreErrors' })
})

test('the panel opens on the universe in play with its stored palette', async ({ page }) => {
  const problems = []
  page.on('pageerror', (e) => problems.push('uncaught: ' + String(e)))
  page.on('console', (m) => { if (m.type() === 'error' && /\[Vue warn\]/.test(m.text())) problems.push(m.text()) })

  const extras = {}
  await stubSave(page, extras)
  await openPanel(page)

  const stored = JSON.parse(earth.palette)
  // The same table the runtime would paint, shown as text in its own row.
  await expect(page.locator('.gp-row', { hasText: 'accent' }).first().locator('.gp-value'))
    .toHaveValue(stored.dark.accent)
  await expect(page.locator('.gp-row', { hasText: 'radius' }).locator('.gp-value')).toHaveValue(stored.radius)
  await expect(page.locator('.gp-row', { hasText: 'font.ui' }).locator('.gp-value')).toHaveValue(stored.font.ui)

  // Nothing unsaved yet, so nothing to save.
  await expect(page.locator('.gp-actions button', { hasText: 'Save' })).toBeDisabled()
  if (process.env.PALETTE_SHOTS) {
    await page.screenshot({ path: `${process.env.PALETTE_SHOTS}/palette-panel.png` })
  }
  expect(problems, problems.join('\n')).toEqual([])
})

test('editing previews on the chrome, and saving writes the cleaned palette', async ({ page }) => {
  const extras = {}
  await stubSave(page, extras)
  await openPanel(page)

  const stored = JSON.parse(earth.palette)
  const accentRow = page.locator('.gp-row', { hasText: 'accent' }).first().locator('.gp-value')
  await accentRow.fill('#ff0000')

  // Live preview: the chrome moves while the GM picks, through the one writer —
  // not by the panel touching a style itself.
  await expect.poll(() => cssVar(page, '--accent')).toBe('#ff0000')
  await expect(page.locator('.gp-actions button', { hasText: 'Save' })).toBeEnabled()

  await page.locator('.gp-actions button', { hasText: 'Save' }).click()
  await expect.poll(() => extras.saved?.palette).toBeTruthy()

  const saved = JSON.parse(extras.saved.palette)
  expect(extras.saved.id).toBe(earth.id)
  expect(saved.dark.accent).toBe('#ff0000')
  // Everything else it did not touch survives, and **no empty string is written**:
  // an omitted knob is how the runtime keeps the app's own value.
  expect(saved.light.accent).toBe(stored.light.accent)
  expect(saved.dark.bgPanelSolid).toBe(stored.dark.bgPanelSolid)
  expect(JSON.stringify(saved)).not.toContain('""')
  expect(Object.keys(saved)).not.toContain('')

  // Saved → the preview is released to the stored value (same outcome here, but
  // the panel must not keep claiming unsaved work).
  await expect(page.locator('.gp-actions button', { hasText: 'Save' })).toBeDisabled()
})

test('unsetting a knob drops it, and Clear empties the palette', async ({ page }) => {
  const extras = {}
  await stubSave(page, extras)
  await openPanel(page)

  const stored = JSON.parse(earth.palette)
  // "×" on a row means "use the app's own value for this knob".
  const accentRow = page.locator('.gp-row', { hasText: 'accent' }).first()
  await accentRow.locator('.gp-clear').click()
  await expect(accentRow.locator('.gp-value')).toHaveValue('')

  await page.locator('.gp-actions button', { hasText: 'Save' }).click()
  await expect.poll(() => extras.saved?.palette).toBeTruthy()
  const saved = JSON.parse(extras.saved.palette)
  expect(saved.dark.accent, 'an unset knob is absent, never empty').toBeUndefined()
  expect(saved.dark.bgDeep).toBe(stored.dark.bgDeep)

  // Clear is the resolver's "" — the universe goes back to the app's own look.
  await page.locator('.gp-actions button', { hasText: 'Clear' }).click()
  await expect.poll(() => extras.saved?.palette).toBe('')
  await expect(page.locator('.gp-root .gp-value').first()).toHaveValue('')
})

test('element CSS previews as a rule scoped to the universe', async ({ page }) => {
  const extras = {}
  await stubSave(page, extras)
  await openPanel(page)

  const css = 'background: linear-gradient(180deg, #ff0000, #0000ff); border-radius: 2px;'
  await page.locator('.gp-style', { hasText: 'Trait rows' }).locator('.gp-css').fill(css)

  // Preview, not save: the injected stylesheet is live while Save is still pending.
  const rule = await page.evaluate(() => {
    const sheet = document.getElementById('universe-style')?.sheet
    const r = sheet && [...sheet.cssRules].find((x) => x.selectorText?.includes('.trait-row'))
    return r ? { selector: r.selectorText, background: r.style.getPropertyValue('background-image'), radius: r.style.borderRadius } : null
  })
  // Scoped to the universe — which is also what outranks the component's own
  // scoped rules, so an ordinary declaration is enough.
  expect(rule?.selector).toBe('html[data-universe="earth"] .trait-row')
  expect(rule?.background).toContain('linear-gradient')
  expect(rule?.radius).toBe('2px')
  await expect(page.locator('.gp-actions button', { hasText: 'Save' })).toBeEnabled()

  // …and it lands in the saved palette, still as declarations.
  await page.locator('.gp-actions button', { hasText: 'Save' }).click()
  await expect.poll(() => extras.saved?.palette).toBeTruthy()
  expect(JSON.parse(extras.saved.palette).styles.traitRow).toBe(css)

  // Clearing the box takes the rule away with it.
  await page.locator('.gp-style', { hasText: 'Trait rows' }).locator('.gp-css').fill('')
  await expect.poll(async () => page.evaluate(() => {
    const sheet = document.getElementById('universe-style')?.sheet
    return sheet ? [...sheet.cssRules].some((x) => x.selectorText?.includes('.trait-row')) : false
  })).toBe(false)
})

test('the picker is the library, and its colour becomes a palette value', async ({ page }) => {
  const extras = {}
  await stubSave(page, extras)
  await openPanel(page)

  // It renders as a real component (a shadow root), not as an unknown element.
  await page.locator('.gp-row', { hasText: 'accent' }).first().locator('.gp-swatch').click()
  const picker = page.locator('hex-alpha-color-picker')
  await expect(picker).toBeVisible()
  expect(await picker.evaluate((el) => !!el.shadowRoot)).toBe(true)

  const accentValue = page.locator('.gp-row', { hasText: 'accent' }).first().locator('.gp-value')
  // Opaque: the palette stores hex. Translucent: it stores rgba, which is what the
  // surfaces already use — the picker's alpha byte is not lost.
  await picker.evaluate((el) => el.dispatchEvent(new CustomEvent('color-changed', { detail: { value: '#00ff00' }, bubbles: true })))
  await expect(accentValue).toHaveValue('#00ff00')
  await picker.evaluate((el) => el.dispatchEvent(new CustomEvent('color-changed', { detail: { value: '#00ff0080' }, bubbles: true })))
  await expect(accentValue).toHaveValue('rgba(0, 255, 0, 0.5)')
  // …and the live preview followed it.
  await expect.poll(() => cssVar(page, '--accent')).toBe('rgba(0, 255, 0, 0.5)')

  // The picker closes on the same control; typing in the field stays authoritative.
  await page.locator('.gp-row', { hasText: 'accent' }).first().locator('.gp-swatch').click()
  await expect(picker).toHaveCount(0)
  await expect(accentValue).toHaveValue('rgba(0, 255, 0, 0.5)')
})

test('an unreadable pair is flagged in the row it applies to', async ({ page }) => {
  const extras = {}
  await stubSave(page, extras)
  await openPanel(page)

  // Panel surface and text both near-white: the 3:1 floor is what an authored
  // palette can quietly break.
  await page.locator('.gp-row', { hasText: 'bgPanelSolid' }).first().locator('.gp-value').fill('#f4f1e2')
  await page.locator('.gp-row', { hasText: 'textDim' }).first().locator('.gp-value').fill('#f0efe8')

  const warned = page.locator('.gp-row.is-warn .gp-warn')
  await expect(warned.first()).toContainText('below the 3:1 floor')
  await expect(warned.first()).toContainText('bgPanelSolid')
})
