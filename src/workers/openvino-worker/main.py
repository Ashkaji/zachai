import json
import logging
import math
import os
import shutil
import subprocess
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
logger = logging.getLogger("openvino-worker")

app = FastAPI(title="openvino-worker")

TMP_BASE = Path("/tmp/openvino-worker")
MAX_FILE_SIZE = 1024 * 1024 * 1024
MAX_INFER_TIMEOUT_SECONDS = 86400 * 7
CONFIDENCE_FALLBACK_FIXED = os.environ.get("CONFIDENCE_FALLBACK_FIXED", "false").lower() == "true"


def _parse_infer_timeout_seconds(env_val: str | None) -> int:
    if env_val is None or not str(env_val).strip():
        return 900
    raw = str(env_val).strip()
    try:
        value = int(raw, 10)
    except ValueError as exc:
        raise RuntimeError(
            f"Invalid INFER_TIMEOUT_SECONDS={env_val!r}; expected positive integer seconds"
        ) from exc
    if value <= 0:
        raise RuntimeError(
            f"Invalid INFER_TIMEOUT_SECONDS={value}; must be positive"
        )
    if value > MAX_INFER_TIMEOUT_SECONDS:
        raise RuntimeError(
            f"Invalid INFER_TIMEOUT_SECONDS={value}; must be <= {MAX_INFER_TIMEOUT_SECONDS} (7 days)"
        )
    return value


INFER_TIMEOUT_SECONDS = _parse_infer_timeout_seconds(os.environ.get("INFER_TIMEOUT_SECONDS"))

required_env = ["MINIO_ENDPOINT", "MINIO_ACCESS_KEY", "MINIO_SECRET_KEY", "WHISPER_MODEL_PATH"]
missing = [env for env in required_env if not os.environ.get(env)]
if missing:
    raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

minio_client = Minio(
    endpoint=os.environ["MINIO_ENDPOINT"],
    access_key=os.environ["MINIO_ACCESS_KEY"],
    secret_key=os.environ["MINIO_SECRET_KEY"],
    secure=os.environ.get("MINIO_SECURE", "false").lower() == "true",
)


def _is_production_environment() -> bool:
    env = os.environ.get("ENVIRONMENT", "development").lower().strip()
    return env in ("production", "prod")


def _test_mode_enabled() -> bool:
    if os.environ.get("OPENVINO_WORKER_TEST_MODE", "false").lower() != "true":
        return False
    if _is_production_environment():
        logger.warning("OPENVINO_WORKER_TEST_MODE ignored in production (ENVIRONMENT=%s)", os.environ.get("ENVIRONMENT"))
        return False
    return True


class TranscribeRequest(BaseModel):
    input_bucket: str
    input_key: str


class WhisperEngine:
    def __init__(self, model_path: str, device: str):
        self.model_path = model_path
        self.device = device
        self.pipeline = None
        self.model_loaded = False

    def load(self) -> None:
        if _test_mode_enabled():
            self.model_loaded = True
            return

        try:
            import openvino_genai as ov_genai  # local import to keep module import lightweight
        except Exception as exc:
            raise RuntimeError(f"openvino_genai import failed: {exc}") from exc

        if not Path(self.model_path).exists():
            raise RuntimeError(f"WHISPER_MODEL_PATH does not exist: {self.model_path}")

        self.pipeline = ov_genai.WhisperPipeline(self.model_path, self.device)
        self.model_loaded = True

    def transcribe(self, input_path: Path) -> list[dict[str, Any]]:
        if not self.model_loaded:
            raise RuntimeError("Model not loaded")

        if _test_mode_enabled():
            return [{"start": 0.0, "end": 1.0, "text": "test segment", "confidence": 0.75}]

        assert self.pipeline is not None
        result = self.pipeline.generate(str(input_path))

        segments_raw = getattr(result, "segments", None)
        if segments_raw is None:
            return []

        segments: list[dict[str, Any]] = []
        for segment in segments_raw:
            text = str(getattr(segment, "text", "")).strip()
            confidence = _extract_confidence(segment)
            segments.append(
                {
                    "start": float(getattr(segment, "start", 0.0)),
                    "end": float(getattr(segment, "end", 0.0)),
                    "text": text,
                    "confidence": confidence,
                }
            )
        return segments


