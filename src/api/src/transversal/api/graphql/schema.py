"""Strawberry GraphQL schema — queries and mutations."""

import json
import strawberry
from typing import Optional

from transversal.api.graphql.types import (
    CharacterView,
    CreateEntityInput,
    CreateRelationshipInput,
    DeleteRelationshipInput,
    EffectActionMeta as GqlEffectActionMeta,
    EffectFieldDef as GqlEffectFieldDef,
    Entity,
    EntityType,
    JournalEntryInput,
    Message,
    MessageKind,
    Projection,
    RelatedEntity,
    Relationship,
    RazmeritResult,
    SendMessageInput,
    SfxEffect as GqlSfxEffect,
    SfxInput,
    SfxRef,
    TraitDisplayName as GqlTraitDisplayName,
    SfxUpdateInput,
    TraitInput,
    TraitRef,
    TraitSetRef,
    TraitSetting,
    TraitSettingInput,
    TraitSettingUpdateInput,
    TraitUpdateInput,
    TransversalTypeEnum,
    UpdateEntityInput,
    UpdateMessageInput,
    Zone,
)
from transversal.domain import Entity as DomainEntity
from transversal.domain import EntityType as DomainEntityType
from transversal.domain import TraitSetting as DomainTraitSetting
from transversal.domain import TraitDisplayName as DomainTraitDisplayName
from transversal.domain import dice_list_to_rating
from transversal.services.entity_manager import EntityManager
from transversal.services.razmerit import RazmeritService


def _em(info: strawberry.Info) -> EntityManager:
    return info.context["entity_manager"]


def _raz(info: strawberry.Info) -> RazmeritService:
    return info.context["razmerit_service"]


def _entity_to_gql(e: DomainEntity) -> Entity:
    return Entity(
        id=e.id, type=e.type, name=e.name, razmerit=e.razmerit,
        current_universe=e.current_universe, current_location=e.current_location,
        hidden=e.hidden, known_to=e.known_to,
        _background_image=e.background_image, overlay=e.overlay,
        zones=[Zone(name=z.name, background_image=z.background_image, x=z.x, y=z.y) for z in e.zones],
        map_x=e.map_x, map_y=e.map_y,
        nav_positions=json.dumps(e.nav_positions) if e.nav_positions else "{}",
        node_ids=e.node_ids, owned_by=e.owned_by,
        lora_config=json.dumps(e.lora_config) if e.lora_config else None,
    )


def _ts_to_gql(s: DomainTraitSetting) -> TraitSetting:
    return TraitSetting(
        id=s.id, entity_id=s.entity_id, trait_id=s.trait_id,
        traitset_id=s.traitset_id,
        rating_type=s.rating_type, dice=s.dice,
        polarity=s.polarity,
        statement=s.statement, negative=s.negative,
        ego=s.ego, sfx_ids=s.sfx_ids,
        known_to=s.known_to,
    )


def _message_to_gql(m: "Message", repo) -> Message:
    """Convert a domain Message to GraphQL Message, resolving the
    ``associate`` relationship description between sender and recipient."""
    from transversal.domain import MessageKind as DomainMessageKind
    rel = repo.get_relationship(m.sender_entity_id, m.recipient_entity_id, "associate")
    if rel is None:
        rel = repo.get_relationship(m.recipient_entity_id, m.sender_entity_id, "associate")
    return Message(
        id=m.id,
        sender_entity_id=m.sender_entity_id,
        recipient_entity_id=m.recipient_entity_id,
        kind=MessageKind(m.kind.value),
        title=m.title,
        body=m.body,
        images=m.images,
        after_ids=m.after_ids,
        threads=m.threads,
        created_at=m.created_at,
        relationship_description=(rel or {}).get("description", ""),
    )


# ── Queries ──────────────────────────────────────────

