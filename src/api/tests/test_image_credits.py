"""Artwork credits and citations (`B204`).

An image can name who made it and where it came from — Creative Commons' TASL
*Author* and *Source*, IPTC's Creator/Credit Line/Source. These run against live
ArangoDB with namespaced fixtures, and skip when it is unavailable.
"""

import pytest
from fastapi.testclient import TestClient

from transversal.api.graphql.type_defs.image_meta import ImageInfo, build_image_info
from transversal.db.repository import EntityRepository
from transversal.main import app
from transversal.domain import (
    Entity,
    EntityType,
    ImageCredit,
    ImageType,
    MediaImage,
)

try:
    _repo = EntityRepository()
    HAVE_DB = True
except Exception:
    _repo = None
    HAVE_DB = False

requires_db = pytest.mark.skipif(not HAVE_DB, reason="ArangoDB not available")


@pytest.fixture(autouse=True)
def _real_repo_singletons():
    """Undo another test module's repository swap before we query GraphQL.

    `tests/test_graphql.py` points `main._repo` at an `InMemoryRepository` and
    clears `_entity_manager`; both are module globals and the swap leaks into
    whatever runs next, so a GraphQL query here would ask a database that has
    never heard of our fixture. Resetting to None makes `_get_repo()` build the
    real one again.
    """
    from transversal import main as api_main
    api_main._repo = None
    api_main._entity_manager = None
    yield

ENTITY = "test-credits-entity"
IMG = "test-credits-img"
EARLY = "2026-01-01T00:00:00+00:00"


# ── The builder (no database) ─────────────────────────


def test_build_image_info_carries_provenance():
    img = MediaImage(
        id="x", owner_kind="trait", owner_id="trait-1", universe="earth",
        image_type=ImageType.UPLOADED, flags=["ai"],
        credits=[ImageCredit(role="artist", name="Jane Doe", url="https://example.org/jane")],
        license="CC BY-SA 4.0", credit_text="Art by Jane Doe",
    )
    info = build_image_info(img, "sheet", "/media/x.webp")
    assert isinstance(info, ImageInfo)
    assert info.url == "/media/x.webp" and info.role == "sheet"
    assert info.flags == ["ai"]
    assert [(c.role, c.name, c.url) for c in info.credits] == [
        ("artist", "Jane Doe", "https://example.org/jane"),
    ]
    assert info.license == "CC BY-SA 4.0"
    assert info.credit_text == "Art by Jane Doe"


# ── Fixtures ──────────────────────────────────────────


def _cleanup(repo):
    if repo.get_image(IMG) is not None:
        repo.delete_image(IMG)
    if repo.get_entity(ENTITY) is not None:
        repo.delete_entity(ENTITY, rmtree=True)


def _fixtures(repo):
    _cleanup(repo)
    repo.create_entity(Entity(
        id=ENTITY, type=EntityType.GMC, name="Credits Probe", current_universe="earth",
    ))
    repo.create_image(MediaImage(
        id=IMG, owner_kind="entity", owner_id=ENTITY, universe="earth",
        image_type=ImageType.UPLOADED, roles=["sheet"],
        filename="probe", extension="webp", created_at=EARLY,
    ))


def _gql(client, query, variables=None):
    r = client.post("/api/v1/graphql", json={"query": query, "variables": variables or {}})
    assert r.status_code == 200, r.text
    data = r.json()
    assert "errors" not in data, data.get("errors")
    return data["data"]


# ── REST write path ───────────────────────────────────


@requires_db
def test_patch_stores_credits_license_and_credit_line():
    repo = _repo
    _fixtures(repo)
    client = TestClient(app)

    r = client.patch(f"/api/v1/imagen/{IMG}", json={
        "credits": [
            {"role": "artist", "name": "Jane Doe", "url": "https://example.org/jane"},
            {"role": "source", "name": "OpenGameArt", "url": "https://opengameart.org/node/1"},
        ],
        "license": "CC BY-SA 4.0",
        "credit_text": "Art by Jane Doe, via OpenGameArt, CC BY-SA 4.0",
    })
    assert r.status_code == 200, r.text

    img = repo.get_image(IMG)
    assert [(c.role, c.name) for c in img.credits] == [("artist", "Jane Doe"), ("source", "OpenGameArt")]
    assert img.license == "CC BY-SA 4.0"
    assert img.credit_text.startswith("Art by Jane Doe")
    # And the list the galleries read carries them.
    row = next(i for i in client.get(f"/api/v1/imagen/{ENTITY}").json()["images"] if i["id"] == IMG)
    assert row["license"] == "CC BY-SA 4.0"
    assert row["credits"][0]["name"] == "Jane Doe"
    _cleanup(repo)


