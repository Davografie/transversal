"""Mutations lifepath — split out of src/api/src/transversal/api/graphql/schema.py."""

import strawberry

from transversal.api.graphql.types import RollTable
from transversal.api.graphql.types import RollTableInput
from typing import Optional
from transversal.api.graphql.type_defs.conditions import (
    ConditionInput as GqlConditionInput,
)
from transversal.api.graphql.type_defs.lifepath import (
    LifePathStepInput as GqlStepInput,
)
from transversal.api.graphql.resolvers.converters import (
    _em,
    _life_path_step_input_to_domain,
    _roll_table_input_to_domain,
    _roll_table_to_gql,
)


@strawberry.type
class MutationsLifepath:
    """Mixin contributing 6 field(s) to the root type."""

    @strawberry.mutation
    def save_life_path(self, info: strawberry.Info, id: str, name: str, universe: str,
                       description: str,
                       entry_table_id: str = "",
                       entry_step: Optional[str] = None,
                       steps: Optional[list[GqlStepInput]] = None,
                       discovery: Optional[strawberry.scalars.JSON] = None,
                       conditions: Optional[list[GqlConditionInput]] = None) -> strawberry.scalars.JSON:
        """Create or update a life path definition. For GM content authoring.

        ``conditions`` is the **walkability** gate ([[B194]]) — may a character
        walk this path now? It is not ``discovery``, which is the one-time reveal
        that the path exists.

        ``None`` means **leave the stored gate alone** and an explicit empty list
        means **clear it**. That is the convention every other update mutation here
        uses, and it matters more for a gate than for a label: a caller editing
        only the name would otherwise wipe it. Note this differs from ``discovery``
        above, which is rebuilt from the argument every time — that is pre-existing
        behaviour and is left alone.

        ``steps`` and ``entry_step`` follow the **same** leave-alone convention,
        and here it is load-bearing rather than tidy: the wrapper is the whole
        graph of the path, so a caller that saved only a name and rebuilt the
        document would silently unwrap every table the path declares. ``None``
        keeps what is stored; a list replaces it.
        """
        from transversal.api.graphql.resolvers.converters import _condition_input_to_domain
        from transversal.domain import DiscoveryBlock, LifePath

        d = None
        if discovery:
            d = DiscoveryBlock(
                at_location=discovery.get("atLocation", []) or [],
                knows_entity=discovery.get("knowsEntity", []) or [],
                possesses_trait=discovery.get("possessesTrait", []) or [],
                has_trait_rating=discovery.get("hasTraitRating"),
                has_relationship=discovery.get("hasRelationship", []) or [],
            )

        import uuid
        if not id:
            id = f"lp-{uuid.uuid4().hex[:8]}"
        repo = info.context["entity_manager"].repo
        existing = repo.get_lifepath(id)
        if conditions is None:
            gate = list(getattr(existing, "conditions", None) or []) if existing else []
        else:
            gate = [_condition_input_to_domain(c) for c in conditions]
        if steps is None:
            wrapped = list(getattr(existing, "steps", None) or []) if existing else []
        else:
            wrapped = [_life_path_step_input_to_domain(st) for st in steps]
        if entry_step is None:
            entry = (getattr(existing, "entry_step", "") or "") if existing else ""
        else:
            entry = entry_step
        lp = LifePath(
            id=id, name=name, universe=universe, description=description,
            entry_table_id=entry_table_id, entry_step=entry, steps=wrapped,
            discovery=d, conditions=gate,
        )

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

    @strawberry.mutation
    def save_roll_table(self, info: strawberry.Info, input: RollTableInput) -> RollTable:
        """Create or update a roll table. Empty ``id`` generates a new key.

        Refuses a table that contradicts itself — a row assigning a name the table
        never **reserved**, or an assignment resolving a different type than the
        reservation states ([[B285]]). The check is here rather than in the editor
        because this is the write boundary every caller shares, and a reservation
        nobody enforces is decoration.
        """
        import uuid

        from transversal.services.roll_table import roll_table_problems

        repo = _em(info).repo
        table = _roll_table_input_to_domain(input)
        problems = roll_table_problems(table)
        if problems:
            raise ValueError("Roll table is inconsistent: " + "; ".join(problems))
        if not table.id:
            table.id = f"rt-{uuid.uuid4().hex[:8]}"

        existing = repo.get_roll_table(table.id)
        if existing is None:
            saved = repo.create_roll_table(table)
        else:
            # Preserve canvas layout positions — they are managed by
            # set_roll_table_position, not by full-table saves.
            table.canvas_x = existing.canvas_x
            table.canvas_y = existing.canvas_y
            saved = repo.update_roll_table(table)
        return _roll_table_to_gql(saved)

    @strawberry.mutation
    def delete_roll_table(self, info: strawberry.Info, id: strawberry.ID) -> bool:
        return _em(info).repo.delete_roll_table(str(id))

    @strawberry.mutation
    def set_roll_table_position(self, info: strawberry.Info, id: strawberry.ID, x: Optional[float] = None, y: Optional[float] = None) -> Optional[RollTable]:
        """Persist a roll table's canvas position (x/y null clears it)."""
        t = _em(info).repo.set_roll_table_position(str(id), x, y)
        return _roll_table_to_gql(t) if t else None

    @strawberry.mutation
    def clear_roll_table_positions(self, info: strawberry.Info, life_path_id: strawberry.ID) -> int:
        """Clear all saved canvas positions for a life path's roll tables."""
        return _em(info).repo.clear_roll_table_positions(str(life_path_id))
