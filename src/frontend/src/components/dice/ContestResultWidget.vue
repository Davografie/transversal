<template>
  <div class="contest-result-widget">
    <div class="contest-sides">
      <div class="contest-side" :class="sideClasses('challenger')">
        <span class="side-icon">{{ sideIcon('challenger') }}</span>
        <span class="side-name">{{ challengerName }}</span>
        <span v-if="result.challenger" class="side-sum"><strong class="result-num">{{ result.challenger.total }}</strong></span>
        <span v-else class="side-empty">gave in</span>
        <span v-if="sideIsWinner('challenger') && appliedEffectDie" class="side-effect">
          <template v-if="steppedDown && winnerOriginalEffectDie">
            <DieIcon :die="winnerOriginalEffectDie" class="side-effect-die original" />
            <span class="step-arrow">↓</span>
          </template>
          <DieIcon :die="appliedEffectDie" class="side-effect-die" />
        </span>
        <span v-else-if="!sideIsWinner('challenger') && loserTakenOut" class="side-effect">taken out</span>
      </div>
      <div class="contest-side" :class="sideClasses('defendant')">
        <span class="side-icon">{{ sideIcon('defendant') }}</span>
        <span class="side-name">{{ defendantName }}</span>
        <span v-if="result.defendant" class="side-sum"><strong class="result-num">{{ result.defendant.total }}</strong></span>
        <span v-else class="side-empty">gave in</span>
        <span v-if="sideIsWinner('defendant') && appliedEffectDie" class="side-effect">
          <template v-if="steppedDown && winnerOriginalEffectDie">
            <DieIcon :die="winnerOriginalEffectDie" class="side-effect-die original" />
            <span class="step-arrow">↓</span>
          </template>
          <DieIcon :die="appliedEffectDie" class="side-effect-die" />
        </span>
        <span v-else-if="!sideIsWinner('defendant') && loserTakenOut" class="side-effect">taken out</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import DieIcon from '@/components/DieIcon.vue'

// The two-sided contest scoreboard: what each side rolled, who won (🏆 / 💀 on
// your own side), and the effect die the winner applies — showing the original
// die and a ↓ when it stepped down. `result` is the server's contest payload;
// `iWon` / `isChallenger` are the viewer's relationship to it.
const props = defineProps({
  result: { type: Object, required: true },
  challengerName: { type: String, default: '' },
  defendantName: { type: String, default: '' },
  iWon: { type: Boolean, default: false },
  isChallenger: { type: Boolean, default: false },
  appliedEffectDie: { type: String, default: null },
})

function sideIsMine(side) { return (side === 'challenger') === props.isChallenger }
function sideIcon(side) { return sideIsMine(side) ? (props.iWon ? '🏆' : '💀') : '' }
function sideClasses(side) {
  const mine = sideIsMine(side)
  return { mine, winner: mine && props.iWon, loser: mine && !props.iWon }
}
function sideIsWinner(side) {
  const challengerWon = props.result.winner === 'player'
  return (side === 'challenger') === challengerWon
}

const loserTakenOut = computed(() => !!props.result?.taken_out)
const winnerOriginalEffectDie = computed(() => {
  const side = props.result.winner === 'player' ? 'challenger' : 'defendant'
  return props.result[side]?.effect_die || null
})
const steppedDown = computed(() =>
  !!props.appliedEffectDie && !!winnerOriginalEffectDie.value && props.appliedEffectDie !== winnerOriginalEffectDie.value
)
</script>

<style scoped>
.contest-result-widget {
  margin-top: 6px;
  padding: 10px 12px;
  border-radius: 10px;
  background: var(--overlay-4);
  border: 1px solid var(--overlay-12);
  display: flex; flex-direction: column; gap: 8px;
}
.contest-sides { display: flex; gap: 8px; }
.contest-side {
  flex: 1; padding: 8px; border-radius: 8px;
  background: rgba(0,0,0,0.2); border: 1px solid transparent;
  display: flex; flex-direction: column; gap: 2px; font-size: 12px;
}
.contest-side.mine.winner { border-color: var(--success, var(--success)); background: var(--success-12); }
.contest-side.mine.loser { border-color: var(--danger, var(--danger)); background: var(--danger-12); }
.side-icon { font-size: 16px; line-height: 1; }
.side-name { font-weight: 600; color: var(--text); }
.side-sum { color: var(--text); }
.side-sum .result-num { font-size: 22px; }
.contest-side.mine.winner .side-sum .result-num { color: var(--success, var(--success)); }
.contest-side.mine.loser .side-sum .result-num { color: var(--danger, var(--danger)); }
.side-effect { color: var(--text-dim); display: flex; align-items: center; gap: 4px; }
.side-effect-die { width: 26px; height: 30px; }
.side-effect-die.original { opacity: 0.35; filter: grayscale(0.6); }
.step-arrow { font-weight: 700; color: var(--text-dim); }
.side-empty { color: var(--text-dim); font-style: italic; }
</style>
