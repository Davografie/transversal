"""Seed data — populate the trait registry and SFX definitions."""

from transversal.db.repository import EntityRepository
from transversal.domain import (
    DieType,
    Effect,
    EffectTiming,
    Entity,
    EntityType,
    RatingType,
    SFX,
    TraitDisplayName,
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


def seed_sfx_registry(repo: EntityRepository, engine=None) -> None:
    """Create the SFX registry entries. Idempotent.

    Deletes any old-format SFXs first, then creates the new model.

    Args:
        repo: EntityRepository for DB access.
        engine: Optional EffectsEngine instance. If None, imports from main's singleton.
    """

    # ── Delete old SFXs (idempotent re-seed) ──────────
    old_ids = [
        "sfx-law-bridge", "sfx-overcharge", "sfx-lucky-break",
        "sfx-catastrophe-insurance", "sfx-dimensional-anchor",
        "sfx-spray-n-pray", "sfx-hinder",
    ]
    for old_id in old_ids:
        try:
            repo.delete_sfx(old_id)
        except Exception:
            pass  # already gone

    # ── New SFX definitions ───────────────────────────
    sfxs = [
        SFX(
            id="sfx-law-bridge",
            name="Law Bridge",
            description="Temporarily attune to the Three Realms, enabling cultivation traits",
            limit="Must be in contact with the Jian of Still Waters",
            trigger="manual",
            effects=[
                Effect(timing=EffectTiming.IMMEDIATE,
                         type="transfer_razmerit", action="spend", target="self", result="1"),
                Effect(timing=EffectTiming.END_OF_SCENE,
                         type="spoof_location", action="enable", target="wielder",
                         result="three_realms"),
            ],
        ),
        SFX(
            id="sfx-overcharge",
            name="Overcharge",
            description="Push beyond normal limits — step up primary trait, then step down after resolution",
            limit="",
            trigger="on_roll",
            effects=[
                Effect(timing=EffectTiming.IMMEDIATE,
                         type="transfer_razmerit", action="spend", target="self", result="1"),
                Effect(timing=EffectTiming.IMMEDIATE,
                         type="modify_roll", action="step_up_die", target="highest_trait_die"),
                Effect(timing=EffectTiming.IMMEDIATE,
                         type="modify_trait", action="step_down", target="primary",
                         result="after_resolution"),
            ],
        ),
        SFX(
            id="sfx-lucky-break",
            name="Lucky Break",
            description="When you roll a hitch, spend razmerit to reroll that die",
            limit="",
            trigger="on_complication",
            effects=[
                Effect(timing=EffectTiming.IMMEDIATE,
                         type="transfer_razmerit", action="spend", target="self", result="1"),
                Effect(timing=EffectTiming.IMMEDIATE,
                         type="modify_roll", action="reroll_die", target="the_hitch_die"),
            ],
        ),
        SFX(
            id="sfx-catastrophe-insurance",
            name="Catastrophe Insurance",
            description="When everything goes wrong, burn razmerit to contain the damage",
            limit="",
            trigger="on_botch",
            effects=[
                Effect(timing=EffectTiming.IMMEDIATE,
                         type="transfer_razmerit", action="spend", target="self", result="2"),
                Effect(timing=EffectTiming.IMMEDIATE,
                         type="modify_outcome", action="convert_complication",
                         target="botch_to_hitch"),
            ],
        ),
        SFX(
            id="sfx-dimensional-anchor",
            name="Dimensional Anchor",
            description="Create a temporary anchor point when entering a new dimension",
            limit="",
            trigger="on_location_change",
            effects=[
                Effect(timing=EffectTiming.END_OF_SCENE,
                         type="create_entity", action="create_asset",
                         target="anchor_point"),
            ],
        ),
        SFX(
            id="sfx-spray-n-pray",
            name="Spray 'n' Pray",
            description="Split a shooting die into two smaller dice, gain an extra effect die option",
            limit="Must be wielding a firearm",
            trigger="manual",
            effects=[
                Effect(timing=EffectTiming.IMMEDIATE,
                         type="transfer_razmerit", action="spend", target="self", result="1"),
                Effect(timing=EffectTiming.IMMEDIATE,
                         type="modify_roll", action="split_die",
                         target="{source_trait}"),
            ],
        ),
        SFX(
            id="sfx-hinder",
            name="Hinder",
            description="Use distinction as d4 for this roll, gain 1 razmerit",
            limit="When this trait has a detrimental effect on the current situation",
            trigger="manual",
            effects=[
                Effect(timing=EffectTiming.IMMEDIATE,
                         type="modify_roll", action="play_as_rating",
                         target="{source_trait}", result="d4"),
                Effect(timing=EffectTiming.IMMEDIATE,
                         type="transfer_razmerit", action="earn",
                         target="self", result="1"),
            ],
        ),
    ]

    # Persist to database
    for s in sfxs:
        if not repo.get_sfx(s.id):
            repo.create_sfx(s)

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
        ("Hacking", DieType.D10, []),
        ("Shooting", DieType.D6, ["sfx-spray-n-pray"]),
        ("Persuasion", DieType.D8, []),
        ("Stealth", DieType.D6, []),
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
        ("Qi Reserves", [DieType.D4, DieType.D4, DieType.D4, DieType.D4], RatingType.RESOURCE),
        ("Dao Comprehension", [DieType.D4], RatingType.STATIC),
        ("Sword Intent", [DieType.D6], RatingType.STATIC),
        ("Footwork", [DieType.D4], RatingType.STATIC),
    ]
    for trait_name, dice, rtype in realm_trait_configs:
        trait = em.repo.get_trait_by_name(trait_name, "three_realms")
        if trait:
            _add_ts_if_missing(f"kael-1:3r:{trait.id}",
                trait_id=trait.id, traitset_id=trait.traitset_id,
                dice=dice, rating_type=rtype)

    # Add ego distinction — follows Kael across universes
    trait = em.repo.get_trait_by_name("Answered Antonov's Call", "earth")
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

    for skill_name, die in [("Investigation", DieType.D10), ("Persuasion", DieType.D8),
                             ("Survival", DieType.D6), ("Stealth", DieType.D4)]:
        trait = em.repo.get_trait_by_name(skill_name, "earth")
        if trait:
            _add_ts(f"elena-1:{trait.id}",
                trait_id=trait.id, traitset_id=trait.traitset_id,
                dice=[die])

    for attr_name, die in [("Intelligence", DieType.D10), ("Willpower", DieType.D8),
                            ("Agility", DieType.D6), ("Strength", DieType.D4)]:
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


