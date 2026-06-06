"""Seed data — populate the trait registry and SFX definitions."""

from transversal.db.repository import EntityRepository
from transversal.domain import (
    DieType,
    EffectAction,
    EffectTiming,
    Entity,
    EntityType,
    RatingType,
    SFX,
    Trait,
    TraitSet,
    Zone,
)


def seed_trait_registry(repo: EntityRepository) -> None:
    """Create the trait registry entries for Earth and the Three Realms.

    Idempotent — skips if traits already exist.
    """

    # ── Earth Traitsets ───────────────────────────────

    earth_traitsets = [
        TraitSet(id="ts-earth-attributes", name="attributes", universe="earth",
                 entity_types=[EntityType.CHARACTER, EntityType.GMC]),
        TraitSet(id="ts-earth-skills", name="skills", universe="earth",
                 entity_types=[EntityType.CHARACTER, EntityType.GMC]),
        TraitSet(id="ts-earth-distinctions", name="distinctions", universe="earth",
                 entity_types=[EntityType.CHARACTER, EntityType.GMC]),
    ]
    for ts in earth_traitsets:
        if not repo.get_traitset_by_id(ts.id):
            repo.create_traitset(ts)

    # ── Earth Traits ───────────────────────────────────

    earth_traits = [
        Trait(id="trait-earth-strength", name="strength", universe="earth",
              traitset_id="ts-earth-attributes", default_die_type=DieType.D6),
        Trait(id="trait-earth-agility", name="agility", universe="earth",
              traitset_id="ts-earth-attributes", default_die_type=DieType.D6),
        Trait(id="trait-earth-intelligence", name="intelligence", universe="earth",
              traitset_id="ts-earth-attributes", default_die_type=DieType.D6),
        Trait(id="trait-earth-willpower", name="willpower", universe="earth",
              traitset_id="ts-earth-attributes", default_die_type=DieType.D6),

        Trait(id="trait-earth-hacking", name="hacking", universe="earth",
              traitset_id="ts-earth-skills", default_die_type=DieType.D6),
        Trait(id="trait-earth-shooting", name="shooting", universe="earth",
              traitset_id="ts-earth-skills", default_die_type=DieType.D6),
        Trait(id="trait-earth-persuasion", name="persuasion", universe="earth",
              traitset_id="ts-earth-skills", default_die_type=DieType.D6),
        Trait(id="trait-earth-stealth", name="stealth", universe="earth",
              traitset_id="ts-earth-skills", default_die_type=DieType.D6),
        Trait(id="trait-earth-investigation", name="investigation", universe="earth",
              traitset_id="ts-earth-skills", default_die_type=DieType.D6),
        Trait(id="trait-earth-survival", name="survival", universe="earth",
              traitset_id="ts-earth-skills", default_die_type=DieType.D6),

        # Distinctions
        Trait(id="trait-earth-antonov-call", name="answered_antonovs_call",
              universe="earth", traitset_id="ts-earth-distinctions",
              default_die_type=DieType.D8),
    ]
    for t in earth_traits:
        if not repo.get_trait(t.id):
            repo.create_trait(t)

    # ── Three Realms Traitsets ────────────────────────

    realm_traitsets = [
        TraitSet(id="ts-3r-cultivation", name="cultivation", universe="three_realms",
                 entity_types=[EntityType.CHARACTER, EntityType.GMC]),
        TraitSet(id="ts-3r-combat", name="combat", universe="three_realms",
                 entity_types=[EntityType.CHARACTER, EntityType.GMC]),
        TraitSet(id="ts-3r-distinctions", name="distinctions", universe="three_realms",
                 entity_types=[EntityType.CHARACTER, EntityType.GMC]),
    ]
    for ts in realm_traitsets:
        if not repo.get_traitset_by_id(ts.id):
            repo.create_traitset(ts)

    # ── Three Realms Traits ───────────────────────────

    realm_traits = [
        Trait(id="trait-3r-qi-reserves", name="qi_reserves", universe="three_realms",
              traitset_id="ts-3r-cultivation",
              default_die_type=DieType.D6, default_rating_type=RatingType.RESOURCE,
              location_restricted=True),
        Trait(id="trait-3r-dao-comprehension", name="dao_comprehension", universe="three_realms",
              traitset_id="ts-3r-cultivation",
              default_die_type=DieType.D4, location_restricted=True),
        Trait(id="trait-3r-alchemy", name="alchemy", universe="three_realms",
              traitset_id="ts-3r-cultivation",
              default_die_type=DieType.D6, location_restricted=True),

        Trait(id="trait-3r-sword-intent", name="sword_intent", universe="three_realms",
              traitset_id="ts-3r-combat",
              default_die_type=DieType.D6, location_restricted=True),
        Trait(id="trait-3r-footwork", name="footwork", universe="three_realms",
              traitset_id="ts-3r-combat",
              default_die_type=DieType.D6, location_restricted=True),
        Trait(id="trait-3r-qi-strike", name="qi_strike", universe="three_realms",
              traitset_id="ts-3r-combat",
              default_die_type=DieType.D6, location_restricted=True),
    ]
    for t in realm_traits:
        if not repo.get_trait(t.id):
            repo.create_trait(t)


