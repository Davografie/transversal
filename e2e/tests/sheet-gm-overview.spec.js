// The roaming GM's play surface, and the rules that live on the GM.
//
// The GM panel's Play tab was migrated onto the character sheet (the author,
// 2026-09-29): the panels keep Prep, the sheet carries play. Three things fall
// out of that and each is asserted here, because each was *separately* broken
// before:
//
//   1. the sheet has a body for a GM who is acting as nobody — the play surface,
//      where "No entity loaded" used to be;
//   2. the sheet band is shown for that GM at all. Two rules hid it, on the same
//      premise ("an empty sheet band"): `useMobileBands`'s `sheetEmpty` collapsed
//      it on mobile, and `sheetShown` excluded the roaming GM entirely. The dock
//      case is the sharp one — the sheet is a permanent column there, so before
//      the fix a docked roaming GM had a permanently blank panel;
//   3. the rules attached to the **GM** are rendered, and a manual one is a press
//      whose question lands on the sheet's own wizard. They live on no entity, so
//      nothing drew them anywhere.
//
// The GM's rules are read from the live world rather than stubbed: `sfx-roll-table`
// is the author's own rule and the only manual GM-owned one, and the spec fails
// loudly if it is not attached, because a silently-empty rules row is exactly the
// failure this feature exists to prevent.

import { test, expect } from '@playwright/test'
import { enterAsArchitect } from '../helpers/session.js'

/** The roaming GM: the architect seat, acting as nobody. */
async function bootRoamingGm(page) {
  await enterAsArchitect(page)
  await page.goto('/')
}

/** The rules that are attached to the GM owner, straight from the API. */
async function gmSfxIds(page) {
  const res = await page.request.post('/api/v1/graphql', {
    data: { query: '{ sfxOwners(ownerType: GM) { sfxIds } }' },
  })
  const body = await res.json()
  return (body?.data?.sfxOwners || []).flatMap((o) => o.sfxIds || [])
}

test('a roaming GM gets the play surface in place of the empty sheet', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 950 })
  await bootRoamingGm(page)

  // Docked and in landscape, the sheet is a permanent column — no hover needed.
  const sheet = page.locator('.sheet-embedded')
  const overview = sheet.locator('.play-overview')
  await expect(overview).toBeVisible({ timeout: 20_000 })

  // The placeholder is gone, not merely covered.
  await expect(sheet.locator('.empty-no-entity')).toHaveCount(0)

  // The four shortcuts. Three render: Start and End are one control.
  await expect(sheet.locator('.gm-shortcuts .shortcut-btn')).toHaveCount(3)
  await expect(sheet.locator('.gm-shortcuts')).toContainText('Next Beat')
  await expect(sheet.locator('.gm-shortcuts')).toContainText('Scene')

  // Both overview components, drawn from the sheet's own data.
  await expect(sheet.locator('.troupe-overview')).toBeVisible()
  await expect(sheet.locator('.troupe-overview .troupe-header h3')).toHaveText('Troupe')
  await expect(sheet.locator('.scene-summary')).toBeVisible()
  await expect(sheet.locator('.scene-summary h3')).toHaveText('Scene')
})

test('the GM rules are drawn, and a manual one asks its question as the sheet body', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 950 })

  const attached = await (async () => {
    await enterAsArchitect(page)
    return gmSfxIds(page)
  })()
  expect(attached, 'the GM owns no rules — nothing to draw').toContain('sfx-roll-table')

  await page.goto('/')
  const sheet = page.locator('.sheet-embedded')
  const rules = sheet.locator('.gm-sfx-rules')
  await expect(rules).toBeVisible({ timeout: 20_000 })

  // One card per attached rule, named from the catalog (not the raw id).
  const cards = rules.locator('.sfx-card')
  await expect(cards).toHaveCount(attached.length)
  const rollTable = rules.locator('.sfx-card', { hasText: 'Roll Table' })
  await expect(rollTable).toBeVisible()

  // The menu rule is stated, not offered: it fires from the roller's hitch menu,
  // so pressing it would be a lie. Exactly the manual rules are pressable.
  await expect(rules.locator('.sfx-card.sfx-readonly')).toHaveCount(1)
  await expect(rollTable).not.toHaveClass(/sfx-readonly/)

  // Pressing it takes the body, the way a sheet-raised question always does.
  await rollTable.click()
  const choice = sheet.locator('.sheet-sfx-choice')
  await expect(choice).toBeVisible({ timeout: 15_000 })
  await expect(sheet.locator('.play-overview')).toHaveCount(0)

  // And the question is the rule's own: `sfx-roll-table` declares a `roll_tables`
  // choose step, so the wizard offers the table, not a shrug.
  await expect(choice.locator('.etw-candidate').first()).toBeVisible()
  await expect(choice.locator('.etw-kind')).toContainText('roll_table')

  // Cancelling puts the surface back.
  await choice.getByRole('button', { name: /^cancel$/i }).click()
  await expect(sheet.locator('.play-overview')).toBeVisible()
})

test('a scene row hands the GM that entity, the way the panel always did', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 950 })
  // Perspective, not identity: the location the GM is standing in is UI state
  // (App seeds it from storage). Eindhoven is chosen because it has occupants —
  // the default location has none, so the roster would be legitimately empty and
  // the test would prove nothing.
  await page.addInitScript(() => localStorage.setItem('currentLocationId', 'loc-469287'))
  await bootRoamingGm(page)

  const sheet = page.locator('.sheet-embedded')
  await expect(sheet.locator('.play-overview')).toBeVisible({ timeout: 20_000 })

  // The scene's own roster, from the roster read the sheet fetched.
  await expect(sheet.locator('.scene-summary .scene-row').first()).toBeVisible()

  // Row → the GM's perspective. A **GMC** on purpose: assuming a character is
  // the one act this suite must not perform against a player's PC, and a GMC is
  // the GM's own material.
  await sheet.locator('.scene-summary .scene-row', { hasText: 'Corwin of Amber' }).first().click()

  // The play surface gives way to that entity's sheet — the same "view this
  // entity" action a peer chip performs, so nothing new is invented here.
  await expect(sheet.locator('.name-primary')).toHaveText('Corwin of Amber', { timeout: 20_000 })
  await expect(sheet.locator('.play-overview')).toHaveCount(0)
})

test('the roaming GM keeps a sheet band on mobile, and can focus it', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await bootRoamingGm(page)

  const stage = page.locator('.stage')
  const sheetBand = page.locator('.sheet-band')
  await expect(stage).toHaveClass(/mobile-stack/, { timeout: 20_000 })

  // Wait for the GM state *itself* before touching the band. `gmMode` starts
  // false and only becomes true once the session answers, so a click inside that
  // window is made by a spectator rather than a GM — and the guard this test
  // exists to prove ("a roaming GM may focus the sheet") would not be consulted
  // at all. That window is a false pass, not a fast one.
  await expect(page.locator('.gm-toggle')).toBeVisible({ timeout: 20_000 })
  await expect(sheetBand.locator('.play-overview')).toBeVisible()

  // The band is not collapsed (`sheet-empty` used to `display: none` it).
  await expect(sheetBand).toBeVisible()

  // …and the sheet focus is reachable: tapping its teaser used to be a no-op.
  await sheetBand.locator('.band-tap').click()
  await expect(stage).toHaveClass(/focus-sheet/)
  await expect(sheetBand.locator('.gm-sfx-rules')).toBeVisible()
})
