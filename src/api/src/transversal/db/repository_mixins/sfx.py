"""Sfx — split out of src/api/src/transversal/db/repository.py."""

from __future__ import annotations

from transversal.db.arango import ENTITIES
from transversal.db.arango import PROJECTIONS
from transversal.db.arango import SFXS
from transversal.db.arango import SFX_OWNERS
from transversal.db.arango import TRAITS
from transversal.db.arango import TRAITSETSETTINGS
from transversal.db.arango import TRAITSETTINGS
from transversal.domain import SFX
from transversal.domain import SfxOwner
from typing import Optional


class RepositorySfx:
    """Mixin contributing 10 member(s) to the repository."""

    def create_sfx(self, sfx: SFX) -> SFX:
        doc = sfx.model_dump()
        doc["_key"] = sfx.id
        self._sfxs.insert(doc)
        return sfx

    def get_sfx(self, sfx_id: str) -> Optional[SFX]:
        doc = self._sfxs.get(sfx_id)
        return SFX.model_validate({**doc, "id": doc["_key"]}) if doc else None

    def get_all_sfxs(self) -> list[SFX]:
        query = f"FOR s IN {SFXS} RETURN s"
        return [
            SFX.model_validate({**doc, "id": doc["_key"]})
            for doc in self.db.aql.execute(query)
        ]

    def update_sfx(self, sfx: SFX) -> SFX:
        doc = sfx.model_dump()
        doc["_key"] = sfx.id
        self._sfxs.replace(doc)
        return sfx

    def delete_sfx(self, sfx_id: str) -> bool:
        """Delete an SFX registry entry and strip its id from every owner.

        SFX ids are soft references held by owner surfaces — the ``table``/``gm``
        buckets, direct entity/projection ownership, trait-instance and
        trait-set-as-unit grants, and trait ``default_sfx_ids`` /
        ``possible_sfx_ids``. Remove the id everywhere so no surface keeps a
        dangling reference to the deleted SFX.
        """
        # Owner buckets.
        self.db.aql.execute(
            f"""
            FOR o IN {SFX_OWNERS}
            FILTER @sid IN o.sfx_ids
            UPDATE o WITH {{ sfx_ids: REMOVE_VALUE(o.sfx_ids, @sid) }} IN {SFX_OWNERS}
            """,
            bind_vars={"sid": sfx_id},
        )
        # Direct entity / projection ownership.
        self.db.aql.execute(
            f"""
            FOR e IN {ENTITIES}
            FILTER @sid IN e.sfx_ids
            UPDATE e WITH {{ sfx_ids: REMOVE_VALUE(e.sfx_ids, @sid) }} IN {ENTITIES}
            """,
            bind_vars={"sid": sfx_id},
        )
        self.db.aql.execute(
            f"""
            FOR p IN {PROJECTIONS}
            FILTER @sid IN p.sfx_ids
            UPDATE p WITH {{ sfx_ids: REMOVE_VALUE(p.sfx_ids, @sid) }} IN {PROJECTIONS}
            """,
            bind_vars={"sid": sfx_id},
        )
        # Trait-instance and trait-set-as-unit grants.
        self.db.aql.execute(
            f"""
            FOR ts IN {TRAITSETTINGS}
            FILTER @sid IN ts.sfx_ids
            UPDATE ts WITH {{ sfx_ids: REMOVE_VALUE(ts.sfx_ids, @sid) }} IN {TRAITSETTINGS}
            """,
            bind_vars={"sid": sfx_id},
        )
        self.db.aql.execute(
            f"""
            FOR tss IN {TRAITSETSETTINGS}
            FILTER @sid IN tss.sfx_ids
            UPDATE tss WITH {{ sfx_ids: REMOVE_VALUE(tss.sfx_ids, @sid) }} IN {TRAITSETSETTINGS}
            """,
            bind_vars={"sid": sfx_id},
        )
        # Trait registry nominations and provisioning defaults.
        self.db.aql.execute(
            f"""
            FOR t IN {TRAITS}
            FILTER @sid IN t.default_sfx_ids OR @sid IN t.possible_sfx_ids
            UPDATE t WITH {{
                default_sfx_ids: REMOVE_VALUE(t.default_sfx_ids, @sid),
                possible_sfx_ids: REMOVE_VALUE(t.possible_sfx_ids, @sid),
            }} IN {TRAITS}
            """,
            bind_vars={"sid": sfx_id},
        )
        try:
            self._sfxs.delete(sfx_id)
            return True
        except Exception:
            return False

    def get_sfx_owner(self, owner_id: str) -> Optional[SfxOwner]:
        doc = self._sfx_owners.get(owner_id)
        return SfxOwner.model_validate({**doc, "id": doc["_key"]}) if doc else None

    def create_sfx_owner(self, owner: SfxOwner) -> SfxOwner:
        doc = owner.model_dump()
        doc["_key"] = owner.id
        self._sfx_owners.insert(doc)
        return owner

    def update_sfx_owner(self, owner: SfxOwner) -> SfxOwner:
        doc = owner.model_dump()
        doc["_key"] = owner.id
        self._sfx_owners.replace(doc)
        return owner

    def delete_sfx_owner(self, owner_id: str) -> bool:
        try:
            self._sfx_owners.delete(owner_id)
            return True
        except Exception:
            return False

    def list_sfx_owners(self) -> list[SfxOwner]:
        """Return every SFX owner bucket (``table``, ``gm``)."""
        return [
            SfxOwner.model_validate({**doc, "id": doc["_key"]})
            for doc in self._sfx_owners.all()
        ]
