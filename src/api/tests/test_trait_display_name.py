"""Dynamic trait display names — the universe alias, and the dice refinement.

Reported 2026-09-25: `trait-saber` was given a display name for `three_realms`
and it never rendered on Jianxin's sheet. The authoring UI's own label is *"No
ratings — matches any dice"*, but the resolver iterated `ratings` and so skipped
an entry that declared none — an empty list has nothing to iterate. It is the
only trait in the registry carrying a display name, so nothing else caught it.

These pin the contract the editor promises, including the case that has no live
data yet: a general alias must not shadow a dice-specific one.
"""

from transversal.domain import DieType, Trait, TraitDisplayName, resolve_trait_display_name


def _trait(*entries: TraitDisplayName) -> Trait:
    return Trait(
        id="trait-probe", name="saber", universes=["three_realms", "aelor-citar"],
        traitset_id="ts-probe", display_names=list(entries),
    )


def test_an_entry_with_no_ratings_matches_any_dice():
    """The reported bug: this is the editor's "matches any dice" entry."""
    trait = _trait(TraitDisplayName(name="dao", universe="three_realms", ratings=[]))
    assert resolve_trait_display_name(trait, [DieType.D8], "three_realms") == "dao"
    assert resolve_trait_display_name(trait, [DieType.D4, DieType.D10], "three_realms") == "dao"


def test_another_universe_still_gets_the_definition_name():
    trait = _trait(TraitDisplayName(name="dao", universe="three_realms", ratings=[]))
    assert resolve_trait_display_name(trait, [DieType.D8], "aelor-citar") == "saber"


def test_a_wildcard_universe_applies_everywhere():
    trait = _trait(TraitDisplayName(name="blade", universe="*", ratings=[]))
    assert resolve_trait_display_name(trait, [DieType.D8], "earth") == "blade"
    assert resolve_trait_display_name(trait, [DieType.D8], "three_realms") == "blade"


def test_declared_dice_still_match_exactly_and_order_independently():
    trait = _trait(TraitDisplayName(name="paired", universe="three_realms", ratings=[[DieType.D8, DieType.D6]]))
    assert resolve_trait_display_name(trait, [DieType.D6, DieType.D8], "three_realms") == "paired"
    assert resolve_trait_display_name(trait, [DieType.D6], "three_realms") == "saber"


def test_a_declared_rating_beats_a_general_alias_whatever_the_order():
    """Most specific wins: stored general-first must not shadow the exact entry."""
    general_first = _trait(
        TraitDisplayName(name="dao", universe="three_realms", ratings=[]),
        TraitDisplayName(name="great dao", universe="three_realms", ratings=[[DieType.D10]]),
    )
    assert resolve_trait_display_name(general_first, [DieType.D10], "three_realms") == "great dao"
    # …and the general one still answers for the dice it does not name.
    assert resolve_trait_display_name(general_first, [DieType.D6], "three_realms") == "dao"

    specific_first = _trait(
        TraitDisplayName(name="great dao", universe="three_realms", ratings=[[DieType.D10]]),
        TraitDisplayName(name="dao", universe="three_realms", ratings=[]),
    )
    assert resolve_trait_display_name(specific_first, [DieType.D10], "three_realms") == "great dao"
    assert resolve_trait_display_name(specific_first, [DieType.D6], "three_realms") == "dao"


def test_no_dice_and_no_display_names_are_unchanged():
    """Both guards are deliberate and kept: see the resolver's docstring."""
    trait = _trait(TraitDisplayName(name="dao", universe="three_realms", ratings=[]))
    assert resolve_trait_display_name(trait, [], "three_realms") == "saber"
    assert resolve_trait_display_name(_trait(), [DieType.D8], "three_realms") == "saber"
