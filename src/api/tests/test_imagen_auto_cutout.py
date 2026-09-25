"""The first image generated for a projection is cut out and tagged (B129).

A cutout needs a source, so the trigger hangs off the first *generated image*
for a projection — not off entity creation, which has no image yet. The
generated image becomes the body's ``background``; the transparent cutout
becomes its ``navdot`` and ``sheet``, which is what lets a body render a
floating cutout instead of a cropped circle.

The GPU path is stubbed: these tests are about the trigger, the tagging, and
the failure policy, not about ComfyUI.
"""

import asyncio

import pytest
from PIL import Image

from transversal.domain import Entity, MediaImage, EntityType, ImageType
from transversal.imagen import orchestrator as orch

PROJECTION = "proj-1"


class _FakeRepo:
    def __init__(self, existing=()):
        self._images = list(existing)
        self.created = []
        self.updates = {}

    def get_images_for_owner(self, entity_id, projection_id=None):
        return [i for i in self._images if (i.projection_id or None) == projection_id]

    def create_image(self, image):
        self.created.append(image)
        self._images.append(image)
        return image

    def update_image(self, image_id, updates):
        self.updates.setdefault(image_id, {}).update(updates)
        for img in self._images:
            if img.id == image_id:
                for key, value in updates.items():
                    setattr(img, key, value)
                return img
        return None

    def get_image(self, image_id):
        return next((i for i in self._images if i.id == image_id), None)


class _FakeComfyUI:
    async def submit_workflow(self, workflow):
        return "pid"

    async def wait_for_result(self, prompt_id, timeout_secs=600):
        return {"filename": "out.png", "subfolder": "", "type": "output"}

    async def get_image(self, filename, subfolder="", image_type="output"):
        return b"png-bytes"

    async def upload_image(self, data, filename):
        return None

    async def free_memory(self):
        return None


@pytest.fixture
def stub_gpu(monkeypatch, tmp_path):
    """Replace everything that would touch ComfyUI, disk or the DB."""
    monkeypatch.setattr(orch, "IMAGEN_DIR", tmp_path)
    monkeypatch.setattr(orch, "_load_workflow", lambda name: {})
    monkeypatch.setattr(orch, "inject_flux_params", lambda wf, **kwargs: wf)
    monkeypatch.setattr(orch, "_save_image_variants", lambda data, out, base: {"large": "L.webp"})
    monkeypatch.setattr(orch, "has_transparency", lambda data: True)
    monkeypatch.setattr(
        orch,
        "build_imagen_prompt",
        lambda entity, universe, repo, projection_id=None: {
            "prompt": "p", "negative": "n", "loras": [], "steps": 4, "width": 8, "height": 8,
        },
    )


def _entity():
    return Entity(id="char-1", type=EntityType.CHARACTER, name="Kael", current_universe="earth")


def _image(image_id, projection_id):
    return MediaImage(
        id=image_id,
        entity_id="char-1",
        projection_id=projection_id or None,
        universe="earth",
        image_type=ImageType.IMAGEN,
        roles=[],
    )


def _generate(repo, monkeypatch, projection=PROJECTION, cutout=None):
    """Run one generation, stubbing the cutout; return (image, cutout_calls)."""
    calls = []

    async def fake_cutout(owner_id, image_id, display_name="", report_gen_type=None):
        # The orchestrator takes the owner id, not an Entity: nothing below the
        # call needs the object, and a trait owner has no Entity at all (B200).
        assert owner_id == _entity().id, "the cutout must report under its owner"
        calls.append(image_id)
        if isinstance(cutout, Exception):
            raise cutout
        return cutout if cutout is not None else _image("cutout-1", projection)

    orchestrator = orch.ImagenOrchestrator(repository=repo, comfyui=_FakeComfyUI())
    monkeypatch.setattr(orchestrator, "run_remove_background", fake_cutout)
    image = asyncio.run(orchestrator.run_imagen(_entity(), "earth", projection_id=projection))
    return image, calls


def test_first_image_for_a_projection_is_cut_out_and_tagged(stub_gpu, monkeypatch):
    repo = _FakeRepo()

    image, calls = _generate(repo, monkeypatch)

    assert calls == [image.id], "the cutout should run on the image just generated"
    assert repo.updates[image.id]["roles"] == ["background"]
    assert repo.updates["cutout-1"]["roles"] == ["navdot", "sheet"]
    assert image.roles == ["background"], "the returned image should reflect the reassignment"


