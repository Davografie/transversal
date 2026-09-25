"""Seed data — populate the trait registry and SFX definitions."""

from transversal.db.repository import EntityRepository
from transversal.domain import (
    DieType,
    Effect,
    EffectTiming,
    Entity,
    EntityType,
    Polarity,
    RatingType,
    SFX,
    Trait,
    TraitSetting,
)
from transversal.services.target_spec import SelectStep, TargetSpec


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
                         type="attune", action="enable", target="wielder",
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
                         target_spec=TargetSpec(steps=[SelectStep(collection="source")]),
                         result="d4"),
                Effect(timing=EffectTiming.IMMEDIATE,
                         type="transfer_razmerit", action="earn",
                         target="self", result="1"),
            ],
        ),
        SFX(
            id="sfx-give-in-get-razmerit",
            name="Give In Reward",
            description="Gain 1 razmerit when you give in during a contest",
            limit="",
            trigger="on_give_in",
            effects=[
                Effect(timing=EffectTiming.IMMEDIATE,
                         type="transfer_razmerit", action="earn",
                         target="self", result="1"),
            ],
        ),
        SFX(
            id="sfx-give-in-targeting-ban",
            name="Give In — Keep Your Distance",
            description="When you give in, you can't target that opponent for the rest of the scene",
            limit="",
            trigger="on_give_in",
            effects=[
                Effect(timing=EffectTiming.IMMEDIATE,
                         type="entity", action="targeting_ban",
                         target="", result="1"),
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
    # Seeding writes SFX records in-process; the availability cache must not
    # keep serving the pre-seed view of them.
    from transversal.services.sfx_owner import invalidate_sfx_cache
    invalidate_sfx_cache()

def seed_locations(em) -> None:
    """Create location entities and their hierarchy relationships. Idempotent."""
    repo = em.repo

    locations = [
        {"id": "loc-valley", "name": "Valley of Ascension", "universe": "three_realms"},
        {"id": "loc-platform", "name": "The Arrival Platform", "universe": "three_realms"},
        {"id": "loc-mistwood", "name": "The Mistwood", "universe": "three_realms"},
        {"id": "loc-sect", "name": "Verdant Steps Sect Grounds", "universe": "three_realms"},
        {"id": "loc-krasnoyarsk", "name": "Krasnoyarsk-45", "universe": "earth", "starter_location": True},
    ]

    for loc in locations:
        if not repo.get_entity(loc["id"]):
            repo.create_entity(Entity(
                id=loc["id"], type=EntityType.LOCATION,
                name=loc["name"], current_universe=loc["universe"],
                current_location=loc["id"], razmerit=0,
                starter_location=loc.get("starter_location", False),
            ))
        elif loc.get("starter_location"):
            existing = repo.get_entity(loc["id"])
            if not existing.starter_location:
                existing.starter_location = True
                repo.update_entity(existing)

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

    # Zones are not seeded: a zone is a link to a child location, and the real
    # ones are appended by `_ensure_child_zone` when a `super` edge is created.
    # (Hand-written test zones used to live here; removed 2026-09-23.)
    # ── Seed challenge traits on locations ────────────
    # A location's doom pool (negative challenge trait) lives in the location
    # trait set. Each entry: (location_id, trait_id, trait_name, dice, polarity).
    _challenge_traits = [
        ("loc-krasnoyarsk", "trait-regime-alert", "regime alert",
         [DieType.D6, DieType.D6, DieType.D8], Polarity.NEGATIVE),
        ("loc-sect", "trait-sect-suspicion", "sect suspicion",
         [DieType.D6], Polarity.NEGATIVE),
    ]
    for loc_id, trait_id, name, dice, polarity in _challenge_traits:
        if not repo.get_trait(trait_id):
            repo.create_trait(Trait(
                id=trait_id, name=name,
                traitset_id="ts-location-afd2",
                default_die_type=dice[0],
                default_rating_type=RatingType.CHALLENGE,
                polarity=polarity,
            ))
        ts_key = f"{loc_id}:challenge:{trait_id.removeprefix('trait-')}"
        if not repo.get_traitsetting(ts_key):
            try:
                repo.create_traitsetting(TraitSetting(
                    id=ts_key, entity_id=loc_id,
                    trait_id=trait_id,
                    rating_type=RatingType.CHALLENGE,
                    dice=list(dice),
                    polarity=polarity,
                ))
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
    seed_sfx_registry(em.repo)
    seed_locations(em)
    seed_life_paths(em.repo)


def seed_life_paths(repo) -> None:
    """Seed the life path content graph: factions, entry points, and linked tables.

    The Verdant Steps Sect path (qualify → learn → survive → mishap/advance →
    muster-out) and the three_realms Rogue Cultivator drifter path are wired
    end-to-end. The earth drifter path remains an entry-point stub.
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
    ROGUE_FACTION = "fac-rogue-cultivators"

    # ── Effect / table builders ───────────────────────
    def eff(type_, action, target="", result=None, context=None, negative=False,
            target_spec=None):
        return Effect(
            timing=EffectTiming.IMMEDIATE,
            type=type_,
            action=action,
            target=target,
            result=result,
            negative=negative,
            context=context or {},
            target_spec=target_spec,
        )

    def rank_die_path(relationship):
        """The lowest rating die of the rank instance on the tie to ``relationship``.

        A demotion changes a **die**: a rating is a list, so "step down the rank"
        has to say which one, and the trait-level verb (retired) silently stepped
        the smallest without the card being able to say so. The path names the tie,
        then the rank instance anchored to it, then the lowest of that rating's
        dice.
        """
        return TargetSpec.model_validate({"steps": [
            {"kind": "select", "collection": "self"},
            {"kind": "navigate", "edge": "relationships"},
            {"kind": "filter", "field": "contact_id", "operator": "==", "value": relationship},
            {"kind": "filter", "field": "type", "operator": "==", "value": "membership"},
            {"kind": "navigate", "edge": "traitsettings"},
            {"kind": "filter", "field": "trait_id", "operator": "==", "value": "trait-rel-rank"},
            {"kind": "navigate", "edge": "rating_dice"},
            {"kind": "aggregate", "fn": "bottom", "field": "rating", "count": 1},
        ]})

    def demote(relationship=FACTION):
        return eff("modify_roll", "step_down_die", target_spec=rank_die_path(relationship))

    def flow(action, target="", context=None):
        return eff("life_path", action, target, context=context)

    def next_step(target="", return_to=None):
        return flow("next_step", target, context={"return_to": return_to} if return_to else None)

    def trait(action, trait_id, die=None, relationship=FACTION, negative=False):
        ctx = {"relationship": relationship} if relationship else {}
        return eff("modify_trait", action, trait_id, result=die, context=ctx, negative=negative)

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
            entry_table_id="rt-drifter-3r-learn",
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
            entry(name, effects=[trait("gain_or_step_up", tid, die, relationship=None),
                                 next_step("rt-survive", return_to={"survived": "rt-verdant-advance", "injured": "rt-verdant-mishap"})])
            for tid, die, name in learn_skills
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
            entry("Qi backlash", effects=[trait("gain_or_step_up", "trait-3r-qi-reserves", "d4", relationship=None, negative=True), next_step("rt-verdant-advance")]),
            entry("Lost ground", effects=[eff("transfer_razmerit", "spend", "self", "2"), next_step("rt-verdant-advance")]),
            entry("Wounded spirit", effects=[trait("gain_or_step_up", "trait-3r-dao-comprehension", "d4", relationship=None, negative=True), next_step("rt-verdant-advance")]),
            entry("Demoted", effects=[demote(), next_step("rt-verdant-advance")]),
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
            entry("Promoted", tier=OutcomeTier.SUCCESS, effects=[trait("gain_or_step_up", "trait-rel-rank", "d4"), next_step("rt-continue", return_to={"next": "rt-verdant-learn"})]),
            entry("Promoted", tier=OutcomeTier.EXCEPTIONAL, effects=[trait("gain_or_step_up", "trait-rel-rank", "d4"), next_step("rt-continue", return_to={"next": "rt-verdant-learn"})]),
            entry("Promoted", tier=OutcomeTier.PERFECT, effects=[trait("gain_or_step_up", "trait-rel-rank", "d4"), next_step("rt-continue", return_to={"next": "rt-verdant-learn"})]),
        ],
    ))

    # ── Rogue Cultivators (drifter) chain ─────────────

    rogue = Entity(
        id=ROGUE_FACTION,
        type=EntityType.FACTION,
        name="Rogue Cultivators",
        current_universe="three_realms",
        active_universes=["three_realms"],
        suitable_life_path_ids=["lp-drifter-three-realms"],
    )
    if repo.get_entity(ROGUE_FACTION) is None:
        repo.create_entity(rogue)
    else:
        repo.update_entity(rogue)

    # Learn — no qualification gate; a drifter accepts anyone who walks the land.
    upsert_table(RollTable(
        id="rt-drifter-3r-learn",
        name="Learn",
        universe="three_realms",
        life_path="lp-drifter-three-realms",
        scheme=RollTableScheme.INDEX,
        entries=[
            entry(name, effects=[trait("gain_or_step_up", tid, die, relationship=None),
                                 next_step("rt-survive", return_to={"survived": "rt-drifter-3r-advance", "injured": "rt-drifter-3r-mishap"})])
            for tid, die, name in learn_skills
        ],
    ))

    # Mishap — complication / loss, or forced muster.
    upsert_table(RollTable(
        id="rt-drifter-3r-mishap",
        name="Mishap",
        universe="three_realms",
        life_path="lp-drifter-three-realms",
        scheme=RollTableScheme.INDEX,
        entries=[
            entry("Lost a little face", effects=[eff("transfer_razmerit", "spend", "self", "1"), next_step("rt-drifter-3r-advance")]),
            entry("Qi backlash", effects=[trait("gain_or_step_up", "trait-3r-qi-reserves", "d4", relationship=None, negative=True), next_step("rt-drifter-3r-advance")]),
            entry("Lost ground", effects=[eff("transfer_razmerit", "spend", "self", "2"), next_step("rt-drifter-3r-advance")]),
            entry("Wounded spirit", effects=[trait("gain_or_step_up", "trait-3r-dao-comprehension", "d4", relationship=None, negative=True), next_step("rt-drifter-3r-advance")]),
            entry("Demoted", effects=[demote(ROGUE_FACTION), next_step("rt-drifter-3r-advance")]),
            entry("Expelled", effects=[flow("force_muster")]),
        ],
    ))

    # Advance — roll Dao Comprehension; rank up on success, else another term.
    upsert_table(RollTable(
        id="rt-drifter-3r-advance",
        name="Advancement",
        universe="three_realms",
        life_path="lp-drifter-three-realms",
        scheme=RollTableScheme.TIER,
        check=RollTableCheck(trait_ids=["trait-3r-dao-comprehension"], difficulty=DieType.D6),
        entries=[
            entry("No progress", tier=OutcomeTier.FAIL, effects=[next_step("rt-drifter-3r-learn")]),
            entry("No progress", tier=OutcomeTier.MARGINAL, effects=[next_step("rt-drifter-3r-learn")]),
            entry("Promoted", tier=OutcomeTier.SUCCESS, effects=[trait("gain_or_step_up", "trait-rel-rank", "d4", relationship=ROGUE_FACTION), next_step("rt-continue", return_to={"next": "rt-drifter-3r-learn"})]),
            entry("Promoted", tier=OutcomeTier.EXCEPTIONAL, effects=[trait("gain_or_step_up", "trait-rel-rank", "d4", relationship=ROGUE_FACTION), next_step("rt-continue", return_to={"next": "rt-drifter-3r-learn"})]),
            entry("Promoted", tier=OutcomeTier.PERFECT, effects=[trait("gain_or_step_up", "trait-rel-rank", "d4", relationship=ROGUE_FACTION), next_step("rt-continue", return_to={"next": "rt-drifter-3r-learn"})]),
        ],
    ))

    # ── Shared tables (life_path=None, reused across life paths) ──

    # Survive — roll Qi Reserves; injured → the path's mishap, survived → its advance.
    upsert_table(RollTable(
        id="rt-survive",
        name="Survival",
        universe="",
        life_path=None,
        scheme=RollTableScheme.TIER,
        check=RollTableCheck(trait_ids=["trait-3r-qi-reserves"], difficulty=DieType.D6),
        entries=[
            entry("Injured", tier=OutcomeTier.FAIL, effects=[next_step("{return:injured}")]),
            entry("Survived", tier=OutcomeTier.MARGINAL, effects=[next_step("{return:survived}")]),
            entry("Survived", tier=OutcomeTier.SUCCESS, effects=[next_step("{return:survived}")]),
            entry("Survived", tier=OutcomeTier.EXCEPTIONAL, effects=[next_step("{return:survived}")]),
            entry("Survived", tier=OutcomeTier.PERFECT, effects=[next_step("{return:survived}")]),
        ],
    ))

    # Continue — after promotion: serve another term (return to the path's learn) or muster out.
    upsert_table(RollTable(
        id="rt-continue",
        name="Continue",
        universe="",
        life_path=None,
        scheme=RollTableScheme.RANGE,
        die=DieType.D6,
        entries=[
            entry("Serve another term", min_value=1, max_value=2,
                 effects=[trait("gain_or_step_up", "trait-rel-tenure", "d4", relationship="{term_faction}"), next_step("{return:next}")]),
            entry("Muster out (respectfully)", min_value=3, max_value=5,
                 effects=[flow("muster")]),
            entry("Muster out (dishonorably)", min_value=6, max_value=6,
                 effects=[flow("force_muster")]),
        ],
    ))

    # Remove the per-path Survive/Muster tables superseded by the shared ones.
    for old_id in ("rt-verdant-survive", "rt-drifter-3r-survive", "rt-verdant-muster", "rt-drifter-3r-muster"):
        repo.delete_roll_table(old_id)
