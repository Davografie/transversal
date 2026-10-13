// A restored life-path window must *mount*.
//
// Nothing mounted `GmLifePathDetailPanel` before this spec: no e2e case opened it
// and there is no component-test harness in the frontend. That blind spot let a
// crash through the whole static stack — `watch(() => form, …)` was written above
// `const form = reactive(…)`, so the eager getter hit the temporal dead zone and
// threw during `setup()`. The panel is on the restore allow-list, so a window
// saved while it was open was rebuilt on **every** load and threw again: the app
// booted into a repeated `Unhandled error` per reactive flush.
//
// The case is deliberately the restore path rather than "click through to it",
// because restore is how the breakage reached a page load — and it needs no
// fixture beyond a minimal `lp` prop (create mode is enough to reach setup).
import { test, expect } from '@playwright/test'
import { gql } from '../helpers/sheet.js'
import { bootGmPanel } from '../helpers/gm.js'

const TEST_CHARACTER = 'character-kael-drift-e555ccde'
const STORE = 'gmPanelWindows'

let character
test.beforeAll(async ({ request }) => {
  const { players } = await gql(request, `query { players { id name agency { entityId main } } }`)
  const owner = players.find((p) => (p.agency || []).some((a) => a.entityId === TEST_CHARACTER && a.main))
  if (!owner) throw new Error(`no player mains ${TEST_CHARACTER} — cannot reach the testing character`)
  character = { playerId: owner.id, playerName: owner.name, entityId: TEST_CHARACTER }
})

test('a restored life-path window mounts without a setup error', async ({ page }) => {
  const unhandled = []
  page.on('console', (m) => {
    if (m.text().includes('Unhandled error')) unhandled.push(m.text())
  })
  page.on('pageerror', (e) => unhandled.push(`pageerror: ${e.message}`))

  // Boot first, *then* seed, then reload: the case is "a window is already saved,
  // the page loads" — and seeding before boot would restore a window over the top
  // bar before the helper can click 🛠.
  //
  // Seeded through an init script, not `evaluate` + reload: the app flushes the
  // store on `pagehide`, so a reload writes the *current* (empty) window list over
  // anything seeded in the running page. An init script runs at document start,
  // ahead of the module that reads it.
  await bootGmPanel(page, character)

  await page.addInitScript(
    ([key, rec]) => localStorage.setItem(key, JSON.stringify(rec)),
    [STORE, [{
      name: 'GmLifePathDetailPanel',
      props: { lp: { id: '', name: '', universe: '', description: '', entryTableId: '', entryStep: '', steps: [], conditions: [] } },
      x: 300, y: 200, direction: 'down', collapsed: false, dock: 'right', sourceParentKey: null, z: 1,
    }]],
  )

  await page.reload()
  await page.waitForTimeout(2500)

  // The component's own root — present only if setup completed.
  await expect(page.locator('.lpd-root'), 'the panel mounted').toHaveCount(1)
  expect(unhandled.join('\n'), 'no unhandled error during the load').toBe('')
})
