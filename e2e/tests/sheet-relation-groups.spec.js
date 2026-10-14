// A relationship states whom it concerns **as a header**, with its traits under it.
//
// The author, after finding that one of `character-20809`'s two Ælor Cıtar traits
// showed no relationship at all (2026-09-29): *"the UI is confusing. Let's have the
// relationship stating to whom it concerns as a header and the traits grouped under
// it."*
//
// What it replaced stated the contact once per run **on the row**, and which row
// that was came from an order nothing pinned — `sortSetTraits` is a stable sort on
// rank alone, so the tiebreak is the order the API returned, and within one edge
// that order is not defined. So a trait could lose its visible relationship with no
// data change at all, and did. A header per group cannot move.
//
// Asserted against the live world rather than a stub: the fixture is the project's
// testing character (see AGENTS.md), and the expectations are read from the API in
// the same run, so this cannot pass by hard-coding today's content.

import { test, expect } from '@playwright/test'
import { asPlayer } from '../helpers/role.js'
import { findPlayableCharacter, openSheet, openSet, TEST_CHARACTER } from '../helpers/sheet.js'

let character

test.beforeAll(async ({ request }) => {
  character = await findPlayableCharacter(request)
})

/** The relationship rows the sheet will draw for that character, in API order. */
async function liveRelationRows(page) {
  const res = await page.request.post('/api/v1/graphql', {
    data: {
      query: `query($id: ID!) {
        entity(id: $id) {
          traitSettings { id traitsetName fromType relationshipContactId relationshipContactName relationshipType }
        }
      }`,
      variables: { id: TEST_CHARACTER },
    },
  })
  const body = await res.json()
  const rows = (body?.data?.entity?.traitSettings || [])
    .filter((t) => t.fromType === 'relationship' && t.traitsetName === 'relations')
  return {
    rows,
    // One header per relationship: contact **and** edge type, since one entity can
    // be both a place you have a `relation` with and a faction you hold
    // `membership` in.
    contacts: [...new Set(rows.map((t) => `${t.relationshipContactName}|${t.relationshipType}`))]
      .map((k) => k.split('|')[0]),
  }
}

/** Headers and rows in the order they are drawn, so a group's shape is visible. */
async function drawnGroups(page) {
  return page.evaluate(() => {
    const nodes = [...document.querySelectorAll('.sheet-embedded .relation-head, .sheet-embedded .trait-node .trait-row')]
    const groups = []
    for (const n of nodes) {
      if (n.classList.contains('relation-head')) {
        groups.push({
          name: n.querySelector('.relation-contact')?.textContent?.trim() || '',
          arrow: n.querySelector('.relation-arrow')?.textContent?.trim() || '',
          type: n.querySelector('.relation-type')?.textContent?.trim() || '',
          rows: 0,
        })
      } else if (groups.length) {
        groups[groups.length - 1].rows++
      }
    }
    return groups
  })
}

test('the relations set heads each relationship, with its traits under it', async ({ page }) => {
  await asPlayer(page)
  await page.setViewportSize({ width: 1280, height: 950 })
  const sheet = await openSheet(page, character)
  const live = await liveRelationRows(page)
  expect(live.rows.length, 'the fixture has relationship traits to group').toBeGreaterThan(0)

  await openSet(page, 'relations')
  const groups = await drawnGroups(page)

  // One header per relationship, naming the contact.
  expect(groups.map((g) => g.name).sort(), 'a header per relationship')
    .toEqual([...live.contacts].sort())
  expect(groups.every((g) => g.arrow === '→'), 'each header points at the contact').toBe(true)

  // Every group holds at least one trait, and no row escaped a header — so the
  // grouping neither drops a row nor leaves one orphaned above the first header.
  expect(groups.every((g) => g.rows > 0), 'no empty group').toBe(true)
  expect(groups.reduce((n, g) => n + g.rows, 0), 'every relationship row is under a header')
    .toBe(live.rows.length)

  // The marker this replaced is gone: the name belongs to the block now, not to a
  // line of it.
  expect(await sheet.locator('.trait-contact').count(), 'no per-row contact marker').toBe(0)
})

test('the drill-in heads them too, in the short dock', async ({ page }) => {
  await asPlayer(page)
  // Docked **and short**: that is the one non-mobile shape that draws the sets as
  // a drill-in rather than the accordion (`traitSetAccordion` needs a large
  // height), and the sheet's column is on screen the whole time. A narrow
  // viewport would not do: there the sheet is the band stack's *teaser* until a
  // tap focuses it, so the set list is clipped and nothing in it is clickable.
  await page.setViewportSize({ width: 1200, height: 480 })
  await openSheet(page, character)
  const live = await liveRelationRows(page)

  await openSet(page, 'relations')

  const groups = await drawnGroups(page)
  expect(groups.map((g) => g.name).sort(), 'the drill-in groups the same way')
    .toEqual([...live.contacts].sort())
  expect(groups.every((g) => g.rows > 0), 'no empty group').toBe(true)
})