@strawberry.type
class Query:
    @strawberry.field
    def entity(self, info: strawberry.Info, id: strawberry.ID) -> Optional[Entity]:
        e = _em(info).repo.get_entity(str(id))
        return _entity_to_gql(e) if e else None

    @strawberry.field
    def character(self, info: strawberry.Info, id: strawberry.ID) -> Optional[CharacterView]:
        cv = _em(info).get_character(str(id))
        if cv is None:
            return None
        return CharacterView(
            entity=_entity_to_gql(cv.entity),
            projections=[
                Projection(id=p.id, entity_id=p.entity_id, universe=p.universe,
                           transversal_type=p.transversal_type)
                for p in cv.projections.values()
            ],
            trait_settings=[_ts_to_gql(s) for s in cv.trait_settings],
        )

    @strawberry.field
    def entities(
        self, info: strawberry.Info,
        type: Optional[EntityType] = None,
        universe: Optional[str] = None,
    ) -> list[Entity]:
        repo = _em(info).repo
        if type is not None:
            domain_type = DomainEntityType(type.value)
            results = repo.list_entities_by_type(domain_type, universe)
        else:
            results = repo.list_all_entities(universe)
        return [_entity_to_gql(e) for e in results]

    @strawberry.field
    def traitsets(self, info: strawberry.Info) -> list[TraitSetRef]:
        tss = _em(info).repo.get_all_traitsets()
        return [
            TraitSetRef(id=ts.id, name=ts.name, universes=ts.universes,
                        entity_types=ts.entity_types, order=ts.order, limit=ts.limit)
            for ts in tss
        ]

    @strawberry.field
    def sfxs(self, info: strawberry.Info) -> list[SfxRef]:
        # Prefer DB-persisted SFXs; fall back to in-memory engine
        repo = _em(info).repo
        db_sfxs = repo.get_all_sfxs()
        if db_sfxs:
            return [
                SfxRef(
                    id=s.id, name=s.name, description=s.description,
                    trigger=s.trigger, limit=s.limit,
                    effects=[GqlSfxEffect(polarity=e.polarity, timing=e.timing, type=e.type, action=e.action, target=e.target, result=e.result) for e in s.effects],
                )
                for s in db_sfxs
            ]
        from transversal.services.effects_engine import EffectsEngine
        engine = info.context.get("effects_engine")
        if engine:
            return [
                SfxRef(
                    id=s.id, name=s.name, description=s.description,
                    trigger=s.trigger, limit=s.limit,
                    effects=[GqlSfxEffect(polarity=e.polarity, timing=e.timing, type=e.type, action=e.action, target=e.target, result=e.result) for e in s.effects],
                ) for s in engine.get_all()
            ]
        return []

    @strawberry.field
    def traits_by_universe(self, info: strawberry.Info, universe: str) -> list[TraitRef]:
        traits = _em(info).repo.get_traits_by_universe(universe)
        return [
            TraitRef(
                id=t.id, name=t.name, universes=t.universes,
                traitset_id=t.traitset_id, default_die_type=t.default_die_type,
                default_rating_type=t.default_rating_type,
                possible_sfx_ids=t.possible_sfx_ids,
                default_sfx_ids=t.default_sfx_ids,
                location_restricted=t.location_restricted,
                display_names=[
                    GqlTraitDisplayName(name=dn.name, universe=dn.universe,
                                        ratings=dn.ratings)
                    for dn in t.display_names
                ],
            )
            for t in traits
        ]

    @strawberry.field
    def traitsets_by_universe(self, info: strawberry.Info, universe: str) -> list[TraitSetRef]:
        tss = _em(info).repo.get_traitsets_by_universe(universe)
        return [
            TraitSetRef(id=ts.id, name=ts.name, universes=ts.universes,
                        entity_types=ts.entity_types, order=ts.order, limit=ts.limit)
            for ts in tss
        ]

    @strawberry.field
    def effect_actions(self, info: strawberry.Info) -> list[GqlEffectActionMeta]:
        from transversal.services.effects_registry import EFFECT_ACTION_REGISTRY
        return [
            GqlEffectActionMeta(
                action_id=m.action_id, label=m.label, description=m.description,
                category=m.category, effect_type=m.effect_type, effect_action=m.effect_action,
                valid_timings=m.valid_timings,
                fields=[GqlEffectFieldDef(name=f.name, label=f.label, field_type=f.field_type, required=f.required, default=f.default, options=f.options or []) for f in m.fields],
                implicit_target=m.implicit_target, implicit_result=m.implicit_result, implicit_timing=m.implicit_timing,
            ) for m in EFFECT_ACTION_REGISTRY
        ]

    @strawberry.field
    def incoming_messages(self, info: strawberry.Info, entity_id: strawberry.ID) -> list[Message]:
        """Get messages addressed to this entity (player: only incoming; GM: all)."""
        repo = _em(info).repo
        messages = repo.get_incoming_messages(str(entity_id))
        return [
            _message_to_gql(m, repo) for m in messages
        ]

    @strawberry.field
    def conversation(
        self, info: strawberry.Info, entity_a: strawberry.ID, entity_b: strawberry.ID
    ) -> list[Message]:
        """Get all messages between two entities (GM view)."""
        repo = _em(info).repo
        messages = repo.get_conversation(str(entity_a), str(entity_b))
        return [
            _message_to_gql(m, repo) for m in messages
        ]

    @strawberry.field
    def recent_messages(
        self, info: strawberry.Info,
        since: str = "",
        kind: Optional[MessageKind] = None,
    ) -> list[Message]:
        """Get all messages across all entities (GM activity feed), newest first.

        Optionally filter by kind and/or minimum created_at ISO timestamp."""
        repo = _em(info).repo
        messages = repo.get_recent_messages(since=since, kind=kind.value if kind else "")
        return [_message_to_gql(m, repo) for m in messages]

    @strawberry.field
    def journal(
        self, info: strawberry.Info, entity_id: strawberry.ID
    ) -> list[Message]:
        """Get an entity's personal journal (self-referential entries, GM-visible)."""
        repo = _em(info).repo
        entries = repo.get_journal(str(entity_id))
        return [_message_to_gql(m, repo) for m in entries]

    @strawberry.field
    def relationship(
        self, info: strawberry.Info,
        from_entity_id: strawberry.ID,
        to_entity_id: strawberry.ID,
        type: str = "associate",
    ) -> Optional[Relationship]:
        """Get a directional relationship edge between two entities, or null."""
        repo = _em(info).repo
        edge = repo.get_relationship(str(from_entity_id), str(to_entity_id), type)
        if edge is None:
            return None
        return Relationship(
            id=edge["_key"],
            from_entity_id=str(from_entity_id),
            to_entity_id=str(to_entity_id),
            type=edge.get("type", type),
            description=edge.get("description", ""),
        )

    @strawberry.field
    def message_threads(self, info: strawberry.Info) -> list[str]:
        """Return all distinct tags across all messages (for autocomplete)."""
        return _em(info).repo.get_all_threads()

    @strawberry.field
    def timeline(
        self, info: strawberry.Info,
        entity_id: strawberry.ID = "",
        tags: Optional[list[str]] = None,
    ) -> list[Message]:
        """Return messages in causal (topological) order.

        Filter by entity (sender or recipient) and/or threads.
        Messages ordered by after_ids DAG; floaters by created_at.
        """
        repo = _em(info).repo
        messages = repo.get_timeline(
            entity_id=str(entity_id) if entity_id else "",
            threads=tags,
        )
        return [_message_to_gql(m, repo) for m in messages]

    @strawberry.field
    def related_entities(
        self, info: strawberry.Info,
        entity_id: strawberry.ID,
        query: str = "",
    ) -> list[RelatedEntity]:
        """Get entities connected via relationship edges, filtered by name."""
        repo = _em(info).repo
        results = repo.get_related_entities(str(entity_id), query)
        return [
            RelatedEntity(id=r["id"], name=r["name"], sheet_portrait=r.get("sheet_portrait", ""))
            for r in results
        ]


