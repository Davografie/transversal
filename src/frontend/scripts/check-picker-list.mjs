/**
 * Executable check for the picker's **result list** (`ui/SearchDropdown.vue`).
 *
 * The core's semantics are `check-combobox.mjs`'s; this guards the shell's
 * *shape*, which is a decision rather than a bug fix:
 *
 *  - the results are **in flow, never an overlay**. An absolutely positioned
 *    list is cropped by any ancestor with `overflow`, which is most hosts (a GM
 *    panel's scroll zone, the sheet, the wizard) — the same field clipped in
 *    different places depending on where it was embedded. In flow the host
 *    scrolls, so nothing can clip, and the list must not grow a second
 *    scrollbar of its own inside the host's.
 *  - the rows are the app's own `.entity-row` shell, so a picker row reads like
 *    a panel row instead of a private vocabulary.
 *  - the options carry the ids its `aria-activedescendant` points at. The
 *    activedescendant was set from the start while the options had no `id`, so
 *    the keyboard highlight announced nothing. That is invisible in a browser
 *    and easy to regress, so it is pinned here.
 *
 * Comments are stripped before matching, deliberately: these files *explain*
 * the overlay they replaced, and a raw text match would fail on the
 * explanation rather than on the code (the same trap `check-choice-table.mjs`
 * records).
 *
 *   docker run --rm \
 *     -v /path/to/src/frontend/scripts:/app/scripts:ro \
 *     -v /path/to/src/frontend/src:/app/src:ro \
 *     -w /app transversal2-frontend:latest node scripts/check-picker-list.mjs
 */
import { readFileSync } from 'node:fs'

let pass = 0, fail = 0
const ok = (name, cond, detail = '') => {
  cond ? pass++ : fail++
  console.log(`${cond ? '  PASS' : '  FAIL'}  ${name}${cond ? '' : `\n         ${detail}`}`)
}

const SHELL = new URL('../src/components/ui/SearchDropdown.vue', import.meta.url)
const PICKER = new URL('../src/components/ui/TargetPicker.vue', import.meta.url)

const read = (url) => readFileSync(url, 'utf8')
// Strip `//` line comments, `/* */` blocks and `<!-- -->` HTML comments, so a
// guard cannot be satisfied or broken by prose.
const strip = (src) => src
  .replace(/<!--[\s\S]*?-->/g, '')
  .replace(/\/\*[\s\S]*?\*\//g, '')
  .replace(/(^|[^:])\/\/[^\n]*/g, '$1')

const shellSrc = read(SHELL)
const shell = strip(shellSrc)
const styleBlock = shell.match(/<style[^>]*>([\s\S]*?)<\/style>/)
const css = styleBlock ? styleBlock[1] : ''
const ruleBody = (sel) => {
  const m = css.match(new RegExp(`\\${sel}\\s*\\{([^}]*)\\}`))
  return m ? m[1] : ''
}
const optionTag = (() => {
  const i = shell.indexOf('v-for="(opt, i) in available"')
  return i < 0 ? '' : shell.slice(i, shell.indexOf('>', i))
})()
const inputTag = (() => {
  const i = shell.indexOf('class="sd-input"')
  return i < 0 ? '' : shell.slice(i, shell.indexOf('/>', i))
})()

console.log('\nSearchDropdown — the result list')

// ── in flow, not an overlay ─────────────────────────────────────────────
{
  const list = ruleBody('.sd-list')
  ok('the list rule exists', !!list, 'no `.sd-list { … }` rule found')
  ok('the list is in flow (no position)',
    !!list && !/position\s*:/.test(list),
    `position: found in .sd-list { ${list.trim()} }`)
  ok('the list is a column', /flex-direction\s*:\s*column/.test(list), list.trim())
  ok('the list keeps no scroller of its own',
    !!list && !/overflow|max-height/.test(list),
    `overflow/max-height found in .sd-list { ${list.trim()} } — the host is the one scroller`)
  ok('the old overlay is gone',
    !ruleBody('.sd-drop') && !ruleBody('.sd-drop-up') && !/sd-drop-up/.test(shell),
    'a `.sd-drop` / `.sd-drop-up` rule or class still exists')
}

// ── the rows are the app's rows ─────────────────────────────────────────
{
  ok('an option is the shared entity row',
    /class="[^"]*\bentity-row\b/.test(optionTag),
    `option class is ${optionTag.match(/class="[^"]*"/) || 'absent'}`)
  ok('an option keeps the `.sd-item` hook the specs use',
    /class="[^"]*\bsd-item\b/.test(optionTag),
    'e2e/tests/target-spec-literal.spec.js selects `.sd-item`')
  ok('the default row content is the shared name span',
    /<span class="entity-name">/.test(shell),
    'the fallback label should read as an entity row')
  ok('the empty state is not the old sd-empty class',
    !/sd-empty/.test(shell),
    '`.sd-empty` was renamed `.sd-state` with the list')
}

// ── the aria wiring actually points at something ────────────────────────
{
  ok('the input carries an activedescendant',
    /aria-activedescendant/.test(inputTag) || /:aria-activedescendant/.test(inputTag),
    'the combobox must announce its highlighted option')
  ok('an option carries an id, so the activedescendant resolves',
    /:id="optionId\(i\)"/.test(optionTag),
    `option tag is: ${optionTag}`)
  ok('a single option id source (the core\'s optionId)',
    /optionId/.test(shell.match(/const \{[^}]*\} = combo/)?.[0] || ''),
    'optionId must be destructured from useCombobox, not rebuilt here')
}

// ── the concrete picker speaks the same vocabulary ──────────────────────
{
  const picker = strip(read(PICKER))
  ok('TargetPicker\'s option slot uses the shared name span',
    /class="entity-name"/.test(picker),
    'the slot should hand back `.entity-name`, not a private `.tp-name`')
  ok('TargetPicker\'s option slot uses the shared secondary',
    /class="entity-universe/.test(picker),
    'the slot should hand back `.entity-universe`, not a private `.tp-universe`')
  ok('no private name rule is left behind',
    !/\.tp-name\s*\{/.test(picker),
    '`.tp-name` is dead once the shared span is used')
}

console.log(`\n  ${pass} passed, ${fail} failed\n`)
process.exit(fail ? 1 : 0)
