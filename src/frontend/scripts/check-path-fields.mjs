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
import { rollTableIdFromAnswer, rollTableIdOf } from '../src/utils/rollTableMenu.js'

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
    'components/gm/ReachEditor.vue',
    'components/gm/GmSfxEditPanel.vue',
  ]
  for (const s of surfaces) {
    const src = read(find(s))
    ok(`${s} imports PathField`, /import PathField from '\.\/PathField\.vue'/.test(src), true)
    ok(`${s} renders a PathField`, src.includes('<PathField'), true)
    ok(`${s} no longer imports the builder directly`, src.includes('TargetSpecBuilder'), false)
  }
}

// ── A reach path cannot start from the source ([[B257]]) ──────────
//
// A reach declaration is resolved for the whole world, with no subject and no
// source, so `select source` errors and the path selects nobody — silently, since
// the declaration *is* present. The author authored exactly that on 2026-09-29 and
// saw a rule that did nothing; the builder must not offer the option, and a stored
// `source` step must stay visible so an existing declaration is not mangled.
{
  const builder = read(find('components/gm/TargetSpecBuilder.vue'))
  ok('the builder knows whether a source may be chosen',
    /allowSource: \{ type: Boolean, default: true \}/.test(builder), true)
  ok('…and gates the `source` option on it, keeping a stored step visible',
    /v-if="sourceElement && \(allowSource \|\| step\.collection === 'source'\)"/.test(builder), true)

  const panel = read(find('components/gm/GmPathEditPanel.vue'))
  ok('GmPathEditPanel declares allowSource', /allowSource: \{ type: Boolean, default: true \}/.test(panel), true)
  ok('GmPathEditPanel forwards it to the builder', /:allow-source="allowSource"/.test(panel), true)

  const fieldSrc = read(find('components/gm/PathField.vue'))
  ok('PathField declares allowSource', /allowSource: \{ type: Boolean, default: true \}/.test(fieldSrc), true)
  ok('PathField hands it to the child panel', /allowSource: props\.allowSource/.test(fieldSrc), true)

  const reach = read(find('components/gm/ReachEditor.vue'))
  ok('the reach editor turns the source option off', /:allow-source="false"/.test(reach), true)
}

// ── Conditions are an ordered, reorderable list ───────────────────
{
  const ce = read(find('components/gm/ConditionEditor.vue'))
  ok('condition rows render through GmList', /<GmList[\s\S]{0,200}reorderable/.test(ce), true)
  ok('…with a drag handle (the rows are full of form controls)', /<GmList[\s\S]{0,200}drag-handle/.test(ce), true)
  ok('…and a commit handler', /@reorder="onReorder"/.test(ce), true)
  ok('the move rewrites the list', /function onReorder\(from, to\)/.test(ce), true)
}

// ── A reach declaration is a path plus a relationship ─────────────
//
// [[Dynamic SFX Reach]]: the path *yields* the owners, so a declaration is not a
// gate. Two things distinguish it from the acquire path it replaced and are worth
// pinning: it is **typed by the rule's `Source`** (a path ending anywhere else is
// not a reach declaration), and it carries one of two **flavours**.
{
  const re = read(find('components/gm/ReachEditor.vue'))
  ok('ReachEditor renders exactly one PathField per declaration',
    (re.match(/<PathField/g) || []).length, 1)
  ok('…typed by the rule\'s source — the element a path must land on',
    /elements: \[props\.sourceElement\]/.test(re), true)
  // The destination is the element and *only* the element: `literal` selects one
  // owner and `select locations` selects many, so constraining cardinality here
  // would refuse a legitimate declaration.
  ok('…and the destination is exactly that element, nothing more',
    /\{ elements: \[props\.sourceElement\] \}/.test(re), true)
  ok('…with both flavours declared',
    /value: 'granted'/.test(re) && /value: 'offered'/.test(re), true)
  ok('a new declaration starts offered (the gentler of the two)',
    /flavour: 'offered'/.test(re), true)
  ok('ReachEditor derives no type of its own — the builder does that',
    /traceTargetSpec/.test(re), false)

  const panel = read(find('components/gm/GmSfxEditPanel.vue'))
  ok('the SFX panel authors reach through it', /<ReachEditor v-model="draft\.reach"/.test(panel), true)
  ok('…and hands it the source element', /<ReachEditor[\s\S]{0,120}:source-element="sourceElement"/.test(panel), true)
}

