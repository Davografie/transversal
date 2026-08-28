---
title: SFX Source Model
tags:
  - transversal
  - technical
  - sfx
  - effects
  - targeting
  - architecture
  - plan
aliases:
  - SFX Source
  - Source Kind
  - SFX Ownership Type
status: implemented
---

# SFX Source Model

An SFX can declare **what kind of thing carries it** (`source_kind`), separate from **when it fires** (`trigger`). When it activates, the carrying thing is exposed as a **typed variable named after its kind** — so a trait-SFX yields `{trait_setting}`, an entity-SFX yields `{entity}` — and the editor/type-checker know exactly which fields that variable has.

> [!note] Status
> Implemented. Settled in discussion 2026-08-28. Supersedes the dangling `{source_trait}` token (which was reserved in `sfx_validation.py` but never resolved anywhere). `source_kind` is stored on `SFX`, exposed as `sourceKind` in GraphQL, and resolved at fire time via `target_resolver.resolve_source`; the `SOURCE_KINDS` seam in `target_catalog.py` is the single touch point for the future entity/projection redesign.

## Goal

Two problems at once, both flagged in [[to-do]]:

1. **Nonsensical owner/SFX combinations** — an SFX attached to a surface it can't meaningfully act from.
2. **No way to reference what activated the SFX** — "the trait I got activated on steps up" is unexpressible today.

`source_kind` solves both: it **enforces** which surface can carry an SFX, and it **declares** the typed variable the author writes effects against.

## Two axes, one SFX

- **`trigger`** = *when/how* it fires (`manual`, `on_roll`, `on_session_start`, `hitch`…). It declares **event** variables (`{effect_die}`, `{total}`, `{contest_entity_opponent}`).
- **`source_kind`** = *where it lives / what carried it*. It declares the **source** variable.

They stay separate. `manual` is **not** split into four triggers — the only thing that varies per source kind is the variable's type, and a filter on `source_kind` gives the "show me trait-SFX" separation without polluting the trigger vocabulary.

## Vocabulary

`source_kind` is **instances only** — registry entries (`Trait`, `TraitSet`) are never a source, because an SFX fires on a concrete thing with concrete state (a trait *instance* has `rating`/`polarity`; a trait *definition* has neither). `Trait.default_sfx_ids` stays a **provisioning template** (seeded onto instances at grant time), never a source.

| `source_kind` | variable | it is (behind the scenes) | example fields |
|---|---|---|---|
| `trait_setting` | `{trait_setting}` | a `TraitSetting` (instance) | `rating`, `rating_type`, `polarity`, `entity_id`, `traitset_id` |
| `traitset_setting` | `{traitset_setting}` | a `TraitSetSetting` (instance) | `entity_id`, `traitset_id`, `limit` |
| `entity` | `{entity}` | an `Entity` | `razmerit`, `type`, `current_location`, `current_universe` |
| `projection` | `{projection}` | a `Projection` | `entity_id`, `current_location`, `type` |

`source_kind` unset = buckets (`table`, `gm`) and passive rules (which are deliberately origin-less).

### Naming

- `{trait_setting}` (not `{trait}`) — `{trait}` already means the **registry** id in `on_trait_learn`/`on_trait_change`/`on_trait_offered`.
- `{traitset_setting}` (not `{traitset}`) — `{traitset}` already means the **registry** id in `on_trait_change`.

Author-facing vocabulary hides the registry/instance split; the catalog maps each `source_kind` to the instance element (`trait_setting` → `traitsetting`, `traitset_setting` → `traitsetsetting`).

## Declarative, not derived

`source_kind` is **authored** on the SFX (a dropdown), not discovered from ownership at fire time. The split:

- **declared** → `source_kind` (the type, authored once).
- **resolved** → the variable's *value* (the concrete id, at activation time).

So the server never guesses a type; it only fills an id of a type it already expects. No polymorphism, no union.

### UX

1. **SFX editor → "Source" dropdown**: `None` (default), `Trait setting`, `Trait set setting`, `Entity`, `Projection`.
2. Picking one **changes the variable palette** — the author sees `{trait_setting}` with its fields (`rating`, `rating_type`, `polarity`, …) *before* anything runs.
3. The choice is **stored on the SFX** (`SFX.source_kind`).
4. The **character sheet places it accordingly** — a `trait_setting` SFX renders on trait cards, an `entity` SFX on the entity, etc.
5. **Enforcement follows** — `sfx_validation.py` rejects attaching an SFX to a surface that doesn't match its `source_kind`; the GM ownership panel only offers compatible surfaces.

### Consequence

Because `source_kind` is singular and enforced, one SFX can't be both a trait-SFX and an entity-SFX. To get the same effect on both, author two SFX. This is the accepted trade for "author knowing what they're authoring for."

## Scope asymmetry

`{source}` is **essential for `manual`** (zero context today) and **mostly validation for auto-fire triggers**, whose event variables already carry "what happened":

- `manual` + `source_kind: trait_setting` → `{trait_setting}` = the trait instance clicked.
- `on_trait_change` + `source_kind: trait_setting` → the *event* already carries `{trait}`; `source_kind`'s job here is enforcement (reject "trait-SFX attached to an entity"), not reference.

`source_kind` is a field on *every* SFX (for enforcement), but `{source}` only resolves when the activation has a meaningful origin (manual; possibly menu triggers — see open questions).

## Catalog work this design implies

1. **`traitsetsetting` element** — new in `target_catalog.ELEMENT_TYPES` (the domain object `TraitSetSetting` already exists with repo methods, but the catalog has no element for it).
2. **`traitsetting.polarity`** — add `ScalarField("traitsetting", "polarity", "string", ("positive", "negative"))`.
3. **`source` seed** — join `COLLECTIONS` as a typed seed (element determined by `source_kind`), so the targeting wizard can `select source → navigate/filter`.
4. **Retire `{source_trait}`** — resolve to a real `{trait_setting}` and drop the reserved token.

## Open questions

- **Menu triggers** (`hitch`, `contest_win`, …): what is `{source}` there, if anything? The "origin" is a player's roll, not an owner surface. Lean: `source_kind` unset for menu triggers, like passive rules.
- **`entity` vs `projection` for the acting character**: a character acting via a projection — is `{source}` the entity or the active projection? Settle when the first projection-owned SFX is authored.

## Related

- [[Effect System Convergence Plan]] — the umbrella plan this folds into (owner-model section).
- [[Targeting Model]] — the type-checker/resolver/catalog the `source` seed and field typing build on.
- [[Effect Variables and Primitives]] — the trigger-variable model `source_kind` extends.
- [[to-do]] — "SFX's need a source" (the driver).
