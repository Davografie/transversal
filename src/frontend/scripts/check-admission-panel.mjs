/**
 * Executable check for the Players tab's admission surface.
 *
 * The frontend has no test runner, so this is a plain node script with
 * assertions — no dependency added. Run it against the frontend image, the same
 * way as the other checks:
 *
 *   docker run --rm \
 *     -v /path/to/src/frontend/scripts:/app/scripts:ro \
 *     -v /path/to/src/frontend/src:/app/src:ro \
 *     -w /app transversal2-frontend:latest node scripts/check-admission-panel.mjs
 *
 * The ask, in the owner's words: *"make sure the QR code / invites open in a child
 * panel and there's no horizontal scrolling."*
 *
 * Both halves were real, and both had the same cause: SEC-3's admission block was
 * written as a `.settings-section` — a 520px column belonging to the player-settings
 * overlay — and then rendered inside the GM panel's ~386px browsing zone. The zone
 * scrolls on one axis, which turns the other into `auto`, so the block's 520px set
 * the scroll width and the tab scrolled sideways.
 *
 * What a *node* check can hold: where the markup lives, which component owns the
 * QR, that the width rule cannot come back, and that the token cannot be persisted.
 * What only the browser can (e2e/tests/admission-window.spec.js): that nothing
 * actually overflows, and that the panel really opens.
 */
import { readFileSync } from 'node:fs'

let pass = 0, fail = 0
const ok = (name, got, want) => {
  const same = JSON.stringify(got) === JSON.stringify(want)
  same ? pass++ : fail++
  console.log(`${same ? '  PASS' : '  FAIL'}  ${name}${same ? '' : `\n         got ${JSON.stringify(got)}  want ${JSON.stringify(want)}`}`)
}
const yes = (name, got) => ok(name, !!got, true)

const read = (p) => readFileSync(new URL(p, import.meta.url), 'utf8')
const PANEL = read('../src/components/gm/GmAdmissionPanel.vue')
const BLOCK = read('../src/components/app/AdmitPlayersBlock.vue')
const GM_PANEL = read('../src/components/GmPanel.vue')
const ADMISSION = read('../src/composables/useAdmission.js')
const CSS = read('../src/assets/styles.css')
const REGISTRY = read('../src/constants/restorablePanels.js')

// ── 1. the invitation is a panel ────────────────────────────────────────
console.log('\nthe QR and the link live in a child panel\n')

yes('the panel exists and shows the QR', /class="admit-qr"/.test(PANEL) && /<img\b/.test(PANEL))
yes('and the link', /class="admit-link"/.test(PANEL) && /aria-label="Admission link"/.test(PANEL))
yes('the QR is generated locally, never fetched',
  /import QRCode from 'qrcode'/.test(PANEL) && /QRCode\.toDataURL/.test(PANEL))
yes('and it is generated in exactly one place — no second QR to drift',
  (read('../src/components/gm/GmAdmissionPanel.vue').match(/from 'qrcode'/g) || []).length
  + (BLOCK.match(/from 'qrcode'/g) || []).length, 1)
yes('the link rule is the composable\'s, not a second copy of it',
  /export function joinUrl\(/.test(ADMISSION) && /import \{[^}]*joinUrl[^}]*\}/.test(PANEL))
yes('the panel closes the window it is showing, and then itself',
  /await close\(joining\.value\.id\)/.test(PANEL) && /panel\.close\(\)/.test(PANEL))
// A props snapshot of the record would keep showing a QR for a token that no
// longer admits anyone — which is exactly what closing from the tab does.
ok('the panel holds no copy of the window — it reads the shared state',
  /defineProps/.test(PANEL), false)
yes('so a window closed elsewhere reaches it, and the QR goes with it',
  /const live = computed\(\(\) => !!joining\.value\?\.id\)/.test(PANEL)
  && /v-if="live"/.test(PANEL) && /That window is closed/.test(PANEL))
yes('and the admission state is shared, not per-instance (Rule 2)',
  ADMISSION.indexOf('const joining = ref(null)') < ADMISSION.indexOf('export function useAdmission()'))

yes('GmPanel opens it as a child panel',
  /component: GmAdmissionPanel/.test(GM_PANEL) && /panel\.open\(\{/.test(GM_PANEL))
yes('with a stable id, so a second open replaces it instead of stacking',
  /id: 'admission'/.test(GM_PANEL))
yes('and the host supplies the reaction a panel cannot carry itself — the clipboard',
  /listeners: \{ copy: copyJoinLink \}/.test(GM_PANEL))
yes('"admit players" mints and shows in one act',
  /await admissionOpen\(\)[\s\S]{0,40}?openInvitation\(\)/.test(GM_PANEL))
yes('and the tab can bring the invitation back without minting another',
  /function showInvitation\(\)/.test(GM_PANEL) && /@show="showInvitation"/.test(GM_PANEL))

// ── 2. the tab no longer holds them ─────────────────────────────────────
console.log('\nthe tab keeps the switch and the open list\n')

ok('the tab renders no image at all any more', /<img\b/.test(BLOCK), false)
ok('and no link field', /admit-link|settings-name-input/.test(BLOCK), false)
yes('it offers the switch', /@click="\$emit\('open'\)"/.test(BLOCK))
yes('and the open windows, with the owner\'s off switch',
  /\$emit\('close', w\.id\)/.test(BLOCK) && /\$emit\('close-all'\)/.test(BLOCK))
yes('its actions are the shared Button primitive, so they are sized like the panel around them',
  /import Button from '@\/components\/ui\/Button\.vue'/.test(BLOCK) && /<Button /.test(BLOCK))

// ── 3. nothing can set a width wider than the zone ──────────────────────
// The bug in one line: `.settings-section` is `min(520px, 100vw - 32px)`, and it
// was rendered in a ~386px zone. The tab must not use it, and the block must not
// carry a width of its own.
console.log('\nno width in the tab is wider than the tab\n')

ok('the tab does not use the settings overlay\'s 520px column',
  /class="[^"]*settings-section/.test(BLOCK), false)
ok('and the block sets no width of its own beyond 100%',
  /width: min\(/.test(BLOCK), false)
ok('the 520px admission column is gone from the stylesheet',
  /\.admit-block \{[^}]*min\(520px/.test(CSS), false)
ok('and so is the nesting-dependent hint cap it needed',
  /\.settings-section \.name-hint/.test(CSS), false)
yes('the block fills its column instead', /\.admit-block \{[^}]*width: 100%/.test(BLOCK.replace(/\n\s*/g, ' ')))

// A long token must ellipsise rather than set the flex row's width, and the QR
// must fit a panel dragged narrow.
yes('the link field can shrink', /flex: 1 1 auto/.test(PANEL) && /min-width: 0/.test(PANEL))
yes('the QR can shrink', /\.admit-qr \{[^}]*max-width: 100%/.test(PANEL))
yes('and the panel itself is shrink-safe', /\.admit-panel \{[^}]*min-width: 0/.test(PANEL.replace(/\n\s*/g, ' ')))

// ── 4. the token must not be written to disk ────────────────────────────
// A window's spec survives a reload by being stored as a registry name + props.
// This panel's props ARE the admission credential, and the API returns it once.
console.log('\nthe invitation is not restorable\n')

ok('GmAdmissionPanel is not in the floating-window registry',
  /^\s*GmAdmissionPanel,$/m.test(REGISTRY), false)
yes('and the registry says why', /GmAdmissionPanel\s+—[\s\S]{0,220}token/.test(REGISTRY))

console.log(`\n${pass} passed, ${fail} failed\n`)
process.exit(fail ? 1 : 0)
