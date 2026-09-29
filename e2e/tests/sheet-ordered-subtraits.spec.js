import { test, expect } from '@playwright/test'
import { gql } from '../helpers/sheet.js'
import { establishSession } from '../helpers/session.js'

// An **ordered** container's contents render as a numbered list with disabled
// entries visible (B186, the human's ask: *"Challenge trait subtraits should work
// like portents: ordered list with disabled entries"*).
//
// Two rules, and each fails on its own:
//
//   - the shape comes from the author's **`ordered` tag** on the container, not
//     from `order` happening to be set. `order` is optional and almost nothing
//     carries one (11 of 926 live sub-trait settings, all portents), so inferring
//     the shape from it would let stray data entry re-lay-out a container.
//   - within an ordered container the rows stack in **one column**, numbered by
//     `order`, instead of packing as right-ended chips — which put a narrow first
//     step further right than the steps after it (measured on the live portents:
//     first entry x=361, the rest x=292) and made the run unreadable as a
//     sequence.
//
// The fixtures are **discovered**, not pinned: which container is ordered is
// content, and an author marking another one (or retiring this one) would break a
// hard-coded id for a reason that has nothing to do with the rule.

/** Everything the assertions need, read once per entity list. */
const SCAN = `
  id name
  traitSettings {
    id name traitsetName ratingType capacity enabled tags registryTags
    subTraitSettings { id order enabled ratingType capacity statement }
  }
`

/** Containers of one entity type matching `match(s, tags)`. One request. */
async function findContainers(request, type, match) {
  const { entities } = await gql(request, `query { entities(type: ${type}) { ${SCAN} } }`)
  const hits = []
  for (const e of entities || []) {
    for (const s of e.traitSettings || []) {
      const tags = [...(s.tags || []), ...(s.registryTags || [])]
      if (match(s, tags)) hits.push({ entityId: e.id, entityName: e.name, container: s })
    }
  }
  return hits
}

/** The authored sequence: `order` ascending, unordered children after it, stable. */
function authoredOrder(children) {
  return children
    .map((c, i) => ({ c, i }))
    .sort((a, b) => {
      const ao = typeof a.c.order === 'number' ? a.c.order : Number.MAX_SAFE_INTEGER
      const bo = typeof b.c.order === 'number' ? b.c.order : Number.MAX_SAFE_INTEGER
      return (ao - bo) || (a.i - b.i)
    })
    .map((e) => e.c)
}

/** Open the entity's sheet in the dock, as the testing identity. */
async function openSheet(page, entityId) {
  await page.setViewportSize({ width: 1280, height: 950 })
  await page.goto('/')
  await page.evaluate((id) => {
    localStorage.setItem('playerId', 'player-75a410')
    localStorage.setItem('playerName', 'DSH MCP')
    localStorage.setItem('entityId', id)
  }, entityId)
  await establishSession(page)
  await page.goto('/')
  await page.waitForTimeout(2000)
  const dot = page.locator('button.map-dot.self').first()
  if (await dot.count()) { await dot.click().catch(() => {}); await page.waitForTimeout(800) }
  await page.waitForFunction(() => !!document.querySelector('.sheet-embedded .header'), null, { timeout: 20_000 })
  await page.waitForTimeout(500)
}

/**
 * Reveal the container's row. A sheet holding more than a dozen traits opens on
 * the **set layer**, which renders no rows at all until its set is opened — the
 * accordion's `set-toggle` where there is height for it, the drill-in's header
 * where there is not. Without this the spec only worked on a flat sheet.
 */
async function revealRow(page, containerId, traitsetName) {
  if (await page.locator(`[data-ts-id="${containerId}"]`).count()) return
  const toggle = page.locator('.set-toggle', { hasText: traitsetName }).first()
  if (await toggle.count()) await toggle.click()
  else {
    const header = page.locator('h4.set-header-link', { hasText: traitsetName }).first()
    if (await header.count()) await header.click()
  }
  await page.waitForTimeout(600)
}

