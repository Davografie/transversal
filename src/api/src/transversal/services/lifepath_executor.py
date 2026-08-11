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
                # Resolve traitset_id from the trait registry
                trait = repo.get_trait(ci.trait_id)
                resolved_ts_id = trait.traitset_id if trait else ""
                ts = TraitSetting(
                    id=f"{entity.id}:{ci.trait_id}",
                    entity_id=entity.id,
                    trait_id=ci.trait_id,
                    traitset_id=resolved_ts_id,
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

    # ── 3. Survive phase ──────────────────────────────
    survive_result = _run_survive(entity, life_path, repo)
    if survive_result and survive_result.get("forced_muster"):
        # Mishap forced muster-out: record with mishap_muster=True
        _record_muster(entity, life_path, repo, mishap_muster=True)
        return {
            "qualification": qual,
            "learn": learn,
            "survive": survive_result,
            "event": None,
            "advance": None,
            "new_trait_settings": new_trait_ids,
            "modified_trait_settings": modified_trait_ids,
            "razmerit_change": razmerit_change,
            "term_number": entity.terms_served,
        }

    # ── 4. Event phase ────────────────────────────────
    event_result = _run_event(entity, life_path, repo)

    # ── 5. Advance phase ──────────────────────────────
    advance_result = _run_advance(entity, life_path, repo)

    # ── 6. Return ─────────────────────────────────────
    return {
        "qualification": qual,
        "learn": learn,
        "survive": survive_result,
        "event": event_result,
        "advance": advance_result,
        "new_trait_settings": new_trait_ids,
        "modified_trait_settings": modified_trait_ids,
        "razmerit_change": razmerit_change,
        "term_number": entity.terms_served,
    }


# ── Phase implementations ─────────────────────────────

def _run_survive(entity, life_path, repo) -> dict | None:
    """Run the survive phase. Returns result dict or None if no survival block."""
    import random

    if not life_path.survival:
        return None

    # ── Calculate effective survival difficulty (term penalties) ──
    survival_difficulty = life_path.survival.difficulty

    # Per-path penalty: count terms already served in this path
    terms_in_path = sum(
        lt.terms_served for lt in entity.life_history if lt.path_id == life_path.id
    )
    if life_path.survival.term_penalty_after and terms_in_path >= life_path.survival.term_penalty_after:
        survival_difficulty = survival_difficulty.step_up()

    # Global penalty: every 7 total terms
    global_penalties = (entity.terms_served - 1) // 7  # terms_served already incremented
    for _ in range(global_penalties):
        survival_difficulty = survival_difficulty.step_up()

    # ── Assemble survival pool ──
    pool_dice: list[tuple[DieType, str]] = []
    trait_settings = repo.get_traitsettings_for_entity(entity.id)
    for ts in trait_settings:
        if ts.trait_id in life_path.survival.trait_ids and ts.dice:
            for d in ts.dice:
                pool_dice.append((d, ts.trait_id))

    if not pool_dice:
        pool_dice = [(DieType.D4, "untrained")]

    # ── Roll ──
    request = DicePoolRequest(
        entity_id=entity.id,
        universe=entity.current_universe,
        dice=pool_dice,
        opposition=Opposition(
            type="static_difficulty",
            static_difficulty=survival_difficulty.max_value,
        ),
    )
    result = resolve(request)
    survive_success = result.tier.value not in ("fail",)

    survive_data = {
        "success": survive_success,
        "roll_summary": f"{result.highest if hasattr(result, 'highest') else result.total} vs {survival_difficulty.max_value} — {'success' if survive_success else 'failure'}",
    }

    # ── Mishap ──
    if not survive_success and life_path.survival.mishaps:
        mishap = random.choice(life_path.survival.mishaps)
        survive_data["mishap_description"] = mishap.get("description", "[Mishap]")
        effect = mishap.get("effect", {})
        if effect.get("type") == "complication":
            comp_trait_id = effect.get("trait_id", "trait-complication-mishap")
            ts = TraitSetting(
                id=f"{entity.id}:{comp_trait_id}:{entity.terms_served}",
                entity_id=entity.id,
                trait_id=comp_trait_id,
                traitset_id="ts-complications",
                dice=[effect.get("die_type", DieType.D4)],
                negative=True,
                source_type="life_path_term",
                source_life_path_id=life_path.id,
                source_term_number=entity.terms_served,
            )
            repo.create_traitsetting(ts)
            survive_data["complication_trait_id"] = ts.id

    return survive_data


def _run_event(entity, life_path, repo) -> dict | None:
    """Run the event phase. Returns result dict or None if no events."""
    import random

    if not life_path.events:
        return None

    # Filter events by rank
    eligible = [e for e in life_path.events if e.min_rank <= entity.current_rank]
    if not eligible:
        return None

    event = random.choice(eligible)
    event_data = {
        "event_index": life_path.events.index(event) if event in life_path.events else 0,
        "description": event.description,
    }

    # Handle event effects
    effect = event.effect
    if effect.get("type") == "create_trait":
        trait_id = effect.get("trait_id", "")
        if trait_id:
            ts = TraitSetting(
                id=f"{entity.id}:{trait_id}:evt{entity.terms_served}",
                entity_id=entity.id,
                trait_id=trait_id,
                traitset_id=effect.get("traitset_id") or (repo.get_trait(trait_id).traitset_id if repo.get_trait(trait_id) else ""),
                dice=[effect.get("die_type", DieType.D4)],
                source_type="event",
                source_life_path_id=life_path.id,
                source_term_number=entity.terms_served,
            )
            repo.create_traitsetting(ts)
            event_data["trait_created_id"] = ts.id

    if effect.get("type") == "discover_path":
        path_id = effect.get("path_id", "")
        if path_id and entity.discovered_life_paths and path_id not in entity.discovered_life_paths:
            entity.discovered_life_paths.append(path_id)
            repo.update_entity(entity)
            event_data["discovered_path_id"] = path_id

    return event_data


def _run_advance(entity, life_path, repo) -> dict | None:
    """Run the advance phase. Returns result dict or None if no advancement block."""
    if not life_path.advancement or not life_path.advancement.ranks:
        return None

    # ── Assemble advancement pool ──
    pool_dice: list[tuple[DieType, str]] = []
    trait_settings = repo.get_traitsettings_for_entity(entity.id)
    for ts in trait_settings:
        if ts.trait_id in life_path.advancement.trait_ids and ts.dice:
            for d in ts.dice:
                pool_dice.append((d, ts.trait_id))

    if not pool_dice:
        pool_dice = [(DieType.D4, "untrained")]

    # ── Roll ──
    request = DicePoolRequest(
        entity_id=entity.id,
        universe=entity.current_universe,
        dice=pool_dice,
        opposition=Opposition(
            type="static_difficulty",
            static_difficulty=life_path.advancement.difficulty.max_value,
        ),
    )
    result = resolve(request)
    advance_success = result.tier.value not in ("fail",)

    advance_data = {
        "success": advance_success,
        "new_rank": entity.current_rank,
        "rank_name": "",
    }

    if advance_success and entity.current_rank < len(life_path.advancement.ranks):
        entity.current_rank += 1
        rank = life_path.advancement.ranks[entity.current_rank - 1]
        advance_data["new_rank"] = entity.current_rank
        advance_data["rank_name"] = rank.name

        # Apply rank benefits
        for benefit in rank.benefits:
            if benefit.get("type") == "trait":
                ts = TraitSetting(
                    id=f"{entity.id}:{benefit.get('trait_id', '')}:r{entity.current_rank}",
                    entity_id=entity.id,
                    trait_id=benefit.get("trait_id", ""),
                    traitset_id=benefit.get("traitset_id") or (repo.get_trait(benefit.get("trait_id", "")).traitset_id if repo.get_trait(benefit.get("trait_id", "")) else ""),
                    dice=[benefit.get("die_type", DieType.D4)],
                    source_type="life_path_term",
                    source_life_path_id=life_path.id,
                )
                repo.create_traitsetting(ts)
        repo.update_entity(entity)
    else:
        # Get current rank name for the response
        if entity.current_rank > 0 and entity.current_rank <= len(life_path.advancement.ranks):
            advance_data["rank_name"] = life_path.advancement.ranks[entity.current_rank - 1].name

    return advance_data


def _record_muster(entity, life_path, repo, mishap_muster: bool = False) -> None:
    """Record a completed life path in the entity's life_history."""
    lt_dict = {
        "path_id": life_path.id,
        "path_name": life_path.name,
        "universe": life_path.universe,
        "terms_served": 1,  # will be aggregated later
        "final_rank": entity.current_rank,
        "mustered_out": True,
        "mishap_muster": mishap_muster,
    }
    # Append to life_history
    if entity.life_history is None:
        entity.life_history = []
    entity.life_history.append(lt_dict)
    entity.current_life_path_id = None
    entity.current_rank = 0
    repo.update_entity(entity)


def muster_out(entity: Entity, repo: "EntityRepository") -> dict:
    """Voluntarily muster out of the current life path.

    Calculates benefits, records the term in life_history, and resets path state.
    Returns a dict suitable for constructing a MusterOutResult.
    """
    if not entity.current_life_path_id:
        raise ValueError("Entity is not currently in a life path")

    life_path = repo.get_lifepath(entity.current_life_path_id)
    if not life_path:
        raise ValueError(f"LifePath '{entity.current_life_path_id}' not found")

    # Count total terms in this path from life_history + current enrollment
    terms_in_path = sum(
        lt.terms_served for lt in entity.life_history if lt.path_id == life_path.id
    ) + 1

    razmerit_gained = 0
    benefits = []

    # Per-term benefits
    if life_path.muster_out and life_path.muster_out.per_term_benefits:
        for benefit in life_path.muster_out.per_term_benefits:
            if benefit.get("type") == "razmerit":
                amount_str = benefit.get("amount", "0")
                if "d" in str(amount_str):
                    # e.g. "1d6" — roll it
                    import random, re
                    match = re.match(r"(\d+)d(\d+)", str(amount_str))
                    if match:
                        count, sides = int(match.group(1)), int(match.group(2))
                        amount = sum(random.randint(1, sides) for _ in range(count))
                        amount *= terms_in_path
                    else:
                        amount = 0
                else:
                    amount = int(amount_str) * terms_in_path
                razmerit_gained += amount
                entity.razmerit += amount
                benefits.append(f"{amount} razmerit")

    # Rank bonuses
    if life_path.muster_out and life_path.muster_out.at_ranks and entity.current_rank > 0:
        rank_key = str(entity.current_rank)
        if rank_key in life_path.muster_out.at_ranks:
            for benefit in life_path.muster_out.at_ranks[rank_key]:
                if benefit.get("type") == "razmerit":
                    razmerit_gained += benefit.get("amount", 0)
                    entity.razmerit += benefit.get("amount", 0)
                    benefits.append(f"rank bonus: {benefit.get('amount', 0)} razmerit")
                elif benefit.get("type") == "trait":
                    ts = TraitSetting(
                        id=f"{entity.id}:{benefit.get('trait_id', '')}:mo",
                        entity_id=entity.id,
                        trait_id=benefit.get("trait_id", ""),
                        traitset_id=benefit.get("traitset_id") or (repo.get_trait(benefit.get("trait_id", "")).traitset_id if repo.get_trait(benefit.get("trait_id", "")) else ""),
                        dice=[benefit.get("die_type", DieType.D4)],
                        source_type="life_path_term",
                        source_life_path_id=life_path.id,
                    )
                    repo.create_traitsetting(ts)
                    benefits.append(f"trait: {benefit.get('trait_id', '')}")

    # Record in life_history
    _record_muster(entity, life_path, repo, mishap_muster=False)

    return {
        "path_id": life_path.id,
        "path_name": life_path.name,
        "terms_served": terms_in_path,
        "final_rank": entity.current_rank,
        "mishap_muster": False,
        "benefits": benefits,
        "razmerit_gained": razmerit_gained,
        "entity": entity,
    }