def seed_relations_traitset(repo) -> None:
    """Seed the Relations trait set and its trait types."""
    from transversal.domain import TraitSet, Trait, DieType, RatingType, EntityType

    ts_id = "ts-relations"
    existing = repo.get_traitset_by_id(ts_id)
    if existing is None:
        ts = TraitSet(
            id=ts_id,
            name="Relations",
            universes=["earth", "three_realms"],
            description="Relationship traits between entities",
            entity_types=[EntityType.CHARACTER, EntityType.GMC, EntityType.FACTION],
            order=100,
            limit=10,
            default_rating_type=RatingType.STATIC,
            default_die_type=DieType.D6,
        )
        repo.create_traitset(ts)

    relation_traits = [
        ("trait-relation-trust", "Trust", "I trust them — adds to cooperative pools"),
        ("trait-relation-debt", "Debt", "Resource pool — razmerit or favors owed"),
        ("trait-relation-rivalry", "Rivalry", "We push each other — adds to opposed pools"),
        ("trait-relation-loyalty", "Loyalty", "I would die for them"),
        ("trait-relation-fear", "Fear", "Negative — opponent uses it against you"),
        ("trait-relation-love", "Love", "Adds to pools involving that person"),
        ("trait-relation-duty", "Duty", "I owe them my service — obligation"),
        # Life path membership — kept after muster (relationship traits on character↔faction).
        ("trait-rel-rank", "Rank", "Standing within a faction's life path"),
        ("trait-rel-tenure", "Tenure", "Terms served in a faction's life path"),
    ]
    for tid, name, explanation in relation_traits:
        existing_trait = repo.get_trait(tid)
        if existing_trait is None:
            trait = Trait(
                id=tid,
                name=name,
                universes=["earth", "three_realms"],
                traitset_id=ts_id,
                default_die_type=DieType.D6,
                default_rating_type=RatingType.STATIC,
                explanation=explanation,
            )
            repo.create_trait(trait)


def seed_all(em) -> None:
    """Run all seed functions."""
    seed_universes(em)
    seed_trait_registry(em.repo)
    seed_sfx_registry(em.repo)
    seed_relations_traitset(em.repo)
    seed_default_character(em)
    seed_elena(em)
    seed_locations(em)
    seed_life_paths(em.repo)


