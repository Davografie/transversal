// The portal-effects panel auto-saves.
//
// The author's request, relayed through [[effects]] on 2026-10-17: *"The portal
// effects panels should have auto-save."* It was the last authoring panel with a
// manual Save — and the save **was** the close, so there was no way to save and
// keep working.
//
// `check-portal-autosave.mjs` reads the wiring; what only a browser can show is
// that the button is really gone and that an edit really reaches the endpoint,
// including one made in the last moments before the panel closes — the edit the
// flush exists for, and the one that would vanish without a trace.
//
// The fixture is two throwaway locations and a transversal edge between them,
// made and torn down through the API. Nothing of anyone's is touched.
import { test, expect } from '@playwright/test'
import { gql } from '../helpers/sheet.js'
import { bootGmPanel, enterPrep } from '../helpers/gm.js'

const TEST_CHARACTER = 'character-kael-drift-e555ccde'
const FROM = 'E2E Portal From'
const TO = 'E2E Portal To'
// The panel only has to draw *a row* it can remove; what the effect does is the
// effect system's business.
const SEED = { actionId: 'show_toast', timing: 'IMMEDIATE' }

let character
let fromId = null
let toId = null

test.beforeAll(async ({ request }) => {
  const { players } = await gql(request, `query { players { id name agency { entityId main } } }`)
  const owner = players.find((p) => (p.agency || []).some((a) => a.entityId === TEST_CHARACTER && a.main))
  if (!owner) throw new Error(`no player mains ${TEST_CHARACTER} — cannot reach the testing character`)
  character = { playerId: owner.id, playerName: owner.name, entityId: TEST_CHARACTER }
})

async function makeLocation(request, name) {
  const d = await gql(request, `mutation($i: CreateEntityInput!){ createEntity(input: $i){ id } }`,
    { i: { name, type: 'LOCATION', universe: 'earth' } })
  return d.createEntity.id
}

/** The effects on the FROM → TO edge, read the way the panel's own parent reads them. */
async function edgeEffects(request) {
  const nav = await (await request.get(`/api/v1/locations/${fromId}/navigate`)).json()
  const link = (nav.transversal || []).find((l) => l._key === toId)
  return link ? (link.effects || []) : null
}

test.beforeEach(async ({ request }) => {
  fromId = await makeLocation(request, FROM)
  toId = await makeLocation(request, TO)
  const made = await request.post(`/api/v1/locations/${fromId}/edges/${toId}`,
    { data: { type: 'transversal', effects: [SEED] } })
  expect(made.ok(), 'the fixture edge exists').toBeTruthy()
  expect((await edgeEffects(request)).length, 'seeded with one effect').toBe(1)
})

test.afterEach(async ({ request }) => {
  // Whatever happened, leave nothing behind: the edge first, then the places.
  if (fromId && toId) {
    await request.delete(`/api/v1/locations/${fromId}/edges/${toId}?type=transversal`)
  }
  for (const id of [fromId, toId].filter(Boolean)) {
    await gql(request, `mutation($id: ID!){ deleteEntity(id: $id, rmtree: false) }`, { id })
  }
  fromId = null
  toId = null
})

/** Open the FROM place's panel, then its portal-effects panel for the link to TO. */
async function openPortalPanel(page) {
  await bootGmPanel(page, character)
  await enterPrep(page)
  await page.locator('.filter-input:visible').first().fill(FROM)
  await page.waitForTimeout(900)
  await page.locator('.suggestion-row:visible').first().click()
  await page.waitForTimeout(1600)
  await page.locator('.transversal-row', { hasText: TO }).locator('.transversal-effects').first().click()
  await page.waitForTimeout(1200)
  const portal = page.locator('.panel-node[data-panel-depth="2"]:visible')
  await expect(portal, 'the portal effects panel is open').toHaveCount(1)
  return portal
}

test('the panel has no Save button, and an edit lands on its own', async ({ page, request }) => {
  const portal = await openPortalPanel(page)

  await expect(portal.locator('button', { hasText: /^Save$/ }), 'no Save button').toHaveCount(0)
  await expect(portal.locator('.ee-del'), 'the seeded effect is a row').toHaveCount(1)

  // Remove it and let the debounce do its work — the panel stays open.
  await portal.locator('.ee-del').first().click()
  await page.waitForTimeout(2500)

  expect(await edgeEffects(request), 'the edit reached the server by itself').toEqual([])
  await expect(portal.locator('.ee-del'), 'and the row is gone').toHaveCount(0)
})

test('one effect is edited in a child panel, not inline', async ({ page }) => {
  const portal = await openPortalPanel(page)

  // The editor is not inline any more: nothing to fill in until a row is opened.
  await expect(portal.locator('.ee-form-title'), 'no inline effect form').toHaveCount(0)

  await portal.locator('.ee-add').click()
  await page.waitForTimeout(1200)

  // A child panel of the portal — depth 3 under the chain root — which is the
  // shape every other effect list uses.
  const editor = page.locator('.panel-node[data-panel-depth="3"]:visible')
  await expect(editor, 'the effect editor is a child panel').toHaveCount(1)
  await expect(editor.locator('.ee-form-title'), 'and it holds the form').toHaveCount(1)
  // The list has to stay in view while an effect is edited — which is the whole
  // reason it is a panel rather than an inline form.
  await expect(portal, 'with the portal and its list still beside it').toHaveCount(1)
})

test('an edit made just before closing still lands', async ({ page, request }) => {
  const portal = await openPortalPanel(page)

  // Remove the effect and close **at once** — inside the 700ms debounce. Without
  // the flush on close this write never happens and the effect is still there.
  await portal.locator('.ee-del').first().click()
  await portal.locator('[title="Close"]').first().click()
  await page.waitForTimeout(2500)

  expect(await edgeEffects(request), 'the edit survived the close').toEqual([])
})
