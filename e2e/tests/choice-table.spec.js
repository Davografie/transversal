// The choice table — one surface behind the roll-table menu, character creation,
// the consequence/hitch menus and a life-path step.
//
// What this spec is for: the surface's whole job is to render on every viewport
// the human named, and a wrong layout still *looks* like a layout. So the layout
// is asserted as measured fact — which cells exist, whether the legend is up,
// whether anything overflows — at all four viewports, plus the two gates that
// would otherwise fail silently: a locked row must say why ([[B190]]), and a
// condition must name its target through the shared resolver rather than
// printing an id (the defect that motivated the resolver).
//
// It drives the *real* app at Kael Drift's identity. The two paths that would
// write (creating a support character, resolving a life-path step) are stubbed
// at the network, so a test run cannot author anything — and the assertions are
// about what the surface sent, which is the thing under test anyway.

import { test, expect } from '@playwright/test'
import { gql, openSheet } from '../helpers/sheet.js'

const DESKTOP = { width: 1280, height: 950 }
const TABLET_LANDSCAPE = { width: 1194, height: 834 }
const TABLET_PORTRAIT = { width: 834, height: 1194 }
const PHONE_PORTRAIT = { width: 390, height: 844 }

const VIEWPORTS = [
  ['desktop landscape', DESKTOP, true],
  ['tablet landscape', TABLET_LANDSCAPE, true],
  ['tablet portrait', TABLET_PORTRAIT, true],
  ['phone portrait', PHONE_PORTRAIT, false],
]

// NEVER a real player character. Kael Drift is the project's testing character
// and the only CHARACTER an agent may act as; its owner is resolved by the
// agency relationship, not by name (the player has been renamed once already).
const KAEL = 'character-kael-drift-e555ccde'

let character
test.beforeAll(async ({ request }) => {
  const { players } = await gql(request, `query { players { id name agency { entityId main } } }`)
  const owner = players.find((p) => (p.agency || []).some((a) => a.entityId === KAEL && a.main))
  if (!owner) throw new Error(`no player mains ${KAEL} — cannot reach the testing character`)
  character = { playerId: owner.id, playerName: owner.name, entityId: KAEL }
})

/**
 * Stub the network paths that write, plus any response a case needs to control.
 *
 * `activeMains` is stubbed to name the testing character as *another* player's
 * main: the create-support entry point only appears when someone else has a main
 * on the table, and the alternative — waiting for a human player to log in — is
 * not a test.
 */
async function stub(page, { table = null, lifePaths = null, extras = {} } = {}) {
  await page.route('**/api/v1/graphql', async (route) => {
    const body = route.request().postData() || ''
    const reply = (data) => route.fulfill({
      status: 200, contentType: 'application/json', body: JSON.stringify({ data }),
    })

    if (body.includes('activeMains')) {
      return reply({
        activeMains: [{
          playerId: 'player-e2e-other',
          playerName: 'Another Player',
          main: {
            id: character.entityId, type: 'CHARACTER', name: 'Kael Drift',
            razmerit: 5, currentUniverse: 'earth', currentLocation: null, sheetPortrait: null,
          },
        }],
      })
    }
    // The two acts that would author something. Recorded, never performed.
    if (body.includes('createSupportCharacter')) {
      extras.created = JSON.parse(body).variables
      return reply({ createSupportCharacter: { id: 'character-e2e-made', type: 'GMC', name: 'Made Up', razmerit: 0 } })
    }
    if (body.includes('resolveStep(')) {
      extras.resolved = JSON.parse(body).variables
      return reply({ resolveStep: { done: true, applied: ['stubbed'], pendingChoices: [], mustered: false, mishapMuster: false, pendingTerm: null, scheduled: 0, error: null, tableId: 'rt-e2e', entryLabel: 'stub' } })
    }
    if (body.includes('startTerm(')) {
      return reply({ startTerm: { factionId: 'fac-e2e', pathId: 'lp-e2e', currentTableId: 'rt-e2e', continuation: [] } })
    }
    if (lifePaths && body.includes('lifePaths(')) return reply({ lifePaths })
    if (lifePaths && body.includes('pendingTerm')) {
      return reply({ entity: { pendingTerm: null } })
    }
    if (table && body.includes('rollTable(') && !body.includes('rollTables')) {
      return reply({ rollTable: table })
    }
    return route.continue()
  })
}

async function seed(page, size) {
  await page.setViewportSize(size)
  await openSheet(page, character)
  await page.waitForTimeout(600)
}