def seed_life_paths(repo) -> None:
    """Seed the life path content graph: faction, entry points, and linked roll tables.

    The Verdant Steps Sect path is wired end-to-end (qualify → learn → survive →
    mishap / advance → muster-out). Drifter paths are entry points only; their
    term tables land later.
    """
    from transversal.domain import (
        DieType,
        Effect,
        EffectTiming,
        Entity,
        EntityType,
        LifePath,
        OutcomeTier,
        RollTable,
        RollTableCheck,
        RollTableEntry,
        RollTableScheme,
    )

    FACTION = "fac-verdant-steps"

    # ── Effect / table builders ───────────────────────
    def eff(type_, action, target="", result=None, context=None):
        return Effect(
            timing=EffectTiming.IMMEDIATE,
            type=type_,
            action=action,
            target=target,
            result=result,
            context=context or {},
        )

    def flow(action, target="", context=None):
        return eff("life_path", action, target, context=context)

    def next_step(target=""):
        return flow("next_step", target)

    def trait(action, trait_id, die=None, relationship=FACTION):
        ctx = {"relationship": relationship} if relationship else {}
        return eff("modify_trait", action, trait_id, result=die, context=ctx)

    def entry(label, effects=None, **fields):
        return RollTableEntry(label=label, effects=effects or [], **fields)

    def upsert_table(table: RollTable) -> None:
        if repo.get_roll_table(table.id) is None:
            repo.create_roll_table(table)
        else:
            repo.update_roll_table(table)

    # ── Faction ──────────────────────────────────────
    faction = Entity(
        id=FACTION,
        type=EntityType.FACTION,
        name="Verdant Steps Sect",
        current_universe="three_realms",
        active_universes=["three_realms"],
        suitable_life_path_ids=["lp-verdant-disciple"],
    )
    if repo.get_entity(FACTION) is None:
        repo.create_entity(faction)
    else:
        repo.update_entity(faction)

    # ── Life paths ───────────────────────────────────
    paths = [
        LifePath(
            id="lp-drifter-three-realms",
            name="Rogue Cultivator",
            universe="three_realms",
            description="Walk the land alone, beholden to no sect.",
        ),
        LifePath(
            id="lp-drifter-earth",
            name="Street Survivor",
            universe="earth",
            description="Live by your wits on the margins of society.",
        ),
        LifePath(
            id="lp-verdant-disciple",
            name="Verdant Steps Outer Disciple",
            universe="three_realms",
            description="Train under the guidance of the Verdant Steps Sect.",
            entry_table_id="rt-verdant-qualify",
        ),
    ]

    for lp in paths:
        if repo.get_lifepath(lp.id) is None:
            repo.create_lifepath(lp)
        else:
            repo.update_lifepath(lp)

    # ── Verdant Steps chain ──────────────────────────

    # Qualify — roll Dao Comprehension against d6; pass → enroll + learn.
    upsert_table(RollTable(
        id="rt-verdant-qualify",
        name="Qualification",
        universe="three_realms",
        life_path="lp-verdant-disciple",
        scheme=RollTableScheme.TIER,
        check=RollTableCheck(trait_ids=["trait-3r-dao-comprehension"], difficulty=DieType.D6),
        entries=[
            entry("Rejected", tier=OutcomeTier.FAIL, effects=[next_step("")]),
            entry("Rejected", tier=OutcomeTier.MARGINAL, effects=[next_step("")]),
            entry("Accepted", tier=OutcomeTier.SUCCESS, effects=[flow("enroll"), next_step("rt-verdant-learn")]),
            entry("Accepted", tier=OutcomeTier.EXCEPTIONAL, effects=[flow("enroll"), next_step("rt-verdant-learn")]),
            entry("Accepted", tier=OutcomeTier.PERFECT, effects=[flow("enroll"), next_step("rt-verdant-learn")]),
        ],
    ))

    # Learn — pick a skill; each entry also advances to survival.
    learn_skills = [
        ("trait-3r-sword-intent", "d6", "Sword Intent"),
        ("trait-3r-footwork", "d6", "Footwork"),
        ("trait-3r-qi-strike", "d6", "Qi Strike"),
        ("trait-3r-alchemy", "d6", "Alchemy"),
        ("trait-3r-qi-reserves", "d4", "Qi Reserves"),
        ("trait-3r-dao-comprehension", "d4", "Dao Comprehension"),
    ]
    upsert_table(RollTable(
        id="rt-verdant-learn",
        name="Learn",
        universe="three_realms",
        life_path="lp-verdant-disciple",
        scheme=RollTableScheme.INDEX,
        entries=[
            entry(name, effects=[trait("gain_or_step_up", tid, die), next_step("rt-verdant-survive")])
            for tid, die, name in learn_skills
        ],
    ))

    # Survive — roll Qi Reserves; fail → mishap, otherwise advance.
    upsert_table(RollTable(
        id="rt-verdant-survive",
        name="Survival",
        universe="three_realms",
        life_path="lp-verdant-disciple",
        scheme=RollTableScheme.TIER,
        check=RollTableCheck(trait_ids=["trait-3r-qi-reserves"], difficulty=DieType.D6),
        entries=[
            entry("Injured", tier=OutcomeTier.FAIL, effects=[next_step("rt-verdant-mishap")]),
            entry("Survived", tier=OutcomeTier.MARGINAL, effects=[next_step("rt-verdant-advance")]),
            entry("Survived", tier=OutcomeTier.SUCCESS, effects=[next_step("rt-verdant-advance")]),
            entry("Survived", tier=OutcomeTier.EXCEPTIONAL, effects=[next_step("rt-verdant-advance")]),
            entry("Survived", tier=OutcomeTier.PERFECT, effects=[next_step("rt-verdant-advance")]),
        ],
    ))

    # Mishap — complication / loss, or forced muster.
    upsert_table(RollTable(
        id="rt-verdant-mishap",
        name="Mishap",
        universe="three_realms",
        life_path="lp-verdant-disciple",
        scheme=RollTableScheme.INDEX,
        entries=[
            entry("Lost a little face", effects=[eff("transfer_razmerit", "spend", "self", "1"), next_step("rt-verdant-advance")]),
            entry("Qi backlash", effects=[trait("gain_complication", "trait-3r-qi-reserves", "d4"), next_step("rt-verdant-advance")]),
            entry("Lost ground", effects=[eff("transfer_razmerit", "spend", "self", "2"), next_step("rt-verdant-advance")]),
            entry("Wounded spirit", effects=[trait("gain_complication", "trait-3r-dao-comprehension", "d4"), next_step("rt-verdant-advance")]),
            entry("Expelled", effects=[flow("force_muster")]),
            entry("Expelled", effects=[flow("force_muster")]),
        ],
    ))

    # Advance — roll Dao Comprehension; rank up on success, else another term.
    upsert_table(RollTable(
        id="rt-verdant-advance",
        name="Advancement",
        universe="three_realms",
        life_path="lp-verdant-disciple",
        scheme=RollTableScheme.TIER,
        check=RollTableCheck(trait_ids=["trait-3r-dao-comprehension"], difficulty=DieType.D6),
        entries=[
            entry("No progress", tier=OutcomeTier.FAIL, effects=[next_step("rt-verdant-learn")]),
            entry("No progress", tier=OutcomeTier.MARGINAL, effects=[next_step("rt-verdant-learn")]),
            entry("Promoted", tier=OutcomeTier.SUCCESS, effects=[trait("gain_or_step_up", "trait-rel-rank", "d4"), next_step("rt-verdant-muster")]),
            entry("Promoted", tier=OutcomeTier.EXCEPTIONAL, effects=[trait("gain_or_step_up", "trait-rel-rank", "d4"), next_step("rt-verdant-muster")]),
            entry("Promoted", tier=OutcomeTier.PERFECT, effects=[trait("gain_or_step_up", "trait-rel-rank", "d4"), next_step("rt-verdant-muster")]),
        ],
    ))

    # Muster-out — the term's end: continue, leave respectfully, or be expelled.
    upsert_table(RollTable(
        id="rt-verdant-muster",
        name="Muster Out",
        universe="three_realms",
        life_path="lp-verdant-disciple",
        scheme=RollTableScheme.RANGE,
        die=DieType.D6,
        entries=[
            entry("Serve another term", min_value=1, max_value=2,
                 effects=[trait("gain_or_step_up", "trait-rel-tenure", "d4"), next_step("rt-verdant-learn")]),
            entry("Muster out (respectfully)", min_value=3, max_value=5,
                 effects=[flow("muster")]),
            entry("Muster out (dishonorably)", min_value=6, max_value=6,
                 effects=[flow("force_muster")]),
        ],
    ))
