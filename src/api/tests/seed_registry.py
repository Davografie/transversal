"""Minimal trait/traitset registry for tests.

Kept in the test package because the production seed no longer carries the
Earth / Three Realms trait registry (it migrated from the old app). Tests that
exercise GraphQL queries/mutations against a known registry seed from here.
"""

from transversal.domain import (
    DieType,
    EntityType,
    RatingType,
    Trait,
    TraitDisplayName,
    TraitSet,
)


def seed_test_trait_registry(repo) -> None:
    """Create the trait registry entries for Earth and the Three Realms.

    Idempotent — skips if traits already exist.
    """

    # ── Earth Traitsets ───────────────────────────────

    earth_traitsets = [
        TraitSet(id="ts-earth-distinctions", name="distinctions", universes=["earth"],
                 entity_types=[EntityType.CHARACTER, EntityType.GMC], order=1, limit=1),
        TraitSet(id="ts-earth-attributes", name="attributes", universes=["earth"],
                 entity_types=[EntityType.CHARACTER, EntityType.GMC], order=2, limit=1),
        TraitSet(id="ts-earth-skills", name="skills", universes=["earth"],
                 entity_types=[EntityType.CHARACTER, EntityType.GMC], order=3, limit=1),
    ]
    for ts in earth_traitsets:
        if not repo.get_traitset_by_id(ts.id):
            repo.create_traitset(ts)

    # ── Earth Traits ───────────────────────────────────

    earth_traits = [
        Trait(id="trait-earth-strength", name="Strength", universes=["earth"],
              traitset_id="ts-earth-attributes", default_die_type=DieType.D6),
        Trait(id="trait-earth-agility", name="Agility", universes=["earth"],
              traitset_id="ts-earth-attributes", default_die_type=DieType.D6),
        Trait(id="trait-earth-intelligence", name="Intelligence", universes=["earth"],
              traitset_id="ts-earth-attributes", default_die_type=DieType.D6,
              display_names=[
                  TraitDisplayName(name="Divine Consciousness",
                                   universe="three_realms",
                                   ratings=[[DieType.D4], [DieType.D6],
                                            [DieType.D8], [DieType.D10],
                                            [DieType.D12]]),
              ]),
        Trait(id="trait-earth-willpower", name="Willpower", universes=["earth"],
              traitset_id="ts-earth-attributes", default_die_type=DieType.D6),

        Trait(id="trait-earth-hacking", name="Hacking", universes=["earth"],
              traitset_id="ts-earth-skills", default_die_type=DieType.D6),
        Trait(id="trait-earth-shooting", name="Shooting", universes=["earth"],
              traitset_id="ts-earth-skills", default_die_type=DieType.D6),
        Trait(id="trait-earth-persuasion", name="Persuasion", universes=["earth"],
              traitset_id="ts-earth-skills", default_die_type=DieType.D6),
        Trait(id="trait-earth-stealth", name="Stealth", universes=["earth"],
              traitset_id="ts-earth-skills", default_die_type=DieType.D6),
        Trait(id="trait-earth-investigation", name="Investigation", universes=["earth"],
              traitset_id="ts-earth-skills", default_die_type=DieType.D6),
        Trait(id="trait-earth-survival", name="Survival", universes=["earth"],
              traitset_id="ts-earth-skills", default_die_type=DieType.D6),

        # Distinctions
        Trait(id="trait-earth-antonov-call", name="Answered Antonov's Call",
              universes=["earth"], traitset_id="ts-earth-distinctions",
              default_die_type=DieType.D8),
    ]
    for t in earth_traits:
        existing = repo.get_trait(t.id)
        if existing:
            existing.name = t.name
            repo.update_trait(existing)
        else:
            repo.create_trait(t)

    # ── Three Realms Traitsets ────────────────────────

    realm_traitsets = [
        TraitSet(id="ts-3r-distinctions", name="distinctions", universes=["three_realms"],
                 entity_types=[EntityType.CHARACTER, EntityType.GMC], order=1, limit=1),
        TraitSet(id="ts-3r-cultivation", name="cultivation", universes=["three_realms"],
                 entity_types=[EntityType.CHARACTER, EntityType.GMC], order=2, limit=1),
        TraitSet(id="ts-3r-combat", name="combat", universes=["three_realms"],
                 entity_types=[EntityType.CHARACTER, EntityType.GMC], order=3, limit=1),
    ]
    for ts in realm_traitsets:
        if not repo.get_traitset_by_id(ts.id):
            repo.create_traitset(ts)

    # ── Three Realms Traits ───────────────────────────

    realm_traits = [
        Trait(id="trait-3r-qi-reserves", name="Qi Reserves", universes=["three_realms"],
              traitset_id="ts-3r-cultivation",
              default_die_type=DieType.D6, default_rating_type=RatingType.RESOURCE,
              location_restricted=True),
        Trait(id="trait-3r-dao-comprehension", name="Dao Comprehension", universes=["three_realms"],
              traitset_id="ts-3r-cultivation",
              default_die_type=DieType.D4, location_restricted=True,
              display_names=[
                  TraitDisplayName(name="Dao Sliver", universe="three_realms",
                                   ratings=[[DieType.D4]]),
                  TraitDisplayName(name="Budding Comprehension", universe="three_realms",
                                   ratings=[[DieType.D6], [DieType.D8]]),
                  TraitDisplayName(name="Dao Insight", universe="three_realms",
                                   ratings=[[DieType.D10]]),
                  TraitDisplayName(name="Law of the Dao", universe="three_realms",
                                   ratings=[[DieType.D12],
                                            [DieType.D10, DieType.D10]]),
              ]),
        Trait(id="trait-3r-alchemy", name="Alchemy", universes=["three_realms"],
              traitset_id="ts-3r-cultivation",
              default_die_type=DieType.D6, location_restricted=True),

        Trait(id="trait-3r-sword-intent", name="Sword Intent", universes=["three_realms"],
              traitset_id="ts-3r-combat",
              default_die_type=DieType.D6, location_restricted=True),
        Trait(id="trait-3r-footwork", name="Footwork", universes=["three_realms"],
              traitset_id="ts-3r-combat",
              default_die_type=DieType.D6, location_restricted=True),
        Trait(id="trait-3r-qi-strike", name="Qi Strike", universes=["three_realms"],
              traitset_id="ts-3r-combat",
              default_die_type=DieType.D6, location_restricted=True),
    ]
    for t in realm_traits:
        existing = repo.get_trait(t.id)
        if existing:
            existing.name = t.name
            repo.update_trait(existing)
        else:
            repo.create_trait(t)
