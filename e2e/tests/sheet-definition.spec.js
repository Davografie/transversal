import { test, expect } from '@playwright/test'

// Scanning sets for one with visible traits can take a few loads' worth of time.
test.setTimeout(120_000)
import { findPlayableCharacter, openSheet, ensureTraitRowsVisible, openTraitEditor } from '../helpers/sheet.js'

// The trait editor's "Definition" control — changing an instance's registry trait.
//
// This exists because the control shipped broken in a way no static check could
// see and no probe of mine caught: the picker's open state lived inside
// `TraitEditPanel`, which the sheet re-creates whenever it re-renders. The first
// click set it open, the options arrived, the re-render replaced the panel, and
// the fresh instance had it closed again — so the list only ever appeared on a
// *second* click, once the fetch was cached. A user clicks once.
//
// Hence the shape of the assertion below: one click, then look.

test('the definition picker opens on the first click', async ({ page, request }) => {
  const character = await findPlayableCharacter(request)
  await openSheet(page, character)
  await ensureTraitRowsVisible(page)
  await openTraitEditor(page)

  const chip = page.locator('.definition-chip')
  await expect(chip).toBeVisible()
  const current = (await chip.innerText()).trim()
  expect(current.length, 'the chip names the instance’s current definition').toBeGreaterThan(0)

  // Exactly one click — the whole point of this test.
  await chip.click()

  const dropdown = page.locator('.definition-dropdown')
  await expect(dropdown, 'one click must open the picker').toBeVisible()
  const options = page.locator('.definition-option')
  expect(await options.count(), 'the picker must offer candidate definitions').toBeGreaterThan(0)

  // The current definition is always among them, marked as selected, so the list
  // is never a dead end and the player can see where they are.
  await expect(page.locator('.definition-option.selected')).toHaveText(new RegExp(current, 'i'))
})

test('the traitset filter opens on the instance’s own set, and can widen', async ({ page, request }) => {
  const character = await findPlayableCharacter(request)
  await openSheet(page, character)
  await ensureTraitRowsVisible(page)
  const settingId = await openTraitEditor(page)
  const setting = character.traitSettings.find((s) => s.id === settingId)
  expect(setting, `the edited setting ${settingId} is in the fetched list`).toBeTruthy()

  await page.locator('.definition-chip').click()
  const setFilter = page.locator('.definition-set-filter')
  await expect(setFilter, 'the picker offers a trait set filter').toBeVisible()

  // The default is the set the instance already lives in — not "all", and not the
  // first set in the list by accident.
  await expect(setFilter).toHaveValue(setting.traitsetId)
  const inSet = await page.locator('.definition-option').count()
  expect(inSet, 'the instance’s own set must offer at least its current definition').toBeGreaterThan(0)

  // Widening to every set can only add candidates, never remove one. `selectOption('')`
  // is the "All trait sets" option.
  await setFilter.selectOption('')
  await expect
    .poll(async () => page.locator('.definition-option').count(), { timeout: 5_000 })
    .toBeGreaterThanOrEqual(inSet)

  // Narrowing back restores exactly the set's candidates.
  await setFilter.selectOption(setting.traitsetId)
  await expect
    .poll(async () => page.locator('.definition-option').count(), { timeout: 5_000 })
    .toBe(inSet)
})

test('the picker filters, and closing it leaves the editor open', async ({ page, request }) => {
  const character = await findPlayableCharacter(request)
  await openSheet(page, character)
  await ensureTraitRowsVisible(page)
  await openTraitEditor(page)

  const chip = page.locator('.definition-chip')
  await chip.click()
  const filter = page.locator('.definition-filter')
  await expect(filter).toBeVisible()

  const all = await page.locator('.definition-option').count()
  await filter.fill('e')
  await expect
    .poll(async () => page.locator('.definition-option').count(), { timeout: 5_000 })
    .toBeLessThan(all)

  // Closing is a toggle, and it must not disturb the editor it sits in — the
  // draft fields the player was editing are the panel's, and re-opening them
  // from scratch would silently discard their work.
  await chip.click()
  await expect(page.locator('.definition-dropdown')).toBeHidden()
  await expect(page.locator('.trait-edit-panel')).toBeVisible()
  await expect(chip).toHaveText(new RegExp((await chip.innerText()).trim(), 'i'))
})

test('the sheet reports no console or page errors while the picker is used', async ({ page, request }) => {
  // This session has already shipped a silent no-op to the human's console once,
  // and a control that throws on click looks identical to one that does nothing.
  //
  // Scoped on purpose: uncaught exceptions always count, but console output only
  // counts when it comes from the sheet. The app also logs *caught*, unrelated
  // network failures through `console.error` (a Firefox `fetchSfxCatalog`
  // NetworkError reproduces here regularly), and failing on those would make this
  // test flaky for reasons that have nothing to do with the picker.
  const pageErrors = []
  const sheetErrors = []
  page.on('pageerror', (e) => pageErrors.push(String(e)))
  page.on('console', (m) => {
    if (m.type() !== 'error') return
    const text = m.text()
    if (/\[sheet\]|definition/i.test(text)) sheetErrors.push(text)
  })

  const character = await findPlayableCharacter(request)
  await openSheet(page, character)
  await ensureTraitRowsVisible(page)
  await openTraitEditor(page)

  const chip = page.locator('.definition-chip')
  await chip.click()
  await expect(page.locator('.definition-dropdown')).toBeVisible()
  await chip.click()
  await expect(page.locator('.definition-dropdown')).toBeHidden()

  expect(pageErrors, `uncaught page errors: ${pageErrors.join(' | ')}`).toEqual([])
  expect(sheetErrors, `sheet errors: ${sheetErrors.join(' | ')}`).toEqual([])
})
