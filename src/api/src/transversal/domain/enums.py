"""Enums — split out of src/api/src/transversal/domain/__init__.py."""

from enum import Enum
from typing import Optional


class DieType(str, Enum):
    D4 = "d4"
    D6 = "d6"
    D8 = "d8"
    D10 = "d10"
    D12 = "d12"

    @property
    def max_value(self) -> int:
        return int(self.value[1:])

    @property
    def tier(self) -> int:
        """Where the die sits on the ladder: ``d4`` → 1 … ``d12`` → 5.

        A *different number* from :attr:`max_value` (the side count): the two
        order identically and arithmetically disagree, which is exactly why a
        conversion has to be named rather than assumed. See
        ``domain.rating.die_tier``.
        """
        return list(DieType).index(self) + 1

    def step_up(self) -> "DieType":
        order = list(DieType)
        idx = order.index(self)
        return order[idx + 1] if idx < len(order) - 1 else self

    def step_down(self) -> "DieType":
        order = list(DieType)
        idx = order.index(self)
        return order[idx - 1] if idx > 0 else self

class RatingType(str, Enum):
    STATIC = "static"
    RESOURCE = "resource"
    CHALLENGE = "challenge"
    EMPTY = "empty"

class Polarity(str, Enum):
    """Whether a trait is a benefit/asset (positive) or a complication (negative).

    Applies to every trait, not just challenge pools.  Trait settings bake a
    concrete polarity at creation from the trait/traitset defaults; the enum is
    the single source of truth for that sign.
    """
    NEGATIVE = "negative"
    POSITIVE = "positive"

class OutcomeTier(str, Enum):
    FAIL = "fail"
    MARGINAL = "marginal"
    SUCCESS = "success"
    EXCEPTIONAL = "exceptional"
    PERFECT = "perfect"

    @property
    def effect_die(self) -> Optional[DieType]:
        return {
            OutcomeTier.FAIL: None,
            OutcomeTier.MARGINAL: DieType.D4,
            OutcomeTier.SUCCESS: DieType.D6,
            OutcomeTier.EXCEPTIONAL: DieType.D8,
            OutcomeTier.PERFECT: DieType.D10,
        }[self]

class EntityType(str, Enum):
    CHARACTER = "character"
    LOCATION = "location"
    FACTION = "faction"
    ASSET = "asset"
    GMC = "gmc"
    UNIVERSE = "universe"
    SUBTRAIT = "subtrait"
    RELATION = "relation"

class TransversalType(str, Enum):
    NATIVE = "native"
    CONSCIOUSNESS = "consciousness"
    INAPPOSITE = "inapposite"


class ArrivalKind(str, Enum):
    """How an entity came to be where it now is.

    Carried on every location change — in the SSE payload and in the SFX event
    context — so a rule (or the viewer) can tell a portal from a step up the
    hierarchy, a direct placement, or being moved by an effect.
    """
    TRANSVERSAL = "transversal"  # through a portal / cross-boundary travel
    HIERARCHY = "hierarchy"      # up or down a sub-location (`super` edge)
    MOVE = "move"                # direct relocation (GM drag, panel, placement)
    EFFECT = "effect"            # an effect action moved them

    @classmethod
    def parse(cls, value: object, default: "ArrivalKind") -> str:
        """The arrival-kind *value* for an API input, falling back to ``default``.

        Returns the plain string — the wire currency. A str-Enum member would
        stringify as ``"ArrivalKind.MOVE"``, which is never what belongs in an
        event context.
        """
        try:
            return cls(str(value or "").strip().lower()).value
        except ValueError:
            return default.value


class RollKind(str, Enum):
    """What kind of roll a dice pool represents.

    - ``test``: one side rolls against a difficulty/opposition.
    - ``contest``: two sides roll head-to-head; a winner is declared.
    - ``roll_table``: reserved for random-table outcomes (resolved via
      ``resolve_table``, not the dice resolver, today).
    """
    TEST = "test"
    CONTEST = "contest"
    ROLL_TABLE = "roll_table"

class ContestWinner(str, Enum):
    """Winner of a two-sided contest.

    ``PLAYER`` is the challenger/initiator (the side that set the
    difficulty); ``OPPONENT`` is the defendant. Ties favor the initiator,
    so a tied contest resolves to ``PLAYER``.
    """
    PLAYER = "player"
    OPPONENT = "opponent"

class EffectTiming(str, Enum):
    """When an effect fires relative to its trigger.

    Time boundaries (``end_of_beat``…) are persisted timers advanced on the
    matching global/state-change event. Roll events (``on_roll``/``on_set``/
    ``on_result``) are ephemeral, per-roll deferrals — they arm the effect and
    fire it at the next matching roll event (see ``services/roll_deferral``).
    """
    IMMEDIATE = "immediate"
    END_OF_BEAT = "end_of_beat"
    END_OF_SCENE = "end_of_scene"
    END_OF_SESSION = "end_of_session"
    AFTER_BEATS = "after_beats"
    ON_CONDITION = "on_condition"
    ON_ROLL = "on_roll"
    ON_SET = "on_set"
    ON_RESULT = "on_result"
    # Outcome-gated timings — fire at the next contest/roll resolution, gated by
    # the outcome. Also expressible via an effect condition, but kept as timing
    # names to mirror the SFX trigger vocabulary.
    ON_CONTEST_WIN = "on_contest_win"
    ON_CONTEST_LOSS = "on_contest_loss"
    ON_SUCCESS = "on_success"
    ON_FAILURE = "on_failure"

