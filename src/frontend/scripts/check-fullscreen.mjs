/**
 * Static + behavioural check: fullscreen enters only when it should, and the
 * rules that make it polite are still wired.
 *
 * The policy has two silent failure modes. One is over-eager: entering when the
 * device is a mouse/keyboard one, or straight back in after the player left
 * with the back gesture — which reads as "the app will not let me out" rather
 * than as a bug. The other is inert: fullscreen quietly never happens, and
 * because a refused request is swallowed on purpose (it is a normal outcome,
 * not a fault) there is nothing in the console to notice. Neither shows up in a
 * build, so this script is the guard.
 *
 * `shouldEnter` is pure, and the store rehydrates from `localStorage`, so the
 * policy is exercised for real here (with `localStorage` stubbed) rather than
 * pattern-matched. No browser and no dependency:
 *
 *   docker run --rm \
 *     -v /path/to/src/frontend/scripts:/app/scripts:ro \
 *     -v /path/to/src/frontend/src:/app/src:ro \
 *     -w /app transversal2-frontend:latest node scripts/check-fullscreen.mjs
 */
import { readFileSync, existsSync } from 'node:fs'

let pass = 0, fail = 0
/** `bad` is the list of problems; empty means pass. */
const ok = (name, bad) => {
  bad.length ? fail++ : pass++
  console.log(`  ${bad.length ? 'FAIL' : 'PASS'}  ${name}${bad.length ? `\n         ${bad.join('\n         ')}` : ''}`)
}
/** For a plain boolean: the problem is the value that failed the claim. */
const yes = (name, cond, got = '') => ok(name, cond ? [] : [String(got)])

const FULLSCREEN = 'src/composables/useFullscreenMode.js'
const BLOCK = 'src/components/app/FullscreenBlock.vue'
const APP = 'src/App.vue'

/** Prose in these files explains what it replaced, so a pattern must not match
 *  a comment (the lesson `check-choice-table.mjs` records). */
const stripComments = (s) => s.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '')

const source = readFileSync(FULLSCREEN, 'utf8')
const code = stripComments(source)

// ── 1. the policy, exhaustively ─────────────────────────────────────────────
const { shouldEnter, FULLSCREEN_MODES } = await import('../src/composables/useFullscreenMode.js')

{
  const modes = ['off', 'on', 'auto']
  const kinds = ['touch', 'pointer']
  const bools = [true, false]
  const wrong = []
  let cases = 0
  for (const mode of modes)
    for (const inputKind of kinds)
      for (const supported of bools)
        for (const fullscreen of bools)
          for (const suppressed of bools)
            for (const visible of bools) {
              cases++
              const got = shouldEnter({ mode, inputKind, supported, fullscreen, suppressed, visible })
              // The reference reads the rule from the other end: fullscreen is
              // permitted only by a live, supported, visible, unsuppressed page
              // that is not already fullscreen — and then `on` permits it
              // outright while `auto` permits it only for a touch device.
              const wants = mode === 'on' || (mode === 'auto' && inputKind === 'touch')
              const expected = mode !== 'off' && wants && supported && visible && !fullscreen && !suppressed
              if (got !== expected) wrong.push(`${mode}/${inputKind}/sup=${supported}/fs=${fullscreen}/sil=${suppressed}/vis=${visible} → ${got}, expected ${expected}`)
            }
  yes(`all ${cases} combinations of the policy agree with the rule`, wrong)
}

// The named cases, so a failure reads as a sentence rather than a combination.
const base = { mode: 'auto', inputKind: 'touch', supported: true, fullscreen: false, suppressed: false, visible: true }
yes('off never enters, even on a touch screen that supports it',
  !shouldEnter({ ...base, mode: 'off' }))
yes('auto enters on a touch screen', shouldEnter(base))
yes('auto leaves a mouse/keyboard device alone',
  !shouldEnter({ ...base, inputKind: 'pointer' }))
yes('on enters whatever the input device is — that is what On means',
  shouldEnter({ ...base, mode: 'on', inputKind: 'pointer' }))
