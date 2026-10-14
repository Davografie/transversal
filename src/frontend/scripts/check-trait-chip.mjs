/**
 * Static check: the trait chip accepts both a **rating** and a **roll**.
 *
 * `location/TraitChip.vue` is drawn in two places now. The location viewer passes
 * plain die *types* (`['d8','d8']`) and shows a rating; the activation splash's
 * target passes **rolled** dice (`{ die, result, hitch }`) so the chip shows the face
 * each die actually produced ([[B287]]). One component, two inputs.
 *
 * The failure mode is silent and looks correct: if the rolled shape stops being
 * normalised, `String(d)` on an object is `[object Object]`, `traitDiceGroups` drops
 * it (`if (!die.die) continue`), and the chip renders **no dice at all** — a target
 * with no opposition behind it, which reads as "nothing was rolled" rather than as a
 * bug. And if the `:die="die.die"` binding reverts to `:die="die"`, every die draws
 * as an unknown type.
 *
 *   docker run --rm \
 *     -v /path/to/src/frontend/scripts:/app/scripts:ro \
 *     -v /path/to/src/frontend/src:/app/src:ro \
 *     -w /app transversal2-frontend:latest node scripts/check-trait-chip.mjs
 */
import { readFileSync } from 'node:fs'

let pass = 0, fail = 0
const ok = (name, bad) => {
  bad.length ? fail++ : pass++
  console.log(`  ${bad.length ? 'FAIL' : 'PASS'}  ${name}${bad.length ? `\n         ${bad.join('\n         ')}` : ''}`)
}
const yes = (name, cond, got = '') => ok(name, cond ? [] : [String(got)])

const CHIP = 'src/components/location/TraitChip.vue'
const VIEWER = 'src/components/LocationViewer.vue'
const SPLASH = 'src/components/app/SplashPanel.vue'

const chip = readFileSync(CHIP, 'utf8')
const viewer = readFileSync(VIEWER, 'utf8')
const splash = readFileSync(SPLASH, 'utf8')

// ── 1. both input shapes ────────────────────────────────────────────────────
{
  yes('a plain die type is still a die (the map passes strings)',
    /typeof d === 'string'/.test(chip) && /result: null, hitch: false/.test(chip))
  yes('…and a rolled entry keeps its face',
    /result: d\?\.result \?\? null, hitch: !!d\?\.hitch/.test(chip))
  yes('an entry with no die type is dropped, not drawn as a blank chip',
    /if \(!die\.die\) continue/.test(chip))
}

// ── 2. the die icon is what draws a face ────────────────────────────────────
{
  yes('the type goes to DieIcon as a type, never as the whole entry',
    /:die="die\.die"/.test(chip) && !/:die="die"/.test(chip))
  yes('…and the rolled value and hitch ride along',
    /:result="die\.result"/.test(chip) && /:is-hitch="die\.hitch"/.test(chip))
  yes('DieIcon prints the result in preference to the label (the face, not the type)',
    /if \(props\.result !== null\) return String\(props\.result\)/.test(readFileSync('src/components/DieIcon.vue', 'utf8')))
}

// ── 3. one staircase per die type, and the lane that fits it ────────────────
{
  yes('dice are grouped by type, ascending',
    /byType\.get\(die\.die\)\.push\(die\)/.test(chip)
      && /groups\.sort\(\(a, b\) => parseInt\(a\[0\]\.die\.slice\(1\), 10\) - parseInt\(b\[0\]\.die\.slice\(1\), 10\)\)/.test(chip))
  yes('…and the reserved lane is still measured from the groups, so dice cannot sit on the words',
    /ratingWidth = computed\(\(\) => \{[\s\S]{0,240}groups\.reduce\(/.test(chip))
}

// ── 3b. spread, for a roll whose faces must be readable ─────────────────────
{
  yes('a rolled chip can spread its dice instead of fanning them',
    /diceLayout: \{ type: String, default: 'fan' \}/.test(chip)
      && /spread\.value \? 2 : -15/.test(chip) && /spread\.value \? 0 : 3/.test(chip))
  yes('…and the reserved lane is measured from the same step, so it cannot disagree',
    /stepX\.value \* \(group\.length - 1\)/.test(chip))
  yes('…and the splash is the surface that asks for it',
    /dice-layout="spread"/.test(splash))
}

// ── 4. the two call sites ───────────────────────────────────────────────────
{
  yes('the location viewer still draws the chip', /<TraitChip/.test(viewer))
  yes('…and the splash draws the same one rather than a second chip',
    /import TraitChip from '@\/components\/location\/TraitChip\.vue'/.test(splash)
      && /<TraitChip/.test(splash))
  yes('…passing rolled dice, so the faces are what it received',
    /:trait="chip"/.test(splash) && /<div v-if="currentNote\.chips\?\.length" class="sp-chips">/.test(splash))
}

console.log(fail ? `\n  ${fail} failed\n` : '\n  all clear\n')
process.exit(fail ? 1 : 0)