def test_second_image_for_the_same_projection_is_not_cut_out(stub_gpu, monkeypatch):
    repo = _FakeRepo(existing=[_image("earlier", PROJECTION)])

    image, calls = _generate(repo, monkeypatch)

    assert calls == [], "only the projection's FIRST image is cut out"
    assert image.roles == [], "a later image is not the owner's first, so no auto-select"


def test_entity_level_generation_is_left_alone(stub_gpu, monkeypatch):
    """The rule is about a projection; entity-level is the soul default."""
    repo = _FakeRepo()

    image, calls = _generate(repo, monkeypatch, projection="")

    assert calls == []
    assert image.roles == ["background", "sheet", "navdot"], "auto-select is unchanged"


def test_a_failing_cutout_does_not_fail_the_generation(stub_gpu, monkeypatch):
    """ComfyUI down must not lose the image that was already generated."""
    repo = _FakeRepo()

    image, calls = _generate(repo, monkeypatch, cutout=RuntimeError("ComfyUI down"))

    assert calls == [image.id], "it should have tried"
    assert repo.updates == {}, "nothing may be reassigned when there is no cutout"
    assert image.roles == ["background", "sheet", "navdot"], (
        "the body keeps an image for every role rather than losing sheet/navdot"
    )


# ── Provenance flags ─────────────────────────────────
#
# `ai_generated` is the imagen pipeline's own label; `ai_animated` is animate's
# (see `run_animate`). A cutout is a *derivative* made by a model itself, so it
# keeps whatever its source disclosed and adds `ai`.


def test_a_generated_image_declares_ai_generated(stub_gpu, monkeypatch):
    repo = _FakeRepo()

    image, _ = _generate(repo, monkeypatch)

    assert image.flags == ["ai_generated"]


def test_a_cutout_inherits_its_source_flags_and_declares_ai(stub_gpu, monkeypatch):
    source = _image("src-1", PROJECTION)
    source.flags = ["ai_generated"]
    source.filename = "src"
    repo = _FakeRepo(existing=[source])

    # The source's Large variant has to exist for the cutout to read it, and the
    # saving stub has to leave an openable file behind (the real one measures it).
    src_dir = orch.IMAGEN_DIR / "char-1" / "earth"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "src_Large.png").write_bytes(b"bytes")

    def _fake_variants(data, out, base):
        out.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (4, 4)).save(out / "o.webp")
        return {"original": "o.webp", "large": "L.webp"}

    monkeypatch.setattr(orch, "inject_bg_removal_params", lambda wf, **kw: wf)
    monkeypatch.setattr(orch, "_save_image_variants", _fake_variants)

    orchestrator = orch.ImagenOrchestrator(repository=repo, comfyui=_FakeComfyUI())
    cutout = asyncio.run(orchestrator.run_remove_background("char-1", "src-1", display_name="Kael"))

    assert cutout.image_type == ImageType.CUTOUT
    assert cutout.flags == ["ai", "ai_generated"], (
        "a cutout keeps its source's disclosure and adds ai — BiRefNet is a model"
    )


def test_a_cutout_of_an_unlabelled_upload_still_declares_ai(stub_gpu, monkeypatch):
    """Hand-made art run through our own cutter has AI in its workflow."""
    source = _image("src-2", PROJECTION)
    source.filename = "src2"
    repo = _FakeRepo(existing=[source])

    src_dir = orch.IMAGEN_DIR / "char-1" / "earth"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "src2_Large.png").write_bytes(b"bytes")

    def _fake_variants(data, out, base):
        out.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (4, 4)).save(out / "o.webp")
        return {"original": "o.webp", "large": "L.webp"}

    monkeypatch.setattr(orch, "inject_bg_removal_params", lambda wf, **kw: wf)
    monkeypatch.setattr(orch, "_save_image_variants", _fake_variants)

    orchestrator = orch.ImagenOrchestrator(repository=repo, comfyui=_FakeComfyUI())
    cutout = asyncio.run(orchestrator.run_remove_background("char-1", "src-2", display_name="Kael"))

    assert cutout.flags == ["ai"]
