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
import { gql } from '../helpers/sheet.js'
import { asPlayer } from '../helpers/role.js'
import { establishSession } from '../helpers/session.js'

const DESKTOP = { width: 1280, height: 950 }

// The human's four viewport modes, plus the one width that reaches the surface's
// middle layout. `layout` is the *state under test*, not a restatement of the
// viewport: the surface is responsive to its own container, and the container is
// the modal's `min(560px, 96vw)`.
const VIEWPORTS = [
  ['desktop landscape', { width: 1280, height: 950 }, 'table', false],
  ['tablet landscape', { width: 1194, height: 834 }, 'table', false],
  ['tablet portrait', { width: 834, height: 1194 }, 'table', false],
  ['phone portrait', { width: 390, height: 844 }, 'stack', true],
  ['a 500px window (two columns)', { width: 500, height: 900 }, 'columns', true],
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
      // The checkpoint is *the server's* — it persists, and it is what the wizard
      // resumes from. Modelling it here is not a detail: the sheet re-reads the
      // entity when the step advances, and a remount that finds no `pendingTerm`
      // legitimately falls back to the path list. A stub that always answered
      // `null` was lying about the contract, and the symptom looked exactly like
      // the app losing the term.
      extras.pendingTerm = { factionId: 'fac-e2e', pathId: 'lp-e2e', currentTableId: 'rt-e2e', continuation: [] }
      return reply({ startTerm: extras.pendingTerm })
    }
    if (lifePaths && body.includes('lifePaths(')) return reply({ lifePaths })
    if (lifePaths && body.includes('pendingTerm')) {
      return reply({ entity: { pendingTerm: extras.pendingTerm ?? null } })
    }
    if (table && body.includes('rollTable(') && !body.includes('rollTables')) {
      return reply({ rollTable: table })
    }
    return route.continue()
  })
}

/**
 * Focus a band in the mobile stack by tapping it, as a reader does.
 *
 * A raw mouse click, not `locator.click()`: a band is a *container* whose
 * top-left corner is covered by one of its own children (the `.band-tap` capture
 * layer at every focus but its own), so Playwright's actionability check sees an
 * intercepted click and retries forever. A finger does not care which descendant
 * is on top — the tap bubbles — so the test should not either. Same recipe as
 * `sfx-rail.spec.js`; it is why the phone case below can reach the sheet's header
 * at all.
 */
async function focusBand(page, bandClass) {
  const y = await page.evaluate((sel) => {
    const r = document.querySelector(sel).getBoundingClientRect()
    return Math.round(r.y + 6)
  }, `.${bandClass}`)
  await page.mouse.click(6, y)
  await page.waitForTimeout(700)
}

/**
 * Seed identity and open the sheet at `size` — the sheet is where the settings
 * overlay (and the surface under test) is entered from.
 *
 * Below the 820px breakpoint the sheet rides in the three-band stack, so the
 * sheet band has to be focused before anything inside its header can be clicked;
 * left alone, the stack opens on the location band and the roller band's
 * `.band-tap` teaser sits over the pill.
 */