// ── A duration that is set is never hidden ────────────────────────
//
// The rule-level `duration` used to default to one roll; the editor round-tripped
// it and wrote it into 42 rules nobody had authored, and it was invisible in the
// panel where it mattered. Two shapes keep that from returning: the editor must not
// fabricate a duration, and a set duration must render even where the action has no
// use for one — a hidden value is one you cannot clear.
{
  // `find`/`read` walk `.vue` files only; this one is a composable.
  const edit = readFileSync(join(SRC, 'composables', 'useSfxEdit.js'), 'utf8')
  ok('the SFX editor fabricates no duration fallback',
    /remaining:\s*1\s*\}\],\s*combine/.test(edit), false)
  ok('…every duration it seeds is an empty timer list',
    (edit.match(/timers: \[\], combine: 'FIRST_TO_FIRE'/g) || []).length, 3)

  const form = read(find('components/gm/EffectForm.vue'))
  ok('the effect form decides visibility from "is it offered OR is it set"',
    /const durationShown = computed\(\(\) =>\s*durationOffered\.value \|\| \(newEffect\.duration\?\.timers \|\| \[\]\)\.length > 0\)/.test(form), true)
  ok('…and the duration field is gated on that, not on "offered" alone',
    /<div v-if="durationShown" class="ee-field">/.test(form) && !/<div v-if="durationOffered"/.test(form), true)
  ok('…with the two explanations alternating on "offered"',
    /<p v-if="durationOffered" class="ee-help">/.test(form) && /<p v-else class="ee-help">/.test(form), true)

  // …and "offered" must be knowable without opening the path's child panel. It turns on
  // the element the path lands on, and reading that only from the builder inside the
  // panel made an unknown read as "not applicable": a stored timer showed the *leftover*
  // explanation and save dropped it (`duration: durationOffered ? … : null`).
  const pathField = read(find('components/gm/PathField.vue'))
  ok('a path reports its destination without opening the child panel',
    /const \{ traceSpec \} = useTargetCatalog\(\)/.test(pathField)
      && /^onMounted\(runTrace\)$/m.test(pathField), true)
  ok('…traced from the same steps the row summarises',
    /^\s*const res = await traceSpec\(steps\.value, props\.destination, props\.sourceElement \|\| null, props\.variables \|\| null\)$/m.test(pathField), true)
  ok('…and re-traced when the path changes',
    /^watch\(steps, scheduleTrace, \{ deep: true \}\)$/m.test(pathField), true)

  const panel = read(find('components/gm/GmSfxEditPanel.vue'))
  ok('the SFX panel calls the rule duration what the Active rail calls it',
    /<label>Duration<\/label>/.test(panel), true)
}