/** Settings → "create a support character" → the menu. The human's reference surface. */
async function openCreateSupport(page) {
  await page.locator('.sheet-pills button[title="Player settings"]').click({ timeout: 15_000 })
  await page.locator('.support-create-btn').first().click({ timeout: 15_000 })
  await page.locator('.rtm-root').waitFor({ state: 'visible', timeout: 15_000 })
  await page.locator('.ct-row').first().waitFor({ state: 'visible', timeout: 15_000 })
}

const measure = (page) => page.evaluate(() => {
  const root = document.querySelector('.rtm-root')
  const ct = document.querySelector('.ct-root')
  const head = document.querySelector('.ct-head')
  const row = document.querySelector('.ct-row')
  const key = document.querySelector('.ct-cell-key')
  const cost = document.querySelector('.ct-cost')
  const costBox = cost && cost.getBoundingClientRect()
  const rowBox = row && row.getBoundingClientRect()
  return {
    containerW: ct.clientWidth,
    head: head ? getComputedStyle(head).display : '(no legend)',
    key: key ? getComputedStyle(key).display : '(no key cell)',
    panelOverflowX: root.scrollWidth - root.clientWidth,
    pageOverflowX: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    rowW: rowBox && Math.round(rowBox.width),
    rowH: rowBox && Math.round(rowBox.height),
    costH: costBox && Math.round(costBox.height),
    costText: cost && cost.innerText,
    rows: document.querySelectorAll('.ct-row').length,
    pips: Array.from(document.querySelectorAll('.ct-pip')).map((e) => e.innerText),
  }
})

// ── the viewport contract ────────────────────────────────────────────────────

for (const [label, size, wide] of VIEWPORTS) {
  test(`the table renders and fits at ${label}`, async ({ page }) => {
    const problems = []
    page.on('pageerror', (e) => problems.push('uncaught: ' + String(e)))
    page.on('console', (m) => {
      if (m.type() === 'error' && /\[Vue warn\]/.test(m.text())) problems.push(m.text())
    })

    await stub(page)
    await seed(page, size)
    await openCreateSupport(page)

    const m = await measure(page)
    expect(m.rows, 'the live support-cast table has entries').toBeGreaterThan(0)
    // Nothing overflows its own panel or the page, at any width.
    expect(m.panelOverflowX, 'the panel does not scroll sideways').toBeLessThanOrEqual(0)
    expect(m.pageOverflowX, 'the page does not scroll sideways').toBeLessThanOrEqual(0)
    // Rows fill the surface rather than a fixed column width.
    expect(m.rowW).toBeGreaterThan(m.containerW - 2)

    if (wide) {
      // There is room: three columns, the legend up, the key cell present, and
      // the cost on one line beside the result.
      expect(m.containerW).toBeGreaterThanOrEqual(520)
      expect(m.head, 'the column legend is up where there is room').not.toBe('(no legend)')
      expect(m.head).not.toBe('none')
      expect(m.key).not.toBe('(no key cell)')
      expect(m.key).not.toBe('none')
      expect(m.costH, 'the cost is not squeezed onto two lines').toBeLessThan(24)
    } else {
      // A phone: the columns collapse, the legend would label nothing, and the
      // row still carries its key — that is what the dice found.
      expect(m.containerW).toBeLessThan(520)
      expect(m.head, 'the legend is hidden once the columns collapse').toBe('none')
      expect(m.key, 'the key survives the collapse').not.toBe('none')
    }

    expect(problems, problems.join('\n')).toEqual([])
  })
}

// ── the two gates that fail silently ────────────────────────────────────────

test('a row that cannot be taken says why, in the row', async ({ page }) => {
  // Five razmerit in hand, an entry that wants nine.
  await stub(page, {
    table: {
      id: 'rt-e2e', name: 'Costly Table', scheme: 'INDEX',
      entries: [
        { label: 'Cheap', description: 'affordable', minValue: null, maxValue: null, weight: null, tier: null, conditions: [], costEffects: [], effects: [] },
        { label: 'Priceless', description: 'not affordable', minValue: null, maxValue: null, weight: null, tier: null, conditions: [], costEffects: [{ type: 'transfer_razmerit', action: 'spend', target: 'self', entity: '', result: '9', dieFilter: '', negative: false, context: '', timing: '', duration: null, targetSpec: null, entitySpec: null, resultSpec: null, ownerSpec: null, refs: [], conditions: [] }], effects: [] },
      ],
    },
  })
  await seed(page, DESKTOP)
  await openCreateSupport(page)

  const locked = page.locator('.ct-row.is-locked')
  await expect(locked).toHaveCount(1)
  // The reason is *in the row* (B190) — not a tooltip, not a title attribute.
  await expect(locked).toContainText('needs 9 razmerit')
  await expect(locked).toBeDisabled()
  await expect(page.locator('.ct-row').first()).not.toHaveClass(/is-locked/)
})

