"""Life path term executor — runs the five-phase term loop."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from transversal.db.repository import EntityRepository

from transversal.domain import (
    DieType,
    Entity,
    LifePath,
    TraitSetting,
    dice_list_to_rating,
)
from transversal.services.dice_resolver import (
    DicePoolRequest,
    Opposition,
    resolve,
)
from transversal.services.lifepath_discovery import check_discovery


def take_term(
    entity: Entity,
    life_path: LifePath,
    razmerit_spent: int,
    repo: "EntityRepository",
) -> dict:
    """Execute one term of a life path.

    Runs qualification (if first term) and learn phases.
    Survive, event, and advance phases are stubbed for Phase D.

    Returns a dict suitable for constructing a TermResult.
    """
    qual = None
    learn = None
    new_trait_ids: list[str] = []
    modified_trait_ids: list[str] = []
    razmerit_change = 0

    is_continuing = (entity.current_life_path_id == life_path.id)

    # ── 0. Location gate ──────────────────────────────
    if life_path.qualification and life_path.qualification.must_be_at_location:
        if entity.current_location != life_path.qualification.must_be_at_location:
            return {
                "qualification": {
                    "success": False,
                    "drafted": False,
                    "drafted_path_id": None,
                    "location_blocked": True,
                },
                "learn": None,
                "survive": None,
                "event": None,
                "advance": None,
                "new_trait_settings": [],
                "modified_trait_settings": [],
                "razmerit_change": 0,
                "term_number": entity.terms_served,
            }

    # ── 1. Qualification ──────────────────────────────
    if not is_continuing and life_path.qualification:
        q = life_path.qualification
        pool_dice: list[tuple[DieType, str]] = []

        # Find the entity's trait setting for the qualification trait
        trait_settings = repo.get_traitsettings_for_entity(entity.id)
        for ts in trait_settings:
            if ts.trait_id == q.trait_id and ts.dice:
                for d in ts.dice:
                    pool_dice.append((d, q.trait_id))
                break

        if not pool_dice:
            # Entity doesn't have the trait — use d4 as minimum
            pool_dice = [(DieType.D4, q.trait_id)]

        # Apply razmerit: step up one die per razmerit spent (max 2)
        for _ in range(min(razmerit_spent, 2)):
            # Find the smallest die and step it up
            min_die = min(pool_dice, key=lambda d: d[0].max_value)
            idx = pool_dice.index(min_die)
            pool_dice[idx] = (min_die[0].step_up(), min_die[1])
            razmerit_change -= 1

        request = DicePoolRequest(
            entity_id=entity.id,
            universe=entity.current_universe,
            dice=pool_dice,
            razmerit_spent=min(razmerit_spent, 2),
            opposition=Opposition(
                type="static_difficulty",
                static_difficulty=q.difficulty.max_value,
            ),
        )
        result = resolve(request)
        # Success if tier is MARGINAL or better
        qual_success = result.tier.value not in ("fail",)

        qual = {
            "success": qual_success,
            "drafted": False,
            "drafted_path_id": None,
            "location_blocked": False,
        }

        if not qual_success:
            # Draft fallback
            if q.draft:
                qual["drafted"] = True
                qual["drafted_path_id"] = q.draft
            return {
                "qualification": qual,
                "learn": None,
                "survive": None,
                "event": None,
                "advance": None,
                "new_trait_settings": [],
                "modified_trait_settings": [],
                "razmerit_change": razmerit_change,
                "term_number": entity.terms_served,
            }
    elif not is_continuing:
        # No qualification block — auto-qualify
        qual = {
            "success": True,
            "drafted": False,
            "drafted_path_id": None,
            "location_blocked": False,
        }

    # ── 2. Learn phase ────────────────────────────────
    trait_settings = repo.get_traitsettings_for_entity(entity.id)
    curriculum_items = [c for c in life_path.curriculum if c.min_rank <= entity.current_rank]

    if curriculum_items:
        # Pick the first curriculum item the entity hasn't maxed out,
        # or the first one if all are maxed
        for ci in curriculum_items:
            existing = next((ts for ts in trait_settings if ts.trait_id == ci.trait_id), None)
            if existing and ci.step_up:
                # Step up the first die
                min_die = min(existing.dice, key=lambda d: d.max_value, default=None)
                if min_die and min_die != DieType.D12:
                    idx = existing.dice.index(min_die)
                    existing.dice[idx] = min_die.step_up()
                    existing.source_type = "life_path_term"
                    existing.source_life_path_id = life_path.id
                    existing.source_term_number = entity.terms_served + 1
                    repo.update_traitsetting(existing)
                    modified_trait_ids.append(existing.id)
                    learn = {
                        "trait_gained_id": existing.id,
                        "trait_name": ci.trait_id,
                        "was_stepped_up": True,
                    }
                    break
            elif not existing:
                # Create new trait setting at create_at rating
                ts = TraitSetting(
                    id=f"{entity.id}:{ci.trait_id}",
                    entity_id=entity.id,
                    trait_id=ci.trait_id,
                    traitset_id="",  # resolved from trait registry at creation time
                    dice=[ci.create_at],
                    source_type="life_path_term",
                    source_life_path_id=life_path.id,
                    source_term_number=entity.terms_served + 1,
                )
                repo.create_traitsetting(ts)
                new_trait_ids.append(ts.id)
                learn = {
                    "trait_gained_id": ts.id,
                    "trait_name": ci.trait_id,
                    "was_stepped_up": False,
                }
                break
    else:
        learn = None  # No curriculum items available

    # ── 3. Update entity ──────────────────────────────
    entity.terms_served += 1
    entity.current_life_path_id = life_path.id
    if not entity.discovered_life_paths:
        entity.discovered_life_paths = []
    if life_path.id not in entity.discovered_life_paths:
        entity.discovered_life_paths.append(life_path.id)
    repo.update_entity(entity)

    # ── 4. Return ─────────────────────────────────────
    return {
        "qualification": qual,
        "learn": learn,
        "survive": None,   # Phase D
        "event": None,     # Phase D
        "advance": None,   # Phase D
        "new_trait_settings": new_trait_ids,
        "modified_trait_settings": modified_trait_ids,
        "razmerit_change": razmerit_change,
        "term_number": entity.terms_served,
    }
