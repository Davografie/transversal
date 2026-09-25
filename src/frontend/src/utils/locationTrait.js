/**
 * A location trait, as the viewer's other code expects to read it.
 *
 * `GET /locations/{id}/traits` speaks the REST wire's dialect — snake_case keys and
 * **lowercase** enum values — while `useTraitPlay` (shared with the character sheet)
 * reads the sheet's GraphQL shape: `ratingType`, `polarity`, and enums compared
 * against **uppercase** constants.
 *
 * Both halves of that mismatch were real bugs, each of which made a CHALLENGE trait
 * look like a static one, so its chip pushed the pool's raw dice into the roller
 * instead of spending a die — and a negative trait read as positive. Neither showed
 * up in a build or in a logic test built from hand-shaped fixtures; only the browser
 * check caught them. Hence this function, and `check-trait-play.mjs` pins it.
 */
export function normalizeLocationTrait(t) {
  return {
    ...t,
    ratingType: String(t.rating_type || '').toUpperCase(),
    polarity: String(t.polarity || '').toUpperCase(),
    sfxIds: t.sfx_ids || [],
  }
}
