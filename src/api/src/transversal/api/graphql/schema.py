"""Strawberry GraphQL schema — queries and mutations."""

import json
import strawberry
from typing import Optional

from transversal.api.graphql.types import (
    CharacterView,
    CreateEntityInput,
    CreateRelationshipInput,
    DeleteRelationshipInput,
    DieType as GqlDieType,
    EffectActionMeta as GqlEffectActionMeta,
    EffectFieldDef as GqlEffectFieldDef,
    Entity,
    EntityType,
    JournalEntryInput,
    LifePath as GqlLifePath,
    Message,
    MessageKind,
    Projection,
    QualificationResult,
    LearnResult,
    RelatedEntity,
    Relationship,
    RazmeritResult,
    SendMessageInput,
    Effect as GqlEffect,
    SfxInput,
    SfxRef,
    SurviveResult,
    EventResult,
    AdvanceResult,
    TeachResult,
    GiftResult,
    TakeResult,
    TermResult,
    MusterOutResult,
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
        zones=[Zone(name=z.name, background_image=z.background_image, location_id=z.location_id, x=z.x, y=z.y) for z in e.zones],
        map_x=e.map_x, map_y=e.map_y,
        nav_positions=json.dumps(e.nav_positions) if e.nav_positions else "{}",
        node_ids=e.node_ids, owned_by=e.owned_by,
        lora_config=json.dumps(e.lora_config) if e.lora_config else None,
        current_life_path_id=e.current_life_path_id,
        terms_served=e.terms_served,
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
                    effects=[GqlEffect(timing=e.timing, type=e.type, action=e.action, target=e.target, result=e.result, target_scope=e.target_scope) for e in s.effects],
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
                    effects=[GqlEffect(timing=e.timing, type=e.type, action=e.action, target=e.target, result=e.result, target_scope=e.target_scope) for e in s.effects],
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
                requires_choice=m.requires_choice, target_kind=m.target_kind,
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

    @strawberry.field
    def life_paths(self, info: strawberry.Info, universe: Optional[str] = None) -> list[GqlLifePath]:
        """List life paths, optionally filtered by universe."""
        repo = _em(info).repo
        if universe:
            lps = repo.list_lifepaths_by_universe(universe)
        else:
            lps = repo.list_all_lifepaths()
        return [_life_path_to_gql(lp) for lp in lps]


# ── Life path helpers ─────────────────────────────────

def _life_path_to_gql(lp) -> GqlLifePath:
    """Convert a domain LifePath to the GraphQL type."""
    import json, logging
    _log = logging.getLogger("transversal.lifepath")
    disc = lp.discovery
    if disc:
        _log.info("_life_path_to_gql discovery: at_location=%s knows_entity=%s possesses_trait=%s has_trait_rating=%s has_relationship=%s",
                  disc.at_location, disc.knows_entity, disc.possesses_trait,
                  dict(disc.has_trait_rating), disc.has_relationship)
    else:
        _log.info("_life_path_to_gql discovery: None")
    return GqlLifePath(
        id=lp.id,
        name=lp.name,
        universe=lp.universe,
        description=lp.description if hasattr(lp, 'description') else "",
        qualification=lp.qualification,
        discovery=lp.discovery,
        curriculum=lp.curriculum,
        survival=lp.survival,
        events=lp.events,
        advancement=lp.advancement,
        muster_out=lp.muster_out,
    )


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
        from transversal.domain import SFX as DomainSFX, Effect as DomainEffect
        s = DomainSFX(
            id=input.id, name=input.name, description=input.description,
            trigger=input.trigger, limit=input.limit,
            effects=[
                DomainEffect(
                    timing=e.timing,
                    type=e.type, action=e.action,
                    target=e.target, result=e.result,
                    target_scope=e.target_scope,
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
            effects=[GqlEffect(timing=e.timing, type=e.type, action=e.action, target=e.target, result=e.result, target_scope=e.target_scope) for e in created.effects],
        )

    @strawberry.mutation
    def update_sfx(self, info: strawberry.Info, input: SfxUpdateInput) -> SfxRef:
        from transversal.domain import Effect as DomainEffect
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
                DomainEffect(
                    timing=e.timing,
                    type=e.type, action=e.action,
                    target=e.target, result=e.result,
                    target_scope=e.target_scope,
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
            effects=[GqlEffect(timing=e.timing, type=e.type, action=e.action, target=e.target, result=e.result, target_scope=e.target_scope) for e in updated.effects],
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
    def add_relationship_trait(self, info: strawberry.Info, from_entity_id: strawberry.ID,
                               to_entity_id: strawberry.ID, rel_type: str = "relation",
                               trait_id: strawberry.ID = "", die: GqlDieType = GqlDieType.D6) -> TraitSetting:
        """Create a rated trait on a relationship edge."""
        repo = _em(info).repo
        edge_key = f"edge:{from_entity_id}:{to_entity_id}:{rel_type}"
        # Ensure the relationship edge exists
        rel = repo.get_relationship(str(from_entity_id), str(to_entity_id), rel_type)
        if not rel:
            repo.create_relationship(str(from_entity_id), str(to_entity_id), rel_type)

        ts = DomainTraitSetting(
            id=f"{edge_key}:{trait_id}",
            entity_id=edge_key,
            trait_id=str(trait_id),
            traitset_id="ts-relations",
            from_type="relationship",
            dice=[die],
        )
        created = repo.create_traitsetting(ts)
        return _ts_to_gql(created)

    @strawberry.mutation
    def update_message(self, info: strawberry.Info, input: UpdateMessageInput) -> bool:
        """Update after_ids and/or threads on an existing message."""
        repo = _em(info).repo
        return repo.update_message(
            str(input.id),
            after_ids=[str(a) for a in input.after_ids] if input.after_ids is not None else None,
            threads=input.threads,
        )

    @strawberry.mutation
    def take_term(self, info: strawberry.Info, entity_id: strawberry.ID, life_path_id: strawberry.ID,
                  razmerit_spent: int = 0, qual_manual: Optional[int] = None,
                  survive_manual: Optional[int] = None,
                  advance_manual: Optional[int] = None,
                  learn_index: Optional[int] = None,
                  mishap_index: Optional[int] = None) -> TermResult:
        """Execute one term of a life path. Pass manual die results for tabletop dice."""
        from transversal.services.lifepath_executor import take_term

        repo = _em(info).repo
        entity = repo.get_entity(str(entity_id))
        if entity is None:
            raise ValueError(f"Entity '{entity_id}' not found")
        life_path = repo.get_lifepath(str(life_path_id))
        if life_path is None:
            raise ValueError(f"LifePath '{life_path_id}' not found")

        result = take_term(entity, life_path, razmerit_spent, repo,
                          qual_manual=qual_manual,
                          survive_manual=survive_manual,
                          advance_manual=advance_manual,
                          learn_index=learn_index,
                          mishap_index=mishap_index)

        def _ql(r: dict | None):
            if r is None:
                return None
            return QualificationResult(
                success=r["success"], drafted=r["drafted"],
                drafted_path_id=r.get("drafted_path_id"),
                location_blocked=r.get("location_blocked", False),
            )

        def _lr(r: dict | None):
            if r is None:
                return None
            return LearnResult(
                trait_gained_id=r["trait_gained_id"],
                trait_name=r["trait_name"],
                was_stepped_up=r["was_stepped_up"],
            )

        def _sr(r: dict | None):
            if r is None:
                return None
            return SurviveResult(
                success=r["success"], roll_summary=r["roll_summary"],
                mishap_description=r.get("mishap_description"),
                complication_trait_id=strawberry.ID(r["complication_trait_id"]) if r.get("complication_trait_id") else None,
                forced_muster=r.get("forced_muster", False),
            )

        def _er(r: dict | None):
            if r is None:
                return None
            return EventResult(event_index=r["event_index"], description=r["description"])

        def _ar(r: dict | None):
            if r is None:
                return None
            return AdvanceResult(success=r["success"], new_rank=r["new_rank"], rank_name=r["rank_name"])

        return TermResult(
            qualification=_ql(result.get("qualification")),
            learn=_lr(result.get("learn")),
            survive=_sr(result.get("survive")),
            event=_er(result.get("event")),
            advance=_ar(result.get("advance")),
            new_trait_settings=[strawberry.ID(ts_id) for ts_id in result.get("new_trait_settings", [])],
            modified_trait_settings=[strawberry.ID(ts_id) for ts_id in result.get("modified_trait_settings", [])],
            razmerit_change=result.get("razmerit_change", 0),
            term_number=result.get("term_number", 0),
        )

    @strawberry.mutation
    def teach_trait(self, info: strawberry.Info, teacher_id: strawberry.ID, student_id: strawberry.ID,
                    trait_setting_id: strawberry.ID) -> TeachResult:
        from transversal.services.trait_transfer import teach_trait

        repo = _em(info).repo
        result = teach_trait(str(teacher_id), str(student_id), str(trait_setting_id), repo)
        # Spend razmerit from teacher
        _raz(info).spend(str(teacher_id), 1, "teach_trait")
        return TeachResult(
            student_trait_setting_id=result["student_trait_setting"].id,
            razmerit_cost=1,
        )

    @strawberry.mutation
    def gift_trait(self, info: strawberry.Info, giver_id: strawberry.ID, recipient_id: strawberry.ID,
                   trait_setting_id: strawberry.ID) -> GiftResult:
        from transversal.services.trait_transfer import gift_trait

        repo = _em(info).repo
        result = gift_trait(str(giver_id), str(recipient_id), str(trait_setting_id), repo)
        return GiftResult(
            transferred_trait_id=result["transferred_trait"].id,
            relationship_created=result.get("relationship_created") is not None,
        )

    @strawberry.mutation
    def take_trait(self, info: strawberry.Info, taker_id: strawberry.ID, victim_id: strawberry.ID,
                   trait_setting_id: strawberry.ID, method: str = "stealth") -> TakeResult:
        from transversal.services.trait_transfer import take_trait

        repo = _em(info).repo
        result = take_trait(str(taker_id), str(victim_id), str(trait_setting_id), method, repo)
        contest = result.get("contest_result")
        summary = ""
        if contest:
            if hasattr(contest, 'player_result') and hasattr(contest.player_result, 'highest'):
                summary = f"taker {contest.player_result.highest} vs victim {contest.opponent_result.highest} — {'success' if result['success'] else 'failure'}"
            else:
                summary = f"{'success' if result['success'] else 'failure'}"
        return TakeResult(
            success=result["success"],
            contest_summary=summary,
            transferred_trait_id=result["transferred_trait"].id if result.get("transferred_trait") else None,
            stolen=result.get("stolen", False),
        )

    @strawberry.mutation
    def muster_out(self, info: strawberry.Info, entity_id: strawberry.ID) -> MusterOutResult:
        """Voluntarily muster out of the current life path, collecting benefits."""
        from transversal.services.lifepath_executor import muster_out

        repo = _em(info).repo
        entity = repo.get_entity(str(entity_id))
        if entity is None:
            raise ValueError(f"Entity '{entity_id}' not found")

        result = muster_out(entity, repo)
        return MusterOutResult(
            path_id=result["path_id"],
            path_name=result["path_name"],
            terms_served=result["terms_served"],
            final_rank=result["final_rank"],
            mishap_muster=result.get("mishap_muster", False),
            benefits=result.get("benefits", []),
            razmerit_gained=result.get("razmerit_gained", 0),
        )

    @strawberry.mutation
    def save_life_path(self, info: strawberry.Info, id: str, name: str, universe: str,
                       description: str,
                       qualification: Optional[strawberry.scalars.JSON] = None,
                       discovery: Optional[strawberry.scalars.JSON] = None,
                       curriculum: Optional[strawberry.scalars.JSON] = None,
                       survival: Optional[strawberry.scalars.JSON] = None,
                       events: Optional[strawberry.scalars.JSON] = None,
                       advancement: Optional[strawberry.scalars.JSON] = None,
                       muster_out: Optional[strawberry.scalars.JSON] = None) -> strawberry.scalars.JSON:
        """Create or update a life path definition. For GM content authoring."""
        from transversal.domain import (
            LifePath, CurriculumItem, QualificationInfo,
            DiscoveryBlock, SurvivalInfo, EventItem, RankInfo, AdvancementInfo, MusterOutInfo,
            DieType,
        )

        def _die(v): return DieType(v) if v else DieType.D4

        q = None
        if qualification:
            q = QualificationInfo(
                trait_id=qualification.get("traitId", ""),
                difficulty=_die(qualification.get("difficulty")),
                must_be_at_location=qualification.get("mustBeAtLocation"),
                draft=qualification.get("draft"),
            )

        d = None
        if discovery:
            d = DiscoveryBlock(
                at_location=discovery.get("atLocation", []) or [],
                knows_entity=discovery.get("knowsEntity", []) or [],
                possesses_trait=discovery.get("possessesTrait", []) or [],
                has_trait_rating=discovery.get("hasTraitRating"),
                has_relationship=discovery.get("hasRelationship", []) or [],
            )

        ci = []
        if curriculum:
            for c in curriculum:
                ci.append(CurriculumItem(
                    trait_id=c.get("traitId", ""),
                    create_at=_die(c.get("createAt")),
                    step_up=c.get("stepUp", False),
                    min_rank=c.get("minRank", 0),
                ))

        sv = None
        if survival:
            sv = SurvivalInfo(
                trait_ids=survival.get("traitIds", []) or [],
                difficulty=_die(survival.get("difficulty")),
                term_penalty_after=survival.get("termPenaltyAfter"),
                mishaps=survival.get("mishaps", []) or [],
            )

        ev = []
        if events:
            for e in events:
                ev.append(EventItem(
                    description=e.get("description", ""),
                    effect=e.get("effect") or {},
                    min_rank=e.get("minRank", 0),
                ))

        av = None
        if advancement:
            ranks = []
            for r in (advancement.get("ranks") or []):
                ranks.append(RankInfo(
                    number=r.get("number", 0),
                    name=r.get("name", ""),
                    benefits=r.get("benefits") or [],
                ))
            av = AdvancementInfo(
                trait_ids=advancement.get("traitIds", []) or [],
                difficulty=_die(advancement.get("difficulty")),
                ranks=ranks,
            )

        mo = None
        if muster_out:
            mo = MusterOutInfo(
                per_term_benefits=muster_out.get("perTermBenefits") or [],
                at_ranks=muster_out.get("atRanks") or {},
            )

        import logging, uuid
        _log = logging.getLogger("transversal.lifepath")
        _log.info("save_life_path discovery received: %s", d.model_dump() if d else None)
        if not id:
            id = f"lp-{uuid.uuid4().hex[:8]}"
        lp = LifePath(
            id=id, name=name, universe=universe, description=description,
            qualification=q, discovery=d,
            curriculum=ci, survival=sv, events=ev, advancement=av, muster_out=mo,
        )

        repo = info.context["entity_manager"].repo
        existing = repo.get_lifepath(id)
        if existing:
            repo.update_lifepath(lp)
        else:
            repo.create_lifepath(lp)
        return {"ok": True, "id": id}

    @strawberry.mutation
    def delete_life_path(self, info: strawberry.Info, id: strawberry.ID) -> strawberry.scalars.JSON:
        repo = info.context["entity_manager"].repo
        repo.delete_lifepath(str(id))
        return {"ok": True}


schema = strawberry.Schema(query=Query, mutation=Mutation)