def seed_sfx_registry(repo: EntityRepository, engine=None) -> None:
    """Create the SFX registry entries. Idempotent.

    Args:
        repo: EntityRepository for DB access.
        engine: Optional EffectsEngine instance. If None, imports from main's singleton.
    """

    sfxs = [
        SFX(
            id="sfx-law-bridge",
            name="Law Bridge",
            description="Temporarily attune to the Three Realms, enabling cultivation traits",
            trigger="on_activate",
            timing=EffectTiming.END_OF_SCENE,
            cost=1,
            effects=[
                EffectAction(type="spoof_location", action="enable", target="wielder",
                            result="three_realms:d8"),
            ],
        ),
        SFX(
            id="sfx-overcharge",
            name="Overcharge",
            description="Push beyond normal limits — step up primary trait, then step down after resolution",
            trigger="on_roll",
            timing=EffectTiming.IMMEDIATE,
            cost=1,
            effects=[
                EffectAction(type="modify_roll", action="step_up_die", target="highest_trait_die"),
                EffectAction(type="modify_trait", action="step_down", target="primary",
                            result="after_resolution"),
            ],
        ),
        SFX(
            id="sfx-lucky-break",
            name="Lucky Break",
            description="When you roll a hitch, spend razmerit to reroll that die",
            trigger="on_complication",
            timing=EffectTiming.IMMEDIATE,
            cost=1,
            effects=[
                EffectAction(type="modify_roll", action="reroll_die", target="the_hitch_die"),
            ],
        ),
        SFX(
            id="sfx-catastrophe-insurance",
            name="Catastrophe Insurance",
            description="When everything goes wrong, burn razmerit to contain the damage",
            trigger="on_botch",
            timing=EffectTiming.IMMEDIATE,
            cost=2,
            effects=[
                EffectAction(type="modify_outcome", action="convert_complication",
                            target="botch_to_hitch"),
            ],
        ),
        SFX(
            id="sfx-dimensional-anchor",
            name="Dimensional Anchor",
            description="Create a temporary anchor point when entering a new dimension",
            trigger="on_location_change",
            timing=EffectTiming.END_OF_SCENE,
            cost=0,
            effects=[
                EffectAction(type="create_entity", action="create_asset",
                            target="anchor_point"),
            ],
        ),
        SFX(
            id="sfx-spray-n-pray",
            name="Spray 'n' Pray",
            description="Split a shooting die into two smaller dice, gain an extra effect die option",
            trigger="on_activate",
            timing=EffectTiming.IMMEDIATE,
            cost=1,
            effects=[
                EffectAction(type="modify_roll", action="split_die",
                            target="{source_trait}"),
            ],
        ),
        SFX(
            id="sfx-hinder",
            name="Hinder",
            description="Use distinction as d4 for this roll, gain 1 razmerit",
            trigger="on_activate",
            timing=EffectTiming.IMMEDIATE,
            cost=0,
            effects=[
                EffectAction(type="transfer_razmerit", action="earn",
                            target="self", result="1"),
            ],
        ),
    ]

    # Load into effects engine
    if engine is None:
        from transversal.main import _get_engine
        engine = _get_engine()
    for s in sfxs:
        engine.register(s)

    # Also link SFXs to traits in the registry
    _link_sfxs_to_traits(repo)


