"""An instance's host — the four anchors, and the two that need walking.

A ``TraitSetting`` is anchored to an entity, a body, a relationship edge, or
another instance (a sub-trait). The GM cleanup surface lists instances *by
definition* — the inverse of every other read — so each row has to say who owns
it, and the four answers are different enough that they cannot be inferred from
one field:

- a **body** anchor's entity is the projection's ``entity_id``, not the setting's;
- a **relationship** anchor's ``entity_id`` is an **edge key**, so reading it as
  an entity id would silently name nobody;
- a **sub-trait** anchor's ``entity_id`` is merely *inherited* from its parent —
  which may itself be a sub-trait, and whose root may be a relationship edge — so
  the entity has to come from the top of the chain, while the super-trait is the
  one directly above.

The repository is faked, so this pins the rules rather than ArangoDB.
"""

from types import SimpleNamespace as NS

from transversal.services.trait_instance_hosts import describe_host


class FakeRepo:
    """Only the reads the host rules make, recording them so a wrong one shows."""

    def __init__(self, entities=None, projections=None, edges=None, traits=None,
                 settings=None):
        self.entities = entities or {}
        self.projections = projections or {}
        self.edges = edges or {}
        self.traits = traits or {}
        self.settings = settings or {}
        self.calls = []

    def get_entity(self, entity_id):
        self.calls.append(("entity", entity_id))
        return self.entities.get(entity_id)

    def get_projection(self, projection_id):
        self.calls.append(("projection", projection_id))
        return self.projections.get(projection_id)

    def get_relationship_by_key(self, key):
        self.calls.append(("edge", key))
        return self.edges.get(key)

    def get_trait(self, trait_id):
        self.calls.append(("trait", trait_id))
        return self.traits.get(trait_id)

    def get_traitsetting(self, ts_id):
        self.calls.append(("setting", ts_id))
        return self.settings.get(ts_id)

    def _resolve_relationship_contact(self, ref):
        """The repository's own endpoint resolver, faked over the same maps."""
        self.calls.append(("contact", ref))
        kind, _, key = ref.partition("/")
        if kind == "entities":
            e = self.entities.get(key)
            return {"id": key, "name": e.name, "type": e.type.value} if e else None
        if kind == "projections":
            p = self.projections.get(key)
            owner = self.entities.get(p.entity_id) if p else None
            return {"id": owner.id, "name": owner.name, "type": owner.type.value} if owner else None
        return None


def entity(entity_id, name, etype="GMC"):
    return NS(id=entity_id, name=name, type=NS(value=etype))


def setting(**kwargs):
    base = dict(id="ts", entity_id="", trait_id="", from_type="entity",
                projection_id=None, parent_traitsetting_id=None)
    base.update(kwargs)
    return NS(**base)


def test_entity_anchor():
    repo = FakeRepo(entities={"gmc-1": entity("gmc-1", "Kael Drift", "CHARACTER")})
    host = describe_host(repo, setting(entity_id="gmc-1", trait_id="trait-duty"))
    assert host.kind == "entity"
    assert (host.entity_id, host.entity_name, host.entity_type) == \
        ("gmc-1", "Kael Drift", "CHARACTER")
    assert (host.universe, host.about_name, host.parent_trait_name) == ("", "", "")


def test_entity_anchor_whose_entity_is_gone():
    host = describe_host(FakeRepo(), setting(entity_id="missing"))
    assert (host.kind, host.entity_id, host.entity_name) == ("entity", "missing", "")


def test_body_anchor_names_the_owner_and_the_universe():
    repo = FakeRepo(
        entities={"gmc-1": entity("gmc-1", "Kael Drift", "CHARACTER")},
        projections={"gmc-1:Earth": NS(id="gmc-1:Earth", entity_id="gmc-1", universe="Earth")},
    )
    host = describe_host(repo, setting(from_type="projection",
                                       projection_id="gmc-1:Earth", entity_id="gmc-1"))
    assert host.kind == "projection"
    # The *owner*, not the body id, and the body's universe beside it.
    assert (host.entity_id, host.entity_name, host.entity_type) == \
        ("gmc-1", "Kael Drift", "CHARACTER")
    assert host.universe == "Earth"


def test_body_anchor_whose_body_is_gone():
    host = describe_host(FakeRepo(entities={"gmc-1": entity("gmc-1", "Kael Drift")}),
                         setting(from_type="projection", projection_id="gone",
                                 entity_id="gmc-1"))
    assert host.kind == "projection" and host.entity_name == "Kael Drift"


def test_relationship_anchor_names_both_ends():
    repo = FakeRepo(
        entities={"gmc-1": entity("gmc-1", "Kael Drift", "CHARACTER"),
                  "gmc-2": entity("gmc-2", "Vashti", "GMC")},
        edges={"edge-1": {"_key": "edge-1", "_from": "entities/gmc-1",
                          "_to": "entities/gmc-2", "type": "trusts"}},
    )
    host = describe_host(repo, setting(from_type="relationship", entity_id="edge-1"))
    assert host.kind == "relationship"
    assert (host.entity_name, host.about_name, host.relationship_type) == \
        ("Kael Drift", "Vashti", "trusts")
    # The guard that this test is really about: the edge key must never be read
    # as an entity id — that would name nobody, silently.
    assert ("entity", "edge-1") not in repo.calls, repo.calls