async function seed(page, size, { stack = false, alreadySeeded = false } = {}) {
  // Pin the role in the browser: the app turns a stored `architect` into GM
  // free-roam (and PATCHes the role back), so a spec that depends on the shared
  // fixture's role is at the mercy of whatever ran before it — and a GM's own
  // sheet renders no ↩ settings button, which is what nine cases here hit.
  // Idempotent: this spec re-seeds inside one test, and registering the same
  // route twice leaves the shadowed handler trying to fulfil a request it no
  // longer owns — the identity fetch is aborted, `ensurePlayer` reads that as a
  // stale id and clears `playerId`, and the login overlay comes back up.
  await page.unroute('**/api/v1/players/**')
  await asPlayer(page)
  await page.setViewportSize(size)
  if (!alreadySeeded) {
    await page.goto('/')
    await page.evaluate(([pid, pname, eid]) => {
      localStorage.setItem('playerId', pid)
      localStorage.setItem('playerName', pname)
      localStorage.setItem('entityId', eid)
    }, [character.playerId, character.playerName, character.entityId])
  await establishSession(page)
  }
  await page.goto('/')

  // The identity overlay (`.name-entry.panel`) is up on the first load — there is
  // no player yet — and it covers the map, so anything clicked through it is
  // intercepted. It comes down once the seeded identity resolves; wait for that
  // rather than racing a `visible` map dot that is visible *behind* it.
  await page.locator('.name-entry.panel').first().waitFor({ state: 'hidden', timeout: 20_000 })

  const sheet = page.locator('.sheet-embedded').first()
  // Docked, the sheet is already up and there is nothing to click; in the
  // portrait and phone layouts it has to be opened from the self dot.
  if (!(await sheet.isVisible())) {
    // The dot also fades in and the camera settles after it, so it is briefly
    // "not stable" and a plain click retries against a moving target — measured
    // as a whole-test timeout at 834×1194, a race rather than a fault. Poll its
    // box until two reads agree, then click.
    const self = page.locator('button.map-dot.self').first()
    await self.waitFor({ state: 'visible', timeout: 20_000 })
    let last = null
    await expect.poll(async () => {
      const b = await self.boundingBox()
      const key = b && `${Math.round(b.x)},${Math.round(b.y)}`
      const settled = !!key && key === last
      last = key
      return settled
    }, { timeout: 15_000, intervals: [150, 150, 150, 250] }).toBe(true)
    await self.click()
  }
  await sheet.waitFor({ state: 'visible', timeout: 20_000 })

  if (stack) {
    await focusBand(page, 'sheet-band')
    await expect(page.locator('.stage')).toHaveClass(/focus-sheet/)
  }
}

/**
 * Re-enter the app *once* with the identity already seeded.
 *
 * `seed()` navigates twice — the first load is what makes setting localStorage
 * take effect. That is fine for a first entry, but a second `seed()` inside one
 * test races the app: the first of its two loads starts `GET /players/{id}`,
 * the second navigation aborts it, and `usePlayerIdentity`'s `fetchPlayer`
 * returns null for an aborted fetch — which `ensurePlayer` reads as *"stale
 * id"* and answers by deleting `playerId` from localStorage. The next load then
 * has no identity at all and the login overlay comes up.
 *
 * That the app treats a *failed* fetch as a stale id is its own problem
 * (reported, not patched here); what a re-entry needs is simply one load.
 */
async function reseed(page) {
  await seed(page, DESKTOP, { alreadySeeded: true })
}

/** Settings → "create a support character" → the menu (the human's reference surface). */
async function openCreateSupport(page) {
  // The ↩ settings button is a *sibling* of `.sheet-pills`, not a child: the tab
  // row became a horizontal scroller (the phone-landscape dock is ~179px of
  // sheet, and wrapping the tabs inside the group's rounded border stopped it
  // reading as a group), so the ↩ was deliberately left outside to stay pinned
  // rather than scroll away. This selector used to be
  // `.sheet-pills button[title="Player settings"]`, which after that change could
  // never match — which is what made nine cases in this spec red.
  await page.locator('.sheet-embedded button[title="Player settings"]').first().click({ timeout: 15_000 })
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
  const label = document.querySelector('.ct-label')
  const costBox = cost && cost.getBoundingClientRect()
  const labelBox = label && label.getBoundingClientRect()
  const rowBox = row && row.getBoundingClientRect()
  const keyBox = key && key.getBoundingClientRect()
  return {
    containerW: ct.clientWidth,
    head: head ? getComputedStyle(head).display : '(no legend)',
    key: key ? getComputedStyle(key).display : '(no key cell)',
    panelOverflowX: root.scrollWidth - root.clientWidth,
    pageOverflowX: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    rowW: rowBox && Math.round(rowBox.width),
    rowH: rowBox && Math.round(rowBox.height),
    costH: costBox && Math.round(costBox.height),
    // Is the price beside the result (same line) or wrapped under it?
    costBelowLabel: !!(costBox && labelBox) && costBox.top >= labelBox.bottom - 1,
    // The key is a *corner chip*, not a column: it shares the label's first line
    // at every width and sits at the content's right edge. Its failure mode is
    // silent — the row simply gets a line taller, which reads as "these rows are
    // a bit roomy" rather than as a bug. It cost 28px per row at the dock's
    // ~290px before this was pinned.
    keyOnLabelLine: !!(keyBox && labelBox) && Math.abs(keyBox.top - labelBox.top) <= 2,
    keyAtContentRight: !!(keyBox && labelBox) && Math.abs(labelBox.right - keyBox.right) <= 1,
    costText: cost && cost.innerText,
    rows: document.querySelectorAll('.ct-row').length,
    pips: Array.from(document.querySelectorAll('.ct-pip')).map((e) => e.innerText),
  }
})

