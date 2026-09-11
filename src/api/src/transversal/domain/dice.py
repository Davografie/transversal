"""Dice — split out of src/api/src/transversal/domain/__init__.py."""

from pydantic import BaseModel
from pydantic import Field
from pydantic import field_validator
from typing import Optional
from transversal.domain.enums import (
    ContestWinner,
    DieType,
    OutcomeTier,
    RollKind,
)


class DieSpec(BaseModel):
    """A die awaiting a roll — the shape shared by pools and roll requests.

    ``source_kind`` is extensible (trait / difficulty / manual / entity /
    projection / location / …); ``source_id`` is the specific identifier;
    ``label`` is the display name; ``ts_id`` is the trait-setting id.
    """
    die: DieType
    source_kind: str = "manual"
    source_id: str = ""
    label: str = ""
    ts_id: Optional[str] = None
    resource: bool = False  # resource-pool die: rolled separately, highest applies to total

class DieRoll(DieSpec):
    """A rolled die — a DieSpec plus its result and outcome tier.

    ``tier`` is the OutcomeTiers-table mapping of ``result`` (1–12) to an
    outcome tier; ``tier.effect_die`` gives the tier's virtual effect die.
    """
    result: int
    tier: Optional[OutcomeTier] = None

def _coerce_die_list(value) -> list[DieSpec]:
    """Accept both legacy `(die, source)` tuples and DieSpec-like dicts."""
    out: list[DieSpec] = []
    for item in value:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            die, source = item
            src = str(source or "")
            out.append(DieSpec(die=die, source_kind="manual", source_id=src, label=src))
        else:
            out.append(item)
    return out

class Opposition(BaseModel):
    type: str  # "challenge", "gmc", "static_difficulty"
    dice: list[DieSpec] = Field(default_factory=list)
    challenge_die: Optional[DieType] = None
    static_difficulty: Optional[int] = None

    @field_validator("dice", mode="before")
    @classmethod
    def _coerce_dice(cls, v):
        return _coerce_die_list(v)

class DicePoolRequest(BaseModel):
    entity_id: str
    universe: str
    dice: list[DieSpec]
    opposition: Optional[Opposition] = None
    razmerit_spent: int = 0
    kind: RollKind = RollKind.TEST
    pipeline: Optional[str] = None  # "simplified" | "pool" | None (auto by size)
    hitches_apply: bool = True  # False for GM difficulty rolls (1s are just dice)
    total_dice_bonus: int = 0  # extra dice kept in the total (base 2)
    effect_dice_bonus: int = 0  # extra effect dice kept (base 1)

    @field_validator("dice", mode="before")
    @classmethod
    def _coerce_dice(cls, v):
        return _coerce_die_list(v)

class ChallengeResult(BaseModel):
    targeted_die: DieType
    effect_die: Optional[DieType]
    outcome: str
    new_challenge_rating: Optional[str] = None

class SimplifiedResult(BaseModel):
    pipeline: str = "simplified"
    kind: RollKind = RollKind.TEST
    rolls: list[DieRoll]
    highest: int
    tier: OutcomeTier
    effect_die: Optional[DieType]
    hitches: list[DieRoll]
    botch: bool
    opposition_roll: Optional[DieRoll] = None
    opposition_total: Optional[int] = None
    challenge_result: Optional[ChallengeResult] = None
    hitches_count: int = 0

class PoolResult(BaseModel):
    pipeline: str = "pool"
    kind: RollKind = RollKind.TEST
    rolls: list[DieRoll]
    kept: list[DieRoll]
    total: int
    resource_rolls: list[DieRoll] = Field(default_factory=list)
    resource_kept: Optional[DieRoll] = None
    effect_die: Optional[DieType]
    effect_die_value: Optional[int]
    effect_dice: list[DieRoll] = Field(default_factory=list)  # all kept effect dice (effect_die is the primary/highest)
    unused: list[DieRoll]
    hitches: list[DieRoll]
    botch: bool
    opposition_rolls: list[DieRoll] = Field(default_factory=list)
    opposition_total: Optional[int] = None
    challenge_result: Optional[ChallengeResult] = None
    hitches_count: int = 0

RollResult = SimplifiedResult | PoolResult

class ContestResult(BaseModel):
    """Result of a head-to-head contest between two sides.

    Both sides roll their pools independently (they may use different
    pipelines) and the resolver compares totals/tiers to declare a winner.
    Effect dies are available for both sides — the winner's effect die
    determines the magnitude of their success; the loser's may still
    matter for certain SFX or narrative mechanics.

    """
    pipeline: str  # "simplified" or "pool" — which pipeline the contest used
    kind: RollKind = RollKind.CONTEST
    winner: ContestWinner
    player_result: SimplifiedResult | PoolResult
    opponent_result: SimplifiedResult | PoolResult
    pushed: bool = False
    push_cost: int = 1

class CommittedResult(BaseModel):
    """One side's committed contest result (after rolling + picking).

    ``total`` is the pool total, or the highest die for a simplified side.
    ``tier`` is the outcome tier for simplified sides.  A committed result
    is frozen — further trait changes don't touch it.
    """
    total: int
    effect_die: Optional[DieType] = None
    tier: Optional[OutcomeTier] = None
    pipeline: str = "pool"  # "pool" | "simplified"

class ContestOutcome(BaseModel):
    """The outcome of a manual contest after both sides commit (or give in).

    ``gave_in`` records which side conceded (``ContestWinner.PLAYER`` means
    the challenger gave in); the other side is the winner.
    """
    winner: ContestWinner
    challenger: Optional[CommittedResult] = None
    defendant: Optional[CommittedResult] = None
    gave_in: Optional[ContestWinner] = None
    pushed: bool = False
    high_stakes: bool = False
    effect_die: Optional[DieType] = None  # effective complication die to apply to the loser
    taken_out: bool = False

class ContestCompare(BaseModel):
    """Provisional contest comparison after both sides commit.

    Produced instead of a final outcome when the attacker beats the current
    difficulty: the now-losing side must give in or push (continue) once.
    """
    status: str = "compare"
    pending: str                       # entity_id that must give in or push
    initiative: str                    # entity_id holding the current difficulty
    challenger_id: str
    defendant_id: str
    challenger: Optional[CommittedResult] = None
    defendant: Optional[CommittedResult] = None
    margin: int = 0                    # attacker total - difficulty total (positive)

def dice_list_to_rating(dice: list[DieType]) -> str:
    """Convert a dice array to a human-readable rating string.

    [D4, D4, D4, D4] → "4d4"
    [D4, D4, D6, D6] → "2d4 + 2d6"
    [D8]             → "d8"
    []               → "empty"
    """
    if not dice:
        return "empty"
    counts: dict[DieType, int] = {}
    for d in dice:
        counts[d] = counts.get(d, 0) + 1
    parts: list[str] = []
    for die in sorted(counts.keys(), key=lambda d: d.max_value):
        n = counts[die]
        parts.append(die.value if n == 1 else f"{n}{die.value}")
    return " + ".join(parts)
