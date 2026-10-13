// The instances panel: one trait definition, every instance of it, and who owns each.
//
// The human: *"open a child panel from a trait that shows all the instances of that
// trait… I want to see who the trait belongs to (entity or projection from,
// relationship between who, sub-trait on which super-trait)… so batch edit trait
// instances."*
//
// **This spec does not write.** Every other assertion here is about a live
// campaign, and the panel's whole point is bulk writes over real instances, so the
// destructive half stops at the confirmation: the first click asks ("Really
// remove N?") and nothing is sent until that is answered. What that leaves
// unproven — that a bulk edit and a bulk remove actually land — is the backend
// suite's `test_trait_instance_hosts.py` (the host rules) and the resolver's own
// tests; this spec's job is that the panel is reachable, shows the four host kinds,
// fits, and cannot destroy anything by accident.
import { test, expect } from '@playwright/test'
import { gql } from '../helpers/sheet.js'
import { bootGmPanel, enterPrep } from '../helpers/gm.js'

const TEST_CHARACTER = 'character-kael-drift-e555ccde'
// `essence` is the heaviest definition in the live registry (547 instances, 544 of
// them on bodies), so it exercises the "projection from" host and a list long
// enough to matter. `distinctions` is the set that holds it.
const TRAIT = 'essence'

let character
test.beforeAll(async ({ request }) => {
  const { players } = await gql(request, `query { players { id name agency { entityId main } } }`)
  const owner = players.find((p) => (p.agency || []).some((a) => a.entityId === TEST_CHARACTER && a.main))
  if (!owner) throw new Error(`no player mains ${TEST_CHARACTER} — cannot reach the testing character`)
  character = { playerId: owner.id, playerName: owner.name, entityId: TEST_CHARACTER }
})

test('a trait opens its instances, each naming its host', async ({ page }) => {
  await bootGmPanel(page, character)
  // The authoring tools are Prep's; the panel opens on Play.
  await enterPrep(page)

  // Each opener adds one level to the chain, so the panels can be addressed by
  // depth — which matters here because the GM panel's own focus filter is also a
  // `.filter-input` (typing into that one filters the tree instead).
  const panelAt = (depth) => page.locator(`.panel-node[data-panel-depth="${depth}"]:visible`).last()

  // GM panel → traitsets → the set holding the trait → the trait → its instances.
  await page.getByRole('button', { name: /manage traits/i }).click()
  await page.waitForTimeout(1200)
  // The traitsets list searches set names *and* the names of the traits they hold.
  await panelAt(1).locator('input[placeholder="Search…"]').fill(TRAIT)
  await page.waitForTimeout(600)
  await panelAt(1).locator('.entity-name').first().click()
  await page.waitForTimeout(1200)
  await panelAt(2).locator('.entity-name', { hasText: new RegExp(`^${TRAIT}$`) }).first().click()
  await page.waitForTimeout(1200)

  await panelAt(3).getByRole('button', { name: /open instances/i }).click()
  await page.waitForTimeout(2500)

  const inst = panelAt(4).locator('.inst-panel')
  await expect(inst, 'the instances panel is open').toBeVisible({ timeout: 15_000 })

  // A child panel of the trait editor, titled for the trait.
  const title = await page.locator('.panel-title:visible', { hasText: /instances/i }).first().innerText()
  expect(title.toLowerCase()).toContain(TRAIT)

  // The summary counts the instances and says where they hang — the answer to
  // "who does this trait belong to", at a glance.
  const summary = await inst.locator('.inst-summary').innerText()
  const total = Number((summary.match(/\d+/) || [0])[0])
  expect(total, 'the trait has instances').toBeGreaterThan(0)

  const rows = inst.locator('.inst-row')
  expect(await rows.count(), 'every instance is a row').toBe(total)

  // The host is the row's headline, and it is one of the four kinds — with the
  // owner named (never the blank a missing lookup would leave). `innerText` is the
  // *rendered* text, and the badge is uppercased by CSS, so compare folded.
  const kinds = (await inst.locator('.host-kind').allInnerTexts()).map((k) => k.trim().toLowerCase())
  expect(new Set(kinds).size, 'the rows carry host kinds').toBeGreaterThan(0)
  for (const kind of new Set(kinds)) {
    expect(['entity', 'body', 'relationship', 'sub-trait']).toContain(kind)
  }
  const names = await inst.locator('.host-name').allInnerTexts()
  expect(names.length).toBe(total)
  expect(names.filter((n) => n.trim()).length, 'no row is hostless').toBe(total)

  // `essence` is held mostly by bodies, and a body's host is the entity it projects
  // FROM plus the universe — the half of the ask that only the server can answer.
  expect(kinds, 'the heaviest trait is body-held').toContain('body')
  const details = await inst.locator('.host-detail').allInnerTexts()
  expect(details.some((d) => /^in /.test(d)), 'a body says which universe it stands in').toBe(true)

  // Nothing scrolls sideways (the panel is ~440px and the rows are long).
  const widths = await page.evaluate(() => {
    const body = document.querySelector('.inst-panel')?.closest('.panel-body')
    return body ? [body.scrollWidth, body.clientWidth] : null
  })
  expect(widths, 'the panel body exists').not.toBeNull()
  expect(widths[0], 'the instances panel does not scroll horizontally').toBeLessThanOrEqual(widths[1] + 1)

  // The filter bar is what makes 547 rows usable: each control is present, and a
  // filter narrows the list rather than re-fetching it.
  await expect(inst.locator('input.filter-input')).toBeVisible()
  for (const label of ['Body', 'Sub-trait', 'Relationship', 'Entity']) {
    await expect(inst.locator('select', { has: page.locator(`option:text-is("${label}")`) }).first()).toBeVisible()
  }
  await inst.locator('select').first().selectOption('Entity')
  await page.waitForTimeout(300)
  const filtered = await inst.locator('.inst-row').count()
  expect(filtered, 'filtering to entities narrows the list').toBeLessThan(total)
  expect(filtered, 'and leaves the ones it kept').toBeGreaterThan(0)
  await inst.locator('select').first().selectOption('')
  await page.waitForTimeout(300)
  await expect(rows).toHaveCount(total)

  // Select all matching, then stop at the confirmation: the removal is two-step,
  // and answering the first step must not have sent anything.
  await inst.getByRole('button', { name: /all matching/i }).click()
  await page.waitForTimeout(300)
  await expect(inst.locator('.selected-count')).toHaveText(`${total} selected`)

  await inst.getByRole('button', { name: /remove \d+ selected/i }).click()
  await page.waitForTimeout(300)
  await expect(inst.getByRole('button', { name: /really remove \d+\?/i }), 'the second step is asked').toBeVisible()

  const stillThere = await inst.locator('.inst-summary').innerText()
  expect(Number((stillThere.match(/\d+/) || [0])[0]), 'asking is not doing').toBe(total)
})