// ── the viewport contract ────────────────────────────────────────────────────
//
// All three layouts the surface has, not just the ones the four named viewports
// happen to produce: the modal is `min(560px, 96vw)`, so 834-wide portrait and
// 1280-wide desktop give it the *same* 534px and only ever exercise the widest
// state. The middle state (two columns, the price wrapped under the result) is
// therefore driven by a viewport that lands the container in that band — it is a
// real state of the component, and an unasserted one is an untested one.

for (const [label, size, layout, stack] of VIEWPORTS) {
  test(`the table renders and fits at ${label}`, async ({ page }) => {
    const problems = []
    page.on('pageerror', (e) => problems.push('uncaught: ' + String(e)))
    page.on('console', (m) => {
      if (m.type() === 'error' && /\[Vue warn\]/.test(m.text())) problems.push(m.text())
    })

    await stub(page)
    await seed(page, size, { stack })
    await openCreateSupport(page)

    const m = await measure(page)
    expect(m.rows, 'the live support-cast table has entries').toBeGreaterThan(0)
    // Nothing overflows its own panel or the page, at any width.
    expect(m.panelOverflowX, 'the panel does not scroll sideways').toBeLessThanOrEqual(0)
    expect(m.pageOverflowX, 'the page does not scroll sideways').toBeLessThanOrEqual(0)
    // Rows fill the surface rather than a fixed column width.
    expect(m.rowW).toBeGreaterThan(m.containerW - 2)

    // The key is a corner chip in the content at *every* width — it shares the
    // label's first line and sits at the content's right edge. This is the
    // compaction contract: if it ever claims a line of its own again, each row
    // silently grows by ~28px (measured at the dock's ~290px).
    expect(m.keyOnLabelLine, 'the key shares the label\'s first line').toBe(true)
    expect(m.keyAtContentRight, 'the key sits at the content\'s right edge').toBe(true)

    if (layout === 'table') {
      // There is room: the legend is up, the key present, and the cost on one
      // line *beside* the result.
      expect(m.containerW).toBeGreaterThanOrEqual(520)
      expect(m.head, 'the column legend is up where there is room').not.toBe('(no legend)')
      expect(m.head).not.toBe('none')
      expect(m.key).not.toBe('(no key cell)')
      expect(m.key).not.toBe('none')
      expect(m.costH, 'the cost is not squeezed onto two lines').toBeLessThan(24)
      expect(m.costBelowLabel, 'the cost sits beside the result, not under it').toBe(false)
    } else if (layout === 'columns') {
      // The cost has wrapped under the result, and the legend has gone with the
      // second column it labelled.
      expect(m.containerW).toBeLessThan(520)
      expect(m.containerW).toBeGreaterThan(340)
      expect(m.head, 'the legend leaves with the columns').toBe('none')
      expect(m.key, 'the key survives').not.toBe('none')
      expect(m.costBelowLabel, 'the cost wraps under the result').toBe(true)
    } else {
      // A phone: one column, and the row still carries its key in the corner —
      // that is what the dice found, and it is the moment the row matters most.
      expect(m.containerW).toBeLessThanOrEqual(340)
      expect(m.head, 'the legend is hidden once the columns collapse').toBe('none')
      expect(m.key, 'the key survives the collapse').not.toBe('none')
      expect(m.costBelowLabel, 'the cost wraps under the result').toBe(true)
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

test('the 🎲 marks a row; the click takes it — there is no confirm', async ({ page }) => {
  const extras = {}
  const three = ['Alpha', 'Beta', 'Gamma'].map((label) => ({
    label, description: `${label} archetype`, minValue: null, maxValue: null,
    weight: null, tier: null, conditions: [], costEffects: [], effects: [],
  }))
  await stub(page, {
    extras,
    table: { id: 'rt-e2e', name: 'Three Things', scheme: 'INDEX', die: 'D6', entries: three },
  })
  await seed(page, DESKTOP)
  await openCreateSupport(page)

  // No confirm anywhere: taking a row is the click and nothing else.
  const actions = page.locator('.ct-actions')
  await expect(actions.getByRole('button', { name: /continue|confirm/i })).toHaveCount(0)

  const roll = actions.getByRole('button', { name: /roll/i })

  // Roll: a row is **marked**, and nothing is taken — the menu is still on the
  // list, and no mutation has run.
  await roll.click()
  const marked = page.locator('.ct-row.is-rolled')
  await expect(marked).toHaveCount(1)
  await expect(page.locator('.rtm-done-title')).toHaveCount(0)
  expect(extras.created).toBeUndefined()
  const markedIndex = await page.locator('.ct-row').evaluateAll(
    (rows) => rows.findIndex((r) => r.classList.contains('is-rolled')),
  )
  expect(markedIndex, 'a row was marked').toBeGreaterThanOrEqual(0)

  // Clicking *that* row takes it, at the index the dice found.
  await marked.click()
  await expect(page.locator('.rtm-done-title')).toHaveText('Created')
  expect(extras.created?.index).toBe(markedIndex + 1)

  // And the other half of the same rule: a roll never locks the choice in, so a
  // click on a *different* row takes that one instead.
  await reseed(page)
  await openCreateSupport(page)
  await page.locator('.ct-actions').getByRole('button', { name: /roll/i }).click()
  const other = await page.locator('.ct-row').evaluateAll(
    (rows) => rows.findIndex((r) => !r.classList.contains('is-rolled')),
  )
  const markedAgain = await page.locator('.ct-row').evaluateAll(
    (rows) => rows.findIndex((r) => r.classList.contains('is-rolled')),
  )
  expect(other).not.toBe(markedAgain)
  await page.locator('.ct-row').nth(other).click()
  await expect.poll(() => extras.created?.index).toBe(other + 1)
})

test('a life-path step is taken by the click, and the roll only marks it', async ({ page }) => {
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

  // A path is taken by the click — no confirm, and the indexed scheme shows its
  // keys rather than a range.
  await page.locator('.ct-row').filter({ hasText: 'Test Path' }).click()
  // The *phase label* is what says the step changed: the path list's rows are
  // still on screen for a moment after the click, so waiting for "a row exists"
  // would race the transition and then click the orphan path by index.
  await expect(page.locator('.wiz-phase-label')).toBeVisible({ timeout: 15_000 })
  await expect(page.locator('.ct-pip').first()).toHaveText('1')
  await expect(page.locator('.ct-actions').getByRole('button', { name: /continue|confirm/i })).toHaveCount(0)

  // Step two: the term's table. Nothing has been resolved by arriving, and the
  // step advances on the row the player clicks — as `2` for the second row.
  expect(extras.resolved).toBeUndefined()
  await page.locator('.ct-row').nth(1).click()
  await expect.poll(() => extras.resolved?.index).toBe(2)
})
