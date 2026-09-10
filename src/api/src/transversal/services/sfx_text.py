"""Derived natural-language rules text for SFX ("card text").

See [[SFX Natural Language Plan]]. This module turns an SFX's authored structure
(trigger + conditions + effects, each optionally carrying a [[target_spec]]
path) into one readable line in the spirit of Magic: The Gathering card text —
technically faithful, but phrased as prose rather than as a step transcript.

Design rules (from the plan):

* **Catalog-driven.** Trigger, collection, edge, field, aggregation and effect
  vocabulary come from [[target_catalog]] / [[menu_contexts]] /
  [[effects_registry]] card phrases, not from a private string table here.
* **Naming is the mechanism.** When a step declares an ``output`` name, the
  author's name is what renders (``d4_traits`` → "d4 traits") — later steps do
  not retrace the pipeline. Named paths become keywords.
* **Terminal-noun composition.** A path renders as *one* noun phrase ("each
  static trait instance you rolled"), never as "take the dice, then their
  traits, then keep rating d4".
* **Pure.** No DB access: ids resolve through an injected ``resolve`` callable,
  so the renderer is unit-testable. An unresolvable id degrades to the raw id —
  ugly, but never wrong.

The renderer is best-effort on *invalid* specs (the targeting wizard already
blocks those): it renders the last coherent phrase rather than raising.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Callable, Optional

from transversal.domain import Condition, ConditionType, Effect, EffectTiming, SFX
from transversal.services import effects_registry as reg
from transversal.services import menu_contexts as mc
from transversal.services import target_catalog as tc
from transversal.services.target_spec import (
    AggregateStep,
    ChooseStep,
    EvaluateStep,
    FilterStep,
    LiteralStep,
    NavigateStep,
    RandomStep,
    SelectStep,
    TargetSpec,
    ValueType,
    trace,
)

#: Maps a raw id to a display name, or ``None`` when it is not a known id.
NameResolver = Callable[[str], Optional[str]]


# ── Vocabulary helpers ────────────────────────────────────────

_OP_WORDS = {
    "==": "equal to",
    "!=": "other than",
    ">": "above",
    ">=": "at least",
    "<": "below",
    "<=": "at most",
    "in": "in",
    "contains": "including",
}

_ELEMENT_NOUNS = {
    "die": "die",
    "traitsetting": "trait instance",
    "traitsetsetting": "trait set instance",
    "trait": "trait",
    "traitset": "trait set",
    "entity": "entity",
    "projection": "projection",
    "location": "location",
    "universe": "universe",
    "pool": "dice pool",
}

_ELEMENT_PLURALS = {
    "die": "dice",
    "traitsetting": "trait instances",
    "traitsetsetting": "trait set instances",
    "trait": "traits",
    "traitset": "trait sets",
    "entity": "entities",
    "projection": "projections",
    "location": "locations",
    "universe": "universes",
    "pool": "dice pools",
}

# Deferred roll timings read as a leading clause ("whenever a roll is resolved, …").
_LEADING_TIMINGS = {
    EffectTiming.ON_ROLL: "whenever a roll happens",
    EffectTiming.ON_RESULT: "whenever a roll is resolved",
    EffectTiming.ON_SET: "when a die is set",
    EffectTiming.ON_CONTEST_WIN: "when you win the contest",
    EffectTiming.ON_CONTEST_LOSS: "when you lose the contest",
    EffectTiming.ON_SUCCESS: "when the roll succeeds",
    EffectTiming.ON_FAILURE: "when the roll fails",
}

# Boundary timings read as a trailing clause ("…, at the end of the beat").
_TRAILING_TIMINGS = {
    EffectTiming.END_OF_BEAT: "at the end of the beat",
    EffectTiming.END_OF_SCENE: "at the end of the scene",
    EffectTiming.END_OF_SESSION: "at the end of the session",
}

# Actions whose magnitude is worth stating when it is the default of one step.
_STEP_ACTIONS = {"step_up", "step_down", "gain_or_step_up"}

# When an effect names no target (and its card template needs one), say what the
# action defaults to rather than trailing off. Keyed by effect action.
_TARGET_FALLBACKS = {
    "targeting_ban": "the acting entity",
}

_KNOWN_PLACEHOLDERS = {
    "self": "the acting entity",
    "source_trait": "this SFX's trait",
    "source_traitset": "this SFX's trait set",
    "effect_die": "the effect die",
    "total": "the roll total",
    "entity_created": "the new entity",
    "buying_entity": "the buying entity",
    "triggered_die_effect_die": "the effect die",
    "contest_entity_opponent": "the opposing entity",
    "from_location": "the previous location",
    "to_location": "the new location",
}


def pluralize(word: str) -> str:
    """Naive English plural (catalog entries override where it matters)."""
    return tc.pluralize(word)


_IRREGULAR_SINGULARS = {"dice": "die"}


def singularize(phrase: str) -> str:
    """Naive English singular for a trailing plural head noun."""
    out = []
    for word in (phrase or "").split():
        low = word.lower()
        if low in _IRREGULAR_SINGULARS:
            word = _IRREGULAR_SINGULARS[low]
        elif low.endswith("ies") and len(word) > 3:
            word = word[:-3] + ("Y" if word.isupper() else "y")
        elif low.endswith(("ses", "ches", "shes")) and len(word) > 3:
            word = word[:-2]
        elif low.endswith("s") and not low.endswith(("ss", "us")):
            word = word[:-1]
        out.append(word)
    return " ".join(out)


def humanize(name: str) -> str:
    """An author's variable name as a card phrase (``d4_traits`` → "d4 traits")."""
    text = (name or "").replace("_", " ").replace("-", " ").strip()
    return re.sub(r"\s+", " ", text)


