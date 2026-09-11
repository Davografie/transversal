"""Strawberry GraphQL schema — composition root.

Resolver implementations live in :mod:`transversal.api.graphql.resolvers`; this
module assembles them into the ``Query`` / ``Mutation`` root types and the
schema object.

Each root type is a ``@strawberry.type`` subclass of one mixin per domain
(players, entities, traits, SFX, targeting, messaging, life-path).  Strawberry
collects fields from the bases, so the resulting schema is identical to the
single-class version it replaced.
"""

import strawberry

from transversal.api.graphql.extensions import ResolverTimingExtension
from transversal.api.graphql.resolvers.converters import (  # noqa: F401
    _OPTION_SOURCES,
    _action_meta_for,
    _check_input_to_domain,
    _condition_input_to_domain,
    _condition_to_gql,
    _consequence_option_input_to_domain,
    _consequence_option_to_gql,
    _duration_input_to_domain,
    _duration_to_gql,
    _effect_input_to_domain,
    _effect_to_gql,
    _effects_result_to_gql,
    _em,
    _entry_input_to_domain,
    _entry_to_gql,
    _entity_to_gql,
    _field_options,
    _gql_field_def,
    _historical_record_to_gql,
    _life_path_to_gql,
    _maybe_rearm_passives,
    _message_to_gql,
    _player_to_gql,
    _raz,
    _refs_from_input,
    _refs_to_gql,
    _resolve_continuation_effects,
    _resolve_relationship_endpoint,
    _roll_table_input_to_domain,
    _roll_table_to_gql,
    _scheduled_event_to_gql,
    _sfx_ref,
    _structured_choice_to_dict,
    _target_spec_from_input,
    _target_spec_input_to_domain,
    _trait_to_gql,
    _ts_to_gql,
    _universe_options,
)
from transversal.api.graphql.resolvers.mutations_effects import MutationsEffects
from transversal.api.graphql.resolvers.mutations_entities import MutationsEntities
from transversal.api.graphql.resolvers.mutations_lifepath import MutationsLifepath
from transversal.api.graphql.resolvers.mutations_messaging import MutationsMessaging
from transversal.api.graphql.resolvers.mutations_players import MutationsPlayers
from transversal.api.graphql.resolvers.mutations_sfx import MutationsSfx
from transversal.api.graphql.resolvers.mutations_traitcatalog import MutationsTraitCatalog
from transversal.api.graphql.resolvers.mutations_traitsettings import MutationsTraitSettings
from transversal.api.graphql.resolvers.queries_entities import QueriesEntities
from transversal.api.graphql.resolvers.queries_lifepath import QueriesLifepath
from transversal.api.graphql.resolvers.queries_messaging import QueriesMessaging
from transversal.api.graphql.resolvers.queries_players import QueriesPlayers
from transversal.api.graphql.resolvers.queries_sfx import QueriesSfx
from transversal.api.graphql.resolvers.queries_targeting import QueriesTargeting
from transversal.api.graphql.resolvers.queries_traits import QueriesTraits


@strawberry.type
class Query(
    QueriesPlayers,
    QueriesEntities,
    QueriesTraits,
    QueriesSfx,
    QueriesTargeting,
    QueriesMessaging,
    QueriesLifepath,
):
    """The query root type; its fields come from the mixins above."""


@strawberry.type
class Mutation(
    MutationsPlayers,
    MutationsEntities,
    MutationsTraitSettings,
    MutationsTraitCatalog,
    MutationsSfx,
    MutationsEffects,
    MutationsMessaging,
    MutationsLifepath,
):
    """The mutation root type; its fields come from the mixins above."""


schema = strawberry.Schema(query=Query, mutation=Mutation, extensions=[ResolverTimingExtension])
