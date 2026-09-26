"""A projection's first generated image gains a matte, and a loop is a render.

A matte needs a source, so the trigger hangs off the first *generated image* for a
projection — not off entity creation, which has no image yet. Under the tier model
([[B210]]) the matte is a **render of that picture**, not a second one: the picture
keeps every role auto-select gave it, and ``sheet``/``navdot`` begin serving the
matte the moment it exists. Likewise a loop is a render of the picture it came
from, so its citation and labels cannot be lost.

The GPU path is stubbed: these tests are about the trigger, the renders, and the
failure policy, not about ComfyUI.
"""

import asyncio
import io

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
    # The loop is written beside its still under the picture's base name, so this
    # must be redirected too — otherwise a sourced-loop test writes into the real
    # media tree at a name a live picture owns.
    monkeypatch.setattr(orch, "ANIMATED_DIR", tmp_path / "animated")
    monkeypatch.setattr(orch, "_load_workflow", lambda name: {})
    monkeypatch.setattr(orch, "inject_flux_params", lambda wf, **kwargs: wf)
    monkeypatch.setattr(orch, "_save_image_variants", _fake_variants)
    monkeypatch.setattr(orch, "has_transparency", lambda data: True)
    monkeypatch.setattr(orch, "inject_bg_removal_params", lambda wf, **kw: wf)
    monkeypatch.setattr(
        orch,
        "build_imagen_prompt",
        lambda entity, universe, repo, projection_id=None: {
            "prompt": "p", "negative": "n", "loras": [], "steps": 4, "width": 8, "height": 8,
        },
    )


def _fake_variants(data, out, base):
    """Write a real tier file, because the next stage reads `_Large` off disk.

    The cutout and the animate paths both open the picture's own ``_Large`` file
    rather than carrying the bytes, so a stub that only returns names would hide
    exactly the wiring these tests are for.
    """
    out.mkdir(parents=True, exist_ok=True)
    name = f"{base}_Large.webp"
    Image.new("RGB", (8, 8)).save(out / name)
    original = f"{base}_Original.webp"
    (out / original).write_bytes((out / name).read_bytes())
    return {"original": original, "large": name}


def _entity():
    return Entity(id="char-1", type=EntityType.CHARACTER, name="Kael", current_universe="earth")


def _location():
    return Entity(id="loc-1", type=EntityType.LOCATION, name="Hall", current_universe="earth")


def _image(image_id, projection_id):
    return MediaImage(
        id=image_id,
        entity_id="char-1",
        projection_id=projection_id or None,
        universe="earth",
        image_type=ImageType.IMAGEN,
        roles=[],
    )


def _generate(repo, monkeypatch, projection=PROJECTION, cutout=None, real_cutout=False, entity=None):
    """Run one generation; return (image, cutout_calls).

    The cutout is stubbed unless ``real_cutout`` — those tests are about the trigger
    and the failure policy, and the real cutter is exercised on its own below.
    """
    calls = []
    ent = entity or _entity()

    async def fake_cutout(owner_id, image_id, display_name="", report_gen_type=None):
        # The orchestrator takes the owner id, not an Entity: nothing below the
        # call needs the object, and a trait owner has no Entity at all (B200).
        assert owner_id == ent.id, "the cutout must report under its owner"
        calls.append(image_id)
        if isinstance(cutout, Exception):
            raise cutout
        return cutout if cutout is not None else _image("cutout-1", projection)

    orchestrator = orch.ImagenOrchestrator(repository=repo, comfyui=_FakeComfyUI())
    if not real_cutout:
        monkeypatch.setattr(orchestrator, "run_remove_background", fake_cutout)
    image = asyncio.run(orchestrator.run_imagen(ent, "earth", projection_id=projection))
    return image, calls


def test_first_image_for_a_projection_gains_a_matte_without_a_second_record(stub_gpu, monkeypatch):
    repo = _FakeRepo()

    image, _ = _generate(repo, monkeypatch, real_cutout=True)

    # The matte is a render of this picture: no row is created and no role moves —
    # `sheet`/`navdot` serve the matte the moment the source carries it.
    assert repo.created == [image], "no cutout record is created"
    assert image.renders == ["cutout"]
    assert image.transparent is True, "the picture now has a transparent render"
    assert image.roles == ["background", "sheet", "navdot"], "roles are untouched"


