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

from transversal.domain import Entity, ImageCredit, MediaImage, EntityType, ImageType
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


class _FakeOllama:
    async def describe_motion(self, data, hint=""):
        return "a slow drift"

    async def unload_model(self):
        return None


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
# (see `run_animate`). The cutter asserts **nothing of its own** — only imagen and
# animate declare AI — but a cutout does carry its source's labels forward.


def test_a_generated_image_declares_ai_generated(stub_gpu, monkeypatch):
    repo = _FakeRepo()

    image, _ = _generate(repo, monkeypatch)

    assert image.flags == ["ai_generated"]


def _run_cutout(repo, source, monkeypatch):
    """Drive the real `run_remove_background` with the GPU stubbed.

    The source must already be in `repo`; its `Large` variant is put on disk here
    because the cutout reads it, and the saving stub leaves an openable file
    behind because the real one measures the result.
    """
    src_dir = orch.IMAGEN_DIR / source.owner_id / source.universe
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / f"{source.filename}_Large.{source.extension}").write_bytes(b"bytes")

    def _fake_variants(data, out, base):
        out.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (4, 4)).save(out / "o.webp")
        return {"original": "o.webp", "large": "L.webp"}

    monkeypatch.setattr(orch, "inject_bg_removal_params", lambda wf, **kw: wf)
    monkeypatch.setattr(orch, "_save_image_variants", _fake_variants)

    orchestrator = orch.ImagenOrchestrator(repository=repo, comfyui=_FakeComfyUI())
    return asyncio.run(orchestrator.run_remove_background(source.owner_id, source.id, display_name="Kael"))


def test_a_cutout_inherits_its_source_flags_and_adds_nothing(stub_gpu, monkeypatch):
    source = _image("src-1", PROJECTION)
    source.flags = ["ai_generated"]
    source.filename = "src"
    repo = _FakeRepo(existing=[source])

    cutout = _run_cutout(repo, source, monkeypatch)

    assert cutout.image_type == ImageType.CUTOUT
    assert cutout.flags == ["ai_generated"], (
        "a cutout carries its source's disclosure forward, and adds nothing: only "
        "imagen and animate declare AI, and cutting out is neither"
    )


def test_a_cutout_of_an_unlabelled_upload_stays_unlabelled(stub_gpu, monkeypatch):
    """Hand-made art run through our own cutter is still hand-made art.

    BiRefNet is a model, but the human's call is that the cutout pipeline does not
    declare AI — otherwise every cutout in the app would be labelled AI by
    default, which would make the label useless."""
    source = _image("src-2", PROJECTION)
    source.filename = "src2"
    repo = _FakeRepo(existing=[source])

    cutout = _run_cutout(repo, source, monkeypatch)

    assert cutout.flags == []


def test_a_cutout_keeps_the_artworks_citation(stub_gpu, monkeypatch):
    """A cutout is the same picture with its background removed, so the artist,
    the source link and the licence must survive the new file id."""
    source = _image("src-3", PROJECTION)
    source.filename = "src3"
    source.credits = [ImageCredit(role="artist", name="Jane Doe", url="https://example.org/jane")]
    source.license = "CC BY-SA 4.0"
    source.credit_text = "Art by Jane Doe, CC BY-SA 4.0"
    repo = _FakeRepo(existing=[source])

    cutout = _run_cutout(repo, source, monkeypatch)

    assert [(c.role, c.name, c.url) for c in cutout.credits] == [
        ("artist", "Jane Doe", "https://example.org/jane"),
    ]
    assert cutout.license == "CC BY-SA 4.0"
    assert cutout.credit_text == "Art by Jane Doe, CC BY-SA 4.0"
    assert cutout.credits[0] is not source.credits[0], "independent rows, not shared objects"


def _run_animate(repo, monkeypatch, source_image_id=""):
    """Drive the real `run_animate` with the GPU and Ollama stubbed."""
    monkeypatch.setattr(orch, "inject_wan_params", lambda wf, **kw: wf)
    orchestrator = orch.ImagenOrchestrator(repository=repo, comfyui=_FakeComfyUI())
    orchestrator.ollama = _FakeOllama()
    return asyncio.run(orchestrator.run_animate(_entity(), "earth", source_image_id=source_image_id))


def _animatable_source(repo, image_id, filename, **fields):
    """An existing image on disk, ready to be animated."""
    source = _image(image_id, PROJECTION)
    source.filename = filename
    for key, value in fields.items():
        setattr(source, key, value)
    repo._images.append(source)

    src_dir = orch.IMAGEN_DIR / "char-1" / "earth"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / f"{filename}_Large.png").write_bytes(b"bytes")
    return source


def test_a_freshly_generated_loop_declares_generated_and_animated(stub_gpu, monkeypatch):
    """A fresh loop is Flux *and* WanVideo, so both of the pipeline's claims hold."""
    repo = _FakeRepo()

    image = _run_animate(repo, monkeypatch)

    assert image.flags == ["ai_animated", "ai_generated"]


def test_a_loop_of_an_ai_generated_picture_keeps_that_label_too(stub_gpu, monkeypatch):
    repo = _FakeRepo()
    _animatable_source(repo, "src-5", "src5", flags=["ai_generated"])

    image = _run_animate(repo, monkeypatch, source_image_id="src-5")

    assert image.flags == ["ai_animated", "ai_generated"]


def test_a_loop_of_a_hand_made_upload_declares_only_the_motion(stub_gpu, monkeypatch):
    """Animating a hand-made picture does not make the picture AI-generated.

    Only the motion is; labelling the imagery too would be the over-claim the
    cutout rule already ruled out."""
    repo = _FakeRepo()
    _animatable_source(repo, "src-6", "src6")

    image = _run_animate(repo, monkeypatch, source_image_id="src-6")

    assert image.flags == ["ai_animated"]


def test_an_animated_loop_keeps_the_artworks_citation(stub_gpu, monkeypatch):
    """Same rule as the cutout: a loop of a credited picture is that picture."""
    repo = _FakeRepo()
    _animatable_source(
        repo, "src-4", "src4",
        credits=[ImageCredit(role="artist", name="Jane Doe", url="https://example.org/jane")],
        license="CC BY-SA 4.0",
        credit_text="Art by Jane Doe, CC BY-SA 4.0",
    )

    image = _run_animate(repo, monkeypatch, source_image_id="src-4")

    assert image.image_type == ImageType.ANIMATED
    assert image.flags == ["ai_animated"], "a hand-made upload declares only the motion"
    assert [(c.role, c.name, c.url) for c in image.credits] == [
        ("artist", "Jane Doe", "https://example.org/jane"),
    ]
    assert image.license == "CC BY-SA 4.0"
    assert image.credit_text == "Art by Jane Doe, CC BY-SA 4.0"