test('a condition names its target through the one resolver', async ({ page }) => {
  // `trait-rel-tenure` is stamped `universes: ["earth"]`. The defect this
  // replaced read traits from the *path's* universe, so in a three_realms table
  // the row printed the raw id; the shared map is registry-wide, so the name is
  // there whatever universe the surface is rendering.
  await stub(page, {
    table: {
      id: 'rt-e2e', name: 'Gated Table', scheme: 'RANGE',
      entries: [
        { label: 'Veteran', description: 'only for the tenured', minValue: 1, maxValue: 3, weight: null, tier: null,
          conditions: [{ type: 'has_trait', subject: '', target: 'trait-rel-tenure', targets: [], value: null, operator: '>=', narrative: '' }],
          costEffects: [], effects: [] },
      ],
    },
  })
  await seed(page, DESKTOP)
  await openCreateSupport(page)

  const row = page.locator('.ct-row').first()
  await expect(row.locator('.ct-cond')).toHaveText('if has tenure')
  // And the key cell reads the scheme, not the row's position.
  await expect(row.locator('.ct-pip')).toHaveText('1–3')
  await expect(page.locator('.ct-head')).toContainText('Key')
})

// ── the two acts the surface reports, and the host resolves ─────────────────

test('picking a row reports it once, with the 1-based index the API takes', async ({ page }) => {
  const extras = {}
  await stub(page, { extras })
  await seed(page, DESKTOP)
  await openCreateSupport(page)

  await page.locator('.ct-row').nth(2).click()
  await expect(page.locator('.rtm-done-title')).toHaveText('Created')
  // The mutation — not the surface — is what ran, and it was handed the third
  // entry as `3`. (The menu's own contract is 1-based; `EntryPicker` has always
  // reported 0-based and the menu adds one, so this pins the seam.)
  expect(extras.created?.index).toBe(3)
  expect(extras.created?.tableId).toBeTruthy()
})

test('a life-path step is rolled into a row, then confirmed — a roll is not a pick', async ({ page }) => {
  const extras = {}
  await stub(page, {
    extras,
    // A path a faction offers, so a term can start at all (the fourth gate) —
    // and one nobody offers, so the gate has something to hold back.
    lifePaths: [
      { id: 'lp-e2e', name: 'Test Path', universe: 'earth', description: 'a path', entryTableId: 'rt-e2e', factionIds: ['fac-e2e'] },
      { id: 'lp-offered-by-nobody', name: 'Orphan Path', universe: 'earth', description: 'nobody offers this', entryTableId: 'rt-e2e', factionIds: [] },
    ],
    table: {
      id: 'rt-e2e', name: 'Term Table', universe: 'earth', lifePath: 'lp-e2e',
      scheme: 'INDEX', rollSource: 'FIXED_DIE', traitDiceCount: 0, die: 'D6',
      entries: [
        { label: 'Quiet year', description: 'nothing happens', minValue: null, maxValue: null, weight: null, tier: null, conditions: [], costEffects: [], effects: [] },
        { label: 'Hard year', description: 'it costs you', minValue: null, maxValue: null, weight: null, tier: null, conditions: [], costEffects: [], effects: [] },
      ],
    },
  })

  await seed(page, DESKTOP)
  await page.locator('.sheet-pills button').filter({ hasText: '🛤' }).click()
  await page.locator('.ct-row').first().waitFor({ state: 'visible', timeout: 15_000 })

  // Step one: the path list. The offering gate is visible and disabled with its
  // reason, not hidden.
  const orphan = page.locator('.ct-row.is-locked')
  await expect(orphan).toContainText('Orphan Path')
  await expect(orphan).toContainText('no offering faction')
  await expect(orphan).toBeDisabled()

  await page.locator('.ct-row').filter({ hasText: 'Test Path' }).click()
  await page.locator('.ct-row').first().waitFor({ state: 'visible', timeout: 15_000 })

  // Step two: the term's table. Nothing is taken until Continue, and Continue
  // refuses to do anything while no row has been found.
  const confirm = page.getByRole('button', { name: 'Continue' })
  await expect(confirm).toBeDisabled()
  await expect(page.locator('.ct-pip').first()).toHaveText('1')

  await page.locator('.ct-row').nth(1).click()
  await expect(confirm).toBeEnabled()
  await expect(page.locator('.ct-row').nth(1)).toHaveClass(/is-selected/)

  await confirm.click()
  await expect.poll(() => extras.resolved?.index).toBe(2)
})
