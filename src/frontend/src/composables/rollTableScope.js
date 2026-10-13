// The names a roll-table row's conditions and effects resolve against *before*
// the table's own bound variables. `table_bindings()` in
// `src/api/src/transversal/services/roll_table.py` is the authority, and this is
// the frontend's mirror of it — kept in step by
// `src/frontend/tests/lifePathConnector.mjs`, which parses that function and
// fails when the two disagree.
//
// The elements mirror what `table_bindings()` binds: the two factions are
// `entity` (the enrollment's faction, or the invoking term's); every other name
// is bound with no catalog element (`one(value)`), so it is usable as a
// `{name}` value in a filter or evaluate (`filter min_value == {roll}`) but not
// as the start of a `select variable` step — the engine treats it as untyped
// too. `path_id` is ambient alongside `path_faction` and is bound in the same
// branch.
export const ROLL_TABLE_AMBIENT_VARIABLES = {
  path_faction: { element: 'entity', cardinality: 'one' },
  path_id: { element: '', cardinality: 'one' },
  term_faction: { element: 'entity', cardinality: 'one' },
  term_path: { element: '', cardinality: 'one' },
  table_id: { element: '', cardinality: 'one' },
  roll: { element: '', cardinality: 'one' },
  entry_label: { element: '', cardinality: 'one' },
  entry_index: { element: '', cardinality: 'one' },
  entry_min: { element: '', cardinality: 'one' },
  entry_max: { element: '', cardinality: 'one' },
  entry_tier: { element: '', cardinality: 'one' },
  entry_effect_die: { element: '', cardinality: 'one' },
}
