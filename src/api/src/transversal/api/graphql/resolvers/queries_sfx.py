"""Queries sfx — split out of src/api/src/transversal/api/graphql/schema.py."""

import strawberry

from transversal.api.graphql.types import ScheduledEvent as GqlScheduledEvent
from transversal.api.graphql.types import ActiveSfx as GqlActiveSfx
from transversal.api.graphql.types import ActiveSfxBinding as GqlActiveSfxBinding
from transversal.api.graphql.types import SfxInput
from transversal.api.graphql.types import SfxOwnerKindGql
from transversal.api.graphql.types import SfxOwnerRef
from transversal.api.graphql.types import SfxRef
from transversal.api.graphql.types import PlaceSfxRules
from transversal.services.sfx_text import repo_name_resolver
from typing import Optional
from transversal.api.graphql.resolvers.converters import (
    _bound_variables_from_input,
    _condition_input_to_domain,
    _duration_input_to_domain,
    _effect_input_to_domain,
    _em,
    _scheduled_event_to_gql,
    _sfx_ref,
    _target_spec_from_input,
)


#: Display nouns for a binding's element, so a many-valued binding reads as a
#: count instead of a wall of ids ("3 dice", not "die:loc:owner:0, …").
_ELEMENT_NOUNS = {
    "die": ("die", "dice"),
    "traitsetting": ("trait", "traits"),
    "traitset": ("trait set", "trait sets"),
    "entity": ("entity", "entities"),
    "location": ("place", "places"),
    "projection": ("body", "bodies"),
    "sfx": ("rule", "rules"),
}


def _display_name(repo, value: str, resolve) -> str:
    """A human name for an id, statement-first for a trait instance.

    Mirrors the sheet: a trait instance reads as its ``statement`` when it has
    one ("Crimson Scar"), otherwise as its registry trait. Falls back to the raw
    id when nothing can name it.
    """
    if not value:
        return ""
    name = resolve(value)
    if name:
        return name
    get_ts = getattr(repo, "get_traitsetting", None)
    ts = get_ts(value) if callable(get_ts) else None
    if ts is not None:
        statement = getattr(ts, "statement", "") or ""
        if statement:
            return statement
        get_trait = getattr(repo, "get_trait", None)
        trait = get_trait(getattr(ts, "trait_id", "")) if callable(get_trait) else None
        return getattr(trait, "name", "") or value
    return value


def _binding_summary(repo, element: str, cardinality: str, values: list[str], resolve) -> str:
    """What to print for a binding: a name for one, a count for many/dice."""
    if not values:
        return ""
    if element == "die" or cardinality == "many" or len(values) > 1:
        singular, plural = _ELEMENT_NOUNS.get(element, ("value", "values"))
        return f"{len(values)} {singular if len(values) == 1 else plural}"
    return _display_name(repo, values[0], resolve)


def _binding_rows(repo, entry, resolve) -> list[GqlActiveSfxBinding]:
    """The armed entry's bound names, ready to render."""
    out: list[GqlActiveSfxBinding] = []
    for name, binding in (entry.bindings or {}).items():
        values = list(binding.values) if binding.values else ([binding.value] if binding.value else [])
        if not values:
            continue
        element = binding.element or ""
        cardinality = binding.cardinality or "one"
        out.append(GqlActiveSfxBinding(
            name=name,
            element=element,
            cardinality=cardinality,
            summary=_binding_summary(repo, element, cardinality, values, resolve),
        ))
    return out


def _row_activation_source(repo, rows, entity_id: str, sfx_id: str) -> Optional[str]:
    """The source instance recorded on the row, for a rule with no armed entry."""
    from transversal.services.scheduled_events import _event_owner_entity

    for event in rows:
        if event.source_sfx_id != sfx_id:
            continue
        if _event_owner_entity(repo, event) != entity_id:
            continue
        source = (event.effect.context or {}).get("activation_source")
        if source:
            return source
    return None


