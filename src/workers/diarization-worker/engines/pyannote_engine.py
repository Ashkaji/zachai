"""Speaker diarization engine backed by pyannote-audio (pyannote/speaker-diarization-community-1)."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("diarization-worker.pyannote")

_pipeline: Any = None


def _get_pipeline() -> Any:
    global _pipeline
    if _pipeline is not None:
        return _pipeline

    from pyannote.audio import Pipeline

    model_id = os.environ.get(
        "PYANNOTE_MODEL_ID", "pyannote/speaker-diarization-3.1"
    )
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")

    local_path = os.environ.get("PYANNOTE_LOCAL_PATH", "")
    if local_path and Path(local_path).is_dir():
        logger.info("loading pyannote pipeline from local path: %s", local_path)
        _pipeline = Pipeline.from_pretrained(local_path)
    else:
        if not token:
            raise RuntimeError(
                "HF_TOKEN is required for gated pyannote models. "
                "Set HF_TOKEN in .env after accepting terms at "
                "https://huggingface.co/pyannote/speaker-diarization-3.1"
            )
        logger.info("loading pyannote pipeline: %s", model_id)
        # pyannote.audio>=4 expects `token=...` (older releases used use_auth_token)
        _pipeline = Pipeline.from_pretrained(model_id, token=token)

    import torch

    device = os.environ.get("DIARIZATION_DEVICE", "cpu")
    _pipeline = _pipeline.to(torch.device(device))
    logger.info("pyannote pipeline ready on device=%s", device)
    return _pipeline


def diarize(audio_path: str | Path) -> list[dict[str, Any]]:
    """Run speaker diarization on a WAV file. Returns speaker turns."""
    pipe = _get_pipeline()
    output = pipe(str(audio_path))

    turns: list[dict[str, Any]] = []
    for turn, _, speaker in output.itertracks(yield_label=True):
        turns.append(
            {
                "start": round(turn.start, 3),
                "end": round(turn.end, 3),
                "speaker": speaker,
            }
        )
    return turns