def _link_sfxs_to_traits(repo: EntityRepository) -> None:
    """Link SFXs to traits that can unlock them."""
    links = {
        "trait-earth-antonov-call": ["sfx-hinder"],
        "trait-earth-shooting": ["sfx-spray-n-pray"],
        "trait-3r-qi-reserves": ["sfx-overcharge"],
        "trait-3r-sword-intent": ["sfx-lucky-break"],
    }
    for trait_id, sfx_ids in links.items():
        trait = repo.get_trait(trait_id)
        if trait:
            trait.possible_sfx_ids = sfx_ids
            # Update doesn't exist on Trait model directly, use repository
            try:
                repo._traits.update({"_key": trait_id, **trait.model_dump()})
            except Exception:
                pass


def seed_default_character(em) -> None:
    """Create the default 'kael-1' character with Earth + Three Realms traits. Idempotent."""
    from transversal.domain import TraitSetting

    # Create entity if missing
    if not em.repo.get_entity("kael-1"):
        em.create(name="Kael Drift", entity_type=EntityType.CHARACTER,
                  entity_id="kael-1", universe="earth",
                  location="loc-krasnoyarsk", razmerit=5)

    def _add_ts_if_missing(ts_id: str, **kwargs) -> None:
        if not em.repo.get_traitsetting(ts_id):
            ts = TraitSetting(id=ts_id, entity_id="kael-1", **kwargs)
            try:
                em.add_traitsetting(ts)
            except Exception:
                pass

    # Add Earth skills (with SFX unlocks)
    skill_configs = [
        ("hacking", DieType.D10, []),
        ("shooting", DieType.D6, ["sfx-spray-n-pray"]),
        ("persuasion", DieType.D8, []),
        ("stealth", DieType.D6, []),
    ]
    for skill_name, die, sfx_ids in skill_configs:
        trait = em.repo.get_trait_by_name(skill_name, "earth")
        if trait:
            _add_ts_if_missing(f"kael-1:{trait.id}",
                trait_id=trait.id, traitset_id=trait.traitset_id,
                dice=[die], sfx_ids=sfx_ids)
            # Ensure sfx_ids is set on existing settings
            if sfx_ids:
                ts = em.repo.get_traitsetting(f"kael-1:{trait.id}")
                if ts:
                    current = set(ts.sfx_ids or [])
                    needed = set(sfx_ids)
                    if not needed.issubset(current):
                        ts.sfx_ids = list(current | needed)
                        em.repo.update_traitsetting(ts)

    # Create Three Realms projection
    em.create_projection(entity_id="kael-1", universe="three_realms",
                         transversal_type="consciousness")

    # Add Three Realms cultivation traits
    realm_trait_configs = [
        ("qi_reserves", [DieType.D4, DieType.D4, DieType.D4, DieType.D4], RatingType.RESOURCE),
        ("dao_comprehension", [DieType.D4], RatingType.STATIC),
        ("sword_intent", [DieType.D6], RatingType.STATIC),
        ("footwork", [DieType.D4], RatingType.STATIC),
    ]
    for trait_name, dice, rtype in realm_trait_configs:
        trait = em.repo.get_trait_by_name(trait_name, "three_realms")
        if trait:
            _add_ts_if_missing(f"kael-1:3r:{trait.id}",
                trait_id=trait.id, traitset_id=trait.traitset_id,
                dice=dice, rating_type=rtype)

    # Add ego distinction — follows Kael across universes
    trait = em.repo.get_trait_by_name("answered_antonovs_call", "earth")
    if trait:
        _add_ts_if_missing("kael-1:ego:antonov",
            trait_id=trait.id, traitset_id=trait.traitset_id,
            dice=[DieType.D8], ego=True,
            statement="He reached out. I answered.",
            sfx_ids=["sfx-hinder"])
        # Always ensure sfx_ids is set (update even if already exists)
        ts = em.repo.get_traitsetting("kael-1:ego:antonov")
        if ts and "sfx-hinder" not in (ts.sfx_ids or []):
            ts.sfx_ids = (ts.sfx_ids or []) + ["sfx-hinder"]
            em.repo.update_traitsetting(ts)