def _extract_confidence(segment: Any) -> float:
    conf = getattr(segment, "confidence", None)
    if conf is not None:
        try:
            return max(0.0, min(1.0, float(conf)))
        except (TypeError, ValueError):
            pass

    logprob = getattr(segment, "avg_logprob", None)
    if logprob is not None:
        try:
            lp = float(logprob)
            lp = max(-30.0, min(0.0, lp))
            return max(0.0, min(1.0, math.exp(lp)))
        except (TypeError, ValueError):
            pass

    if CONFIDENCE_FALLBACK_FIXED:
        return 0.75
    return 0.0


engine = WhisperEngine(
    model_path=os.environ["WHISPER_MODEL_PATH"],
    device=os.environ.get("OV_DEVICE", "CPU"),
)


def _error(status: int, message: str, code: str | None = None) -> JSONResponse:
    body = {"error": message}
    if code:
        body["code"] = code
    return JSONResponse(status_code=status, content=body)


def _s3_not_found(exc: S3Error) -> bool:
    code = str(getattr(exc, "code", ""))
    return code == "NoSuchKey" or "NoSuchKey" in str(exc)


def _validate_wav_format(input_path: Path) -> tuple[bool, str]:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=codec_name,sample_rate,channels",
        "-of",
        "json",
        str(input_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except Exception as exc:
        return False, f"ffprobe failed: {exc}"

    if result.returncode != 0:
        return False, f"ffprobe failed: {result.stderr.strip() or 'unknown error'}"

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return False, f"ffprobe JSON parse failed: {exc}"

    streams = data.get("streams") or []
    if not streams:
        return False, "No audio stream found"

    stream = streams[0]
    codec_name = stream.get("codec_name")
    sample_rate = stream.get("sample_rate")
    channels = stream.get("channels")

    if codec_name != "pcm_s16le":
        return False, f"Invalid codec '{codec_name}', expected pcm_s16le"
    if str(sample_rate) != "16000":
        return False, f"Invalid sample rate '{sample_rate}', expected 16000"
    if str(channels) != "1":
        return False, f"Invalid channel count '{channels}', expected 1"
    return True, ""


@app.on_event("startup")
async def startup_event() -> None:
    if TMP_BASE.exists():
        logger.info("Cleaning up %s", TMP_BASE)
        shutil.rmtree(TMP_BASE, ignore_errors=True)
    TMP_BASE.mkdir(parents=True, exist_ok=True)
    try:
        await anyio.to_thread.run_sync(engine.load)
    except Exception as exc:
        logger.exception("Model loading failed")
        raise RuntimeError(f"Failed to load whisper model: {exc}") from exc


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "model_loaded": engine.model_loaded}


@app.post("/transcribe")
async def transcribe(req: TranscribeRequest) -> Any:
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
            if _s3_not_found(exc):
                return _error(404, f"MinIO object not found: {req.input_bucket}/{req.input_key}")
            return _error(500, f"MinIO stat failed: {exc}")
        except Exception as exc:
            return _error(500, f"MinIO stat failed: {exc}")

        try:
            await anyio.to_thread.run_sync(
                minio_client.fget_object, req.input_bucket, req.input_key, str(input_path)
            )
        except S3Error as exc:
            if _s3_not_found(exc):
                return _error(404, f"MinIO object not found: {req.input_bucket}/{req.input_key}")
            return _error(500, f"MinIO download failed: {exc}")
        except Exception as exc:
            return _error(500, f"MinIO download failed: {exc}")

        if not input_path.exists():
            return _error(404, "Downloaded file not found on disk")

        ok, reason = await anyio.to_thread.run_sync(_validate_wav_format, input_path)
        if not ok:
            return _error(400, f"Invalid audio format: {reason}")

        try:
            with anyio.fail_after(INFER_TIMEOUT_SECONDS):
                segments = await anyio.to_thread.run_sync(
                    engine.transcribe, input_path, abandon_on_cancel=False
                )
        except TimeoutError:
            return _error(504, "Inference timed out", "ERR_ASR_01")
        except Exception as exc:
            return _error(500, f"Inference failed: {exc}", "ERR_ASR_01")

        if not segments:
            return {"segments": []}

        return {"segments": segments}
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)