// ── How many they pick: a toggle for `choose`, a number for `random` ──
//
// The author, 2026-09-27: *"when I enter 'N' into the choose.pick input, it sets
// it to '1' instead"*, then *"change the amount choice to toggle between 'choose
// one' and 'choose multiple'"*. The number never capped anything — it only chose
// single-pick vs multi-select — so a `choose` now says which of the two it is, and
// `null` is the multiple side rather than a magic number. The **aggregate** row's
// pick is genuinely numeric (an exact sample size) and keeps its number input.
{
  const b = read(find('components/gm/TargetSpecBuilder.vue'))
  // Read the *hints*, not the file: comments explaining these fixes quote the old
  // copy, so a whole-file regex matches an explanation and fails on correct code.
  const hints = [...b.matchAll(/<em>(.*?)<\/em>/g)].map((m) => m[1]).join(' | ')
  ok('the sample-size hint names a number, never a bare N',
    /2 or more = subset/.test(hints) && /\bN = (multi-select|subset)/.test(hints), false)
  ok('the aggregate count input is still a number input',
    /<input type="number" min="1" :value="step\.count \?\? 1"/.test(b), true)
  ok('an unusable value falls back to one rather than to nothing',
    /Number\.isFinite\(n\) && n >= 1 \? n : 1/.test(b), true)

  // A `choose` is a one/multiple toggle, and its multiple side is `null`.
  ok('a choose step is a one/multiple toggle',
    /<div v-else-if="step\.kind === 'choose'"[\s\S]{0,600}<SegmentedControl/.test(b)
      && /label: 'Choose one'/.test(b) && /label: 'Choose multiple'/.test(b), true)
  ok('…whose multiple side is null, not a magic number',
    /const MULTI = null/.test(b) && /step\.count == null \? MULTI : ONE/.test(b), true)
  ok('…written straight through, so the stored count is 1 or null',
    /step\.count = \(mode == null \? null : Number\(mode\)\)/.test(b), true)

  const wiz = read(find('components/gm/EffectTargetWizard.vue'))
  // A nullable count must be read as *multiple*: `null > 1` is false in JS, which
  // is exactly how a null would silently become a single pick.
  ok('the wizard reads a null count as multiple, not as a single pick',
    /const isMultiple = computed/.test(wiz) && /n == null \|\| n > 1/.test(wiz), true)
  ok('…and says "any number" rather than naming a cap it does not enforce',
    /'Select any number\.'/.test(wiz), true)

  // A list-valued field (`known_to`, `tags`, `universes`) is matched with
  // `contains`: a pick that set `==` or `in` would write a step the resolver
  // evaluates against the whole list, which is never true.
  ok('a pick on a list field sets contains, not an operator that cannot match',
    /function isListField\(i\)/.test(b)
      && /if \(isListField\(i\)\) \{[\s\S]*?step\.operator = 'contains'/.test(b), true)
  ok('…and list-ness is read from the field\'s declared operators',
    /return ops\.includes\('contains'\) && !ops\.includes\('in'\)/.test(b), true)

  // Filling in a value must land in the list family without overwriting a
  // deliberate choice *within* it: picking a value for "nobody knows this" has to
  // stay a `not contains`. Both fill-in sites (the tags editor and the id picker)
  // go through the same guard.
  ok('a pick keeps a deliberate "not contains" instead of resetting it',
    /const LIST_OPERATORS = \['contains', 'not contains'\]/.test(b)
      && (b.match(/!LIST_OPERATORS\.includes\(step\.operator\)/g) || []).length === 2, true)
}

// ── A choice table appears where the question was raised ──────────
//
// The author's rule (2026-09-26): a manual press on a sheet asks on the sheet, a roll
// asks in the roller, and an automatic rule asks in a floating panel. The server tags
// every choice with its `origin`, the app shell routes by it, and the roller no longer
// resolves answers itself — it hands them up, so one owner carries the origin across a
// follow-up instead of three hosts each guessing.
{
  const app = read(find('App.vue'))
  ok('the shell routes choices by origin',
    /const rollerChoices = computed/.test(app) && /const sheetChoices = computed/.test(app), true)
  ok('…the roller gets everything that is not a sheet question',
    /:sfx-choice-request="rollerChoices"/.test(app), true)
  ok('…and the sheet gets its own', /:sfx-choice-request="sheetChoices"/.test(app), true)
  ok('…answered through one pair of handlers',
    /async function answerSfxChoices\(/.test(app) && /function clearSfxChoicesAll\(/.test(app), true)

  // The third host ([[B230]]). Its two silent failure modes: `auto` falling
  // through to the roller (a question with no reader), and a second card — the
  // wizard draws its own surface, so a host that adds another makes the same
  // table look different depending on where it was raised.
  const splash = read(find('components/app/SplashPanel.vue'))
  ok('the shell has a third routing bucket for automatic rules',
    /const autoChoices = computed/.test(app), true)
  ok('…and the roller excludes it rather than showing it by default',
    /filter\(\(c\) => !\['sheet', 'auto'\]\.includes\(c\.origin \|\| 'roll'\)\)/.test(app), true)
  ok('…the splash is mounted with the origin-carrying handlers',
    /<SplashPanel/.test(app)
      && /answerSfxChoices\(r, 'auto'\)/.test(app)
      && /loopSfxChoice\(c, 'auto'\)/.test(app), true)
  ok('…and the question goes to its own entity, which is not always the acting one',
    /entity_id \|\| props\.entityId/.test(splash), true)

  // The activation splash ([[B229]]): one surface, two faces. The prompt face is
  // the wizard and waits; the note face reports and fades.
  ok('the splash is the prompt face — the wizard, positioned, not re-drawn',
    /<EffectTargetWizard/.test(splash) && /position: fixed/.test(splash), true)
  ok('…with one surface, not a second card of its own token set',
    /background: var\(--bg-panel-solid\)/.test(splash), true)
  ok('…and no timer on the question: only the wizard\'s own Cancel leaves it',
    /'A rule is asking for a choice'/.test(splash)
      && !/setTimeout|setInterval|autoDismiss/.test(splash), true)
  // Both of these bit for real (`emit` in the first host, `props` in this one):
  // a bare defineProps/defineEmits leaves the identifier undefined, which reads
  // as "the click did nothing" or a blank splash rather than as a missing
  // declaration.
  ok('the splash captures what its template and computeds read',
    /const props = defineProps\(/.test(splash) && /const emit = defineEmits\(/.test(splash), true)
  ok('…and the SSE client subscribes to the note event, or it is dropped silently',
    /'effects_changed'/.test(read(`${SRC}/composables/useSSE.js`)), true)
  ok('…and it carries the note face, announced and non-interactive',
    /role="status"/.test(splash) && /sp-note-lines/.test(splash), true)
  ok('the shell owns the note queue and its dwell',
    /function pushSplashNote/.test(app) && /SPLASH_DWELL = \{ change: 2000, summary: 5000 \}/.test(app), true)
  ok('…queued one at a time rather than stacked',
    /splashNote\.value = splashQueue\.value\.shift\(\) \|\| null/.test(app), true)
  ok('…and held while a question is up, so a note cannot fade unseen behind it',
    /watch\(\(\) => autoChoices\.value\.length/.test(app), true)
  ok('a change is aimed at the entity acting, or the place they are standing',
    /evt\.data\.entity_id === entityId\.value[\s\S]{0,120}evt\.data\.location_id === currentLocationId\.value/.test(app), true)

  const roller = read(find('components/DiceRoller.vue'))
  ok('the roller hands the answer up rather than resolving it',
    /emit\('sfx-choice-answer', resolutions\)/.test(roller), true)
  ok('…and no longer owns the answer event',
    /sfx-choice-resolved/.test(roller), false)

  const sheet = read(find('components/CharacterSheet.vue'))
  ok('the sheet renders a choice table when one is routed to it',
    /v-if="sfxChoiceRequest && sfxChoiceRequest\.length"/.test(sheet)
      && /<EffectTargetWizard/.test(sheet), true)
  ok('…and emits the same three events the roller does',
    /'sfx-choice-answer', 'sfx-choice-cancel', 'sfx-choice-loop'/.test(sheet), true)

  const apply = readFileSync(join(SRC, 'composables', 'useEffectApplication.js'), 'utf8')
  ok('the resolve call carries the origin back for the follow-up',
    /resolveEffectTargets\(entityId: \$entityId, resolutions: \$resolutions, origin: \$origin\)/.test(apply), true)

  // Cancelling a question takes the activation back (the author's rule, 2026-09-26):
  // "cancelling the choice table cancels the SFX" — the same take-back the sheet's own
  // toggle-off makes. Scoped to a question a *press* raised, and never a loop decline,
  // which is the loop ending rather than a bargain being undone.
  ok('cancelling a question takes the activation back',
    /function endActivationsBehindChoices\(choices\)/.test(app)
      && /function clearSfxChoicesAll\(\) \{\s*endActivationsBehindChoices\(sfxChoiceRequest\.value\)/.test(app), true)
  ok('…through the same take-back the sheet\'s own toggle-off makes',
    /endSfx: apiEndSfx/.test(app)
      && /apiEndSfx\(entity, sfxId, true\)/.test(app), true)
  // The third argument is `pending` ([[B259]]): an activation blocked on its *first*
  // question has booked nothing, so an end that only reported booked rows went silent
  // and the chip stayed lit. Asserted here because this regex is what broke when the
  // flag was added — the call changed and the check did not.
  ok('…and says the activation is blocked on the question, not merely empty',
    /pending: true/.test(app) && /apiEndSfx\(entity, sfxId, true\)/.test(app), true)
  ok('…only for an activation a press started',
    /\(c\?\.origin \|\| 'roll'\) !== 'sheet'/.test(app), true)
  ok('…naming the rule the question belongs to',
    /const sfxId = c\.source_sfx_id \|\| c\.sfx_id/.test(app), true)
  ok('…once per activation, however many questions it raised',
    /ends\.some\(\(e\) => e\.entity === entity && e\.sfxId === sfxId\)/.test(app), true)
  ok('…and declining a loop is not a take-back',
    /if \(c\?\.loop\) continue/.test(app), true)

  // The owner path is a declared **anchor** reference ([[B261]]): it renders as a
  // ref row like every other input, and the older standalone block becomes its
  // fallback — shown only while no ref is authored, so both cannot appear at once.
  const effectForm = read(find('components/gm/EffectForm.vue'))
  // A fallback field whose reference reads identically is a duplicate, not a
  // fallback: `travel` rendered two "Entity" inputs for one question ([[B261]]).
  ok('a fallback that duplicates its reference steps aside at once',
    /declared\.label === f\.label\) return false/.test(effectForm), true)

  ok('the owner path defers to its declared reference',
    /const ownerFallbackShown = computed/.test(effectForm)
      && /!\(newEffect\.refs\?\.owner\?\.spec\?\.steps \|\| \[\]\)\.length/.test(effectForm), true)
  ok('…and the standalone owner block is gated on that fallback',
    /ownerFallbackShown\.value && !declaredNames\.has\('owner'\)/.test(effectForm)
      && /if \(name === 'owner' && ownerFallbackShown\.value\)/.test(effectForm), true)
}

// ── A rule authored from an owner's screen lands on that owner ────
//
// The author, 2026-10-09: *"I just authored `sfx-roll-table`, but apparently it's
// not in the GM bucket?"* — and it was not. The picker's `+ New SFX` attaches the
// rule it creates; the management panel's own button created the rule and left it
// attached to nothing, so a rule authored while standing in a bucket appeared in no
// bucket. Attachment is a grant on the owner side, so the screen that knows the
// owner has to make it — and both buttons now do.
{
  const mgmt = read(find('components/gm/GmSfxManagementPanel.vue'))
  ok('creating a rule from an owner screen attaches it to that owner',
    /'sfx-created': async \(created\) => \{[\s\S]{0,400}addOwnerSfx\(\[\{ ownerType: ref\.ownerType, ownerId: ref\.ownerId \}\], created\.id\)/.test(mgmt), true)
  ok('…and the editor is told where the rule lives',
    /props: \{ sfx: null, prefillName: search\.value\.trim\(\), owner: ref \}/.test(mgmt), true)
  ok('…and the owner is re-read, so the member is on it rather than merely created',
    /addOwnerSfx\([\s\S]{0,260}fetchOwners\(ownerType\.value\)/.test(mgmt), true)

  // The path that already worked stays working — this is the same guarantee, not a
  // replacement for it.
  const picker = read(find('components/gm/GmSfxPickerPanel.vue'))
  ok('the picker still attaches what it creates',
    /'sfx-created': \(created\) => \{\s*emit\('add-sfx', created\.id\)/.test(picker), true)
}

// ── A roll-table menu opens the table it names ────────────────────
//
// The author, 2026-10-09: *"I choose the `rt-earth-regions` roll table, I expect to
// see the table and be able to roll against it. But the table doesn't appear."*
// The table is a **reference** (`refs.table`) since the migration, and the client's
// only gate read the positional `target` the migration emptied — so every menu rule
// opened nothing, silently. A literal reference names the table outright and opens
// on the click; a path reference names it by *asking*, so the answer opens it.
{
  const literal = { type: 'roll_table', action: 'menu', target: '',
                    refs: { table: { value: 'rt-earth-regions', spec: null } } }
  ok('a literal table reference names the table', rollTableIdOf(literal), 'rt-earth-regions')
  ok('…and the positional field still works for older content',
    rollTableIdOf({ type: 'roll_table', action: 'menu', target: 'rt-legacy' }), 'rt-legacy')

  const path = { type: 'roll_table', action: 'menu', target: '',
                 refs: { table: { value: '', spec: { steps: [{ kind: 'select' }, { kind: 'choose' }] } } } }
  ok('a path reference names no table on its own', rollTableIdOf(path), '')
  ok('the answer to its last step is the table',
    rollTableIdFromAnswer({ effect: path, field: 'refs.table',
                            answers: [{ stepIndex: 1, ids: ['rt-earth-regions'] }] }), 'rt-earth-regions')
  ok('…an earlier step of the same path is not',
    rollTableIdFromAnswer({ effect: path, field: 'refs.table',
                            answers: [{ stepIndex: 0, ids: ['three_realms'] }] }), '')
  ok('…and another action\'s answer never opens a table',
    rollTableIdFromAnswer({ effect: { type: 'travel', action: 'move' }, field: 'refs.location',
                            answers: [{ stepIndex: 1, ids: ['loc-1'] }] }), '')

  const sheet = read(find('components/CharacterSheet.vue'))
  ok('the sheet asks for its rules\' references',
    /effects \{ timing type action target entity result refs \}/.test(sheet), true)
  // Two hosts show a question: the entity sheet and the roaming GM's play surface —
  // and a GM-bucket rule is pressed on the *latter*.
  ok('…and opens the table from the answer, on both wizard hosts',
    (sheet.match(/@resolve="onChoiceResolved"/g) || []).length, 2)
  ok('…through one shared decision rather than a local copy',
    /const menu = rollTableMenuEffect\(sfxCatalog\.value\[sfxId\]\)/.test(sheet)
      && /function rollTableMenuEffect\(/.test(sheet), false)
}

console.log(fail ? `\n  ${fail} failed\n` : '\n  all clear\n')
process.exit(fail ? 1 : 0)