def element_noun(element: str) -> str:
    """The singular card noun for a catalog element type."""
    if element in _ELEMENT_NOUNS:
        return _ELEMENT_NOUNS[element]
    known = tc.element(element)
    return known.label.lower() if known else element


def element_plural(element: str) -> str:
    """The plural card noun for a catalog element type."""
    if element in _ELEMENT_PLURALS:
        return _ELEMENT_PLURALS[element]
    return pluralize(element_noun(element))


def _article(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" else "a"


# ── Phrases ───────────────────────────────────────────────────

@dataclass
class Phrase:
    """A rendered-so-far noun phrase for the collection a path resolves to.

    Exactly one of ``noun`` / ``scalar`` / ``predicate`` / ``pronoun`` carries
    the meaning; the renderer picks the complete form.
    """
    element: str = ""
    cardinality: str = "one"
    adjectives: list[str] = field(default_factory=list)
    noun: str = ""            # singular head noun
    plural: str = ""          # plural head noun ("" → pluralize(noun))
    origin: str = ""          # trailing qualifier: "in your roll" / "you rolled"
    prefix: str = ""          # leading quantifier: "one of the …"
    scalar: str = ""          # a complete scalar phrase (aggregates)
    predicate: str = ""       # a complete boolean clause (evaluate)
    possessive: bool = False  # renders as "your {noun}"
    pronoun: bool = False     # the bare pronoun "you"
    modal: bool = False       # a choose/random step made this interactive


def render_phrase(p: Phrase, determiner: str = "") -> str:
    """Render a phrase, applying ``determiner`` unless the phrase supplies one."""
    if p.predicate:
        return p.predicate
    if p.scalar:
        return p.scalar
    if p.possessive:
        determiner = "your"
    if p.pronoun and not p.noun:
        return "you" if not determiner else f"{determiner} you"
    if p.prefix:
        # "one of the challenge negative trait instances of each entity"
        body = " ".join([*p.adjectives, p.plural or pluralize(p.noun)]).strip()
        out = f"{p.prefix} {body}".strip()
        return f"{out} {p.origin}".strip() if p.origin else out
    singular = p.cardinality == "one" or determiner in ("each", "every", "any")
    head = p.noun if singular else (p.plural or pluralize(p.noun))
    body = " ".join([*p.adjectives, head]).strip()
    out = f"{determiner} {body}".strip() if determiner else body
    if p.origin:
        out = f"{out} {p.origin}".strip()
    return out


def _determiner(p: Phrase) -> str:
    """The default determiner for a phrase in an effect/target position."""
    if p.scalar or p.predicate or p.pronoun or p.possessive or p.prefix or not p.noun:
        return ""
    return "the" if p.cardinality == "one" else "each"


def _as_one(p: Phrase) -> Phrase:
    return replace(p, cardinality="one")


def _as_many(p: Phrase) -> Phrase:
    return replace(p, cardinality="many")


def _with_article(p: Phrase) -> str:
    """A singular rendering with an article ("a d4 trait instance")."""
    body = render_phrase(replace(p, cardinality="one", possessive=False), "")
    if not body:
        return body
    return f"your {body}" if p.possessive else f"{_article(body)} {body}"


def _at_least_one(p: Phrase) -> str:
    """The existence clause for a collection ("there is at least one d4 trait")."""
    if p.possessive:
        return f"there is at least one of {render_phrase(_as_many(p), '')}"
    if p.cardinality == "many":
        return f"there is at least one {render_phrase(_as_one(p), '')}".strip()
    return f"there is {_with_article(p)}"


# ── Value rendering ───────────────────────────────────────────

def _placeholder(token: str) -> str:
    """Expand a ``{token}`` authoring placeholder into card text."""
    inner = token.strip("{}")
    if inner in _KNOWN_PLACEHOLDERS:
        return _KNOWN_PLACEHOLDERS[inner]
    if ":" in inner:
        kind, _, arg = inner.partition(":")
        if kind == "random":
            return f"a random {arg.replace('_', ' ')}"
        if kind == "return":
            return f"the {arg.replace('_', ' ')}"
        if kind == "choose":
            return f"a {arg.replace('_', ' ')} you choose"
    if inner.startswith("choose_"):
        return f"a {inner[len('choose_'):].replace('_', ' ')} you choose"
    return f"the {inner.replace('_', ' ')}"


def display_value(value, resolve: NameResolver | None = None) -> str:
    """A card-facing rendering of an authored value (id → name, token → phrase)."""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if value is None:
        return ""
    text = str(value)
    if text.startswith("{") and text.endswith("}"):
        return _placeholder(text)
    if resolve:
        name = resolve(text)
        if name:
            return name
    return text


def id_phrase(value: str, element: str = "", resolve: NameResolver | None = None) -> str:
    """A self-contained noun phrase for a concrete id or literal word."""
    text = (value or "").strip()
    if not text:
        return ""
    if text.startswith("{"):
        return _placeholder(text)
    name = resolve(text) if resolve else None
    if name:
        if element in ("trait", "traitset"):
            return f"the {name} {element_noun(element)}"
        return name
    if "-" in text or ":" in text:
        return text  # an unresolvable id — shown raw rather than invented
    if element in ("trait", "traitset"):
        return f"the {element_noun(element)} {text}"
    return f"the {text}"


# ── Step composition ──────────────────────────────────────────

def _select_phrase(step: SelectStep, source_element: str | None = None) -> Phrase:
    if step.collection == "variable":
        # The author named it — their name *is* the card phrase.
        named = humanize(step.variable) or "value"
        return Phrase(noun=singularize(named), plural=named)
    if step.collection == "source":
        if source_element:
            return Phrase(
                element=source_element,
                noun=f"{element_noun(source_element)} this SFX sits on",
                plural=f"{element_plural(source_element)} this SFX sits on",
            )
        return Phrase(noun="source", plural="sources")
    col = tc.collection(step.collection)
    if col is None:
        return Phrase(noun=step.collection.replace("_", " "))
    return Phrase(
        element=col.element,
        cardinality="one" if col.singular else "many",
        noun=col.noun or element_noun(col.element),
        plural=col.plural or ("" if col.noun else element_plural(col.element)),
        origin=col.origin,
        possessive=col.possessive,
        pronoun=col.pronoun,
    )


def _filter_phrase(p: Phrase, step: FilterStep, resolve: NameResolver | None = None) -> Phrase:
    field_def = tc.field(p.element, step.field) if p.element else None
    resolved = None
    if resolve and isinstance(step.value, str) and not step.value.startswith("{"):
        resolved = resolve(step.value)

    # Enum- or die-valued equality reads as an adjective: "static", "d4".
    if (step.operator == "==" and field_def is not None and not resolved
            and (field_def.type == "die"
                 or (field_def.type == "string" and field_def.options))):
        p.adjectives.append(display_value(step.value, resolve))
        return p

    field_text = tc.field_label(field_def) if field_def else step.field.replace("_", " ")
    value_text = resolved or display_value(step.value, resolve)
    clause = f"with {field_text} {_OP_WORDS.get(step.operator, step.operator)} {value_text}".strip()
    p.origin = f"{p.origin} {clause}".strip()
    return p


def _navigate_phrase(p: Phrase, step: NavigateStep) -> Phrase:
    edge = tc.edge(p.element, step.edge) if p.element else None
    if edge is None:
        # An unnamed or unknown hop (an unfinished step): keep the source phrase
        # rather than inventing a noun for it.
        return p
    noun, plural = tc.edge_noun(edge)
    element = edge.target[0] if len(edge.target) == 1 else p.element
    cardinality = "many" if (p.cardinality == "many" or edge.cardinality == "many") else "one"
    origin = edge.card_origin

    if p.pronoun:
        # "you" → "your location" (one possessive hop; a further hop goes back
        # to "the X of your location" so long chains stay unambiguous).
        return Phrase(element=element, cardinality=cardinality, noun=noun,
                      plural=plural, possessive=True, modal=p.modal)

    if origin:
        # The edge absorbs its source ("… you rolled"): carry the source's
        # adjectives, but drop any that merely echo the new head noun — a "trait
        # die" navigated to its trait instance is already a trait instance.
        head_words = set(noun.lower().split())
        keep = [a for a in p.adjectives if a.lower().split()[-1] not in head_words]
        return Phrase(element=element, cardinality=cardinality, adjectives=keep,
                      noun=noun, plural=plural, origin=origin, modal=p.modal)

    return Phrase(element=element, cardinality=cardinality, noun=noun, plural=plural,
                  origin=f"of {render_phrase(p, _determiner(p))}".strip(), modal=p.modal)


def _aggregate_phrase(p: Phrase, step: AggregateStep) -> Phrase:
    agg = tc.aggregation(step.fn)
    field_text = ""
    if step.field:
        field_def = tc.field(p.element, step.field) if p.element else None
        field_text = tc.field_label(field_def) if field_def else step.field.replace("_", " ")
    if agg is None:
        return Phrase(scalar=f"{step.fn} of {render_phrase(p, '')}".strip())
    return Phrase(element=agg.output, cardinality="one",
                  scalar=tc.aggregation_card(agg, render_phrase(p, ""), field_text))


def _choose_phrase(p: Phrase, step: ChooseStep) -> Phrase:
    """A `choose` step is a *modal*, not a fact: it reads as a quantifier."""
    if step.count == 1:
        return replace(p, modal=True, prefix="one of the")
    return replace(p, modal=True, prefix="a chosen set of the")


def _random_phrase(p: Phrase, step: RandomStep) -> Phrase:
    return replace(p, cardinality="one" if step.count == 1 else p.cardinality,
                   adjectives=[*p.adjectives, "random"])


def _literal_phrase(step: LiteralStep, resolve: NameResolver | None = None) -> Phrase:
    # A literal is a complete reference, like a scalar: it carries its own article.
    return Phrase(element=step.element, cardinality="one",
                  scalar=id_phrase(step.value, step.element, resolve))


def _evaluate_phrase(p: Phrase, step: EvaluateStep, named: Phrase | None = None) -> Phrase:
    """Render the terminal boolean test as a standalone clause."""
    subject = named or p
    value = display_value(step.value)

    if step.operator == "exists":
        return Phrase(predicate=_at_least_one(subject))

    field_name = (step.field or "").strip()
    if field_name and field_name != "count":
        field_def = tc.field(subject.element, field_name) if subject.element else None
        field_text = tc.field_label(field_def) if field_def else field_name.replace("_", " ")
        one = _as_one(subject)
        if subject.cardinality != "many":
            if field_name == "rating":
                return Phrase(predicate=f"{_with_article(one)} is rated {value}"
                              if step.operator == "==" else
                              f"{_with_article(one)} is rated "
                              f"{_OP_WORDS.get(step.operator, step.operator)} {value}")
            return Phrase(predicate=f"{_with_article(one)} has {field_text} "
                                    f"{_OP_WORDS.get(step.operator, step.operator)} {value}")
        return Phrase(predicate=f"every {render_phrase(one, '')} has {field_text} "
                                f"{_OP_WORDS.get(step.operator, step.operator)} {value}")

    op = step.operator
    try:
        count: int | None = int(step.value)
    except (TypeError, ValueError):
        count = None

    if count is None:
        return Phrase(predicate=f"the number of {render_phrase(_as_many(subject), '')} is "
                                f"{_OP_WORDS.get(op, op)} {value}".strip())
    if count == 1 and op in (">=", "=="):
        return Phrase(predicate=_at_least_one(subject))
    if count == 0 and op == ">":
        return Phrase(predicate=_at_least_one(subject))
    if op == "==" and count == 0:
        if subject.possessive:
            bare = render_phrase(replace(subject, cardinality="one", possessive=False), "")
            return Phrase(predicate=f"there is no {bare} of yours".strip())
        return Phrase(predicate=f"there is no {render_phrase(_as_one(subject), '')}".strip())
    plural = render_phrase(_as_many(subject), "")
    if subject.possessive:
        plural = f"of {plural}"
    phrases = {
        ">": f"there are more than {count} {plural}",
        ">=": f"there are at least {count} {plural}",
        "==": f"there are {count} {plural}",
        "<": f"there are fewer than {count} {plural}",
        "<=": f"there are at most {count} {plural}",
        "!=": f"there are not {count} {plural}",
    }
    return Phrase(predicate=phrases.get(op, f"there are {count} {plural}").strip())


# ── Path rendering ────────────────────────────────────────────

def _named_phrase(output: str, value_type: ValueType | None) -> Phrase:
    """The author's own name for a step output, used verbatim as the phrase."""
    named = humanize(output)
    return Phrase(
        element=value_type.element if value_type else "",
        cardinality=value_type.cardinality if value_type else "one",
        noun=singularize(named),
        plural=named,
    )


def path_phrase(spec: TargetSpec | None, *, source_element: str | None = None,
                variables=None, resolve: NameResolver | None = None) -> Phrase:
    """Render a targeting path as a single noun phrase.

    A path is a pipeline; English wants a head noun with qualifiers. Each step
    rewrites the phrase rather than appending a clause, so ``select rolled_dice
    → navigate traitsetting → filter rating d4`` becomes "each d4 trait instance
    you rolled" instead of a step-by-step transcript.

    When the terminal step declares an ``output``, that name is the phrase — the
    naming mechanism from [[SFX Natural Language Plan]].
    """
    if spec is None or not spec.steps:
        return Phrase()
    types, _errors = trace(spec, source_element, variables)
    phrase = Phrase()
    named: Phrase | None = None
    terminal_named: Phrase | None = None

    for step, step_type in zip(spec.steps, types):
        if isinstance(step, SelectStep):
            phrase = _select_phrase(step, source_element)
        elif isinstance(step, FilterStep):
            phrase = _filter_phrase(phrase, step, resolve)
        elif isinstance(step, NavigateStep):
            phrase = _navigate_phrase(phrase, step)
        elif isinstance(step, AggregateStep):
            phrase = _aggregate_phrase(phrase, step)
        elif isinstance(step, LiteralStep):
            phrase = _literal_phrase(step, resolve)
        elif isinstance(step, RandomStep):
            phrase = _random_phrase(phrase, step)
        elif isinstance(step, ChooseStep):
            phrase = _choose_phrase(phrase, step)
        elif isinstance(step, EvaluateStep):
            phrase = _evaluate_phrase(phrase, step, named)

        if not isinstance(step, EvaluateStep) and step_type is not None:
            phrase.element = step_type.element
            phrase.cardinality = step_type.cardinality

        output = getattr(step, "output", None)
        if output and not isinstance(step, EvaluateStep):
            named = _named_phrase(output, step_type)
            terminal_named = named

    if terminal_named is not None and not phrase.predicate:
        return terminal_named
    return phrase


# ── Conditions ────────────────────────────────────────────────

def condition_text(condition: Condition, *, resolve: NameResolver | None = None,
                   source_element: str | None = None, variables=None) -> str:
    """Render one condition as a clause ("you have the Fire trait")."""
    ctype = condition.type
    target = display_value(condition.target, resolve)
    value = display_value(condition.value, resolve)
    op = _OP_WORDS.get(condition.operator, condition.operator)

    if ctype == ConditionType.ALWAYS:
        return ""
    if ctype == ConditionType.NARRATIVE:
        return (condition.narrative or "").strip()
    if ctype == ConditionType.TARGET_PATH:
        phrase = path_phrase(condition.spec, source_element=source_element,
                             variables=variables, resolve=resolve)
        return phrase.predicate or _at_least_one(phrase)
    if ctype == ConditionType.AT_LOCATION:
        return f"you are at {target}"
    if ctype == ConditionType.HAS_TRAIT:
        return f"you have {target}"
    if ctype == ConditionType.HAS_EFFECTIVE_TRAIT:
        return f"you have {target} enabled"
    if ctype == ConditionType.HAS_TRAIT_IN_TRAITSET:
        return f"you have a trait in {target}"
    if ctype == ConditionType.HAS_RELATIONSHIP:
        return f"you are related to {target}"
    if ctype == ConditionType.TRAIT_RATING:
        return f"{target} is rated {op} {value}"
    if ctype == ConditionType.HAS_RAZMERIT:
        return f"you have {op} {value} razmerit"
    if ctype == ConditionType.ENTITY_TYPE:
        return f"you are {_article(target)} {target}"
    if ctype == ConditionType.USER_ROLE:
        return f"{_article(target)} {target} is acting"
    if ctype == ConditionType.UNPLACED:
        return "you are not at a location yet"
    if ctype == ConditionType.IN_UNIVERSE:
        return f"you are in {target}"
    if ctype == ConditionType.PHASE:
        return f"the dice pool is in its {target} phase"
    if ctype == ConditionType.CONTEST_OUTCOME:
        return f'the contest outcome is "{target}"'
    if ctype == ConditionType.HITCH:
        return "a hitch is being resolved"
    if ctype == ConditionType.ROLL_TIER:
        return f"the roll is {op} {value}"
    if ctype == ConditionType.TEST_OUTCOME:
        return "the test succeeds" if target == "success" else "the test fails"
    if ctype == ConditionType.SOURCE_RATING:
        return f"this SFX's source is rated {op} {value}"
    return (condition.narrative or "").strip()


# ── Effects ───────────────────────────────────────────────────

def _effect_result(effect: Effect) -> str:
    """The magnitude/rating an effect states, falling back to its field default."""
    if effect.result not in (None, ""):
        return str(effect.result)
    meta = next((m for m in reg.EFFECT_ACTION_REGISTRY
                 if m.effect_type == effect.type and m.effect_action == effect.action), None)
    if meta:
        for fdef in [*meta.fields, *meta.context_fields]:
            if fdef.name == "result" and fdef.default:
                return str(fdef.default)
    return ""


def _target_element(effect: Effect) -> str:
    """The catalog element a bare (non-path) target id belongs to."""
    if effect.type == "modify_trait":
        return "trait"
    if effect.type == "modify_pool":
        return "pool"
    if effect.type in ("entity", "relationship", "attune", "location"):
        return "entity"
    if effect.type == "roll_table":
        return "roll_table"
    if effect.type == "life_path":
        return "life_path"
    return ""


def effect_target(effect: Effect, *, resolve: NameResolver | None = None,
                  source_element: str | None = None, variables=None) -> str:
    """Render an effect's target: a path phrase, a placeholder, or a named id."""
    if effect.target_spec is not None and effect.target_spec.steps:
        phrase = path_phrase(effect.target_spec, source_element=source_element,
                             variables=variables, resolve=resolve)
        return render_phrase(phrase, _determiner(phrase))
    raw = (effect.target or "").strip()
    if raw in ("", "self"):
        if effect.entity and effect.entity not in ("self",):
            return id_phrase(effect.entity, "entity", resolve)
        return ""
    return id_phrase(raw, _target_element(effect), resolve)


def _target_placeholder(effect: Effect) -> str:
    """What an effect with no authored target acts on (for card templates that
    name one) — its declared target field, else its element noun."""
    if effect.action in _TARGET_FALLBACKS:
        return _TARGET_FALLBACKS[effect.action]
    meta = next((m for m in reg.EFFECT_ACTION_REGISTRY
                 if m.effect_type == effect.type and m.effect_action == effect.action), None)
    if meta:
        for fdef in [*meta.fields, *meta.context_fields]:
            if fdef.name == "target":
                label = re.sub(r"^(target|destination)\s+", "", fdef.label.strip(), flags=re.I)
                return f"the {label.lower()}"
    return f"the {element_noun(_target_element(effect))}" if _target_element(effect) else ""


def effect_text(effect: Effect, *, resolve: NameResolver | None = None,
                source_element: str | None = None, variables=None) -> str:
    """Render one effect as a clause ("step down each static trait instance you rolled")."""
    target = effect_target(effect, resolve=resolve, source_element=source_element,
                           variables=variables)
    result = _effect_result(effect)
    template = reg.effect_card(effect.type, effect.action)
    if not target and "{target}" in template:
        target = _target_placeholder(effect)
    text = template.format(target=target, result=display_value(result, resolve))
    if effect.negative and "complication" not in text:
        text = f"{text} as a complication"

    if effect.type == "modify_trait" and effect.action in _STEP_ACTIONS:
        steps = display_value(str((effect.context or {}).get("steps") or "1"))
        if steps == "1":
            text = f"{text} by one step"
        elif steps.isdigit():
            text = f"{text} by {steps} steps"
        else:
            text = f"{text} by a number of steps equal to {steps}"
    if "{result}" not in template and result:
        text = f"{text} ({display_value(result, resolve)})"

    text = _tidy(text)
    lead = _LEADING_TIMINGS.get(effect.timing)
    if lead:
        text = f"{lead}, {text}"
    elif effect.timing in _TRAILING_TIMINGS:
        text = f"{text}, {_TRAILING_TIMINGS[effect.timing]}"
    if effect.duration is not None and effect.duration.timers:
        text = f"{text} ({_duration_text(effect.duration)})"
    return text


def _duration_text(duration) -> str:
    """Effect duration = the *undo* timer (distinct from the SFX listening window)."""
    parts = []
    for timer in duration.timers:
        unit = (timer.event or "scene").replace("_", " ")
        parts.append(f"{timer.remaining} {unit}" if timer.remaining != 1 else unit)
    joined = " and ".join(parts) if parts else "the next scene"
    return f"reverts after {joined}"


def _tidy(text: str) -> str:
    """Collapse the seams left by empty placeholders."""
    out = re.sub(r"\s{2,}", " ", text)
    out = re.sub(r"\s+([,.;:])", r"\1", out)
    out = re.sub(r"\s+\b(at|to|by|as|on|with|from|of)\s*$", "", out)
    return out.strip().rstrip(",").strip()


# ── SFX ───────────────────────────────────────────────────────

def sfx_text(sfx: SFX, *, resolve: NameResolver | None = None,
             include_narrative: bool = True) -> str:
    """Render an SFX as one readable line of rules text.

    Shape: ``[trigger][, if conditions]: [effects]``. Narrative conditions (the
    legacy ``limit`` text) are authors' flavour, never checked by the engine, so
    they trail in parentheses rather than masquerading as rules text.
    """
    source_element = tc.source_element(sfx.source_kind) if sfx.source_kind else None
    rules: list[str] = []
    narrative: list[str] = []

    for cond in sfx.conditions:
        clause = condition_text(cond, resolve=resolve, source_element=source_element)
        if not clause:
            continue
        (narrative if cond.type == ConditionType.NARRATIVE else rules).append(clause)

    effects = [t for t in (effect_text(e, resolve=resolve, source_element=source_element)
                           for e in sfx.effects) if t]

    head = mc.trigger_card(sfx.trigger)
    if rules:
        head = f"{head}, if {' and '.join(rules)}"
    text = f"{head}: {'; '.join(effects)}." if effects else f"{head}."
    if narrative and include_narrative:
        text = f"{text} ({'; '.join(narrative)})"
    return text