/** Expand the container and read its contents as the reader sees them. */
async function readContainer(page, container) {
  await revealRow(page, container.id, container.traitsetName)
  const row = page.locator(`.trait-row[data-ts-id="${container.id}"]`).first()
  await row.scrollIntoViewIfNeeded()
  const toggle = row.locator('.container-toggle button')
  expect(await toggle.count(), 'the container renders a disclosure').toBeGreaterThan(0)
  await toggle.first().click()
  await page.waitForTimeout(600)

  const node = page.locator('.trait-node', { has: page.locator(`.trait-row[data-ts-id="${container.id}"]`) }).first()
  const handle = await node.elementHandle()
  return handle.evaluate((n) => {
    const list = n.querySelector(':scope > .sub-trait-list')
    const rows = [...(list ? list.querySelectorAll(':scope > .trait-node > .sub-trait-row') : [])]
    return {
      listClasses: list ? [...list.classList] : null,
      containerGhosts: n.querySelectorAll(':scope > .trait-row .trait-die-icon.ghost').length,
      rows: rows.map((r) => ({
        tsId: r.dataset.tsId,
        number: r.querySelector('.sub-trait-order')?.textContent.trim() ?? null,
        disabledBadge: !!r.querySelector('.trait-disabled-badge'),
        left: Math.round(r.getBoundingClientRect().left),
        overflow: r.scrollWidth - r.clientWidth,
      })),
    }
  })
}

test('an ordered container renders a numbered, single-column list with disabled entries visible', async ({ page, request }) => {
  const hits = await findContainers(request, 'FACTION', (s, tags) =>
    tags.includes('ordered') && (s.subTraitSettings || []).length >= 2)
  // Prefer the fixture that also carries a *disabled* entry: without one the
  // badge half of this test would pass on a build that marks nothing.
  const fixture = hits.find((h) => h.container.subTraitSettings.some((c) => c.enabled === false)) || hits[0]
  test.skip(!fixture, 'no container in this data carries the `ordered` tag with sub-traits to render')

  const { entityId, container } = fixture
  const children = container.subTraitSettings
  const expected = authoredOrder(children)

  // Assert the data really has the shape first, so the DOM assertions below
  // cannot pass vacuously.
  expect(children.some((c) => c.enabled === false), `${entityId}: the fixture has a disabled child`).toBe(true)
  expect(expected.every((c) => typeof c.order === 'number'), `${entityId}: every child carries an order`).toBe(true)

  await openSheet(page, entityId)
  const dom = await readContainer(page, container)

  expect(dom.listClasses, 'the container renders its contents as a list').toContain('ordered')

  // The authored sequence, in the authored order — computed here rather than
  // imported, so a change to the sheet's own sort shows up as a failure instead
  // of agreeing with itself.
  expect(dom.rows.map((r) => r.tsId), 'rows render in `order`').toEqual(expected.map((c) => c.id))
  expect(dom.rows.map((r) => r.number), 'and each states its own `order`')
    .toEqual(expected.map((c) => String(c.order)))

  // One column: the chip layout's right-packing is what this replaces, and it
  // showed up as rows sharing a right edge but not a left one.
  const lefts = [...new Set(dom.rows.map((r) => r.left))]
  expect(lefts.length, `rows share one left edge (saw ${lefts.join(', ')})`).toBe(1)
  expect(dom.rows.every((r) => r.overflow <= 0), 'no row overflows its column').toBe(true)

  // Disabled is *stated*, not left to the dimming — the reader cannot tell
  // "not yet, it is the next step" from "spent" otherwise.
  const disabledIds = new Set(children.filter((c) => c.enabled === false).map((c) => c.id))
  expect(dom.rows.filter((r) => r.disabledBadge).map((r) => r.tsId).sort())
    .toEqual([...disabledIds].sort())

  // And a challenge container keeps its track: the portents agenda used to draw
  // nothing at all, so its four capacity slots were invisible.
  if ((container.capacity || []).length) {
    expect(dom.containerGhosts, 'the challenge container draws its unfilled track').toBe(container.capacity.length)
  }
})

test('an untagged container still renders its contents as chips', async ({ page, request }) => {
  // The rule is scoped to the tagged container: the chip layout is the convention
  // for every other container, and a number lane there would be new chrome. This
  // is the half a static check cannot hold — `isOrdered` can be right while the
  // component keys off the wrong thing.
  const hits = await findContainers(request, 'GMC', (s, tags) =>
    tags.includes('container') && !tags.includes('ordered') && (s.subTraitSettings || []).length > 0)
  test.skip(!hits.length, 'no untagged container with live contents to check')

  const { entityId, container } = hits[0]
  await openSheet(page, entityId)
  const dom = await readContainer(page, container)
  expect(dom.listClasses, 'an untagged container keeps the chip layout').not.toContain('ordered')
  expect(dom.rows.length, 'and still shows its contents').toBeGreaterThan(0)
  expect(dom.rows.some((r) => r.number), 'with no number lane').toBe(false)
})
