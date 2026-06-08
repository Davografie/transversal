"""Strawberry GraphQL schema — queries and mutations."""

import json
import strawberry
from typing import Optional

from transversal.api.graphql.types import (
    CharacterView,
    CreateEntityInput,
    Entity,
    EntityType,
    Projection,
    RazmeritResult,
    TraitRef,
    TraitSetRef,
    TraitSetting,
    TraitSettingInput,
    TraitSettingUpdateInput,
    TransversalTypeEnum,
    UpdateEntityInput,
    Zone,
)
from transversal.domain import Entity as DomainEntity
from transversal.domain import EntityType as DomainEntityType
from transversal.domain import TraitSetting as DomainTraitSetting
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
        background_image=e.background_image, overlay=e.overlay,
        zones=[Zone(name=z.name, background_image=z.background_image, x=z.x, y=z.y) for z in e.zones],
        map_x=e.map_x, map_y=e.map_y,
        nav_positions=json.dumps(e.nav_positions) if e.nav_positions else "{}",
        node_ids=e.node_ids, owned_by=e.owned_by,
    )


def _ts_to_gql(s: DomainTraitSetting) -> TraitSetting:
    return TraitSetting(
        id=s.id, entity_id=s.entity_id, trait_id=s.trait_id,
        traitset_id=s.traitset_id,
        rating_type=s.rating_type, dice=s.dice,
        polarity=s.polarity,
        statement=s.statement, negative=s.negative,
        ego=s.ego, sfx_ids=s.sfx_ids,
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
    def traits_by_universe(self, info: strawberry.Info, universe: str) -> list[TraitRef]:
        traits = _em(info).repo.get_traits_by_universe(universe)
        return [
            TraitRef(
                id=t.id, name=t.name, universes=t.universes,
                traitset_id=t.traitset_id, default_die_type=t.default_die_type,
                default_rating_type=t.default_rating_type,
                possible_sfx_ids=t.possible_sfx_ids,
                location_restricted=t.location_restricted,
            )
            for t in traits
        ]

    @strawberry.field
    def traitsets_by_universe(self, info: strawberry.Info, universe: str) -> list[TraitSetRef]:
        tss = _em(info).repo.get_traitsets_by_universe(universe)
        return [
            TraitSetRef(id=ts.id, name=ts.name, universes=ts.universes,
                        entity_types=ts.entity_types)
            for ts in tss
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
        ts = DomainTraitSetting(
            id=f"{entity_id}:{input.trait_id}",
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
        updated = _em(info).update(e)
        return _entity_to_gql(updated)

    @strawberry.mutation
    def delete_entity(self, info: strawberry.Info, id: strawberry.ID) -> bool:
        return _em(info).delete(str(id))

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
        updated = _em(info).update_traitsetting(ts)
        return _ts_to_gql(updated)


schema = strawberry.Schema(query=Query, mutation=Mutation)
