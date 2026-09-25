"""Both trait-setting converters must forward every field the GraphQL type exposes.

There are two of them, and they had each silently dropped a *different* field:
`_gql_trait_setting` (the read path — the sheet's trait list, sub-traits,
relationship traits) dropped `enabled`, so a disabled setting read as enabled
everywhere; `_ts_to_gql` (the mutation path) dropped `capacity`, so writing a
capacity read back `null`. Neither was visible, because the other converter was
correct and whoever checked the field found it present.

So this test does not spot-check fields — it walks the GraphQL type's own field
list and requires **both** converters to carry each one, which is what makes it
catch the next field someone forgets.
"""

from transversal.api.graphql.resolvers.converters import _ts_to_gql
from transversal.api.graphql.type_defs.traits import TraitSetting as GqlTraitSetting
from transversal.api.graphql.type_defs.traits import _gql_trait_setting
from transversal.domain import DieType, Polarity, RatingType, TraitSetting


def _populated() -> TraitSetting:
    """Every field set to something a default would not be."""
    return TraitSetting(
        id="ts-1", entity_id="e-1", trait_id="trait-1",
        rating_type=RatingType.CHALLENGE, dice=[DieType.D8], spent_dice=[DieType.D6],
        capacity=[DieType.D6, DieType.D6], polarity=Polarity.NEGATIVE,
        statement="a step", notes="gm only", order=7, tags=["coming"],
        from_type="traitsetting", parent_traitsetting_id="parent-1",
        sfx_ids=["sfx-1"], known_to=["e-2"], enabled=False,
    )


def test_both_converters_carry_every_exposed_field():
    setting = _populated()
    read = _gql_trait_setting(setting)
    mutation = _ts_to_gql(setting)

    fields = [
        f.name for f in GqlTraitSetting.__strawberry_definition__.fields
        # A resolver on the type is derived when the query runs, not carried by a
        # converter: `ego` from the anchor, `die_type` and `rating` from `dice`.
        if not callable(getattr(GqlTraitSetting, f.name, None))
        # Filled from the relationship edge the setting is anchored to.
        and not f.name.startswith("relationship_")
    ]
    # The two that were dropped, named so the test fails loudly if either is
    # removed from the type it is guarding.
    assert "capacity" in fields
    assert "enabled" in fields

    for name in fields:
        expected = getattr(setting, name)
        assert getattr(read, name) == expected, f"read path dropped or changed {name}"
        assert getattr(mutation, name) == expected, f"mutation path dropped or changed {name}"
