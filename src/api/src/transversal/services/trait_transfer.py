"""Trait transfer mutations — teach, gift, and take traits between entities."""

from typing import Optional

from transversal.domain import (
    DicePoolRequest,
    DieType,
    Opposition,
    TraitSetting,
    TransferFlags,
)
from transversal.services.dice_resolver import resolve_contest


# ── Teaching Die Step-Down Table ────────────────────────

_TEACH_STEP_DOWN: dict[DieType, DieType] = {
    DieType.D4: DieType.D4,
    DieType.D6: DieType.D4,
    DieType.D8: DieType.D6,
    DieType.D10: DieType.D6,
    DieType.D12: DieType.D8,
}


# ── Method Trait Keywords ───────────────────────────────

_METHOD_KEYWORDS: dict[str, list[str]] = {
    "stealth": ["perception", "stealth", "sneak", "hide", "shadow", "covert"],
    "combat": ["combat", "strength", "fight", "brawl", "melee", "weapon"],
    "social": ["willpower", "persuasion", "charm", "charisma", "negotiate", "deceive"],
    "technical": ["hacking", "intelligence", "tech", "repair", "engineer", "computers"],
}


def _match_method(trait_id: str, trait_name: str, method: str) -> bool:
    """Check if a trait matches the given method based on its id/name keywords."""
    keywords = _METHOD_KEYWORDS.get(method, [])
    combined = (trait_id + " " + trait_name).lower()
    for kw in keywords:
        if kw in combined:
            return True
    return False


# ── Transfer Flags Resolution ───────────────────────────

def resolve_transfer_flags(trait_setting, repo) -> TransferFlags:
    """Get effective TransferFlags for a trait setting by checking trait → traitset."""
    trait = repo.get_trait(trait_setting.trait_id)
    if trait and trait.transfer_flags:
        return trait.transfer_flags
    if trait:
        traitset = repo.get_traitset_by_id(trait.traitset_id)
        if traitset and traitset.transfer_flags:
            return traitset.transfer_flags
    return TransferFlags()


# ── Teach ───────────────────────────────────────────────

def teach_trait(teacher_id: str, student_id: str, trait_setting_id: str, repo) -> dict:
    """Teach a trait from teacher to student.

    Creates a new TraitSetting on the student at a reduced die rating.
    """
    # 1. Get teacher's TraitSetting
    ts = repo.get_traitsetting(trait_setting_id)
    if ts is None:
        raise ValueError(f"TraitSetting '{trait_setting_id}' not found")
    if ts.entity_id != teacher_id:
        raise ValueError(f"TraitSetting '{trait_setting_id}' does not belong to teacher '{teacher_id}'")

    # 2. Verify teachable
    flags = resolve_transfer_flags(ts, repo)
    if not flags.teachable:
        raise ValueError(f"Trait '{ts.trait_id}' is not teachable")

    # 3. Get teacher's current die rating (use the first die)
    if not ts.dice:
        raise ValueError(f"TraitSetting '{trait_setting_id}' has no dice")
    teacher_die = ts.dice[0]

    # 4. Determine student's rating
    student_die = _TEACH_STEP_DOWN.get(teacher_die, DieType.D4)

    # 5. Create new TraitSetting on student
    new_id = f"{student_id}:{ts.trait_id}"
    new_ts = TraitSetting(
        id=new_id,
        entity_id=student_id,
        trait_id=ts.trait_id,
        traitset_id=ts.traitset_id,
        rating_type=ts.rating_type,
        dice=[student_die],
        statement=ts.statement,
        # Provenance
        source_type="taught",
        source_entity_id=teacher_id,
        source_trait_setting_id=trait_setting_id,
    )
    created = repo.create_traitsetting(new_ts)

    return {"student_trait_setting": created, "razmerit_cost": 1}


# ── Gift ────────────────────────────────────────────────

