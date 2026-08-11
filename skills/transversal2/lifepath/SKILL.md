# LifePath Skill

## Purpose
Implement, extend, or debug the Traveller-style life path system (career terms, discovery, trait transfer, relationship ratings) in Transversal.

## Key Files

| File | Purpose |
|------|---------|
| `src/api/src/transversal/domain/__init__.py` | Domain models: `LifePath`, `DiscoveryBlock`, `TransferFlags`, `LifeTerm`, `LifePathType`, `QualificationInfo`, `CurriculumItem`, `SurvivalInfo`, `EventItem`, `RankInfo`, `AdvancementInfo`, `MusterOutInfo` |
| `src/api/src/transversal/db/arango.py` | `LIFE_PATHS` collection constant |
| `src/api/src/transversal/db/repository.py` | CRUD: `create/get/list/update/delete_lifepath()` |
| `src/api/src/transversal/db/seed.py` | Seed life paths — `seed_life_paths(repo)` + `seed_relations_traitset(repo)` |
| `src/api/src/transversal/services/lifepath_discovery.py` | `check_discovery(entity_id, discovery_block, repo) → bool` |
| `src/api/src/transversal/services/lifepath_executor.py` | `take_term(entity, life_path, razmerit, repo)` + `muster_out(entity, repo)` |
| `src/api/src/transversal/services/trait_transfer.py` | `teach_trait`, `gift_trait`, `take_trait`, `resolve_transfer_flags` |
| `src/api/src/transversal/api/graphql/types.py` | Strawberry types: `LifePath`, `TermResult`, `TeachResult`, `GiftResult`, `TakeResult`, `MusterOutResult` |
| `src/api/src/transversal/api/graphql/schema.py` | Queries: `lifePaths`, Mutations: `takeTerm`, `musterOut`, `teachTrait`, `giftTrait`, `takeTrait`, `addRelationshipTrait` |
| `src/api/tests/test_life_paths.py` | Domain model tests (17) |
| `src/api/tests/test_lifepath_discovery.py` | Discovery check tests (12) |
| `src/api/tests/test_life_paths.py` | Domain model tests |
| `src/api/tests/test_trait_transfer.py` | Transfer tests (9) |
| `src/api/tests/test_relationship_ratings.py` | Relationship rating tests (11) |
| `src/frontend/src/components/LifePathWizard.vue` | Step-wise term UI |
| `src/frontend/src/components/CharacterSheet.vue` | Transfer buttons, rated relationship widget, wizard entry |

## Domain Model Quick Reference

### LifePath
```python
LifePath(
    id="lp-{slug}",
    name="Name",
    universe="earth" | "three_realms",
    type=LifePathType.DRIFTER | SECT | GUILD | MERCENARY | TRADE | LINEAGE,
    qualification=QualificationInfo(...),  # None → no qual needed
    discovery=DiscoveryBlock(...),         # None → always visible
    curriculum=[CurriculumItem(...)],
    survival=SurvivalInfo(...),            # None → no survival risk
    events=[EventItem(...)],
    advancement=AdvancementInfo(...),      # None → no rank ladder
    muster_out=MusterOutInfo(...),
)
```

### DiscoveryBlock (5 conditions, any one met → discovered)
```python
DiscoveryBlock(
    at_location=["loc-..."],           # entity.current_location in list
    knows_entity=["gmc-..."],          # entity.known_to ∩ list non-empty
    possesses_trait=["trait-..."],     # has traitsetting for trait
    has_trait_rating={"trait-...": DieType.D8},  # trait + minimum die
    has_relationship=["entity-..."],   # relationship edge exists
)
```

### TransferFlags
On `Trait` and `TraitSet`: `transfer_flags: TransferFlags(teachable=True, giftable=False, takable=True)`. Per-trait overrides per-traitset. Resolution: trait → traitset → all False.

### Provenance (TraitSetting)
`source_type`: "taught" | "gifted" | "taken" | "life_path_term" | "event"
`source_entity_id`, `source_trait_setting_id`, `source_life_path_id`, `source_term_number`, `stolen`

## The Term Loop (5 phases)

```
Choose Path → Learn → Survive → Event → Advance → (repeat or Muster Out)
```

1. **Qualification**: Roll trait vs difficulty. Fail → draft or retry. Razmerit can step up dice. No qual block → auto-qualify.
2. **Learn**: Always succeeds. Picks next curriculum item at entity's rank. Creates new TraitSetting or steps up existing. **Always resolve traitset_id from trait registry** — never leave empty.
3. **Survive**: Roll survival traits vs difficulty. Term penalties stack (per-path + global/7). Failure → mishap (complication trait, razmerit loss, rank demotion, forced muster).
4. **Event**: Random selection from eligible events (filtered by rank). Can create traits, discover paths, earn razmerit.
5. **Advance**: Roll vs difficulty. Success → rank up, unlock curriculum, gain benefits.

**Muster Out**: Between terms. Voluntary → no re-entry penalty. Mishap-forced → rank resets to 0 on re-entry. Calculates per-term razmerit (1d6 × terms) + rank bonuses.

## Docker Testing

```bash
# Seed/re-seed life paths
docker compose exec api python -c "
from transversal.db.seed import seed_life_paths
from transversal.db.repository import EntityRepository
seed_life_paths(EntityRepository())
"

# Quick mutation test
curl -s -X POST http://localhost:8085/api/v1/graphql \
  -H "Content-Type: application/json" \
  -d '{"query": "mutation { takeTerm(entityId: \"kael-1\", lifePathId: \"lp-drifter-three-realms\") { qualification { success } learn { traitName } termNumber } }"}'
```

## Common Pitfalls

### Empty traitset_id crashes GraphQL
When creating `TraitSetting` manually (in executor, transfer, events), always resolve `traitset_id` from the trait registry:
```python
trait = repo.get_trait(trait_id)
resolved_ts_id = trait.traitset_id if trait else ""
```

### Non-existent trait IDs in seed data
Life path curriculum/qualification/survival `trait_id` values must reference actual traits in the `traits` collection. Check with:
```python
repo.get_trait(trait_id)  # must not be None
```

### Frontend watch without immediate
Vue `watch` on `props.visible` needs `{ immediate: true }` so it fires when the component mounts with `visible=true`:
```javascript
watch(() => props.visible, (v) => { if (v) loadPaths() }, { immediate: true })
```

### Null qualification from continuing term
When entity is already in a path, `take_term` returns `qualification: null`. Frontend must handle this:
```html
<button v-if="!result.qualification || result.qualification?.success">Continue</button>
```

### transferFlags resolver requires possibleSfxIds
Both `transfer_flags` and `possible_sfx_ids` are separate `@strawberry.field` resolvers on the GraphQL `TraitSetting` type. Adding one must not remove the other.

## Design Doc

Full spec: `docs/Game Design/Character Growth.md`