def test_a_later_image_for_the_same_projection_is_also_cut_out(stub_gpu, monkeypatch):
    """The matte is a rule about the picture, not about being first ([[B214]]).
    Before this, only the projection's first image was cut out."""
    repo = _FakeRepo(existing=[_image("earlier", PROJECTION)])

    image, calls = _generate(repo, monkeypatch)

    assert calls == [image.id], "every generated occupant picture is a subject"
    assert image.roles == [], "a later image is not the owner's first, so no auto-select"


def test_entity_level_generation_is_cut_out_too(stub_gpu, monkeypatch):
    """Entity-level is the soul default, and still an occupant's picture — the old
    rule excluded it because it hung off a *projection* ([[B214]])."""
    repo = _FakeRepo()

    image, calls = _generate(repo, monkeypatch, projection="")

    assert calls == [image.id]
    assert image.roles == ["background", "sheet", "navdot"], "auto-select is unchanged"


def test_a_location_generation_is_not_cut_out(stub_gpu, monkeypatch):
    """A room is a scene: there is nothing to cut out of it."""
    repo = _FakeRepo()

    image, calls = _generate(repo, monkeypatch, entity=_location(), projection="")

    assert calls == [], "locations never get a matte"
    assert image.renders == []


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


def _run_cutout(repo, source):
    """Drive the real `run_remove_background` with the GPU stubbed.

    The source must already be in `repo`; its `Large` variant is put on disk here
    because the cutout reads it, and the saving stub leaves an openable file behind
    because the real one measures the result.
    """
    src_dir = orch.IMAGEN_DIR / source.owner_id / source.universe
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / f"{source.filename}_Large.{source.extension}").write_bytes(b"bytes")

    orchestrator = orch.ImagenOrchestrator(repository=repo, comfyui=_FakeComfyUI())
    return asyncio.run(orchestrator.run_remove_background(source.owner_id, source.id, display_name="Kael"))


def test_a_cutout_inherits_its_source_flags_and_adds_nothing(stub_gpu, monkeypatch):
    source = _image("src-1", PROJECTION)
    source.flags = ["ai_generated"]
    source.filename = "src"
    repo = _FakeRepo(existing=[source])

    cutout = _run_cutout(repo, source)

    # The matte is a render on the source record, so the flags are inherited by
    # construction — the cutter has no row of its own to stamp.
    assert cutout is source
    assert cutout.renders == ["cutout"]
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

    cutout = _run_cutout(repo, source)

    assert cutout is source
    assert cutout.flags == []


def test_a_cutout_keeps_the_artworks_citation(stub_gpu, monkeypatch):
    """A cutout is the same picture with its background removed, so the artist,
    the source link and the licence cannot be lost — there is no second row to
    forget to copy them to."""
    source = _image("src-3", PROJECTION)
    source.filename = "src3"
    source.credits = [ImageCredit(role="artist", name="Jane Doe", url="https://example.org/jane")]
    source.license = "CC BY-SA 4.0"
    source.credit_text = "Art by Jane Doe, CC BY-SA 4.0"
    repo = _FakeRepo(existing=[source])

    cutout = _run_cutout(repo, source)

    assert cutout is source, "the matte is a render, not a new record"
    assert [(c.role, c.name, c.url) for c in cutout.credits] == [
        ("artist", "Jane Doe", "https://example.org/jane"),
    ]
    assert cutout.license == "CC BY-SA 4.0"
    assert cutout.credit_text == "Art by Jane Doe, CC BY-SA 4.0"


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