def seed_elena(em) -> None:
    """Create the 'elena-1' character. Idempotent."""
    from transversal.domain import TraitSetting

    if not em.repo.get_entity("elena-1"):
        em.create(name="Elena Antonova", entity_type=EntityType.CHARACTER,
                  entity_id="elena-1", universe="earth",
                  location="loc-krasnoyarsk", razmerit=3)

    def _add_ts(ts_id: str, **kwargs):
        if not em.repo.get_traitsetting(ts_id):
            ts = TraitSetting(id=ts_id, entity_id="elena-1", **kwargs)
            try:
                em.add_traitsetting(ts)
            except Exception:
                pass

    for skill_name, die in [("investigation", DieType.D10), ("persuasion", DieType.D8),
                             ("survival", DieType.D6), ("stealth", DieType.D4)]:
        trait = em.repo.get_trait_by_name(skill_name, "earth")
        if trait:
            _add_ts(f"elena-1:{trait.id}",
                trait_id=trait.id, traitset_id=trait.traitset_id,
                dice=[die])

    for attr_name, die in [("intelligence", DieType.D10), ("willpower", DieType.D8),
                            ("agility", DieType.D6), ("strength", DieType.D4)]:
        trait = em.repo.get_trait_by_name(attr_name, "earth")
        if trait:
            _add_ts(f"elena-1:{trait.id}",
                trait_id=trait.id, traitset_id=trait.traitset_id,
                dice=[die])


