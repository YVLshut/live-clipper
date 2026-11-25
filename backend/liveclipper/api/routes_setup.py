"""Assistant de premier lancement."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from .. import config, paths, secrets
from ..errors import UserError
from ..setup import MODEL_SIZES, cuda_libs_installed, model_installed, nvidia_gpu, setup_task

router = APIRouter(prefix="/api/setup")


@router.get("/status")
def status():
    gpu = nvidia_gpu()
    from ..pipeline.transcribe import cuda_available
    cuda_ok, cuda_detail = cuda_available() if gpu["present"] else (False, "pas de GPU NVIDIA")
    return {
        "setup_done": bool(config.get("setup_done")),
        "whisper_model": config.get("whisper_model"),
        "models": [{"name": m, "size": MODEL_SIZES.get(m, ""), "installed": model_installed(m)}
                   for m in config.WHISPER_MODELS],
        "gpu": {**gpu, "windows": paths.IS_WINDOWS, "cuda_libs": cuda_libs_installed(),
                "cuda_ok": cuda_ok, "detail": cuda_detail},
        "has_anthropic_key": secrets.has(secrets.ANTHROPIC_KEY),
        "task": setup_task.state,
    }


class ModelBody(BaseModel):
    model: str


@router.post("/whisper")
def download_whisper(body: ModelBody):
    if body.model not in config.WHISPER_MODELS:
        raise UserError("Modèle Whisper inconnu.")
    if setup_task.busy():
        raise UserError("Un téléchargement est déjà en cours.")
    config.update({"whisper_model": body.model})
    if model_installed(body.model):
        return {"ok": True, "already": True}
    setup_task.start("whisper", f"Modèle Whisper {body.model}", lambda: setup_task.download_whisper(body.model))
    return {"ok": True}


@router.post("/cuda")
def download_cuda():
    if not paths.IS_WINDOWS:
        raise UserError("Les bibliothèques CUDA se téléchargent ici uniquement sous Windows.")
    if setup_task.busy():
        raise UserError("Un téléchargement est déjà en cours.")
    setup_task.start("cuda", "Bibliothèques GPU (CUDA)", setup_task.download_cuda)
    return {"ok": True}


@router.post("/cancel")
def cancel():
    setup_task.cancel()
    return {"ok": True}


@router.post("/finish")
def finish():
    config.update({"setup_done": True})
    return {"ok": True}


@router.post("/restart")
def restart():
    config.update({"setup_done": False})
    return {"ok": True}