class AttunementScope(str, Enum):
    """Who an attunement affects."""
    SELF = "self"        # only the entity carrying the attunement
    DOMAIN = "domain"    # occupants in the entity's location subtree

class AttunementOp(str, Enum):
    """What a projection grant does to its carrier's active set."""
    ADD = "add"        # attune — bring a body (or a universe's bodies) live
    REMOVE = "remove"  # suppress — cut a specific body out of the set

class TimerCombine(str, Enum):
    """How multiple timers combine to determine expiry."""
    FIRST_TO_FIRE = "first_to_fire"      # any timer reaches 0
    ALL_TRANSPIRED = "all_transpired"    # every timer reaches 0

class ConditionType(str, Enum):
    """Kinds of automatically-evaluable gate/limit conditions."""
    ALWAYS = "always"
    AT_LOCATION = "at_location"          # target = location entity id
    HAS_TRAIT = "has_trait"              # target = trait id
    HAS_EFFECTIVE_TRAIT = "has_effective_trait"  # target = trait id; possession AND enabled
    HAS_TRAIT_IN_TRAITSET = "has_trait_in_traitset"  # target = traitset id
    HAS_RELATIONSHIP = "has_relationship"  # target = related entity id
    TRAIT_RATING = "trait_rating"        # target = trait id; value = rating threshold (e.g. d8)
    HAS_RAZMERIT = "has_razmerit"        # value = integer; operator = numeric comparator
    ENTITY_TYPE = "entity_type"          # target = entity type (character/gmc/asset); subject = the entity
    USER_ROLE = "user_role"              # target = "player" | "architect"; the acting human's role (context or controlling player)
    NARRATIVE = "narrative"              # human-readable only, never auto-blocks
    UNPLACED = "unplaced"                # entity has no current location yet
    IN_UNIVERSE = "in_universe"          # target = universe key; entity is currently there
    PHASE = "phase"                      # target = dice-pool phase (e.g. "adding"); reads trigger context
    CONTEST_OUTCOME = "contest_outcome"  # target = "player" | "opponent" | "give_in"; reads context
    HITCH = "hitch"                      # marker: the hitch-buying menu is active (reads context["hitch"])
    ROLL_TIER = "roll_tier"              # operator + value against OutcomeTier (e.g. >= success); reads roll_result.tier
    TEST_OUTCOME = "test_outcome"        # target = "success" | "fail" (binary); success = tier != fail
    SOURCE_RATING = "source_rating"      # the source trait-setting's rating (dice) vs a die threshold
    HIGH_STAKES = "high_stakes"          # target = "high" | "low"; the contest in play is high-stakes
    TARGET_PATH = "target_path"          # a targeting path (spec) resolves non-empty; source-aware predicate
    ARRIVAL_KIND = "arrival_kind"        # target = how they arrived (transversal/hierarchy/move/effect); reads context
    CONTEST_CHALLENGER = "contest_challenger"  # this entity is the side that declared the contest
    CONTEST_DEFENDANT = "contest_defendant"    # this entity is the side that was challenged
    SESSION = "session"                  # target = "active" | "inactive"; is a session running now

class RollTableScheme(str, Enum):
    """How a roll table selects an entry."""
    RANGE = "range"    # entry declares min_value / max_value
    WEIGHT = "weight"  # entry declares weight; cumulative proportional pick
    TIER = "tier"      # entry keyed to an OutcomeTier
    INDEX = "index"    # ordered list; roll 1 → first entry

class RollSource(str, Enum):
    """Where a roll table's number comes from.

    FIXED_DIE — roll the table's own ``die`` (the original behaviour).
    TRAIT_DICE — the player picks ``trait_dice_count`` traits they have and
    rolls those instead; the derived number selects the entry.
    """
    FIXED_DIE = "fixed_die"
    TRAIT_DICE = "trait_dice"

class ImageType(str, Enum):
    UPLOADED = "uploaded"
    IMAGEN = "imagen"
    ANIMATED = "animated"
    CUTOUT = "cutout"  # background-removed transparent variant of a static image

class MessageKind(str, Enum):
    LETTER = "letter"
    JOURNAL = "journal"
    REPORT = "report"
    GM_NOTE = "gm_note"

class HistoricalRecordType(str, Enum):
    """Kinds of append-only historical events."""
    ROLL_TABLE = "roll_table"
    CONTEST = "contest"
    TRANSVERSAL = "transversal"


class SheetTab(str, Enum):
    """Which character-sheet tab a trait set renders its traits on.

    ``traits`` is the default: mechanically usable traits, grouped by set.
    ``profile`` is for descriptive traits that carry no mechanical benefit
    (name, gender, appearance). It is a deliberate authoring decision rather
    than an inference from the rating type, which could not tell a container
    trait (sub-traits, no own rating) from a genuinely descriptive one.
    """
    TRAITS = "traits"
    PROFILE = "profile"
