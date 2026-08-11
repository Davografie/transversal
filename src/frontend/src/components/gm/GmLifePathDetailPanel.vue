<template>
  <div class="lpd-root">
    <div class="lpd-header">
      <span class="lpd-name">{{ lp.name }}</span>
      <span class="lpd-type">{{ lp.type }}</span>
    </div>
    <p class="lpd-desc">{{ lp.description }}</p>

    <!-- Qualification -->
    <div v-if="lp.qualification" class="lpd-subsection">
      <span class="lpd-subtitle">Qualification</span>
      <span class="lpd-detail">Roll {{ tName(lp.qualification.traitId) }} vs {{ lp.qualification.difficulty }}</span>
      <span v-if="lp.qualification.mustBeAtLocation" class="lpd-detail">📍 Must be at {{ lp.qualification.mustBeAtLocation }}</span>
      <span v-if="lp.qualification.draft" class="lpd-detail">📋 Drafts to {{ lp.qualification.draft }}</span>
    </div>
    <div v-else class="lpd-subsection">
      <span class="lpd-subtitle">Qualification</span>
      <span class="lpd-detail">None required — always available</span>
    </div>

    <!-- Discovery -->
    <div v-if="lp.discovery" class="lpd-subsection">
      <span class="lpd-subtitle">Discovery</span>
      <span v-if="lp.discovery.atLocation?.length" class="lpd-detail">📍 At: {{ lp.discovery.atLocation.join(', ') }}</span>
      <span v-if="lp.discovery.knowsEntity?.length" class="lpd-detail">👤 Knows: {{ lp.discovery.knowsEntity.join(', ') }}</span>
      <span v-if="lp.discovery.possessesTrait?.length" class="lpd-detail">🎯 Has trait: {{ tNames(lp.discovery.possessesTrait) }}</span>
      <span v-if="lp.discovery.hasRelationship?.length" class="lpd-detail">🔗 Relationship: {{ lp.discovery.hasRelationship.join(', ') }}</span>
    </div>

    <!-- Curriculum -->
    <div v-if="lp.curriculum?.length" class="lpd-subsection">
      <span class="lpd-subtitle">Curriculum</span>
      <table class="lpd-table">
        <thead><tr><th>Trait</th><th>Create At</th><th>Step Up</th><th>Min Rank</th></tr></thead>
        <tbody>
          <tr v-for="c in lp.curriculum" :key="c.traitId">
            <td>{{ tName(c.traitId) }}</td>
            <td>{{ c.createAt }}</td>
            <td>{{ c.stepUp ? '✅' : '—' }}</td>
            <td>{{ c.minRank }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Survival + Mishaps -->
    <div v-if="lp.survival" class="lpd-subsection">
      <span class="lpd-subtitle">Survival</span>
      <span class="lpd-detail">Roll {{ tNames(lp.survival.traitIds) }} vs {{ lp.survival.difficulty }}</span>
      <span v-if="lp.survival.termPenaltyAfter" class="lpd-detail">📈 +1 difficulty every {{ lp.survival.termPenaltyAfter }} terms</span>
      <div v-if="lp.survival.mishaps?.length">
        <span class="lpd-subsubtitle">Mishaps</span>
        <table class="lpd-table">
          <thead><tr><th>#</th><th>Description</th><th class="lpd-mo-col">Musters Out</th></tr></thead>
          <tbody>
            <tr v-for="(m, i) in lp.survival.mishaps" :key="i">
              <td class="lpd-num">{{ i + 1 }}</td>
              <td>{{ m.description || m }}</td>
              <td class="lpd-mo-col">{{ m.must_muster_out ? '🏁' : '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Events -->
    <div v-if="lp.events?.length" class="lpd-subsection">
      <span class="lpd-subtitle">Events</span>
      <table class="lpd-table">
        <thead><tr><th>#</th><th>Description</th><th>Min Rank</th></tr></thead>
        <tbody>
          <tr v-for="(e, i) in lp.events" :key="i">
            <td class="lpd-num">{{ i + 1 }}</td>
            <td>{{ e.description }}</td>
            <td>{{ e.minRank }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Advancement -->
    <div v-if="lp.advancement" class="lpd-subsection">
      <span class="lpd-subtitle">Advancement</span>
      <span class="lpd-detail">Roll {{ tNames(lp.advancement.traitIds) }} vs {{ lp.advancement.difficulty }}</span>
      <div v-if="lp.advancement.ranks?.length">
        <span class="lpd-subsubtitle">Ranks</span>
        <table class="lpd-table">
          <thead><tr><th>#</th><th>Name</th><th>Benefits</th></tr></thead>
          <tbody>
            <tr v-for="r in lp.advancement.ranks" :key="r.number">
              <td class="lpd-num">{{ r.number }}</td>
              <td>{{ r.name }}</td>
              <td>{{ (r.benefits || []).map(b => b.type || b).join(', ') || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Muster Out -->
    <div v-if="lp.musterOut" class="lpd-subsection">
      <span class="lpd-subtitle">Muster Out</span>
      <span v-if="lp.musterOut.perTermBenefits?.length" class="lpd-detail">Per term: {{ lp.musterOut.perTermBenefits.map(b => b.type || b).join(', ') }}</span>
      <span v-if="lp.musterOut.atRanks" class="lpd-detail">At ranks: {{ JSON.stringify(lp.musterOut.atRanks) }}</span>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  lp: { type: Object, required: true },
  traitNameMap: { type: Object, default: () => ({}) },
})

function tName(id) {
  if (!id) return '—'
  return props.traitNameMap[id] || id.replace(/^trait-/, '').replace(/[-_]\w{4}$/, '').replace(/[-_]/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

function tNames(ids) {
  return (ids || []).map(tName).join(', ') || '—'
}
</script>

<style scoped>
.lpd-root { padding: 0; }
.lpd-header { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.lpd-name { font-weight: 600; font-size: 14px; }
.lpd-type { font-size: 9px; color: var(--text-dim); text-transform: uppercase; background: rgba(255,255,255,0.06); padding: 1px 5px; border-radius: 3px; }
.lpd-desc { font-size: 11px; color: var(--text-dim); margin: 0 0 8px 0; }
.lpd-subsection { margin-top: 8px; }
.lpd-subtitle { display: block; font-size: 9px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 2px; }
.lpd-subsubtitle { display: block; font-size: 8px; color: var(--text-dim); text-transform: uppercase; margin: 4px 0 2px; }
.lpd-detail { display: block; font-size: 10px; color: var(--text-dim); line-height: 1.5; }
.lpd-table { width: 100%; border-collapse: collapse; margin: 4px 0 6px; font-size: 10px; }
.lpd-table th { text-align: left; padding: 2px 6px; border-bottom: 1px solid rgba(255,255,255,0.06); color: var(--text-dim); font-size: 8px; text-transform: uppercase; }
.lpd-table td { padding: 2px 6px; border-bottom: 1px solid rgba(255,255,255,0.03); color: var(--text); }
.lpd-num { width: 24px; text-align: center; color: var(--text-dim); }
.lpd-mo-col { width: 56px; text-align: center; }
</style>
