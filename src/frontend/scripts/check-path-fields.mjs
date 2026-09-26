/**
 * Executable check for the B72 "path sets" shape.
 *
 * The frontend has no test runner, so this is a plain node script with
 * assertions — no dependency added. Run it against the frontend image:
 *
 *   docker run --rm \
 *     -v /path/to/src/frontend/scripts:/app/scripts:ro \
 *     -v /path/to/src/frontend/src:/app/src:ro \
 *     -w /app transversal2-frontend:latest node scripts/check-path-fields.mjs
 *
 * The report: "each set of targeting path … the height of the targeting path is
 * quite large, so the SFX/Effect contents become very tall / lots of scrolling.
 * So I want the target path to open in a child panel … Then within e.g.
 * conditions … re-order the conditions using drag-and-drop."
 *
 * So the invariant is a *shape*, not a behaviour: a targeting-path builder lives
 * in exactly one place (`GmPathEditPanel`, the child panel's body), every form
 * that used to inline one shows a `PathField` instead, and the builder's
 * `resolve` event survives the extra hop — an effect reads where its path
 * *landed*, and only `GmPathEditPanel` forwards it.
 *
 * The `resolve` half is not hypothetical: the first cut of this change hosted the
 * builder correctly and dropped the forward, so the Duration field silently
 * stopped appearing for a rating-die target. The build was green.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

let pass = 0, fail = 0
const ok = (name, got, want) => {
  const same = JSON.stringify(got) === JSON.stringify(want)
  same ? pass++ : fail++
  console.log(`${same ? '  PASS' : '  FAIL'}  ${name}${same ? '' : `\n         got ${JSON.stringify(got)}  want ${JSON.stringify(want)}`}`)
}

const SRC = fileURLToPath(new URL('../src', import.meta.url))

function walk(dir) {
  const out = []
  for (const entry of readdirSync(dir)) {
    const p = join(dir, entry)
    if (statSync(p).isDirectory()) out.push(...walk(p))
    else if (entry.endsWith('.vue')) out.push(p)
  }
  return out
}

const VUE = walk(SRC)
const read = (p) => readFileSync(p, 'utf8')
const rel = (p) => p.slice(SRC.length + 1)
const find = (name) => VUE.find((p) => rel(p) === name)

// ── The builder has exactly one home ──────────────────────────────
{
  const hosts = VUE.filter((p) => read(p).includes('<TargetSpecBuilder')).map(rel)
  ok('the path builder is rendered in exactly one component', hosts, ['components/gm/GmPathEditPanel.vue'])
}

// ── …and that home forwards what the builder learns ───────────────
{
  const panel = read(find('components/gm/GmPathEditPanel.vue'))
  ok('GmPathEditPanel declares the resolve event', /defineEmits\(\['resolve'\]\)/.test(panel), true)
  ok('GmPathEditPanel forwards resolve from the builder',
    /@resolve="emit\('resolve', \$event\)"/.test(panel), true)
}

// ── PathField is the way in: one line, plus a panel that carries the path ──
{
  const field = read(find('components/gm/PathField.vue'))
  ok('PathField emits resolve as well as the model', /defineEmits\(\['update:modelValue', 'resolve'\]\)/.test(field), true)
  ok('PathField hands the path across as a get/set pair', /context: \{ pathBinding \}/.test(field), true)
  ok('PathField rebroadcasts the builder\'s resolve', /resolve: \(element\) => emit\('resolve', element\)/.test(field), true)
  ok('PathField builds the summary from the steps it is given', /const stepCount = computed/.test(field), true)
}

// ── Every surface that used to inline a path now shows a PathField ──
{
  const surfaces = [
    'components/gm/ConditionEditor.vue',
    'components/gm/EffectForm.vue',
    'components/gm/EffectRefField.vue',
    'components/gm/BoundVariablesEditor.vue',
    'components/gm/GmSfxEditPanel.vue',
  ]
  for (const s of surfaces) {
    const src = read(find(s))
    ok(`${s} imports PathField`, /import PathField from '\.\/PathField\.vue'/.test(src), true)
    ok(`${s} renders a PathField`, src.includes('<PathField'), true)
    ok(`${s} no longer imports the builder directly`, src.includes('TargetSpecBuilder'), false)
  }
}

// ── Conditions are an ordered, reorderable list ───────────────────
{
  const ce = read(find('components/gm/ConditionEditor.vue'))
  ok('condition rows render through GmList', /<GmList[\s\S]{0,200}reorderable/.test(ce), true)
  ok('…with a drag handle (the rows are full of form controls)', /<GmList[\s\S]{0,200}drag-handle/.test(ce), true)
  ok('…and a commit handler', /@reorder="onReorder"/.test(ce), true)
  ok('the move rewrites the list', /function onReorder\(from, to\)/.test(ce), true)
}

console.log(fail ? `\n  ${fail} failed\n` : '\n  all clear\n')
process.exit(fail ? 1 : 0)