def test_a_freshly_generated_loop_is_an_imagen_picture_with_an_animated_render(stub_gpu, monkeypatch):
    """A fresh loop is Flux *and* WanVideo, so the picture is `imagen` with an
    `animated` render — a loop is not a separate kind of picture ([[B210]])."""
    repo = _FakeRepo()

    image = _run_animate(repo, monkeypatch)

    assert image.image_type == ImageType.IMAGEN
    assert image.renders == ["animated"]
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
    """Same rule as the cutout: a loop of a credited picture is that picture, so
    the render is added to the source and the citation is untouched."""
    repo = _FakeRepo()
    source = _animatable_source(
        repo, "src-4", "src4",
        credits=[ImageCredit(role="artist", name="Jane Doe", url="https://example.org/jane")],
        license="CC BY-SA 4.0",
        credit_text="Art by Jane Doe, CC BY-SA 4.0",
    )

    image = _run_animate(repo, monkeypatch, source_image_id="src-4")

    assert image is source, "the loop merges into the picture, it is not a new one"
    assert image.image_type == ImageType.IMAGEN
    assert image.renders == ["animated"]
    assert image.flags == ["ai_animated"], "a hand-made upload declares only the motion"
    assert [(c.role, c.name, c.url) for c in image.credits] == [
        ("artist", "Jane Doe", "https://example.org/jane"),
    ]
    assert image.license == "CC BY-SA 4.0"
    assert image.credit_text == "Art by Jane Doe, CC BY-SA 4.0"


def test_a_sourced_loop_lands_under_the_pictures_own_name(stub_gpu, monkeypatch):
    """One picture is true on disk too, not only in the record: the loop shares the
    still's base name, so a role can serve either from one name."""
    repo = _FakeRepo()
    _animatable_source(repo, "src-7", "src7")

    image = _run_animate(repo, monkeypatch, source_image_id="src-7")

    assert image.filename == "src7"
    loop = orch.ANIMATED_DIR / "char-1" / "earth" / f"{image.filename}.png"
    assert loop.exists(), "the loop sits beside the still under one base name"
    # And no second still ladder was written for the loop.
    assert not (orch.IMAGEN_DIR / "char-1" / "earth" / "src7_anim_Large.webp").exists()


def test_the_matte_is_trimmed_to_its_subject_before_it_is_saved(stub_gpu, monkeypatch):
    """A matte keeps the source's canvas, so a subject in one corner of the frame
    would be served at that fraction of the tier — small, and floating in empty
    space on every surface ([[B213]])."""
    source = _image("src-9", PROJECTION)
    source.filename = "src9"
    repo = _FakeRepo(existing=[source])
    src_dir = orch.IMAGEN_DIR / source.owner_id / source.universe
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / f"src9_Large.{source.extension}").write_bytes(b"bytes")

    canvas = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
    canvas.paste(Image.new("RGBA", (80, 80), (200, 30, 30, 255)), (300, 300))
    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    png = buf.getvalue()

    seen = {}

    def _capture(data, out, base):
        with Image.open(io.BytesIO(data)) as im:
            seen["size"] = im.size
        out.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (4, 4)).save(out / "o.webp")
        return {"original": "o.webp", "large": "L.webp"}

    monkeypatch.setattr(orch, "_save_image_variants", _capture)
    async def _get_image(self, *args, **kwargs):
        return png

    monkeypatch.setattr(_FakeComfyUI, "get_image", _get_image)

    orchestrator = orch.ImagenOrchestrator(repository=repo, comfyui=_FakeComfyUI())
    asyncio.run(orchestrator.run_remove_background(source.owner_id, source.id))

    assert seen["size"] == (80, 80), f"the matte was saved at {seen['size']}, untrimmed"


def test_the_auto_cutout_trims_the_matte_too(stub_gpu, monkeypatch):
    """The projection's first generated image gets its matte from the same
    `run_remove_background`, so it is trimmed like any other cutout ([[B213]]).

    This is the path with no button on it — the one a future change could quietly
    leave behind while the endpoint stays correct."""
    repo = _FakeRepo()

    canvas = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
    canvas.paste(Image.new("RGBA", (80, 80), (200, 30, 30, 255)), (300, 300))
    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    png = buf.getvalue()

    sizes = {}

    def _capture(data, out, base):
        if base.endswith("_Cutout"):
            with Image.open(io.BytesIO(data)) as im:
                sizes["matte"] = im.size
        out.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (8, 8)).save(out / f"{base}_Large.webp")
        return {"original": f"{base}_Original.webp", "large": f"{base}_Large.webp"}

    async def _get_image(self, *args, **kwargs):
        return png

    monkeypatch.setattr(orch, "_save_image_variants", _capture)
    monkeypatch.setattr(_FakeComfyUI, "get_image", _get_image)

    image, _ = _generate(repo, monkeypatch, real_cutout=True)

    assert sizes.get("matte") == (80, 80), f"auto-cutout saved {sizes.get('matte')}, untrimmed"
    assert image.renders == ["cutout"]
