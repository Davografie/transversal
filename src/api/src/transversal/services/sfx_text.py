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
from types import SimpleNamespace
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
    SelectStep,
    TargetSpec,
    ValueType,
    spec_variables,
    trace,
)

#: Maps a raw id to a display name, or ``None`` when it is not a known id.
NameResolver = Callable[[str], Optional[str]]


#: Words that already determine a noun phrase, so the renderer must not add one
#: (an author's step name like ``their_counterpart`` reads as-is).
_LEADING_DETERMINERS = (
    "the ", "a ", "an ", "your ", "their ", "his ", "her ", "its ", "our ", "my ",
    "each ", "every ", "any ", "one of ", "that ", "this ", "some ",
)


def _has_own_determiner(body: str) -> bool:
    """Whether a rendered body already opens with its own determiner."""
    return body.lower().startswith(_LEADING_DETERMINERS)


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
    "not contains": "not including",
}

# A `contains` filter on a list-valued label field reads as membership of the
# named thing, not as the field's name: "your trait instances tagged violent"
# rather than "with tag including violent".
_CONTAINS_WORDS = {
    "tags": "tagged",
}

# How an arrival reads on the card (``ConditionType.ARRIVAL_KIND``), keyed by
# :class:`ArrivalKind` value. An unknown value falls back to naming it.
_ARRIVAL_PHRASES = {
    "transversal": "you arrived through a portal",
    "hierarchy": "you arrived through the location hierarchy",
    "move": "you were placed here",
    "effect": "an effect moved you here",
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

# The change-die verbs that take a count: how many steps along the ladder, or how
# many extra dice. One `count` key, read here the way the applier reads it.
_CHANGE_DIE_COUNT_ACTIONS = {"step_up_die", "step_down_die", "double_die", "split_die"}
_CHANGE_DIE_STEP_ACTIONS = {"step_up_die", "step_down_die"}

# When an effect names no target (and its card template needs one), say what the
# action defaults to rather than trailing off. Keyed by effect action.
_TARGET_FALLBACKS = {
    "targeting_ban": "the acting entity",
}

_KNOWN_PLACEHOLDERS = {
    "self": "the acting entity",
    # The *source* variables read as the thing the rule sits on ("this trait"),
    # not as their token name: "step up this trait", not "step up the trait
    # setting". Same voice the source-aware conditions already use.
    "trait_setting": "this trait",
    "traitset_setting": "this trait set",
    "projection": "this projection",
    "location": "this location",
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


_DETERMINERS = ("this", "the", "that", "these", "those", "a", "an")


def named_variable_phrase(name: str) -> tuple[str, str]:
    """A bound-variable name → ``(determiner, noun)``.

    ``_KNOWN_PLACEHOLDERS`` stores whole phrases ("this trait", "the opposing
    entity") because a ``{token}`` value needs the determiner in the sentence. A
    *select* step needs the two apart: the noun still has to pluralise and be
    counted. An unknown name falls back to its own words.
    """
    phrase = _KNOWN_PLACEHOLDERS.get(name, "")
    if not phrase:
        return ("", humanize(name) or "value")
    head, _, rest = phrase.partition(" ")
    if head in _DETERMINERS and rest:
        return (head, rest)
    return ("", phrase)


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
    absorb: str = ""          # the phrase a hop from this seed reads as: "you rolled"
    prefix: str = ""          # leading quantifier: "one of the …"
    scalar: str = ""          # a complete scalar phrase (aggregates)
    predicate: str = ""       # a complete boolean clause (evaluate)
    #: A complete clause for a hop that lands on a **state** rather than a thing
    #: you possess ("you are in a contest"). Only the condition renderer reads it
    #: (`_at_least_one`), so a *target* position still gets the noun phrase — the
    #: two positions want different sentences out of the same hop.
    state: str = ""
    possessive: bool = False  # renders as "your {noun}"
    pronoun: bool = False     # the bare pronoun "you"
    modal: bool = False       # a choose/random step made this interactive
    fixed_determiner: str = ""  # a determiner the phrase supplies ("that die")


def render_phrase(p: Phrase, determiner: str = "") -> str:
    """Render a phrase, applying ``determiner`` unless the phrase supplies one."""
    if p.predicate:
        return p.predicate
    if p.scalar:
        return p.scalar
    if p.possessive:
        determiner = "your"
    elif p.fixed_determiner:
        determiner = p.fixed_determiner
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
    if determiner and _has_own_determiner(body):
        determiner = ""
    out = f"{determiner} {body}".strip() if determiner else body
    if p.origin:
        out = f"{out} {p.origin}".strip()
    return out


def _determiner(p: Phrase) -> str:
    """The default determiner for a phrase in an effect/target position."""
    if p.fixed_determiner:
        return p.fixed_determiner
    if p.scalar or p.predicate or p.pronoun or p.possessive or p.prefix or not p.noun:
        return ""
    if _has_own_determiner(" ".join([*p.adjectives, p.noun])):
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
    if p.possessive:
        return f"your {body}"
    # A phrase that brought its own determiner ("this trait") keeps it: "a this
    # trait" is what happens when one is added anyway.
    if p.fixed_determiner:
        return body
    return f"{_article(body)} {body}"


def _at_least_one(p: Phrase) -> str:
    """The existence clause for a collection ("there is at least one d4 trait").

    A hop onto a **state** supplies its own sentence, because "there is at least
    one of your contest" is what a possessive noun phrase does to a state — the
    entity does not *have* a contest, it *is in* one.
    """
    if p.state:
        return p.state
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


def _or_join(values: list[str], resolve: NameResolver | None = None) -> str:
    """Several values read as alternatives: "character or gmc"."""
    rendered = [display_value(v, resolve) for v in values if str(v).strip()]
    if not rendered:
        return ""
    if len(rendered) == 1:
        return rendered[0]
    return ", ".join(rendered[:-1]) + f" or {rendered[-1]}"


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

def _select_phrase(step: SelectStep, source_element: str | None = None,
                   die_scoped: bool = False, variables=None) -> Phrase:
    if step.collection == "variable":
        # A bound variable's phrase is the author's name for it — and its type,
        # which the later steps need in order to rewrite the phrase at all
        # (`select variable self → navigate projections` must be able to hop).
        vt = (variables or {}).get(step.variable)
        element = getattr(vt, "element", "") or ""
        cardinality = getattr(vt, "cardinality", "") or "one"
        if step.variable == "self":
            # The actor itself is the one name that reads as a pronoun.
            return Phrase(element=element or "entity", cardinality=cardinality, pronoun=True)
        # **Every other name is named.** Treating a *known* name as a pronoun when
        # its element wasn't supplied (the editor's card call passes no variable
        # types) did two wrong things at once: it pointed the card at the wrong
        # party — the opponent's pool read as "your dice pool" — and, because a
        # pronoun phrase renders without its qualifiers, it swallowed every step
        # after it ("if there is a you", with the tags filter gone).
        determiner, noun = named_variable_phrase(step.variable)
        return Phrase(element=element, cardinality=cardinality,
                      noun=singularize(noun), plural=pluralize(noun),
                      fixed_determiner=determiner)
    if step.collection == "source":
        if source_element:
            return Phrase(
                element=source_element,
                noun=f"{element_noun(source_element)} this SFX sits on",
                plural=f"{element_plural(source_element)} this SFX sits on",
            )
        return Phrase(noun="source", plural="sources")
    if step.collection == "rolled_dice" and die_scoped:
        # This effect runs once per die: to the path, that die *is* the roll.
        return Phrase(element="die", cardinality="one", noun="die", plural="dice",
                      fixed_determiner="that")
    col = tc.collection(step.collection)
    if col is None:
        return Phrase(noun=step.collection.replace("_", " "))
    return Phrase(
        element=col.element,
        cardinality="one" if col.singular else "many",
        # A pronoun collection *is* the actor: "you", not "the entity".
        noun="" if col.pronoun else (col.noun or element_noun(col.element)),
        plural="" if col.pronoun else (col.plural or ("" if col.noun else element_plural(col.element))),
        origin=col.origin,
        absorb=col.card_origin,
        possessive=col.possessive,
        pronoun=col.pronoun,
    )


# The relation a filter's field implies when its value is a *thing* decided
# earlier rather than a literal: "in the universe you chose" reads, "with
# universe equal to the universe" does not.
_RELATION_WORDS = {"universe": "in", "origin_universe": "from", "location": "in",
                   "current_location": "in", "current_universe": "in",
                   # A path that names the far end of a hop relates the collection
                   # to that thing: "your relationships **with** the Verdant
                   # Steps", "your trait instances **of** Spiritual Power" — not
                   # "with contact equal to" / "with trait equal to".
                   "contact_id": "with", "trait_id": "of"}


def _bound_name(value) -> str:
    """The variable name a step value refers to, or "" when it is a literal.

    A reference to a thing decided elsewhere, as opposed to an authoring token
    (``{choose_trait}``) or a plain value.
    """
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if not (text.startswith("{") and text.endswith("}")):
        return ""
    inner = text[1:-1]
    if not inner or ":" in inner or inner.startswith("choose_"):
        return ""
    return inner


def _filter_phrase(p: Phrase, step: FilterStep, resolve: NameResolver | None = None,
                   variables=None) -> Phrase:
    field_def = tc.field(p.element, step.field) if p.element else None
    resolved = None
    if resolve and isinstance(step.value, str) and not step.value.startswith("{"):
        resolved = resolve(step.value)

    bound = _bound_name(step.value)
    if bound and bound not in _KNOWN_PLACEHOLDERS:
        # A filter against a bound value relates the collection to something
        # decided earlier, so it reads as *that thing* — "your projections in the
        # universe you chose". Rendering the field and the value separately is
        # what produced "with universe equal to the universe".
        named = _named_phrase(bound, (variables or {}).get(bound))
        relation = _RELATION_WORDS.get(step.field, "with")
        clause = f"{relation} {render_phrase(named, _determiner(named))}".strip()
        p.origin = f"{p.origin} {clause}".strip()
        return p

    # Enum- or die-valued equality reads as an adjective: "static", "d4". Several
    # values (`in …`, or a list) read as alternatives: "static or resource".
    if (step.operator in ("==", "in") and field_def is not None and not resolved
            and (field_def.type == "die"
                 or (field_def.type == "string" and field_def.options))):
        values = step.value if isinstance(step.value, list) else [step.value]
        p.adjectives.append(_or_join([str(v) for v in values], resolve))
        return p

    # A negated set: "not one of static or resource". The phrase is chosen so it
    # cannot be misread as a plain equality on the first value.
    if step.operator == "not in":
        values = step.value if isinstance(step.value, list) else [step.value]
        p.adjectives.append(f"not one of {_or_join([str(v) for v in values], resolve)}")
        return p

    if step.operator == "contains" and step.field in _CONTAINS_WORDS:
        value_text = (_or_join([str(v) for v in step.value], resolve)
                      if isinstance(step.value, list)
                      else resolved or display_value(step.value, resolve))
        p.origin = f"{p.origin} {_CONTAINS_WORDS[step.field]} {value_text}".strip()
        return p

    field_text = tc.field_label(field_def) if field_def else step.field.replace("_", " ")
    if isinstance(step.value, list):
        value_text = _or_join([str(v) for v in step.value], resolve)
    else:
        value_text = resolved or display_value(step.value, resolve)
    relation = _RELATION_WORDS.get(step.field)
    if relation and step.operator == "==":
        # A container field reads as a place: "in earth", not "with universe
        # equal to earth".
        clause = f"{relation} {value_text}"
    else:
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
    # Where the hop's source came from decides who did the rolling: an edge
    # origin is the actor's default, a seed that knows its own party wins (the
    # other side's dice read "they rolled", never "you rolled").
    origin = p.absorb or edge.card_origin
    # A state hop reads as a clause *about the actor* — and only there, because
    # from another party's seed the declared sentence would name the wrong party
    # ("you are in a contest" for their contest). Every other branch below keeps
    # the noun phrase.
    state = edge.state_phrase if p.pronoun else ""

    if p.pronoun:
        # "you" → "your location" (one possessive hop; a further hop goes back
        # to "the X of your location" so long chains stay unambiguous).
        return Phrase(element=element, cardinality=cardinality, noun=noun,
                      plural=plural, possessive=True, state=state, modal=p.modal)

    if not origin and len(edge.target) == 1 and noun == p.noun:
        # A hop to the *same word* says nothing new, so it does not get said: a
        # trait instance and its registry trait are both "trait", and the hop from
        # one to the other is how a filter reaches the definition's tags. Reading
        # it literally gave "a trait of this trait tagged fire" for what the author
        # wrote as "this trait tagged fire".
        return replace(p, element=element, cardinality=cardinality, state=state)

    if origin:
        # The edge absorbs its source ("… you rolled"): carry the source's
        # adjectives, but drop any that merely echo the new head noun — a "trait
        # die" navigated to its trait instance is already a trait instance.
        head_words = set(noun.lower().split())
        keep = [a for a in p.adjectives if a.lower().split()[-1] not in head_words]
        return Phrase(element=element, cardinality=cardinality, adjectives=keep,
                      noun=noun, plural=plural, origin=origin, state=state, modal=p.modal)

    return Phrase(element=element, cardinality=cardinality, noun=noun, plural=plural,
                  origin=f"of {render_phrase(p, _determiner(p))}".strip(),
                  state=state, modal=p.modal)


def _aggregate_phrase(p: Phrase, step: AggregateStep) -> Phrase:
    agg = tc.aggregation(step.fn)
    field_text = ""
    if step.field:
        field_def = tc.field(p.element, step.field) if p.element else None
        field_text = tc.field_label(field_def) if field_def else step.field.replace("_", " ")
    if agg is not None and agg.name == "tier":
        # A **cast** transforms the value the path already selected, so it must not
        # throw the selection away: after `top(rating)` the phrase carries "with
        # the highest rating", and the generic branch below would flatten that to
        # "the tier of the rating" — reading as if any rating would do. Keep the
        # superlative the path earned.
        m = re.match(r"with the (highest|lowest) (.+)$", (p.origin or "").strip())
        if m:
            return Phrase(element="int", cardinality="one",
                          scalar=f"the tier of the {m.group(1)} {m.group(2)}")
    if agg is not None and agg.name == "random":
        # A sample is an indefinite noun, not a definite one: "a random die in
        # your roll", "some random traits". A phrase that already carries its own
        # determiner (a possessive or pronoun) is left alone.
        article = "" if (p.possessive or p.pronoun or p.prefix) else (
            "a" if step.count == 1 else "some")
        return replace(p, cardinality="one" if step.count == 1 else p.cardinality,
                       adjectives=[*p.adjectives, "random"],
                       fixed_determiner=article)
    if agg is not None and agg.output == "element":
        # top/bottom select the element *carrying* the extreme value — a
        # superlative selection, which is why the path keeps walking from it.
        return _superlative_phrase(p, step.field or "", agg.name == "top")
    if agg is None:
        return Phrase(scalar=f"{step.fn} of {render_phrase(p, '')}".strip())
    return Phrase(element=agg.output, cardinality="one",
                  scalar=tc.aggregation_card(agg, render_phrase(p, ""), field_text))


def _choose_phrase(p: Phrase, step: ChooseStep) -> Phrase:
    """A `choose` step is a *modal*, not a fact: it reads as a quantifier."""
    if step.count == 1:
        return replace(p, modal=True, prefix="one of the")
    return replace(p, modal=True, prefix="a chosen set of the")


# Trait-granting actions whose target can be named by the author's own config:
# a `statement` makes the granted thing "a Crimson Scar" rather than "the
# Environmental Hazard trait".
_STATED_GRANTS = {("modify_trait", "gain"), ("modify_trait", "cortex_gain"),
                  ("modify_trait", "gain_or_step_up")}


def _stated_grant(effect: Effect) -> str:
    """The author's own name for a granted trait ("a Crimson Scar"), or "".

    Falls back to nothing — the target phrase already names the trait definition,
    which is the fallback the author asked for.
    """
    if (effect.type, effect.action) not in _STATED_GRANTS:
        return ""
    statement = str((effect.context or {}).get("statement") or "").strip()
    return f"a {statement}" if statement else ""


def _superlative_phrase(p: Phrase, field_name: str, highest: bool) -> Phrase:
    """``top``/``bottom`` read as superlatives: "the most recently used".

    A timestamp has an obvious reading (*most recently used* — how a path asks
    for the body you were last in); any other orderable field reads as "with the
    highest/lowest …". It collapses to one, so it supplies its own determiner.
    """
    from transversal.services import target_catalog as _tc
    f = _tc.field(p.element, field_name) if p.element else None
    if f is not None and f.type == "datetime":
        head = "most recently used" if highest else "least recently used"
        return replace(p, cardinality="one", adjectives=[*p.adjectives, head],
                       fixed_determiner="the")
    label = _tc.field_label(f) if f is not None else field_name.replace("_", " ")
    edge = "highest" if highest else "lowest"
    return replace(p, cardinality="one", origin=f"with the {edge} {label}",
                   fixed_determiner="the")


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
    if count == 1 and op == ">=":
        return Phrase(predicate=_at_least_one(subject))
    if count == 1 and op == "==":
        # ``== 1`` is **exactly one**, not "at least one": the evaluator compares
        # the collection's length, so a roll carrying two matching traits fails
        # this gate. Reading it as existence made the card promise a rule narrower
        # than it reads — the live `sfx-d4-bonus` says "at least one d4 trait" and
        # fires only when there is exactly one, which is how this was found.
        one = render_phrase(_as_one(subject), "")
        if subject.possessive:
            one = f"of {one}"
        return Phrase(predicate=f"there is exactly one {one}".strip())
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
                variables=None, resolve: NameResolver | None = None,
                die_scoped: bool = False) -> Phrase:
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
            phrase = _select_phrase(step, source_element, die_scoped, variables)
        elif isinstance(step, FilterStep):
            phrase = _filter_phrase(phrase, step, resolve, variables)
            # A type-proving filter re-types the phrase's noun too, so the rest of
            # the path is described in the narrower vocabulary ("the occupants of
            # the location", not "… of the entity"). The head noun changes with
            # it; a possessive/pronoun phrase keeps its shape.
            narrowed = tc.narrowed_element(phrase.element, step.field, step.operator, step.value)
            if narrowed and not phrase.pronoun and phrase.element != narrowed:
                phrase.element = narrowed
                # The proven type becomes the head noun, so drop the adjective the
                # filter just added — otherwise it reads "location location".
                head = element_noun(narrowed)
                phrase.adjectives = [a for a in phrase.adjectives if a.strip().lower() != head.lower()]
                phrase.noun = head
                phrase.plural = ""
        elif isinstance(step, NavigateStep):
            phrase = _navigate_phrase(phrase, step)
        elif isinstance(step, AggregateStep):
            phrase = _aggregate_phrase(phrase, step)
        elif isinstance(step, LiteralStep):
            phrase = _literal_phrase(step, resolve)
        elif isinstance(step, ChooseStep):
            phrase = _choose_phrase(phrase, step)
        elif isinstance(step, EvaluateStep):
            phrase = _evaluate_phrase(phrase, step, named)

        if not isinstance(step, EvaluateStep) and step_type is not None:
            phrase.element = step_type.element
            # A die-scoped path reads one die, so its own composition decides the
            # cardinality; the roll-wide trace would say "many" at every hop.
            if not die_scoped:
                phrase.cardinality = step_type.cardinality

        output = getattr(step, "output", None)
        if output and not isinstance(step, EvaluateStep) and output not in _KNOWN_PLACEHOLDERS:
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
        return f"{target} is rated {value}" if condition.operator == "==" \
            else f"{target} is rated {op} {value}"
    if ctype == ConditionType.HAS_RAZMERIT:
        return f"you have {op} {value} razmerit"
    if ctype == ConditionType.ENTITY_TYPE:
        values = condition.target_values()
        if len(values) > 1:
            return f"you are {' or '.join(f'{_article(v)} {v}' for v in values)}"
        return f"you are {_article(target)} {target}"
    if ctype == ConditionType.USER_ROLE:
        values = condition.target_values()
        if len(values) > 1:
            return f"{' or '.join(f'{_article(v)} {v}' for v in values)} is acting"
        return f"{_article(target)} {target} is acting"
    if ctype == ConditionType.UNPLACED:
        return "you are not at a location yet"
    if ctype == ConditionType.IN_UNIVERSE:
        return f"you are in {target}"
    if ctype == ConditionType.PHASE:
        values = condition.target_values()
        return f"the dice pool is in its {_or_join(values, resolve) or target} phase"
    if ctype == ConditionType.CONTEST_OUTCOME:
        values = condition.target_values()
        if len(values) > 1:
            return f"the contest outcome is {_or_join(values, resolve)}"
        return f'the contest outcome is "{target}"'
    if ctype == ConditionType.CONTEST_CHALLENGER:
        return "you are the challenger"
    if ctype == ConditionType.CONTEST_DEFENDANT:
        return "you are the defendant"
    if ctype == ConditionType.SESSION:
        return "no session is running" if (condition.target or "active").strip() == "inactive" \
            else "a session is running"
    if ctype == ConditionType.HITCH:
        return "a hitch is being resolved"
    if ctype == ConditionType.HIGH_STAKES:
        return "the contest is not high stakes" if (condition.target or "high").strip() == "low" \
            else "the contest is high stakes"
    if ctype == ConditionType.ARRIVAL_KIND:
        return _ARRIVAL_PHRASES.get((condition.target or "").strip(),
                                    f"you arrived as \"{target}\"")
    if ctype == ConditionType.ROLL_TIER:
        return f"the roll is {op} {value}"
    if ctype == ConditionType.TEST_OUTCOME:
        values = condition.target_values()
        if len(values) > 1:
            return "the test resolves either way"
        return "the test fails" if values[:1] == ["fail"] else "the test succeeds"
    if ctype == ConditionType.SOURCE_RATING:
        # The source is the instance the SFX sits on, so "this trait" reads shorter
        # than "this SFX's source" — and is closer to how a card would say it.
        subject = {"traitsetting": "this trait", "traitsetsetting": "this trait set"}.get(
            source_element or "", "this SFX's source")
        return f"{subject} is rated {value}" if condition.operator == "==" \
            else f"{subject} is rated {op} {value}"
    return (condition.narrative or "").strip()


# ── Effects ───────────────────────────────────────────────────

def _effect_meta(effect: Effect):
    """The registry entry for an effect's ``(type, action)``, or None."""
    return next((m for m in reg.EFFECT_ACTION_REGISTRY
                 if m.effect_type == effect.type and m.effect_action == effect.action), None)


def _result_field(effect: Effect):
    """The action's own ``result`` field definition, or None when it has none."""
    meta = _effect_meta(effect)
    return next((f for f in meta.fields if f.name == "result"), None) if meta else None


def _effect_result(effect: Effect) -> str:
    """The magnitude/rating an effect states, falling back to its field default."""
    if effect.result not in (None, ""):
        return str(effect.result)
    meta = _effect_meta(effect)
    if meta:
        for fdef in [*meta.fields, *meta.context_fields]:
            if fdef.name == "result" and fdef.default:
                return str(fdef.default)
    return ""


def _result_text(effect: Effect, ref_result: str,
                 resolve: NameResolver | None = None) -> str:
    """What fills the card's ``{result}`` — the author's amount, or a ref's object.

    An action may have both a result **field** and references, and they mean
    different things. ``increase_dice_limit``'s ``pool`` ref names **whose** limits
    move while the amount is its own field; ``move``/``copy``/``change`` have no
    result field at all, so a reference *is* how they name their object. Reading
    the ref first made the author's card say "increase the dice limit by your dice
    pool" and never mention the amount.

    The registry already declares which case it is: a result field naming a ref in
    ``hidden_when_ref`` is the **fallback form** that ref supersedes — Attune's
    named universe vs. its resolved projection. So the ref wins only there, or
    where there is no result field to speak; otherwise the field does.
    """
    field_def = _result_field(effect)
    stated = _effect_result(effect)
    if field_def is None:
        return ref_result or (display_value(stated, resolve) if stated else "")
    superseding = (getattr(field_def, "hidden_when_ref", "") or "").strip()
    if superseding and superseding in (effect.refs or {}) and ref_result:
        return ref_result
    # "Nothing stated" is answered here rather than left to the name resolver: an
    # action with no result field must not have the empty string resolved into
    # something, however the resolver happens to treat `""`.
    return display_value(stated, resolve) if stated else ""


def _target_element(effect: Effect) -> str:
    """The catalog element a bare (non-path) target id belongs to."""
    if effect.type == "modify_trait":
        return "trait"
    if effect.type == "modify_pool":
        return "pool"
    if effect.type == "set_destination":
        return "location"
    if effect.type in ("entity", "relationship", "attune", "location", "contest", "client"):
        return "entity"
    if effect.type == "roll_table":
        return "roll_table"
    if effect.type == "life_path":
        return "life_path"
    return ""


def _effect_parts(effect: Effect, *, resolve: NameResolver | None = None,
                  source_element: str | None = None, variables=None) -> tuple[str, str]:
    """``(target phrase, subject clause)`` for an effect.

    Most effects have one. An effect may also say *who it lands on* separately
    from what it acts on — a trait granted **to a location**, say — which is what
    ``entity_spec``/``entity`` carry.
    """
    # True when the applier will iterate this effect once per matching die, which
    # makes the die the path's subject rather than the whole roll. `_apply_armed`
    # checks refs, then target_spec, before the die filter — an effect carrying
    # either never reaches the per-die loop.
    per_die = bool(effect.die_filter) and effect.target_spec is None and not effect.refs

    subject = ""
    if effect.entity_spec is not None and effect.entity_spec.steps:
        phrase = path_phrase(effect.entity_spec, source_element=source_element,
                             variables=variables, resolve=resolve, die_scoped=per_die)
        subject = render_phrase(phrase, _determiner(phrase))

    target = ""
    if effect.target_spec is not None and effect.target_spec.steps:
        phrase = path_phrase(effect.target_spec, source_element=source_element,
                             variables=variables, resolve=resolve)
        target = render_phrase(phrase, _determiner(phrase))
    else:
        raw = (effect.target or "").strip()
        if raw not in ("", "self"):
            target = id_phrase(raw, _target_element(effect), resolve)
        elif effect.entity and effect.entity not in ("self",):
            target = id_phrase(effect.entity, "entity", resolve)

    if target:
        if subject:
            if "{subject}" in reg.effect_card(effect.type, effect.action):
                # The template gives the subject its own slot, so it is handed
                # over bare: there it leads the clause ("each occupant here
                # travels to X") rather than trailing a preposition that would
                # reverse who moves and what they move to.
                return target, subject
            prep = _EFFECT_SUBJECT_PREPOSITIONS.get(effect.type, "on")
            # The "lands on" clause is joined with a preposition, and a path can
            # end with that same word: "one of the trait instances of the entity
            # this SFX sits **on**" + "**on** one of the occupants…" reads as
            # "on on". The seam is the sentence's only place to break, so when
            # the target already ends with the preposition the clause takes a
            # comma instead of a second copy of the word.
            if target.rstrip().lower().endswith(f" {prep}"):
                return target, f", {prep} {subject}"
            return target, f"{prep} {subject}"
        return target, ""
    # No primary target: the subject *is* what the effect acts on.
    return subject, ""


def effect_target(effect: Effect, *, resolve: NameResolver | None = None,
                  source_element: str | None = None, variables=None) -> str:
    """Render an effect's target: a path phrase, a placeholder, or a named id."""
    return _effect_parts(effect, resolve=resolve, source_element=source_element,
                         variables=variables)[0]


# Prepositions for the "lands on" clause, by effect type.
_EFFECT_SUBJECT_PREPOSITIONS = {
    "modify_trait": "on",
    "transfer_razmerit": "to",
    "attune": "to",
    "location": "to",
}


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


def _die_scope(effect: Effect) -> str:
    """The dice an effect runs for, when it is scoped to a subset (e.g. unchosen).

    A die filter runs the effect once per matching die — including when the
    effect also names a target path or resolves references, which are then
    resolved per die with that die as the roll (so "for each unchosen die, give
    its owner's location a hazard" happens per die, not once for the pool).
    """
    if not effect.die_filter:
        return ""
    filt = effect.die_filter
    parts = []
    if "role" in filt:
        parts.append("unchosen die" if filt["role"] is None else f"{filt['role']} die")
    if "ts_id" in filt:
        # *Whose* die, and it belongs to the noun rather than beside it: a rule
        # that works from its own die says `{trait_setting}` here, and the reading
        # is "for each unchosen die **from this trait**" — not "…and from this
        # trait", which is what a separate part would join it with. Read in a fixed
        # order so the phrase cannot depend on the order the keys were authored.
        who = f"from {display_value(filt['ts_id'])}"
        if parts:
            parts[-1] = f"{parts[-1]} {who}"
        else:
            parts.append(who)
    for key, value in filt.items():
        if key in ("role", "ts_id"):
            continue
        parts.append(f"{key.replace('_', ' ')} {display_value(value)}")
    return f"for each {' and '.join(parts)}"


def _ref_result(effect: Effect, *, resolve: NameResolver | None = None,
                source_element: str | None = None, variables=None) -> str:
    """A rendered reference path — the object an effect resolves for itself.

    Attune's ``projection`` reference is the case this exists for: the capability
    is sourced from a *life*, so the card says "… to their counterpart" rather
    than naming a universe. The reference path starts from the effect's target
    path, so the author's own name for that step is what reads here.
    The last reference with a path is the one rendered: references are declared in
    dependency order (the universe decided first, the life drawn from it second),
    so the most-derived one is what the effect's object actually is.

    A reference that names a *literal* id instead of a path renders as that
    object's **name**. Without it a card whose point is the reference read
    "… into." — the sentence lost the thing the effect acts on.
    """
    text = ""
    for ref in (effect.refs or {}).values():
        spec = getattr(ref, "spec", None)
        if spec is not None and spec.steps:
            phrase = path_phrase(spec, source_element=source_element, variables=variables,
                                 resolve=resolve)
            rendered = render_phrase(phrase, _determiner(phrase))
        else:
            rendered = display_value(getattr(ref, "value", ""), resolve)
        if rendered:
            text = rendered
    return text


def _drop_empty_clause(template: str, placeholder: str) -> str:
    """Remove a prepositional clause whose placeholder came up empty.

    ``{result}`` and ``{owner}`` are optional — an effect with no die, or one that
    anchors to nothing — and their clauses are introduced by a preposition, so an
    empty value leaves the sentence dangling ("gain X on", "… as"). Removing the
    whole clause is what the reading wants; leaving the preposition is how the card
    lied by omission in the other direction.
    """
    return re.sub(rf"\s+\b(at|to|by|as|on|with|from|of|under)\s+\{{{placeholder}\}}",
                  "", template)


def _effect_core(effect: Effect, *, resolve: NameResolver | None = None,
                 source_element: str | None = None, variables=None) -> str:
    """An effect's clause, without timing/scope/duration (those group)."""
    variables = _effect_scope(effect, source_element, variables)
    target, subject = _effect_parts(effect, resolve=resolve, source_element=source_element,
                                    variables=variables)
    ref_result = _ref_result(effect, resolve=resolve, source_element=source_element,
                             variables=variables)
    result_text = _result_text(effect, ref_result, resolve)
    # `modify_dice_limit` chooses *which* limit moves, and the card has to say it:
    # "total" and "effect" are different effects that otherwise read identically.
    # Defaults to `total`, which is what `_apply_dice_limit` does with no choice.
    which_limit = str((effect.context or {}).get("limit") or "total")
    template = reg.effect_card(effect.type, effect.action)
    stated = _stated_grant(effect)
    if stated:
        # "create a Crimson Scar" — the author named the thing, so the card uses
        # their name for it (and "create" rather than "gain").
        target = stated
        template = "create {target}"
    elif not target and "{target}" in template:
        target = _target_placeholder(effect)
    if subject and "{subject}" not in template:
        target = f"{target} {subject}" if target else subject
    # The anchor, for the two verbs that hang what they make on something other
    # than the entity ("gain a rank on your tie to …", "gain a facet under …").
    # It was never filled in, so those cards raised instead of rendering: nothing
    # live used them, which is exactly how it stayed hidden.
    owner = ""
    if effect.owner_spec is not None and effect.owner_spec.steps:
        phrase = path_phrase(effect.owner_spec, source_element=source_element,
                             variables=variables, resolve=resolve)
        owner = render_phrase(phrase, _determiner(phrase))
    if not owner:
        # No anchor path = the trait anchors to the entity, so the clause goes
        # rather than dangling ("gain a rank on").
        template = _drop_empty_clause(template, "owner")
    if not result_text:
        # Drop a clause the empty placeholder leaves dangling ("… as {result}").
        template = _drop_empty_clause(template, "result")
    text = template.format(target=target, result=result_text, limit=which_limit,
                           subject=subject, owner=owner)
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
    if effect.type == "modify_roll" and effect.action in _CHANGE_DIE_COUNT_ACTIONS:
        count = display_value(str((effect.context or {}).get("count") or "1"))
        stepping = effect.action in _CHANGE_DIE_STEP_ACTIONS
        if count == "1":
            # The default already reads ("step up X", "double X").
            if stepping:
                text = f"{text} by one step"
        elif count.isdigit():
            if stepping:
                text = f"{text} by {count} steps"
            else:
                # `double 2` on a d8 gives 3d8; `split 2` gives 3d6.
                more = int(count) + 1
                smaller = ", each a step smaller" if effect.action == "split_die" else ""
                text = f"{text} into {more} dice{smaller}"
        elif stepping:
            text = f"{text} by a number of steps equal to {count}"
    if effect.type == "attune" and (effect.context or {}).get("scope") == "domain":
        # Kept for callers that set a domain scope programmatically; the editor no
        # longer exposes it — reach is meant to come from how many targets the
        # "who" path resolves to.
        text = f"{text}, reaching everyone there"
    if effect.type == "branch":
        # The options *are* the clause: a card that says only "choose" hides the
        # one thing the reader needs.
        labels = [b.label or f"Option {i}" for i, b in enumerate(effect.branches or [], start=1)]
        if labels:
            text = "choose: " + ", or ".join(labels)
        else:
            text = "choose (no options authored)"
    if effect.type == "modify_trait" and effect.action == "set_polarity":
        # Which polarity *is* the effect ("set positive" vs "set negative"), and
        # the form's default hides that it was a choice — the same reason the
        # dice limit is said out loud.
        polarity = str((effect.context or {}).get("polarity") or "positive")
        text = f"{text} to {polarity}"
    if "{result}" not in template and result_text:
        text = f"{text} ({result_text})"

    text = _tidy(text)
    gates, flavour = [], []
    for cond in effect.conditions:
        clause = condition_text(cond, resolve=resolve, source_element=source_element,
                                variables=variables)
        if not clause:
            continue
        (flavour if cond.type == ConditionType.NARRATIVE else gates).append(clause)
    if gates:
        text = f"if {' and '.join(gates)}, {text}"
    if flavour:
        text = f"{text} ({'; '.join(flavour)})"
    return text


def effect_text(effect: Effect, *, resolve: NameResolver | None = None,
                source_element: str | None = None, variables=None) -> str:
    """Render one effect as a clause ("step down each static trait instance you rolled")."""
    return _effects_text([effect], resolve=resolve, source_element=source_element,
                         variables=variables)


def _effect_scope(effect: Effect, source_element: str | None, variables):
    """The activation scope as *this* effect sees it — its own gate outputs included.

    An effect's conditions run before it does, so the names their paths output are
    in scope for its own paths; without tracing them here a path naming one ("for
    each d4 trait") renders untyped, i.e. singular.
    """
    for cond in (effect.conditions or []):
        if cond.spec is not None:
            variables = spec_variables(cond.spec, source_element, variables)
    return variables


def _repeat_scope(effect: Effect, *, resolve: NameResolver | None = None,
                  source_element: str | None = None, variables=None) -> str:
    """How many times the effect runs, when it runs once per thing.

    Two ways to say it, one reading. A ``die_filter`` names dice ("for each
    unchosen die from this trait"). A ``target_spec`` on an action whose card
    template has no ``{target}`` slot — ``earn``/``spend`` razmerit, a dice-limit
    bump, a suppress — names the things it happens *for*, because the template
    has nowhere else to put them ("for each d4 trait"). That clause is not
    decoration: the applier fans the effect out once per resolved target, so a
    card that dropped it would promise one razmerit where the rule pays one per
    trait.
    """
    die_scope = _die_scope(effect)
    if die_scope:
        return die_scope
    if "{target}" in reg.effect_card(effect.type, effect.action):
        return ""  # the path is the effect's object, and the template names it
    spec = effect.target_spec
    if spec is None or not spec.steps:
        return ""
    phrase = path_phrase(spec, source_element=source_element, resolve=resolve,
                         variables=_effect_scope(effect, source_element, variables))
    rendered = render_phrase(phrase, _determiner(phrase) or "the")
    return f"for {rendered}" if rendered else ""


def _effect_key(effect: Effect, resolve: NameResolver | None = None,
                source_element: str | None = None, variables=None) -> tuple:
    """What two effects must share to be read as one sentence."""
    duration = effect.duration
    timers = tuple((t.event, t.remaining) for t in duration.timers) if duration else ()
    combine = getattr(duration.combine, "value", duration.combine) if duration else ""
    return (effect.timing, timers, combine,
            _repeat_scope(effect, resolve=resolve, source_element=source_element,
                          variables=variables))


def _effects_text(effects: list[Effect], *, resolve: NameResolver | None = None,
                  source_element: str | None = None, variables=None) -> str:
    """Render an effect sequence, grouping consecutively-shared framing.

    Effects that share a timing, a die scope and a duration read as one clause
    list with the framing stated once — five rating-gated dice-limit bumps
    revert at the next roll *together*, so the card says so once.
    """
    groups: list[tuple[tuple, list[Effect]]] = []
    for effect in effects:
        key = _effect_key(effect, resolve=resolve, source_element=source_element,
                          variables=variables)
        if groups and groups[-1][0] == key:
            groups[-1][1].append(effect)
        else:
            groups.append((key, [effect]))

    rendered = []
    for (timing, timers, combine, repeat_scope), group in groups:
        body = "; ".join(
            c for c in (_effect_core(e, resolve=resolve, source_element=source_element,
                                     variables=variables) for e in group) if c
        )
        if not body:
            continue
        lead = _LEADING_TIMINGS.get(timing)
        if lead and repeat_scope:
            body = f"{lead}, {repeat_scope}, {body}"
        elif repeat_scope:
            body = f"{repeat_scope}, {body}"
        elif lead:
            body = f"{lead}, {body}"
        if timing in _TRAILING_TIMINGS:
            body = f"{body}, {_TRAILING_TIMINGS[timing]}"
        if timers:
            duration = SimpleNamespace(timers=[SimpleNamespace(event=e, remaining=n)
                                               for e, n in timers], combine=combine)
            body = f"{body} ({_duration_text(duration, count=len(group))})"
        rendered.append(body)
    return "; ".join(rendered)


def _duration_text(duration, count: int = 1) -> str:
    """Effect duration = the *undo* timer (distinct from the SFX listening window).

    ``count`` is how many effects share it — a group states the revert once.
    """
    parts = [_timer_phrase(t) for t in duration.timers] or ["1 scene"]
    subject = "each reverts" if count > 1 else "reverts"
    if len(parts) == 1:
        return f"{subject} {parts[0]}"
    if getattr(duration.combine, "value", duration.combine) == "all_transpired":
        return f"{subject} once {', '.join(parts)} have all passed"
    return f"{subject} as soon as any of {', '.join(parts)} passes"


def _timer_phrase(timer) -> str:
    """One timer as a card phrase ("at the end of the scene", "after 2 beats")."""
    event = (timer.event or "scene").replace("_", " ")
    boundary = {"beat": "the end of the beat", "scene": "the end of the scene",
                "session": "the end of the session", "rolls": "the next roll"}
    if timer.remaining == 1 and event in boundary:
        return f"at {boundary[event]}"
    unit = pluralize(event) if timer.remaining != 1 else event
    return f"after {timer.remaining} {unit}"


def _tidy(text: str) -> str:
    """Collapse the seams left by empty placeholders."""
    out = re.sub(r"\s{2,}", " ", text)
    out = re.sub(r"\s+([,.;:])", r"\1", out)
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
    # The names the activation puts in scope, typed — the *same declaration* the
    # wizard offers and the engine binds (`scope_seed_names`). Without this a
    # `select variable` seed carries no element, and the renderer then skips every
    # step after it: the card said "if there is a this trait" and dropped the tags
    # filter that was the whole point of the condition.
    seeds = {
        name: ValueType(element, "one")
        for name, element in tc.scope_seed_names(sfx.trigger or "", sfx.source_kind).items()
    }

    # The rule's **declared** variables, named and said out loud. A card that reads
    # "increase the limit by the cultivation tier" has to state what that tier is
    # somewhere, so each declaration contributes "«name» is «what its path reads»"
    # — built from the declaration's own path with the same phrase builder every
    # other path uses. Each one is seeded as it is declared, in order, so a later
    # declaration and every use below read the types the engine will bind.
    definitions: list[str] = []
    for bv in (getattr(sfx, "bound_variables", None) or []):
        name = (getattr(bv, "name", "") or "").strip()
        spec = getattr(bv, "spec", None)
        if not name or spec is None or not getattr(spec, "steps", None) or name in seeds:
            continue
        types, errors = trace(spec, source_element, seeds)
        if errors or not types or types[-1] is None or not types[-1].element:
            continue
        meaning = render_phrase(
            path_phrase(spec, source_element=source_element, variables=seeds, resolve=resolve)
        )
        if not meaning:
            continue
        seeds[name] = types[-1]
        definitions.append(f"the {humanize(name)} is {meaning}")

    rules: list[str] = []
    narrative: list[str] = []

    for cond in sfx.conditions:
        clause = condition_text(cond, resolve=resolve, source_element=source_element, variables=seeds)
        # A condition's named outputs are in scope for every effect — the engine
        # evaluates the gate first and shares the scope — so the effects below
        # must be typed against them. Without this a path naming a gate's output
        # ("for each d4 trait") renders untyped, i.e. singular.
        if cond.spec is not None:
            seeds = spec_variables(cond.spec, source_element, seeds)
        if not clause:
            continue
        (narrative if cond.type == ConditionType.NARRATIVE else rules).append(clause)

    effects = _effects_text(sfx.effects, resolve=resolve, source_element=source_element, variables=seeds)

    head = mc.trigger_card(sfx.trigger)
    if definitions:
        head = f"{head}, where {', and '.join(definitions)}"
    if rules:
        head = f"{head}, if {' and '.join(rules)}"
    text = f"{head}: {effects}." if effects else f"{head}."

    # An *acquire* gate is deliberately absent from the card: where a rule may be
    # taken is not part of what it does. The card states the ability; the gate
    # lives in the editor (and is enforced at the attach). Narrative conditions
    # (the legacy ``limit`` text) are authors' flavour, so they still trail here.
    trailing: list[str] = []
    if narrative and include_narrative:
        trailing.extend(narrative)
    if trailing:
        text = f"{text} ({'; '.join(trailing)})"
    return text


# ── DB glue (optional) ────────────────────────────────────────
#
# The renderer above is pure; this factory supplies it with real display names
# so a card shows "the Fire trait" rather than "trait-fire". Kept here (rather
# than in the GraphQL layer) so every consumer resolves names identically.

_NAME_LOOKUPS = ("get_entity", "get_trait", "get_traitset_by_id", "get_lifepath", "get_roll_table")


def repo_name_resolver(repo) -> NameResolver:
    """A memoized ``id → display name`` resolver over the repository.

    Covers entities (including locations and universes), registry traits, trait
    sets, life paths, roll tables, and *universe keys* — the short handles
    (``earth``, ``three_realms``) that universe entities carry in
    ``current_universe`` rather than as their id.

    Duck-typed on purpose: a caller holding only part of the repository surface
    (a narrow test double, say) resolves what it can — the renderer falls back to
    raw ids for the rest.
    """
    lookups = [getattr(repo, name) for name in _NAME_LOOKUPS
               if callable(getattr(repo, name, None))]
    cache: dict[str, str | None] = {}
    universes: dict[str, str] = {}
    universes_loaded = False

    def resolve(ident: str) -> str | None:
        nonlocal universes, universes_loaded
        if not ident:
            return None
        if ident in cache:
            return cache[ident]

        name: str | None = None
        for lookup in lookups:
            found = lookup(ident)
            if found is not None and getattr(found, "name", ""):
                name = found.name
                break
        if name is None and not universes_loaded:
            universes_loaded = True
            list_entities = getattr(repo, "list_all_entities", None)
            for candidate in (list_entities() if callable(list_entities) else []):
                if getattr(candidate, "type", "") != "universe":
                    continue
                key = getattr(candidate, "current_universe", "") or candidate.id
                universes.setdefault(key, candidate.name or candidate.id)
            name = universes.get(ident)
        if name is None:
            name = _traitsetting_name(repo, ident, resolve)

        cache[ident] = name
        return name

    return resolve


def _traitsetting_name(repo, ident: str, resolve: NameResolver) -> str | None:
    """Name a trait **instance** the way the sheet does: statement first.

    A trait setting has no ``name`` of its own, so it cannot ride the
    ``_NAME_LOOKUPS`` protocol that names every other element. That left a *teach*
    card reading "give Dmitri a copy of ``char-1:three_realms:trait-129471191``" —
    and the referenced instance is the entire subject of a copy/move card, so the
    raw id was the least readable place in the whole renderer. Falls back to the
    registry trait's name, then to the id.
    """
    get_ts = getattr(repo, "get_traitsetting", None)
    if not callable(get_ts):
        return None
    ts = get_ts(ident)
    if ts is None:
        return None
    statement = (getattr(ts, "statement", "") or "").strip()
    if statement:
        return statement
    return resolve(getattr(ts, "trait_id", "") or "")