# ── Mutations ────────────────────────────────────────

@strawberry.type
class Mutation:
    @strawberry.mutation
    def create_entity(self, info: strawberry.Info, input: CreateEntityInput) -> Entity:
        e = _em(info).create(
            name=input.name,
            entity_type=DomainEntityType(input.type.value),
            universe=input.universe,
            location=input.location,
            razmerit=input.razmerit,
        )
        return _entity_to_gql(e)

    @strawberry.mutation
    def add_trait_setting(self, info: strawberry.Info, entity_id: strawberry.ID, input: TraitSettingInput) -> TraitSetting:
        ts_id = f"{entity_id}:{input.trait_id}"
        existing = _em(info).repo.get_traitsetting(ts_id)
        if existing:
            raise ValueError(f"TraitSetting '{ts_id}' already exists")
        ts = DomainTraitSetting(
            id=ts_id,
            entity_id=str(entity_id),
            trait_id=str(input.trait_id),
            traitset_id=str(input.traitset_id),
            dice=input.dice,
            rating_type=input.rating_type,
            polarity=input.polarity,
            statement=input.statement,
            negative=input.negative,
            ego=input.ego,
            sfx_ids=[str(s) for s in input.sfx_ids],
        )
        created = _em(info).add_traitsetting(ts)
        return _ts_to_gql(created)

    @strawberry.mutation
    def step_up_trait(self, info: strawberry.Info, trait_setting_id: strawberry.ID) -> TraitSetting:
        ts = _em(info).repo.get_traitsetting(str(trait_setting_id))
        if ts is None:
            raise ValueError(f"TraitSetting '{trait_setting_id}' not found")
        updated = _em(info).step_up_trait(ts)
        return _ts_to_gql(updated)

    @strawberry.mutation
    def step_down_trait(self, info: strawberry.Info, trait_setting_id: strawberry.ID) -> TraitSetting:
        ts = _em(info).repo.get_traitsetting(str(trait_setting_id))
        if ts is None:
            raise ValueError(f"TraitSetting '{trait_setting_id}' not found")
        updated = _em(info).step_down_trait(ts)
        return _ts_to_gql(updated)

    @strawberry.mutation
    def spend_razmerit(self, info: strawberry.Info, entity_id: strawberry.ID, amount: int, reason: str = "sfx_cost") -> RazmeritResult:
        r = _raz(info).spend(str(entity_id), amount, reason)
        return RazmeritResult(
            from_id=r.from_id, from_balance=r.from_balance,
            to_id=r.to_id, to_balance=r.to_balance,
            amount=r.amount, reason=r.reason,
        )

    @strawberry.mutation
    def earn_razmerit(self, info: strawberry.Info, entity_id: strawberry.ID, amount: int, reason: str = "complication") -> RazmeritResult:
        r = _raz(info).earn(str(entity_id), amount, reason)
        return RazmeritResult(
            from_id=r.from_id, from_balance=r.from_balance,
            to_id=r.to_id, to_balance=r.to_balance,
            amount=r.amount, reason=r.reason,
        )

    @strawberry.mutation
    def transfer_razmerit(self, info: strawberry.Info, from_id: strawberry.ID, to_id: strawberry.ID, amount: int, reason: str = "transfer") -> RazmeritResult:
        r = _raz(info).transfer(str(from_id), str(to_id), amount, reason)
        return RazmeritResult(
            from_id=r.from_id, from_balance=r.from_balance,
            to_id=r.to_id, to_balance=r.to_balance,
            amount=r.amount, reason=r.reason,
        )

    @strawberry.mutation
    def add_projection(self, info: strawberry.Info, entity_id: strawberry.ID, universe: str, type: TransversalTypeEnum = TransversalTypeEnum.CONSCIOUSNESS) -> Entity:
        e = _em(info).get(str(entity_id))
        updated = _em(info).add_projection(e, universe, type)
        return _entity_to_gql(updated)

    @strawberry.mutation
    def update_entity(self, info: strawberry.Info, input: UpdateEntityInput) -> Entity:
        e = _em(info).get(str(input.id))
        if input.name is not None:
            e.name = input.name
        if input.razmerit is not None:
            e.razmerit = input.razmerit
        if input.current_universe is not None:
            e.current_universe = input.current_universe
        if input.current_location is not None:
            e.current_location = input.current_location
        if input.hidden is not None:
            e.hidden = input.hidden
        if input.known_to is not None:
            e.known_to = input.known_to
        if input.background_image is not None:
            e.background_image = input.background_image
        if input.owned_by is not None:
            e.owned_by = input.owned_by
        if input.overlay is not None:
            e.overlay = input.overlay if input.overlay != "" else None
        if input.nav_positions is not None:
            e.nav_positions = json.loads(input.nav_positions)
        if input.lora_config is not None:
            e.lora_config = json.loads(input.lora_config) if input.lora_config else None
        updated = _em(info).update(e)
        return _entity_to_gql(updated)

    @strawberry.mutation
    def delete_entity(self, info: strawberry.Info, id: strawberry.ID, rmtree: bool = False) -> bool:
        return _em(info).delete(str(id), rmtree=rmtree)

    @strawberry.mutation
    def remove_trait_setting(self, info: strawberry.Info, id: strawberry.ID) -> bool:
        return _em(info).repo.delete_traitsetting(str(id))

    @strawberry.mutation
    def update_trait_setting(self, info: strawberry.Info, id: strawberry.ID, input: TraitSettingUpdateInput) -> TraitSetting:
        ts = _em(info).repo.get_traitsetting(str(id))
        if ts is None:
            raise ValueError(f"TraitSetting '{id}' not found")
        if input.dice is not None:
            ts.dice = input.dice
        if input.rating_type is not None:
            ts.rating_type = input.rating_type
        if input.polarity is not None:
            ts.polarity = input.polarity
        if input.statement is not None:
            ts.statement = input.statement
        if input.negative is not None:
            ts.negative = input.negative
        if input.ego is not None:
            ts.ego = input.ego
        if input.sfx_ids is not None:
            ts.sfx_ids = [str(s) for s in input.sfx_ids]
        if input.known_to is not None:
            ts.known_to = [str(k) for k in input.known_to]
        updated = _em(info).update_traitsetting(ts)
        return _ts_to_gql(updated)

    # ── Traitset CRUD ────────────────────────────────────

    @strawberry.mutation
    def create_traitset(self, info: strawberry.Info, id: str, name: str, universes: list[str],
                        entity_types: Optional[list[EntityType]] = None, description: str = "",
                        order: int = 0, limit: int = 1) -> TraitSetRef:
        from transversal.domain import TraitSet as DomainTraitSet
        ts = DomainTraitSet(id=id, name=name, universes=universes,
                            entity_types=entity_types or [], description=description,
                            order=order, limit=limit)
        created = _em(info).repo.create_traitset(ts)
        return TraitSetRef(id=created.id, name=created.name, universes=created.universes,
                           entity_types=created.entity_types, order=created.order, limit=created.limit)

    @strawberry.mutation
    def update_traitset(self, info: strawberry.Info, id: strawberry.ID, name: Optional[str] = None,
                        universes: Optional[list[str]] = None, entity_types: Optional[list[EntityType]] = None,
                        description: Optional[str] = None, order: Optional[int] = None,
                        limit: Optional[int] = None) -> TraitSetRef:
        existing = _em(info).repo.get_traitset_by_id(str(id))
        if not existing: raise ValueError(f"TraitSet '{id}' not found")
        if name is not None: existing.name = name
        if universes is not None: existing.universes = universes
        if entity_types is not None: existing.entity_types = entity_types
        if description is not None: existing.description = description
        if order is not None: existing.order = order
        if limit is not None: existing.limit = limit
        updated = _em(info).repo.update_traitset(existing)
        return TraitSetRef(id=updated.id, name=updated.name, universes=updated.universes,
                           entity_types=updated.entity_types, order=updated.order, limit=updated.limit)

    @strawberry.mutation
    def delete_traitset(self, info: strawberry.Info, id: strawberry.ID) -> str:
        result = _em(info).repo.delete_traitset(str(id))
        return f"Deleted traitset and {result['traits_removed']} traits, {result['settings_removed']} settings"

    @strawberry.mutation
    def reorder_traitsets(self, info: strawberry.Info, ids: list[strawberry.ID]) -> bool:
        _em(info).repo.reorder_traitsets([str(i) for i in ids])
        return True

    # ── Trait CRUD ────────────────────────────────────────

    @strawberry.mutation
    def create_trait(self, info: strawberry.Info, input: TraitInput) -> TraitRef:
        from transversal.domain import Trait as DomainTrait
        t = DomainTrait(
            id=input.id, name=input.name, universes=input.universes,
            traitset_id=str(input.traitset_id),
            default_die_type=input.default_die_type,
            default_rating_type=input.default_rating_type,
            possible_sfx_ids=[str(s) for s in input.possible_sfx_ids],
            default_sfx_ids=[str(s) for s in input.default_sfx_ids],
            location_restricted=input.location_restricted,
            display_names=[
                DomainTraitDisplayName(name=dn.name, universe=dn.universe,
                                       ratings=dn.ratings)
                for dn in input.display_names
            ],
        )
        created = _em(info).repo.create_trait(t)
        return TraitRef(
            id=created.id, name=created.name, universes=created.universes,
            traitset_id=created.traitset_id,
            default_die_type=created.default_die_type,
            default_rating_type=created.default_rating_type,
            possible_sfx_ids=created.possible_sfx_ids,
            default_sfx_ids=created.default_sfx_ids,
            location_restricted=created.location_restricted,
            display_names=[
                GqlTraitDisplayName(name=dn.name, universe=dn.universe,
                                    ratings=dn.ratings)
                for dn in created.display_names
            ],
        )

    @strawberry.mutation
    def update_trait(self, info: strawberry.Info, id: strawberry.ID, input: TraitUpdateInput) -> TraitRef:
        existing = _em(info).repo.get_trait(str(id))
        if not existing:
            raise ValueError(f"Trait '{id}' not found")
        if input.name is not None:
            existing.name = input.name
        if input.universes is not None:
            existing.universes = input.universes
        if input.traitset_id is not None:
            existing.traitset_id = str(input.traitset_id)
        if input.default_die_type is not None:
            existing.default_die_type = input.default_die_type
        if input.default_rating_type is not None:
            existing.default_rating_type = input.default_rating_type
        if input.possible_sfx_ids is not None:
            existing.possible_sfx_ids = [str(s) for s in input.possible_sfx_ids]
        if input.default_sfx_ids is not None:
            existing.default_sfx_ids = [str(s) for s in input.default_sfx_ids]
        if input.location_restricted is not None:
            existing.location_restricted = input.location_restricted
        if input.display_names is not None:
            existing.display_names = [
                DomainTraitDisplayName(name=dn.name, universe=dn.universe,
                                       ratings=dn.ratings)
                for dn in input.display_names
            ]
        updated = _em(info).repo.update_trait(existing)
        return TraitRef(
            id=updated.id, name=updated.name, universes=updated.universes,
            traitset_id=updated.traitset_id,
            default_die_type=updated.default_die_type,
            default_rating_type=updated.default_rating_type,
            possible_sfx_ids=updated.possible_sfx_ids,
            default_sfx_ids=updated.default_sfx_ids,
            location_restricted=updated.location_restricted,
            display_names=[
                GqlTraitDisplayName(name=dn.name, universe=dn.universe,
                                    ratings=dn.ratings)
                for dn in updated.display_names
            ],
        )

    @strawberry.mutation
    def delete_trait(self, info: strawberry.Info, id: strawberry.ID) -> bool:
        return _em(info).repo.delete_trait(str(id))

    # ── SFX CRUD ──────────────────────────────────────────

    @strawberry.mutation
    def create_sfx(self, info: strawberry.Info, input: SfxInput) -> SfxRef:
        from transversal.domain import SFX as DomainSFX, SfxEffect as DomainSfxEffect
        s = DomainSFX(
            id=input.id, name=input.name, description=input.description,
            trigger=input.trigger, limit=input.limit,
            effects=[
                DomainSfxEffect(
                    polarity=e.polarity, timing=e.timing,
                    type=e.type, action=e.action,
                    target=e.target, result=e.result,
                )
                for e in input.effects
            ],
        )
        created = _em(info).repo.create_sfx(s)
        # Also register with the in-memory engine
        engine = info.context.get("effects_engine")
        if engine:
            engine.register(created)
        return SfxRef(
            id=created.id, name=created.name, description=created.description,
            trigger=created.trigger, limit=created.limit,
            effects=[GqlSfxEffect(polarity=e.polarity, timing=e.timing, type=e.type, action=e.action, target=e.target, result=e.result) for e in created.effects],
        )

    @strawberry.mutation
    def update_sfx(self, info: strawberry.Info, input: SfxUpdateInput) -> SfxRef:
        from transversal.domain import SfxEffect as DomainSfxEffect
        existing = _em(info).repo.get_sfx(str(input.id))
        if not existing:
            raise ValueError(f"SFX '{input.id}' not found")
        if input.name is not None:
            existing.name = input.name
        if input.description is not None:
            existing.description = input.description
        if input.limit is not None:
            existing.limit = input.limit
        if input.trigger is not None:
            existing.trigger = input.trigger
        if input.effects is not None:
            existing.effects = [
                DomainSfxEffect(
                    polarity=e.polarity, timing=e.timing,
                    type=e.type, action=e.action,
                    target=e.target, result=e.result,
                )
                for e in input.effects
            ]
        updated = _em(info).repo.update_sfx(existing)
        # Also update in-memory engine
        engine = info.context.get("effects_engine")
        if engine:
            engine.register(updated)
        return SfxRef(
            id=updated.id, name=updated.name, description=updated.description,
            trigger=updated.trigger, limit=updated.limit,
            effects=[GqlSfxEffect(polarity=e.polarity, timing=e.timing, type=e.type, action=e.action, target=e.target, result=e.result) for e in updated.effects],
        )

    @strawberry.mutation
    def delete_sfx(self, info: strawberry.Info, id: strawberry.ID) -> bool:
        return _em(info).repo.delete_sfx(str(id))

    @strawberry.mutation
    def send_message(self, info: strawberry.Info, input: SendMessageInput) -> Message:
        """Send a persistent message from one entity to another.

        Publishes a ``message_received`` SSE event to all active sessions.
        """
        from transversal.api.sse.bus import StreamEvent, event_bus
        from transversal.services.session_manager import session_manager

        repo = _em(info).repo
        msg = repo.send_message(
            str(input.sender_entity_id),
            str(input.recipient_entity_id),
            body=input.body,
            kind=input.kind.value if input.kind else "letter",
            title=input.title,
            images=list(input.images or []),
            after_ids=[str(a) for a in (input.after_ids or [])],
            threads=list(input.threads or []),
        )

        gql_msg = _message_to_gql(msg, repo)
        for s in session_manager.list_active():
            event_bus.publish(StreamEvent(
                event="message_received",
                session_id=s.id,
                data={
                    "id": msg.id,
                    "sender_entity_id": msg.sender_entity_id,
                    "recipient_entity_id": msg.recipient_entity_id,
                    "kind": msg.kind.value if hasattr(msg.kind, 'value') else msg.kind,
                    "title": msg.title,
                    "body": msg.body,
                    "images": msg.images,
                    "after_ids": msg.after_ids,
                    "threads": msg.threads,
                    "created_at": msg.created_at,
                    "relationship_description": gql_msg.relationship_description,
                },
            ))

        return gql_msg

    @strawberry.mutation
    def add_journal_entry(self, info: strawberry.Info, input: JournalEntryInput) -> Message:
        """Add a personal journal entry for an entity.

        Journal entries are self-referential (character writes to themself)
        and visible to the GM. No recipient parameter needed.
        """
        from transversal.api.sse.bus import StreamEvent, event_bus
        from transversal.services.session_manager import session_manager

        repo = _em(info).repo
        msg = repo.send_message(
            str(input.entity_id),
            str(input.entity_id),
            body=input.body,
            kind="journal",
            title=input.title,
            images=list(input.images or []),
            after_ids=[str(a) for a in (input.after_ids or [])],
            threads=list(input.threads or []),
        )

        gql_msg = _message_to_gql(msg, repo)
        for s in session_manager.list_active():
            event_bus.publish(StreamEvent(
                event="message_received",
                session_id=s.id,
                data={
                    "id": msg.id,
                    "sender_entity_id": msg.sender_entity_id,
                    "recipient_entity_id": msg.recipient_entity_id,
                    "kind": "journal",
                    "title": msg.title,
                    "body": msg.body,
                    "images": msg.images,
                    "after_ids": msg.after_ids,
                    "threads": msg.threads,
                    "created_at": msg.created_at,
                    "relationship_description": "",
                },
            ))

        return gql_msg

    @strawberry.mutation
    def create_relationship(self, info: strawberry.Info, input: CreateRelationshipInput) -> Relationship:
        """Create (or update) a directional relationship edge between two entities."""
        repo = _em(info).repo
        # Upsert: delete first if exists, then create fresh
        repo.delete_relationship(str(input.from_entity_id), str(input.to_entity_id), input.type)
        repo.create_relationship(
            str(input.from_entity_id), str(input.to_entity_id),
            input.type, description=input.description,
        )
        return Relationship(
            id="",
            from_entity_id=str(input.from_entity_id),
            to_entity_id=str(input.to_entity_id),
            type=input.type,
            description=input.description,
        )

    @strawberry.mutation
    def delete_relationship(self, info: strawberry.Info, input: DeleteRelationshipInput) -> bool:
        """Delete a directional relationship edge between two entities."""
        repo = _em(info).repo
        return repo.delete_relationship(
            str(input.from_entity_id), str(input.to_entity_id), input.type,
        )

    @strawberry.mutation
    def update_message(self, info: strawberry.Info, input: UpdateMessageInput) -> bool:
        """Update after_ids and/or threads on an existing message."""
        repo = _em(info).repo
        return repo.update_message(
            str(input.id),
            after_ids=[str(a) for a in input.after_ids] if input.after_ids is not None else None,
            threads=input.threads,
        )


schema = strawberry.Schema(query=Query, mutation=Mutation)