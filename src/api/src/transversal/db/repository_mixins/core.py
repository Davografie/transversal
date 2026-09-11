"""Core — split out of src/api/src/transversal/db/repository.py."""

import time

from transversal.domain import CharacterView
from typing import Optional


class RepositoryCore:
    """Mixin contributing 6 member(s) to the repository."""

    _REGISTRY_CACHE_TTL = 30.0  # seconds; out-of-process writes surface within this window

    def _traits_index(self) -> dict[str, dict]:
        now = time.monotonic()
        cache = getattr(self, "_traits_index_cache", {})
        at = getattr(self, "_traits_index_at", 0.0)
        if not cache or now - at > self._REGISTRY_CACHE_TTL:
            store = self._traits
            docs = store.all() if hasattr(store, "all") else store.values()
            cache = {d["_key"]: d for d in docs}
            self._traits_index_cache = cache
            self._traits_index_at = now
        return cache

    def _traitsets_index(self) -> dict[str, dict]:
        now = time.monotonic()
        cache = getattr(self, "_traitsets_index_cache", {})
        at = getattr(self, "_traitsets_index_at", 0.0)
        if not cache or now - at > self._REGISTRY_CACHE_TTL:
            store = self._traitsets
            docs = store.all() if hasattr(store, "all") else store.values()
            cache = {d["_key"]: d for d in docs}
            self._traitsets_index_cache = cache
            self._traitsets_index_at = now
        return cache

    def _invalidate_traits_index(self) -> None:
        self._traits_index_cache = {}
        self._traits_index_at = 0.0

    def _invalidate_traitsets_index(self) -> None:
        self._traitsets_index_cache = {}
        self._traitsets_index_at = 0.0

    def assemble_character(self, entity_id: str) -> Optional[CharacterView]:
        entity = self.get_entity(entity_id)
        if entity is None:
            return None

        projections = self.get_projections_for_entity(entity_id)
        # All trait settings (morph + ego)
        all_settings = self.get_traitsettings_for_entity(entity_id)

        return CharacterView(
            entity=entity,
            projections=projections,
            trait_settings=all_settings,
        )
