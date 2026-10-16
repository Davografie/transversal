"""GPU jobs are off on the public deployment (B88).

The GPU is the owner's own card, in the machine that serves an app now on the public
internet, so `GPU_JOBS` has to switch off **every** way to spend it. The endpoints are
the obvious ones; the upload's automatic matte is the one that gets forgotten, and it
has its own test next to the upload guard.
"""

import pytest
from fastapi.testclient import TestClient

from transversal.services import gpu_jobs


@pytest.mark.parametrize("value", ["off", "OFF", "0", "false", "no", "disabled", " none "])
def test_an_off_value_disables_gpu_jobs(monkeypatch, value):
    monkeypatch.setenv(gpu_jobs.ENV, value)

    assert gpu_jobs.enabled() is False


@pytest.mark.parametrize("value", ["on", "1", "true", "yes", ""])
def test_anything_else_leaves_gpu_jobs_on(monkeypatch, value):
    monkeypatch.setenv(gpu_jobs.ENV, value)

    assert gpu_jobs.enabled() is True


def test_unset_means_on(monkeypatch):
    """Disabling is the deliberate act: a missing variable must not silently change
    what a single-user install can do."""
    monkeypatch.delenv(gpu_jobs.ENV, raising=False)

    assert gpu_jobs.enabled() is True


#: Every way to spend the GPU. Upscale is in here although the owner named only
#: generation, animation and cutout: it is the same card and the same door.
GPU_ENDPOINTS = (
    "/api/v1/imagen/loc-probe",
    "/api/v1/animate/loc-probe",
    "/api/v1/remove-background/loc-probe",
    "/api/v1/upscale/img-probe",
)


@pytest.mark.parametrize("path", GPU_ENDPOINTS)
def test_every_gpu_endpoint_refuses_when_jobs_are_off(monkeypatch, path):
    monkeypatch.setenv(gpu_jobs.ENV, "off")
    from transversal.main import app

    response = TestClient(app).post(path)

    assert response.status_code == 503
    assert response.json()["detail"] == gpu_jobs.REFUSAL


def test_a_read_is_not_refused_when_jobs_are_off(monkeypatch):
    """The gallery has to work while generation is off — reads never touched the
    GPU, and a surface that breaks when it cannot generate is a worse surface."""
    monkeypatch.setenv(gpu_jobs.ENV, "off")
    from transversal.main import app

    response = TestClient(app).get("/api/v1/imagen/jobs")

    assert response.status_code != 503
