"""Assistant de premier lancement : téléchargement réel du modèle Whisper tiny avec progression."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(lc_home):
    from liveclipper.main import create_app
    with TestClient(create_app(start_workers=False)) as c:
        yield c


def test_status(client):
    st = client.get("/api/setup/status").json()
    assert st["setup_done"] is False and len(st["models"]) == 6
    assert st["gpu"]["present"] is False
    assert client.post("/api/setup/cuda").status_code == 400   # Linux
    client.post("/api/setup/finish")
    assert client.get("/api/settings").json()["setup_done"] is True


@pytest.mark.slow
def test_download_whisper_tiny(client):
    import httpx
    try:
        httpx.get("https://huggingface.co/api/models/Systran/faster-whisper-tiny", timeout=10).raise_for_status()
    except Exception:
        pytest.skip("Hugging Face injoignable")
    from liveclipper.events import bus
    from liveclipper.setup import setup_task
    r = client.post("/api/setup/whisper", json={"model": "tiny"})
    assert r.json()["ok"]
    setup_task.join(300)
    assert setup_task.state["status"] == "done", setup_task.state
    progress = [m["data"]["progress"] for m in bus.history if m["type"] == "setup.progress"]
    assert progress[-1] == 1.0 and any(0 < p < 1 for p in progress)
    st = client.get("/api/setup/status").json()
    assert [m for m in st["models"] if m["name"] == "tiny"][0]["installed"]
    assert st["whisper_model"] == "tiny"
    # le modèle local est utilisé par la transcription
    from liveclipper import paths
    from liveclipper.pipeline.transcribe import model_path
    assert model_path("tiny") == str(paths.models_dir() / "tiny")


@pytest.mark.slow
def test_cuda_wheel_lookup():
    import httpx
    from liveclipper.setup import CUDA_PACKAGES, SetupTask
    try:
        with httpx.Client(timeout=20) as c:
            for pkg, prefix in CUDA_PACKAGES:
                url, size = SetupTask.wheel_url(c, pkg, prefix)
                assert url.endswith("win_amd64.whl") and size > 50_000_000
                if prefix:
                    assert f"-{prefix}" in url.rsplit("/", 1)[-1]
    except httpx.HTTPError:
        pytest.skip("PyPI injoignable")


@pytest.mark.slow
@pytest.mark.parametrize("model", ["tiny", "small", "medium", "large-v3", "large-v3-turbo"])
def test_whisper_file_listing_follows_redirects(model):
    """Les dépôts Hugging Face peuvent être renommés (ex. large-v3-turbo) : la liste doit suivre la redirection."""
    import httpx
    from liveclipper.setup import SetupTask, repo_for
    try:
        with httpx.Client(timeout=30, follow_redirects=True) as c:
            files = SetupTask().whisper_files(c, repo_for(model))
    except httpx.HTTPError as e:
        pytest.skip(f"Hugging Face injoignable : {e}")
    names = [n for n, _ in files]
    assert "model.bin" in names and "config.json" in names
    assert dict(files)["model.bin"] > 30_000_000