@requires_db
def test_a_credit_url_must_be_http():
    """These become links the UI renders, so the scheme is checked — an unchecked
    one is a stored-XSS vector (the class of bug that removed `.svg` uploads)."""
    repo = _repo
    _fixtures(repo)
    client = TestClient(app)

    for bad in ("javascript:alert(1)", "data:text/html;base64,PHNjcmlwdD4=", "/relative", "ftp://x/y"):
        r = client.patch(f"/api/v1/imagen/{IMG}", json={
            "credits": [{"role": "source", "name": "x", "url": bad}],
        })
        assert r.status_code == 400, f"{bad} should be refused"
        assert "http" in r.json()["detail"]

    assert repo.get_image(IMG).credits == [], "a refused write changes nothing"
    _cleanup(repo)


@requires_db
def test_an_unknown_credit_role_is_rejected_and_blanks_are_dropped():
    repo = _repo
    _fixtures(repo)
    client = TestClient(app)

    bad = client.patch(f"/api/v1/imagen/{IMG}", json={
        "credits": [{"role": "webmaster", "name": "x"}],
    })
    assert bad.status_code == 400
    assert "Unknown credit role" in bad.json()["detail"]

    # An empty editor row is not an error — it is simply not a credit.
    ok = client.patch(f"/api/v1/imagen/{IMG}", json={
        "credits": [{"role": "artist", "name": "", "url": ""},
                    {"role": "artist", "name": "Real Artist"}],
    })
    assert ok.status_code == 200, ok.text
    assert [c.name for c in repo.get_image(IMG).credits] == ["Real Artist"]
    _cleanup(repo)


@requires_db
def test_credits_can_be_cleared():
    repo = _repo
    _fixtures(repo)
    client = TestClient(app)

    client.patch(f"/api/v1/imagen/{IMG}", json={
        "credits": [{"role": "artist", "name": "Jane"}], "license": "CC0",
    })
    assert repo.get_image(IMG).credits

    r = client.patch(f"/api/v1/imagen/{IMG}", json={"credits": [], "license": ""})
    assert r.status_code == 200, r.text
    assert repo.get_image(IMG).credits == [] and repo.get_image(IMG).license == ""
    _cleanup(repo)


# ── GraphQL read path (what a player-facing viewer uses) ──


@requires_db
def test_image_info_serves_flags_and_credits_to_a_viewer():
    repo = _repo
    _fixtures(repo)
    repo.update_image(IMG, {
        "flags": ["ai_generated"],
        "credits": [{"role": "artist", "name": "Jane Doe", "url": "https://example.org/jane"}],
        "license": "CC BY-SA 4.0",
        "credit_text": "Art by Jane Doe, CC BY-SA 4.0",
    })
    client = TestClient(app)

    data = _gql(client, """
        query($id: ID!) {
          entity(id: $id) {
            imageInfo(role: "sheet") {
              url flags license creditText
              credits { role name url }
            }
          }
        }
    """, {"id": ENTITY})

    info = data["entity"]["imageInfo"]
    # `sheet` renders from the Small variant, as it does for an entity portrait.
    assert info["url"].endswith("probe_Small.webp"), info["url"]
    assert info["flags"] == ["ai_generated"]
    assert info["credits"] == [
        {"role": "artist", "name": "Jane Doe", "url": "https://example.org/jane"},
    ]
    assert info["license"] == "CC BY-SA 4.0"
    assert info["creditText"] == "Art by Jane Doe, CC BY-SA 4.0"

    # An image with no metadata still resolves, with empty provenance — the
    # viewer must not have to special-case "no credits".
    repo.update_image(IMG, {"flags": [], "credits": [], "license": "", "credit_text": ""})
    data = _gql(client, """
        query($id: ID!) { entity(id: $id) { imageInfo(role: "sheet") { url flags credits { role } } } }
    """, {"id": ENTITY})
    assert data["entity"]["imageInfo"]["flags"] == []
    assert data["entity"]["imageInfo"]["credits"] == []
    _cleanup(repo)
