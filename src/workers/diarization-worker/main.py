"""
ZachAI — Speaker Diarization Worker.

FastAPI microservice that identifies *who spoke when* in an audio file.
Two engines available (selectable via env or per-request):
  - pyannote : high-quality PyTorch pipeline (gated HF model, heavier on CPU)
  - sherpa-onnx : lightweight ONNX pipeline (no HF gate, CPU-friendly)

The ML bridge calls ``POST /diarize`` after obtaining ASR segments from
``openvino-worker``, then merges the two to produce per-speaker annotated
predictions for Label Studio.
"""
from __future__ import annotations

import logging
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

import anyio
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from minio import Minio
from minio.error import S3Error
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("diarization-worker")

app = FastAPI(title="diarization-worker")

TMP_BASE = Path("/tmp/diarization-worker")
MAX_FILE_SIZE = 1024 * 1024 * 1024  # 1 GiB

DEFAULT_ENGINE = os.environ.get("DIARIZATION_ENGINE", "pyannote")
def _parse_max_speaker_labels(raw: str | None) -> int:
    if raw is None or not str(raw).strip():
        return 10
    try:
        value = int(str(raw).strip(), 10)
    except ValueError as exc:
        raise RuntimeError(
            f"Invalid MAX_SPEAKER_LABELS={raw!r}; expected integer >= 1"
        ) from exc
    if value < 1:
        raise RuntimeError("MAX_SPEAKER_LABELS must be >= 1")
    return value


MAX_SPEAKER_LABELS = _parse_max_speaker_labels(os.environ.get("MAX_SPEAKER_LABELS", "10"))

TEST_MODE = (
    os.environ.get("DIARIZATION_TEST_MODE", "false").lower() == "true"
    and os.environ.get("ENVIRONMENT", "development").lower()
    not in ("production", "prod")
)

MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "minioadmin")
MINIO_SECURE = os.environ.get("MINIO_SECURE", "false").lower() == "true"

minio_client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=MINIO_SECURE,
)


def _parse_timeout_seconds(raw: str | None) -> int:
    if raw is None or not str(raw).strip():
        return 900
    try:
        value = int(str(raw).strip(), 10)
    except ValueError as exc:
        raise RuntimeError(
            f"Invalid DIARIZATION_TIMEOUT_SECONDS={raw!r}; expected positive integer"
        ) from exc
    if value <= 0:
        raise RuntimeError("DIARIZATION_TIMEOUT_SECONDS must be > 0")
    if value > 86_400 * 7:
        raise RuntimeError("DIARIZATION_TIMEOUT_SECONDS must be <= 604800 (7 days)")
    return value


DIARIZATION_TIMEOUT_SECONDS = _parse_timeout_seconds(
    os.environ.get("DIARIZATION_TIMEOUT_SECONDS", "900")
)


class DiarizeRequest(BaseModel):
    input_bucket: str
    input_key: str
    engine: str | None = None


def _error(status: int, msg: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": msg})


def _run_diarization(audio_path: Path, engine: str) -> list[dict[str, Any]]:
    if TEST_MODE:
        return [
            {"start": 0.0, "end": 2.5, "speaker": "SPEAKER_00"},
            {"start": 2.5, "end": 5.0, "speaker": "SPEAKER_01"},
        ]

    if engine == "pyannote":
        from engines.pyannote_engine import diarize
    elif engine == "sherpa-onnx":
        from engines.sherpa_engine import diarize
    else:
        raise ValueError(f"Unknown diarization engine: {engine!r}")

    return diarize(audio_path)


def _normalize_speaker_ids(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remap arbitrary speaker IDs (e.g. pyannote's SPEAKER_00, SPEAKER_01)
    to sequential SPEAKER_XX starting from 00."""
    seen: dict[str, int] = {}
    for t in turns:
        raw = t["speaker"]
        if raw not in seen:
            seen[raw] = len(seen)
        mapped = seen[raw]
        if mapped >= MAX_SPEAKER_LABELS:
            # Keep predictions valid against Label Studio schema (SPEAKER_00..SPEAKER_09 by default).
            mapped = MAX_SPEAKER_LABELS - 1
        t["speaker"] = f"SPEAKER_{mapped:02d}"
    return turns


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "default_engine": DEFAULT_ENGINE,
        "test_mode": TEST_MODE,
        "max_speaker_labels": MAX_SPEAKER_LABELS,
        "timeout_seconds": DIARIZATION_TIMEOUT_SECONDS,
    }


@app.post("/diarize")
async def diarize(req: DiarizeRequest) -> Any:
    engine = req.engine or DEFAULT_ENGINE
    if engine not in ("pyannote", "sherpa-onnx"):
        return _error(400, f"Unknown diarization engine: {engine!r}. Allowed: pyannote, sherpa-onnx")
    job_id = str(uuid.uuid4())
    job_dir = TMP_BASE / job_id
    try:
        job_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return _error(500, f"Failed to create job directory: {exc}")

    input_path = job_dir / "input.wav"
    try:
        try:
            stat = await anyio.to_thread.run_sync(
                minio_client.stat_object, req.input_bucket, req.input_key
            )
            if stat.size > MAX_FILE_SIZE:
                return _error(413, f"File too large: {stat.size} bytes")
        except S3Error as exc:
            code = getattr(exc, "code", "")
            if code in ("NoSuchKey", "NoSuchBucket"):
                return _error(404, f"MinIO object not found: {req.input_bucket}/{req.input_key}")
            return _error(500, f"MinIO stat failed: {exc}")

        await anyio.to_thread.run_sync(
            minio_client.fget_object, req.input_bucket, req.input_key, str(input_path)
        )

        def _infer() -> list[dict[str, Any]]:
            return _run_diarization(input_path, engine)

        try:
            with anyio.fail_after(DIARIZATION_TIMEOUT_SECONDS):
                turns = await anyio.to_thread.run_sync(_infer, abandon_on_cancel=False)
        except TimeoutError:
            return _error(504, "Diarization timed out")
        except Exception as exc:
            logger.exception("Diarization failed")
            return _error(500, f"Diarization failed: {exc}")

        turns = _normalize_speaker_ids(turns)

        unique_speakers = sorted({t["speaker"] for t in turns})
        return {
            "speakers": turns,
            "num_speakers": len(unique_speakers),
            "engine": engine,
        }
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)