def seed_locations(em) -> None:
    """Create location entities and their hierarchy relationships. Idempotent."""
    repo = em.repo

    locations = [
        {"id": "loc-valley", "name": "Valley of Ascension", "universe": "three_realms"},
        {"id": "loc-platform", "name": "The Arrival Platform", "universe": "three_realms"},
        {"id": "loc-mistwood", "name": "The Mistwood", "universe": "three_realms"},
        {"id": "loc-sect", "name": "Verdant Steps Sect Grounds", "universe": "three_realms"},
        {"id": "loc-krasnoyarsk", "name": "Krasnoyarsk-45", "universe": "earth"},
    ]

    for loc in locations:
        if not repo.get_entity(loc["id"]):
            repo.create_entity(Entity(
                id=loc["id"], type=EntityType.LOCATION,
                name=loc["name"], current_universe=loc["universe"],
                current_location=loc["id"], razmerit=0,
            ))

    # Helper: create edge only if it doesn't already exist
    def _edge_key(from_id, to_id, rel_type):
        return f"edge:{from_id}:{to_id}:{rel_type}"

    hierarchy = [
        ("loc-platform", "loc-valley"),
        ("loc-mistwood", "loc-valley"),
        ("loc-sect", "loc-valley"),
    ]

    for child_id, parent_id in hierarchy:
        k = _edge_key(child_id, parent_id, "super")
        try:
            if not repo._relationships.has(k):
                repo._relationships.insert({"_key": k, "_from": f"entities/{child_id}", "_to": f"entities/{parent_id}", "type": "super"})
        except Exception:
            pass

    # Transversal edges (bidirectional)
    transversal = [
        ("loc-krasnoyarsk", "loc-platform"),  # Earth → Three Realms
    ]
    for from_id, to_id in transversal:
        for f, t in [(from_id, to_id), (to_id, from_id)]:
            k = _edge_key(f, t, "transversal")
            try:
                if not repo._relationships.has(k):
                    repo._relationships.insert({"_key": k, "_from": f"entities/{f}", "_to": f"entities/{t}", "type": "transversal"})
            except Exception:
                pass

    # ── Seed zones on locations ──────────────────────

    location_zones = {
        "loc-krasnoyarsk": [
            Zone(name="Control Room", x=40, y=30),
            Zone(name="Holding Cells", x=70, y=60),
            Zone(name="Extraction Point", x=20, y=75),
        ],
        "loc-platform": [
            Zone(name="Landing Pad", x=50, y=60),
            Zone(name="Observation Deck", x=30, y=25),
        ],
        "loc-valley": [
            Zone(name="The Gate", x=50, y=20),
            Zone(name="Training Grounds", x=25, y=65),
            Zone(name="Meditation Stones", x=75, y=70),
        ],
        "loc-mistwood": [
            Zone(name="The Clearing", x=45, y=55),
            Zone(name="Deep Woods", x=15, y=30),
            Zone(name="Elder Tree", x=80, y=40),
        ],
        "loc-sect": [
            Zone(name="Main Hall", x=50, y=35),
            Zone(name="Training Courtyard", x=25, y=70),
            Zone(name="Elder's Pavilion", x=75, y=20),
            Zone(name="Herb Garden", x=60, y=80),
        ],
    }

    for loc_id, zones in location_zones.items():
        loc = repo.get_entity(loc_id)
        if loc and not loc.zones:
            loc.zones = list(zones)
            repo.update_entity(loc)
    # ── Seed challenge traits on locations ────────────

    from transversal.domain import ChallengePolarity

    _challenge_traits = [
        ("loc-krasnoyarsk", "regime_alert", "ts-earth-distinctions",
         [DieType.D6, DieType.D6, DieType.D8], ChallengePolarity.NEGATIVE),
        ("loc-sect", "sect_suspicion", "ts-earth-distinctions",
         [DieType.D6], ChallengePolarity.NEGATIVE),
    ]
    for loc_id, name, tsid, dice, polarity in _challenge_traits:
        ts_key = f"{loc_id}:challenge:{name}"
        if not repo.get_traitsetting(ts_key):
            ts = TraitSetting(
                id=ts_key, entity_id=loc_id,
                trait_id="trait-earth-hacking",  # placeholder — will need proper challenge trait registry
                traitset_id=tsid,
                rating_type=RatingType.CHALLENGE,
                dice=list(dice),
                polarity=polarity,
            )
            try:
                repo.create_traitsetting(ts)
            except Exception:
                pass


def seed_universes(em) -> None:
    """Create universe entities. Idempotent."""
    repo = em.repo

    universes = [
        {"id": "universe-earth", "name": "Earth", "key": "earth"},
        {"id": "universe-three_realms", "name": "Three Realms", "key": "three_realms"},
    ]

    for u in universes:
        if not repo.get_entity(u["id"]):
            repo.create_entity(Entity(
                id=u["id"], type=EntityType.UNIVERSE,
                name=u["name"], current_universe=u["key"],
                current_location=None, razmerit=0,
            ))


def seed_all(em) -> None:
    """Run all seed functions."""
    seed_universes(em)
    seed_trait_registry(em.repo)
    seed_sfx_registry(em.repo)
    seed_default_character(em)
    seed_elena(em)
    seed_locations(em)

