"""Where a trait instance hangs — the host a ``TraitSetting`` is anchored to.

A trait *definition* belongs to the registry; its **instances** are
``traitsettings`` rows, and an instance is anchored to one of four things:

- an **entity** (``from_type='entity'``) — the ordinary case;
- a **body** (``'projection'``, ``projection_id``) — one per-universe projection
  of an entity, so the host is reported as *that entity* and the body's universe
  comes along beside it;
- a **relationship edge** (``'relationship'``) — where ``entity_id`` is the
  **edge key**, not an entity: the holder is the edge's ``_from`` side and the
  subject is its ``_to``, which is what makes "what A thinks of B" a host;
- another **instance** (``'traitsetting'``, ``parent_traitsetting_id``) — a
  sub-trait. It has no anchor of its own, so it takes the one at the **root of
  its parent chain** (the same rule ``TraitSetting.ego`` uses, and for the same
  reason: a sub-trait's ``entity_id`` is merely *inherited* from its parent, so
  it cannot answer the question on its own), and it names the super-trait it
  sits under.

Why this exists: every read path in the API walks instances *from* a host
(``entity.traitSettings``, ``relationship.relationTraits``, ``subTraitSettings``),
while the GM cleanup surface asks the other way round — "every instance of this
trait definition, and who owns it" — which is the inverse read
``Repository.get_traitsettings_by_trait`` can do but nothing exposed. The four
descriptions exist in one place so the four host kinds cannot drift apart.
"""

from dataclasses import dataclass

# A sub-trait chain is a nesting, not a graph, and the write path refuses a cycle
# — this is a guard against data that predates that, not an expected depth.
MAX_CHAIN_DEPTH = 16


@dataclass(frozen=True)
class InstanceHost:
    """One instance's host, flattened for display.

    ``kind`` is the setting's own ``from_type`` (so a sub-trait reports
    ``traitsetting`` even though its *entity* comes from the root), and
    ``entity_*`` are the anchor entity in every case — the entity itself, the
    body's owner, the relationship's holder, or the root of a sub-trait chain.
    """

    kind: str = "entity"
    entity_id: str = ""
    entity_name: str = ""
    entity_type: str = ""
    # Set for a body anchor: which universe that body stands in.
    universe: str = ""
    # Set for a relationship anchor: the other party, and the edge's type.
    about_id: str = ""
    about_name: str = ""
    about_type: str = ""
    relationship_type: str = ""
    # Set for a sub-trait anchor: the super-trait it sits under.
    parent_traitsetting_id: str = ""
    parent_trait_id: str = ""
    parent_trait_name: str = ""


def describe_host(repo, setting) -> InstanceHost:
    """Resolve the host of one trait setting. Never raises; missing data is blank."""
    return _describe(repo, setting, depth=0)


def _entity_fields(repo, entity_id: str) -> tuple[str, str]:
    entity = repo.get_entity(entity_id) if entity_id else None
    if entity is None:
        return "", ""
    # `type` is an enum on the domain model and a bare string on the wire.
    return entity.name, (entity.type.value if entity.type else "")


def _describe(repo, setting, depth: int) -> InstanceHost:
    kind = getattr(setting, "from_type", "") or "entity"

    if kind == "projection":
        projection = (
            repo.get_projection(setting.projection_id)
            if getattr(setting, "projection_id", None) else None
        )
        if projection is None:
            # A body that has been deleted leaves its settings behind only if
            # something failed to cascade; report the entity we do know.
            name, etype = _entity_fields(repo, setting.entity_id)
            return InstanceHost(kind=kind, entity_id=setting.entity_id,
                                entity_name=name, entity_type=etype)
        name, etype = _entity_fields(repo, projection.entity_id)
        return InstanceHost(
            kind=kind,
            entity_id=projection.entity_id,
            entity_name=name,
            entity_type=etype,
            universe=projection.universe or "",
        )

    if kind == "relationship":
        edge = repo.get_relationship_by_key(setting.entity_id)
        if edge is None:
            return InstanceHost(kind=kind)
        holder = repo._resolve_relationship_contact(edge.get("_from", "")) or {}
        about = repo._resolve_relationship_contact(edge.get("_to", "")) or {}
        return InstanceHost(
            kind=kind,
            entity_id=holder.get("id", ""),
            entity_name=holder.get("name", ""),
            entity_type=holder.get("type", ""),
            about_id=about.get("id", ""),
            about_name=about.get("name", ""),
            about_type=about.get("type", ""),
            relationship_type=edge.get("type", ""),
        )

    if kind == "traitsetting":
        parent_id = getattr(setting, "parent_traitsetting_id", None)
        parent = repo.get_traitsetting(parent_id) if parent_id else None
        if parent is None or depth >= MAX_CHAIN_DEPTH:
            # A broken chain (or a parent past the guard): report the kind and the
            # parent we were given, and claim no entity — `entity_id` here is
            # merely inherited, so it may well be a relationship edge key.
            return InstanceHost(kind=kind, parent_traitsetting_id=parent_id or "")
        super_trait = repo.get_trait(parent.trait_id)
        root = _describe(repo, parent, depth + 1)
        return InstanceHost(
            kind=kind,
            entity_id=root.entity_id,
            entity_name=root.entity_name,
            entity_type=root.entity_type,
            universe=root.universe,
            about_id=root.about_id,
            about_name=root.about_name,
            about_type=root.about_type,
            relationship_type=root.relationship_type,
            parent_traitsetting_id=parent.id,
            parent_trait_id=parent.trait_id,
            parent_trait_name=(super_trait.name if super_trait else ""),
        )

    # `entity`, and anything unrecognised: the anchor is the entity itself.
    name, etype = _entity_fields(repo, setting.entity_id)
    return InstanceHost(kind="entity", entity_id=setting.entity_id,
                        entity_name=name, entity_type=etype)