def test_relationship_anchor_whose_edge_is_gone():
    host = describe_host(FakeRepo(), setting(from_type="relationship",
                                             entity_id="edge-gone"))
    assert (host.kind, host.entity_name, host.about_name) == ("relationship", "", "")


def test_subtrait_anchor_takes_the_super_trait_and_the_root_entity():
    repo = FakeRepo(
        entities={"gmc-1": entity("gmc-1", "Kael Drift", "CHARACTER")},
        traits={"trait-origin": NS(name="Origin"), "trait-homeland": NS(name="Homeland")},
        settings={
            "root-1": setting(id="root-1", entity_id="gmc-1", trait_id="trait-origin"),
            "sub-1": setting(id="sub-1", entity_id="gmc-1", trait_id="trait-homeland",
                             from_type="traitsetting", parent_traitsetting_id="root-1"),
        },
    )
    host = describe_host(repo, repo.settings["sub-1"])
    assert host.kind == "traitsetting"
    assert host.parent_trait_name == "Origin"
    assert host.parent_traitsetting_id == "root-1"
    assert (host.entity_id, host.entity_name) == ("gmc-1", "Kael Drift")


def test_nested_subtrait_reports_its_own_super_trait_but_the_root_entity():
    repo = FakeRepo(
        entities={"gmc-1": entity("gmc-1", "Kael Drift")},
        traits={"a": NS(name="Origin"), "b": NS(name="Homeland")},
        settings={
            "root-1": setting(id="root-1", entity_id="gmc-1", trait_id="a"),
            "sub-1": setting(id="sub-1", entity_id="gmc-1", trait_id="b",
                             from_type="traitsetting", parent_traitsetting_id="root-1"),
            "sub-2": setting(id="sub-2", entity_id="gmc-1", trait_id="b",
                             from_type="traitsetting", parent_traitsetting_id="sub-1"),
        },
    )
    host = describe_host(repo, repo.settings["sub-2"])
    assert host.parent_traitsetting_id == "sub-1"
    assert host.parent_trait_name == "Homeland"        # the one directly above
    assert (host.entity_id, host.entity_name) == ("gmc-1", "Kael Drift")   # the root's


def test_subtrait_under_a_relationship_anchor_carries_the_edge_names():
    """Its own ``entity_id`` is only the inherited edge key — the chain answers."""
    repo = FakeRepo(
        entities={"gmc-1": entity("gmc-1", "Kael Drift"), "gmc-2": entity("gmc-2", "Vashti")},
        edges={"edge-1": {"_key": "edge-1", "_from": "entities/gmc-1",
                          "_to": "entities/gmc-2", "type": "trusts"}},
        traits={"trait-trust": NS(name="Trust"), "trait-doubt": NS(name="Doubt")},
        settings={
            "edge-root": setting(id="edge-root", entity_id="edge-1",
                                 trait_id="trait-trust", from_type="relationship"),
            "edge-sub": setting(id="edge-sub", entity_id="edge-1",
                                trait_id="trait-doubt", from_type="traitsetting",
                                parent_traitsetting_id="edge-root"),
        },
    )
    host = describe_host(repo, repo.settings["edge-sub"])
    assert (host.entity_name, host.about_name, host.relationship_type) == \
        ("Kael Drift", "Vashti", "trusts")
    assert host.parent_trait_name == "Trust"


def test_subtrait_whose_parent_cannot_be_read():
    host = describe_host(FakeRepo(), setting(from_type="traitsetting",
                                             parent_traitsetting_id="gone"))
    assert (host.kind, host.parent_traitsetting_id, host.entity_name) == \
        ("traitsetting", "gone", "")


def test_unknown_anchor_kind_reads_as_an_entity():
    repo = FakeRepo(entities={"gmc-1": entity("gmc-1", "Kael Drift")})
    for kind in ("", "something-new"):
        host = describe_host(repo, setting(from_type=kind, entity_id="gmc-1"))
        assert (host.kind, host.entity_name) == ("entity", "Kael Drift")


def test_a_looping_chain_is_bounded():
    """Corrupt data must not spin: the walk stops at the depth guard."""
    settings = {}
    for i in range(40):
        settings[f"s{i}"] = setting(id=f"s{i}", entity_id="edge-1", trait_id="trait-x",
                                    from_type="traitsetting",
                                    parent_traitsetting_id=f"s{i + 1}")
    repo = FakeRepo(traits={"trait-x": NS(name="X")}, settings=settings)
    host = describe_host(repo, settings["s0"])
    assert host.kind == "traitsetting"
    assert len([c for c in repo.calls if c[0] == "setting"]) <= 17