@strawberry.type
class QueriesSfx:
    """Mixin contributing 11 field(s) to the root type."""

    @strawberry.field
    def sfx_text(self, info: strawberry.Info, sfx: SfxInput) -> str:
        """Derived rules text for an SFX payload.

        Stateless on purpose: the SFX editor renders an *unsaved* draft, so the
        text must come from the payload, not from the stored SFX.
        """
        from transversal.domain import SFX as DomainSFX
        from transversal.services.sfx_text import sfx_text as render

        domain = DomainSFX(
            id=sfx.id, name=sfx.name, description=sfx.description,
            trigger=sfx.trigger, limit=sfx.limit,
            source_kind=sfx.source_kind, placement=sfx.placement,
            arming_scope=sfx.arming_scope,
            bound_variables=_bound_variables_from_input(sfx.bound_variables),
            conditions=[_condition_input_to_domain(c) for c in (sfx.conditions or [])],
            effects=[_effect_input_to_domain(e) for e in (sfx.effects or [])],
            duration=_duration_input_to_domain(sfx.duration),
        )
        return render(domain, resolve=repo_name_resolver(_em(info).repo))

    @strawberry.field
    def acquirable_sfx_ids(self, info: strawberry.Info, trait_setting_id: strawberry.ID) -> list[strawberry.ID]:
        """The trait instance's *possible* SFX that may be taken right now.

        A rule can be gated to where it may be learned (`acquire_spec`): the
        instance's trait offers it, but the chip only appears where the path
        resolves. This is the list the sheet should render — enforcement lives in
        the attach, so this is the honest preview of what would be accepted.

        An **implicit** rule is left out ([[B131]]): it needs no learning, so
        offering a learn-chip for it would offer to take what the instance already
        has. Its reach is the acquire path's business, read by availability
        instead.
        """
        from transversal.services.sfx_owner import acquire_gate_holds

        repo = _em(info).repo
        ts = repo.get_traitsetting(str(trait_setting_id))
        if ts is None:
            return []
        trait = repo.get_trait(ts.trait_id)
        possible = list(getattr(trait, "possible_sfx_ids", None) or [])
        out: list[strawberry.ID] = []
        for sfx_id in possible:
            sfx = repo.get_sfx(sfx_id) if hasattr(repo, "get_sfx") else None
            if sfx is None or getattr(sfx, "implicit", False):
                continue
            if acquire_gate_holds(sfx, "trait_instance", ts.id, repo):
                out.append(strawberry.ID(sfx_id))
        return out

    @strawberry.field
    def place_sfx_rules(
        self,
        info: strawberry.Info,
        entity_id: strawberry.ID,
        universe: Optional[str] = None,
    ) -> list[PlaceSfxRules]:
        """The rules an entity may use *because of where it stands*, by place.

        A place owns rules that reach whoever is inside it (rooms included), and
        nothing is written on the occupant — step out and they're gone. This is
        that contribution kept apart from the entity's own rules, so the sheet
        can show them under the place they come from. Same source as
        ``availableSfxIds``, so the two can't disagree about what's usable.
        """
        from transversal.services.sfx_owner import get_place_sfx_rules

        repo = _em(info).repo
        uni = universe
        if not uni:
            entity = repo.get_entity(str(entity_id))
            uni = (getattr(entity, "current_universe", "") or "") if entity is not None else ""
        return [
            PlaceSfxRules(
                location_id=strawberry.ID(g["location_id"]),
                location_name=g["location_name"],
                sfx_ids=[strawberry.ID(s) for s in g["sfx_ids"]],
            )
            for g in get_place_sfx_rules(str(entity_id), uni, repo)
        ]

    @strawberry.field
    def sfxs(self, info: strawberry.Info) -> list[SfxRef]:
        # Prefer DB-persisted SFXs; fall back to in-memory engine
        repo = _em(info).repo
        db_sfxs = repo.get_all_sfxs()
        if db_sfxs:
            resolve = repo_name_resolver(repo)
            return [_sfx_ref(s, resolve) for s in db_sfxs]
        from transversal.services.effects_engine import EffectsEngine
        engine = info.context.get("effects_engine")
        if engine:
            resolve = repo_name_resolver(repo)
            return [_sfx_ref(s, resolve) for s in engine.get_all()]
        return []

    @strawberry.field
    def sfx_owners(self, info: strawberry.Info, owner_type: SfxOwnerKindGql) -> list[SfxOwnerRef]:
        """Flattened owner instances of one type for the SFX ownership manager."""
        from transversal.services.sfx_owner import list_owner_refs

        refs = list_owner_refs(_em(info).repo, owner_type.value)
        return [
            SfxOwnerRef(
                owner_type=r["owner_type"],
                owner_id=r["owner_id"],
                label=r["label"],
                entity_type=r.get("entity_type", ""),
                sfx_ids=r["sfx_ids"],
            )
            for r in refs
        ]

    @strawberry.field
    def scheduled_events(
        self, info: strawberry.Info,
        target_type: Optional[str] = None,
        target_id: Optional[strawberry.ID] = None,
        target_ids: Optional[list[strawberry.ID]] = None,
    ) -> list[GqlScheduledEvent]:
        """Running centrally-scheduled timers, optionally scoped to owners.

        ``target_type`` is ``"entity"`` or ``"trait_setting"``. ``target_id``
        scopes to one owner; ``target_ids`` scopes to a set of owners (e.g. a
        sheet's trait-setting ids). Omit all for the full store.
        """
        repo = _em(info).repo
        events = repo.list_scheduled_events(
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            target_ids=[str(i) for i in target_ids] if target_ids is not None else None,
        )
        # Holds are the activation's *cancelability* record, not a running timer:
        # they are not displayed as a countdown. (The sheet asks for them through
        # the activation's own affordance, not the ⏳ line.)
        return [_scheduled_event_to_gql(e, repo) for e in events if getattr(e, "kind", "revert") != "hold"]

    @strawberry.field
    def armed_sfx_ids(self, info: strawberry.Info, entity_id: strawberry.ID) -> list[strawberry.ID]:
        """SFX ids currently armed (roll-deferred, in effect) for an entity."""
        from transversal.services.roll_deferral import list_armed_sfx_ids

        return [strawberry.ID(i) for i in list_armed_sfx_ids(str(entity_id))]

    @strawberry.field
    def in_flight_sfx_ids(self, info: strawberry.Info, entity_id: strawberry.ID) -> list[strawberry.ID]:
        """Manual rules the entity has activated and not yet committed.

        The chip's take-back state: while a rule is in flight, pressing it again
        ends it — the undos it still owes are applied, what is still waiting is
        dropped. Once the dice are rolled (or a delayed part fires) the rule is
        committed and leaves this list.
        """
        from transversal.main import _get_engine
        from transversal.services.scheduled_events import in_flight_sfx_ids

        engine = _get_engine()
        out = []
        for sfx_id in in_flight_sfx_ids(_em(info).repo, str(entity_id)):
            sfx = engine.get(sfx_id)
            if sfx is not None and sfx.trigger in ("manual", "on_activate"):
                out.append(strawberry.ID(sfx_id))
        return out

    @strawberry.field
    def active_sfx(self, info: strawberry.Info, entity_id: strawberry.ID) -> list[GqlActiveSfx]:
        """Every rule the entity is currently under — the Active rail's read.

        Unlike ``inFlightSfxIds`` (deliberately narrowed to the manual take-back
        window, because its caller is the chip that offers to end the rule), this
        is the *display* union: an armed rule waiting on a roll, a manual
        activation not yet committed, an **automatic** rule whose duration timer
        is still running, and a **globally-armed passive** (a session rule covers
        every entity, so it belongs on every entity's rail even though no entity
        armed it). Holds count too — an un-fired undo still means the activation
        is live. Unknown ids are dropped, so an orphaned row from a deleted rule
        cannot render a card.

        Each entry also says *what it came from* (the activation's source
        instance) and *what it bound* (the names its targeting paths could use).
        Bindings are live-only — they are not persisted on the timer rows — so a
        rule known solely by its row shows its source and no bindings.
        """
        from transversal.main import _get_engine
        from transversal.services.roll_deferral import (
            armed_entry_for,
            list_global_armed_sfx_ids,
        )
        from transversal.services.scheduled_events import in_flight_sfx_ids

        repo = _em(info).repo
        engine = _get_engine()
        eid = str(entity_id)
        ids: list[str] = []
        for sfx_id in (*in_flight_sfx_ids(repo, eid), *list_global_armed_sfx_ids()):
            if sfx_id not in ids and engine.get(sfx_id) is not None:
                ids.append(sfx_id)

        resolve = repo_name_resolver(repo)
        rows = repo.list_all_scheduled_events()
        out: list[GqlActiveSfx] = []
        for sfx_id in ids:
            sfx = engine.get(sfx_id)
            entry = armed_entry_for(eid, sfx_id)
            source_id = (
                entry.source_id if entry is not None
                else _row_activation_source(repo, rows, eid, sfx_id)
            )
            out.append(GqlActiveSfx(
                sfx_id=strawberry.ID(sfx_id),
                name=getattr(sfx, "name", "") or sfx_id,
                source_kind=entry.source_kind if entry is not None else None,
                source_id=source_id,
                source_name=_display_name(repo, source_id, resolve) if source_id else None,
                bindings=_binding_rows(repo, entry, resolve) if entry is not None else [],
            ))
        return out

    @strawberry.field
    def available_sfx_ids(self, info: strawberry.Info, entity_id: strawberry.ID, universe: str = "") -> list[strawberry.ID]:
        """SFX ids currently available to an entity (ownership + static conditions).

        ``universe`` gates trait-level grants via effective trait settings; when
        blank it falls back to the entity's current universe.
        """
        from transversal.services.sfx_owner import get_available_sfx_ids

        repo = _em(info).repo
        if not universe:
            entity = repo.get_entity(str(entity_id))
            universe = entity.current_universe if entity else ""
        return [strawberry.ID(i) for i in get_available_sfx_ids(str(entity_id), universe, repo)]

    @strawberry.field
    def validate_sfx(self, info: strawberry.Info, input: SfxInput) -> list[str]:
        """Return authoring warnings for an SFX draft (unknown variables, etc.)."""
        from transversal.domain import SFX as DomainSFX
        from transversal.services.sfx_validation import validate_sfx

        draft = DomainSFX(
            id=input.id, name=input.name, trigger=input.trigger,
            source_kind=input.source_kind, placement=input.placement,
            arming_scope=input.arming_scope,
            listener_spec=_target_spec_from_input(input.listener_spec),
            acquire_spec=_target_spec_from_input(input.acquire_spec),
            bound_variables=_bound_variables_from_input(input.bound_variables),
            conditions=[_condition_input_to_domain(c) for c in (input.conditions or [])],
            effects=[_effect_input_to_domain(e) for e in (input.effects or [])],
            duration=_duration_input_to_domain(input.duration),
        )
        return validate_sfx(draft, repo=_em(info).repo)
