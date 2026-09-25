"""Per-request DataLoaders for the entity-list hot path.

Batch the per-entity resolvers (projections, trait settings, trait-set settings,
relationship trait settings) into single ``FILTER … IN @ids`` AQL queries, so the
entity-list query drops from ~3,995 AQL round-trips to a handful.

Built per-request in ``get_context`` (see ``main.py``), so batching is
request-scoped: there is no cross-request cache and therefore no invalidation
hazard.
"""

from __future__ import annotations

from dataclasses import dataclass

from strawberry.dataloader import DataLoader

from transversal.services.entity_manager import EntityManager


def _ordered(keys: list[str], grouped: dict[str, list]) -> list[list]:
    """Map DataLoader keys back to grouped results in the loader's key order."""
    return [grouped.get(k, []) for k in keys]


@dataclass
class Loaders:
    projections: DataLoader
    traitsettings: DataLoader
    traitsetsettings: DataLoader
    sub_traitsettings: DataLoader
    relationship_traitsettings: DataLoader
    images: DataLoader


def build_loaders(em: EntityManager) -> Loaders:
    repo = em.repo

    async def load_projections(keys: list[str]) -> list[list]:
        return _ordered(keys, repo.get_projections_for_entities(keys))

    async def load_traitsettings(keys: list[str]) -> list[list]:
        return _ordered(keys, repo.get_traitsettings_for_entities(keys))

    async def load_traitsetsettings(keys: list[str]) -> list[list]:
        return _ordered(keys, repo.get_traitsetsettings_for_entities(keys))

    async def load_sub_traitsettings(keys: list[str]) -> list[list]:
        return _ordered(keys, repo.get_sub_traitsettings_for_parents(keys))

    async def load_relationship_traitsettings(keys: list[str]) -> list[list]:
        return _ordered(keys, repo.get_relationship_traitsettings_for_entities(keys))

    # Keyed by **owner** (an entity or a trait), not by the asking object: a trait
    # setting and its registry trait share one owner, and so do the several
    # settings a sheet holds of one trait (`portents`, the statement traits), so
    # the batch collapses those as well as the round trips.
    async def load_images(keys: list[str]) -> list[list]:
        return _ordered(keys, repo.get_images_for_owners(keys))

    return Loaders(
        projections=DataLoader(load_fn=load_projections),
        traitsettings=DataLoader(load_fn=load_traitsettings),
        traitsetsettings=DataLoader(load_fn=load_traitsetsettings),
        sub_traitsettings=DataLoader(load_fn=load_sub_traitsettings),
        relationship_traitsettings=DataLoader(load_fn=load_relationship_traitsettings),
        images=DataLoader(load_fn=load_images),
    )
