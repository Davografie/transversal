"""Trimming the margins off existing cutouts ([[B213]]).

Driven against a fake `images` collection and a temporary media tree, because the
script's job is file surgery. `trim_transparent_margins` itself is covered in
`test_image_variants.py`; this is about what the pass touches and what it leaves.
"""

import io

from PIL import Image

from transversal import trim_cutout_margins as mig


class _FakeCollection:
    def __init__(self, docs):
        self.docs = {d["_key"]: dict(d) for d in docs}


class _FakeAQL:
    def __init__(self, collection):
        self.collection = collection

    def execute(self, query, bind_vars=None):
        return [dict(d) for d in self.collection.docs.values()]


class _FakeDB:
    def __init__(self, docs):
        self.collection_handle = _FakeCollection(docs)
        self.aql = _FakeAQL(self.collection_handle)

    def has_collection(self, name):
        return True


def _matte(path, size=(400, 400), subject=(300, 300, 380, 380)):
    """A transparent canvas with an opaque patch — margins to trim."""
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    patch = Image.new("RGBA", (subject[2] - subject[0], subject[3] - subject[1]), (200, 30, 30, 255))
    img.paste(patch, (subject[0], subject[1]))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


def _record(key="img-1", filename="charsheet_abc", owner="char-1"):
    return {
        "_key": key, "id": key, "owner_id": owner, "owner_kind": "entity",
        "universe": "earth", "image_type": "imagen", "filename": filename,
        "extension": "webp", "roles": ["sheet"], "renders": ["cutout"], "flags": [],
    }


def _run(monkeypatch, docs, apply=True):
    monkeypatch.setattr(mig, "get_db", lambda: _FakeDB(docs))
    assert mig.migrate(apply=apply) == 0


def test_a_matte_with_margins_is_trimmed_and_its_ladder_rebuilt(tmp_path, monkeypatch):
    monkeypatch.setattr(mig, "IMAGEN_DIR", tmp_path)
    _matte(tmp_path / "char-1" / "earth" / "charsheet_abc_Cutout_Original.webp")

    _run(monkeypatch, [_record()])

    master = tmp_path / "char-1" / "earth" / "charsheet_abc_Cutout_Original.webp"
    with Image.open(master) as im:
        assert im.size == (80, 80), f"still {im.size}, untrimmed"
    # Every tier is re-derived from the trimmed master, so no surface keeps a
    # full-canvas file under a tight name.
    for tier in ("XLarge", "Large", "Small", "Mini"):
        assert (tmp_path / "char-1" / "earth" / f"charsheet_abc_Cutout_{tier}.webp").exists()


def test_the_source_picture_is_never_touched(tmp_path, monkeypatch):
    """Its framing is its own, and the record's width/height describe *it*."""
    monkeypatch.setattr(mig, "IMAGEN_DIR", tmp_path)
    _matte(tmp_path / "char-1" / "earth" / "charsheet_abc_Cutout_Original.webp")
    still = tmp_path / "char-1" / "earth" / "charsheet_abc_Original.webp"
    _matte(still, size=(400, 400), subject=(10, 10, 390, 390))
    before = still.read_bytes()

    _run(monkeypatch, [_record()])

    assert still.read_bytes() == before


def test_a_tight_matte_is_left_alone(tmp_path, monkeypatch):
    """No re-encode for no gain — and that is what makes the pass idempotent."""
    monkeypatch.setattr(mig, "IMAGEN_DIR", tmp_path)
    master = tmp_path / "char-1" / "earth" / "charsheet_abc_Cutout_Original.webp"
    _matte(master, size=(200, 200), subject=(0, 0, 200, 200))
    before = master.read_bytes()

    _run(monkeypatch, [_record()])

    assert master.read_bytes() == before


def test_a_dry_run_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(mig, "IMAGEN_DIR", tmp_path)
    master = tmp_path / "char-1" / "earth" / "charsheet_abc_Cutout_Original.webp"
    _matte(master)
    before = master.read_bytes()

    _run(monkeypatch, [_record()], apply=False)

    assert master.read_bytes() == before
    assert not (tmp_path / "char-1" / "earth" / "charsheet_abc_Cutout_Small.webp").exists()


def test_trimming_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(mig, "IMAGEN_DIR", tmp_path)
    master = tmp_path / "char-1" / "earth" / "charsheet_abc_Cutout_Original.webp"
    _matte(master)

    _run(monkeypatch, [_record()])
    once = master.read_bytes()
    _run(monkeypatch, [_record()])

    assert master.read_bytes() == once, "a second pass must find nothing to do"


def test_a_record_without_a_matte_is_skipped(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(mig, "IMAGEN_DIR", tmp_path)
    _run(monkeypatch, [_record(filename="gone")])
    assert "no matte master" in capsys.readouterr().out