def gift_trait(giver_id: str, recipient_id: str, trait_setting_id: str, repo) -> dict:
    """Gift a trait from giver to recipient.

    Transfers the existing TraitSetting by changing its entity_id.
    """
    # 1. Get TraitSetting, verify ownership
    ts = repo.get_traitsetting(trait_setting_id)
    if ts is None:
        raise ValueError(f"TraitSetting '{trait_setting_id}' not found")
    if ts.entity_id != giver_id:
        raise ValueError(f"TraitSetting '{trait_setting_id}' does not belong to giver '{giver_id}'")

    # 2. Verify giftable
    flags = resolve_transfer_flags(ts, repo)
    if not flags.giftable:
        raise ValueError(f"Trait '{ts.trait_id}' is not giftable")

    # 3. Change entity_id
    ts.entity_id = recipient_id

    # 4. Update id if it follows the {entity}:{trait} pattern
    if ":" in trait_setting_id:
        ts.id = f"{recipient_id}:{ts.trait_id}"

    # 5. Set provenance
    ts.source_type = "gifted"
    ts.source_entity_id = giver_id

    # 6. Create relationship edge
    rel = repo.create_relationship(giver_id, recipient_id, "gifted",
                                   description=f"Gifted trait {ts.trait_id}")

    # 7. Update the TraitSetting
    updated = repo.update_traitsetting(ts)

    return {"transferred_trait": updated, "relationship_created": rel}


# ── Take ────────────────────────────────────────────────

def take_trait(taker_id: str, victim_id: str, trait_setting_id: str, method: str, repo) -> dict:
    """Take a trait from victim by contest.

    On success: transfers the trait to taker.
    On failure: creates a "suspects" relationship from victim to taker.
    """
    # 1. Get TraitSetting, verify ownership
    ts = repo.get_traitsetting(trait_setting_id)
    if ts is None:
        raise ValueError(f"TraitSetting '{trait_setting_id}' not found")
    if ts.entity_id != victim_id:
        raise ValueError(f"TraitSetting '{trait_setting_id}' does not belong to victim '{victim_id}'")

    # 2. Verify takable
    flags = resolve_transfer_flags(ts, repo)
    if not flags.takable:
        raise ValueError(f"Trait '{ts.trait_id}' is not takable")

    # 3. Assemble dice pools
    taker_settings = repo.get_traitsettings_for_entity(taker_id)
    victim_settings = repo.get_traitsettings_for_entity(victim_id)

    # Taker: prefer method-matching traits, fall back to all
    taker_dice: list[tuple[DieType, str]] = []
    for s in taker_settings:
        if not s.dice:
            continue
        trait = repo.get_trait(s.trait_id)
        trait_name = trait.name if trait else ""
        if _match_method(s.trait_id, trait_name, method):
            for d in s.dice[:3]:  # up to 3 dice per relevant trait
                taker_dice.append((d, s.trait_id))
    # If no method-matching traits found, use all
    if not taker_dice:
        for s in taker_settings:
            if not s.dice:
                continue
            for d in s.dice[:3]:
                taker_dice.append((d, s.trait_id))

    # Victim: use all trait settings
    victim_dice: list[tuple[DieType, str]] = []
    for s in victim_settings:
        if not s.dice:
            continue
        for d in s.dice[:3]:
            victim_dice.append((d, s.trait_id))

    # Get entities for universe context
    taker_entity = repo.get_entity(taker_id)
    universe = taker_entity.current_universe if taker_entity else "unknown"

    # Build DicePoolRequests
    player_req = DicePoolRequest(
        entity_id=taker_id,
        universe=universe,
        dice=taker_dice,
    )
    opponent_req = DicePoolRequest(
        entity_id=victim_id,
        universe=universe,
        dice=victim_dice,
    )

    # 4. Resolve contest
    contest_result = resolve_contest(player_req, opponent_req)

    # 5. Determine success
    from transversal.domain import ContestWinner
    success = contest_result.winner in (ContestWinner.PLAYER,)

    if success:
        # Transfer the trait
        ts.entity_id = taker_id
        if ":" in trait_setting_id:
            ts.id = f"{taker_id}:{ts.trait_id}"
        ts.source_type = "taken"
        ts.source_entity_id = victim_id
        ts.stolen = True
        updated = repo.update_traitsetting(ts)
        return {
            "success": True,
            "contest_result": contest_result,
            "transferred_trait": updated,
            "stolen": True,
        }
    else:
        # Create suspects relationship
        repo.create_relationship(victim_id, taker_id, "suspects",
                                 description=f"Suspects theft of trait {ts.trait_id}")
        return {
            "success": False,
            "contest_result": contest_result,
            "transferred_trait": None,
        }