yes('a device that cannot go fullscreen never tries',
  !shouldEnter({ ...base, mode: 'on', supported: false }))
yes('a hidden page never tries (a request there is refused anyway)',
  !shouldEnter({ ...base, mode: 'on', visible: false }))
yes('an already-fullscreen page does not re-request',
  !shouldEnter({ ...base, mode: 'on', fullscreen: true }))
yes('after the player left with the back gesture, neither mode takes it back',
  !shouldEnter({ ...base, mode: 'on', suppressed: true }) &&
  !shouldEnter({ ...base, suppressed: true }))
yes('the vocabulary is exactly off / on / auto',
  JSON.stringify(FULLSCREEN_MODES) === JSON.stringify(['off', 'on', 'auto']), FULLSCREEN_MODES.join(','))
yes('the default is off — nobody gets fullscreen before choosing it',
  /read\(MODE_KEY, FULLSCREEN_MODES, 'off'\)/.test(code))

// ── 2. the store only trusts a value it knows ───────────────────────────────
// (That it actually *survives a reload* is measured in a browser, where
// `localStorage` is real: `e2e/tests/fullscreen.spec.js`.)
{
  yes('a stored mode outside the vocabulary cannot be trusted',
    /return valid\.includes\(v\) \? v : fallback/.test(code))
  yes('…and every write goes through the one guarded writer',
    (code.match(/localStorage\.setItem/g) || []).length === 1 &&
    /function write\(key, v\) \{[\s\S]{0,120}localStorage\.setItem\(key, v\)/.test(code) &&
    /write\(MODE_KEY, v\)/.test(code) && /write\(INPUT_KEY, v\)/.test(code))
}

// ── 3. the timing and the manners ───────────────────────────────────────────
{
  yes('entering rides a *completed* interaction, not pointerdown',
    /addEventListener\('click', tryEnter/.test(code) && !/pointerdown', tryEnter/.test(code))
  yes('…and a keypress counts too, so On works on a keyboard device',
    /addEventListener\('keydown', onKeyboard/.test(code))
  yes('pointerdown only records which device was used',
    /function onPointerDown\(e\) \{\s*setInputKind\([^}]*\}/.test(code))
  yes('a pen counts as touch (no keyboard in hand)',
    /e\.pointerType === 'mouse' \? 'pointer' : 'touch'/.test(code))

  yes('a *user* exit is the transition into not-fullscreen',
    /watch\(api\.isFullscreen, \(now, was\) => \{\s*if \(was && !now\) suppressed\.value = true/.test(code))
  yes('…and coming back to the page re-arms auto',
    /function onVisibility\(\) \{[\s\S]{0,200}visibilityState === 'visible'[\s\S]{0,80}suppressed\.value = false/.test(code))
  yes('…and that handler is actually wired to the page becoming visible',
    /addEventListener\('visibilitychange', onVisibility\)/.test(code))
  yes('…and an explicit choice outranks the suppression',
    /function setMode[\s\S]{0,300}suppressed\.value = false/.test(code))

  yes('the only exit is the player choosing off',
    (code.match(/api\.exit\(\)/g) || []).length === 1 && /if \(v === 'off'\) \{\s*api\.exit\(\)/.test(code))
  yes('a refused request is swallowed, so it cannot reach the console',
    /try \{\s*await api\.enter\(\)\s*\} catch \{/.test(code))
  yes('support is decided by document.fullscreenEnabled, not only the library',
    /document\.fullscreenEnabled === true/.test(code) && /api\?\.isSupported\.value/.test(code))
  yes('the device kind is remembered per device',
    /write\(INPUT_KEY, v\)/.test(code) && /read\(INPUT_KEY, INPUT_KINDS, guessInputKind\(\)\)/.test(code))
}

// ── 4. the surface ──────────────────────────────────────────────────────────
{
  const block = readFileSync(BLOCK, 'utf8')
  yes('the block renders the options it is given and invents no vocabulary',
    /:options="options"/.test(block) && !/value: 'auto'/.test(block))
  yes('…and names no CSS property itself',
    !/style=|--[a-z-]+:/.test(block))
  yes('…and does not reach for the library directly (one owner of the API)',
    !/@vueuse/.test(block) && !/requestFullscreen/.test(block))

  const app = readFileSync(APP, 'utf8')
  const atFind = app.indexOf('<FindCharacterBlock')
  const atFull = app.indexOf('<FullscreenBlock')
  const atBack = app.indexOf('Back to game')
  yes('the settings screen mounts the control', atFull > -1)
  yes('…below Find character', atFind > -1 && atFull > atFind, `find=${atFind} fullscreen=${atFull}`)
  yes('…and above the exit button', atBack > -1 && atFull < atBack)
  yes('the shell claims the policy, so Auto works without opening that screen',
    /const \{ mode: fullscreenMode, setMode: setFullscreenMode[\s\S]{0,120}useFullscreenMode\(\)/.test(app))

  // The screen's order is a convention, and it has one silent failure mode: a
  // block drifts back into the middle of the screen, which reads as clutter
  // rather than as a bug. Mode is what the app *is*; the three below it are how
  // this device shows it, and they are set once.
  const atMode = app.indexOf('<ModeBlock')
  const atChars = app.indexOf('<CharacterListBlock')
  const atAppearance = app.indexOf('<AppearanceBlock')
  const atMedia = app.indexOf('<MediaQualityBlock')
  yes('Mode stays at the top, above the characters',
    atMode > -1 && atChars > -1 && atMode < atChars, `mode=${atMode} chars=${atChars}`)
  yes('Appearance, media quality and fullscreen sit together under Find character',
    atFind < atAppearance && atAppearance < atMedia && atMedia < atFull,
    `find=${atFind} appearance=${atAppearance} media=${atMedia} fullscreen=${atFull}`)
  yes('…and the component they were split out of is gone, not left as a second doorway',
    !/<ModeAndMediaBlock/.test(app) && !existsSync('src/components/app/ModeAndMediaBlock.vue'))
  yes('…with Mode and media quality each owning one block',
    /<label class="settings-label">Mode<\/label>/.test(readFileSync('src/components/app/ModeBlock.vue', 'utf8')) &&
    /<label class="settings-label">Media quality<\/label>/.test(readFileSync('src/components/app/MediaQualityBlock.vue', 'utf8')))

  const css = readFileSync('src/assets/styles.css', 'utf8')
  yes('the hint style is shared with the other settings controls',
    /\.settings-note \{/.test(css) && !/\.quality-hint/.test(css))
}

// ── 5. the way back in ─────────────────────────────────────────────────────
// Found by running it, not by reading: after a user exit the setting still reads
// `On`, and a segment click that emits nothing left the player with no way to
// ask for fullscreen again. Both halves are pinned, because repairing either one
// alone looks like nothing is broken.
{
  const segmented = readFileSync('src/components/ui/SegmentedControl.vue', 'utf8')
  yes('an already-chosen segment can still be re-asserted, opt-in',
    /reselect: \{ type: Boolean, default: false \}/.test(segmented) &&
    /value !== props\.modelValue \|\| props\.reselect/.test(segmented))
  yes('…and the fullscreen control is the one that opts in',
    /reselect/.test(readFileSync(BLOCK, 'utf8')))
  yes('…and a plain preference is unchanged by it',
    !/reselect/.test(readFileSync('src/components/app/MediaQualityBlock.vue', 'utf8')) &&
    !/reselect/.test(readFileSync('src/components/app/AppearanceBlock.vue', 'utf8')))
  yes('the player can see that we are holding off after they left',
    /if \(suppressed\.value && !isFullscreen\.value\)[\s\S]{0,120}Left fullscreen/.test(code))
}

console.log(fail ? `\n  ${fail} failed\n` : '\n  all clear\n')
process.exit(fail ? 1 : 0)
