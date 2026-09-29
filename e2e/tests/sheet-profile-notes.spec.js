import { test, expect } from '@playwright/test'
import { gql } from '../helpers/sheet.js'
import { establishSession } from '../helpers/session.js'

// A trait with **notes but no statement** shows its full notes on the profile
// page (2026-09-25, the human's ask). The traits tab is deliberately left alone:
// it is a dense list of lines, and a paragraph per trait is a different question
// — the row's `showNotes` prop is what the host uses to choose, and only the
// profile list sets it.
//
// Why it matters: on the profile page a trait with no statement rendered as its
// **bare name**. Measured on `gmc-44623820` ("Mr. 1"), the `Appearance` chip showed
// one word while four lines of description sat one click away in the detail.
//
// The subjects are *discovered* rather than pinned: these are GMC traits whose
// notes are content, so an author editing one would break a hard-coded id for a
// reason that has nothing to do with this rule.

/**
 * GMCs carrying the shapes this rule is about: a profile trait with notes and no
 * statement, one with both, and — best of all — a sheet with **both kinds**, since
 * that single page can prove the notes render *and* that a statement suppresses
 * them, rather than passing vacuously on a build that renders no notes at all.
 */
async function findProfileGmcs(request) {
  const { entities } = await gql(request, `query { entities(type: GMC) { id } }`)
  const ids = (entities || []).map((e) => e.id)
  let notesOnly = null
  let both = null
  let mixed = null
  for (let i = 0; i < ids.length && !(notesOnly && both && mixed); i += 25) {
    const chunk = ids.slice(i, i + 25)
    const query = `query { ${chunk.map((id, n) =>
      `e${n}: entity(id: "${id}") { id traitSettings { traitsetTab statement notes } }`).join(' ')} }`
    const data = await gql(request, query)
    for (const v of Object.values(data || {})) {
      if (!v) continue
      const profile = (v.traitSettings || []).filter((s) => s.traitsetTab === 'PROFILE')
      const described = profile.some((s) => !s.statement && s.notes)
      const stated = profile.some((s) => s.statement && s.notes)
      if (!notesOnly && described) notesOnly = v.id
      if (!both && stated) both = v.id
      if (!mixed && described && stated) mixed = v.id
    }
  }
  return { notesOnly, both, mixed }
}

async function openProfile(page, entityId) {
  await page.setViewportSize({ width: 1280, height: 950 })
  await page.goto('/')
  await page.evaluate((id) => {
    localStorage.setItem('playerId', 'player-75a410')
    localStorage.setItem('playerName', 'DSH MCP')
    localStorage.setItem('entityId', id)
  }, entityId)
  await establishSession(page)
  await page.goto('/')
  await page.waitForTimeout(2500)
  const dot = page.locator('button.map-dot.self').first()
  if (await dot.count()) { await dot.click().catch(() => {}); await page.waitForTimeout(1000) }
  await page.waitForFunction(() => !!document.querySelector('.sheet-embedded .header'), null, { timeout: 20_000 })
}

/** Open the profile tab and read the trait rows as the reader sees them. */
async function profileRows(page, tab = '👤') {
  await page.locator('.sheet-embedded button.pill', { hasText: tab }).first().click()
  await page.waitForTimeout(700)
  return page.evaluate(() => [...document.querySelectorAll('.sheet-embedded .trait-row')].map((r) => ({
    name: r.querySelector('.trait-name')?.innerText.trim(),
    statement: r.querySelector('.trait-statement')?.innerText.trim() || null,
    notes: r.querySelector('.trait-notes')?.innerText.trim() || null,
    // The markdown has to arrive *rendered*, which is what the `:deep()` selectors
    // in the component depend on: `v-html` tags carry no scope attribute.
    notesHtml: r.querySelector('.trait-notes')?.innerHTML || null,
  })))
}

test('a notes-only profile trait shows its full notes, and the traits tab does not', async ({ page, request }) => {
  const { notesOnly, mixed } = await findProfileGmcs(request)
  const subject = mixed || notesOnly
  test.skip(!subject, 'no GMC in this data has a profile trait with notes and no statement')

  await openProfile(page, subject)
  const profile = await profileRows(page)
  const described = profile.filter((r) => r.notes)
  expect(described.length, 'the notes-only traits show their notes').toBeGreaterThan(0)
  // Full notes, not a preview: the row's text is the whole note.
  expect(described.every((r) => r.notes.length > 10)).toBe(true)
  // …and rendered as markdown, so the block markup is real elements.
  expect(described.some((r) => /<(p|ul|ol|strong|em)\b/.test(r.notesHtml))).toBe(true)
  // The rule is a conjunction: notes only where there is no statement.
  expect(profile.filter((r) => r.notes && r.statement), 'never both at once').toEqual([])

  const traits = await profileRows(page, '🎲')
  expect(traits.filter((r) => r.notes).length, 'the traits tab is unchanged').toBe(0)
})

test('a statement still wins over the notes', async ({ page, request }) => {
  const { both, mixed } = await findProfileGmcs(request)
  const subject = mixed || both
  test.skip(!subject, 'no GMC in this data has a profile trait with both a statement and notes')

  // Assert the data really has the shape. Without this the test passes vacuously
  // against a build that renders no notes at all — which is exactly what it did
  // before this check was added.
  const { entity } = await gql(request, `query($id: ID!) {
    entity(id: $id) { traitSettings { traitsetTab statement notes } }
  }`, { id: subject })
  const profileData = (entity.traitSettings || []).filter((s) => s.traitsetTab === 'PROFILE')
  expect(profileData.filter((s) => s.statement && s.notes).length, 'this sheet has traits carrying both').toBeGreaterThan(0)

  await openProfile(page, subject)
  const profile = await profileRows(page)
  expect(profile.filter((r) => r.statement).length, 'and it shows the statements').toBeGreaterThan(0)
  expect(profile.filter((r) => r.statement && r.notes), 'but not their notes').toEqual([])
  // Non-vacuous only where the same sheet also has a notes-only trait to render:
  // that is what shows the suppression is a decision, not an absence.
  if (mixed) {
    expect(profile.filter((r) => r.notes).length, 'the same sheet still renders notes where they belong').toBeGreaterThan(0)
  }
})
