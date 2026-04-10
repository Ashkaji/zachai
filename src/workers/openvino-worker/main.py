import asyncio
import json
import logging
import math
import os
from collections import Counter
import shutil
import subprocess
import threading
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import anyio
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from minio import Minio
from minio.error import S3Error
from pydantic import BaseModel

# Story 8.1 Traceability
request_id_var: ContextVar[str] = ContextVar("request_id", default="no-request-id")

class RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = request_id_var.get()
        return True

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(request_id)s] %(name)s: %(message)s"
)
logger = logging.getLogger("openvino-worker")
logger.addFilter(RequestIdFilter())

app = FastAPI(title="openvino-worker")

@app.middleware("http")
async def add_request_id(request: Request, call_next):
    rid = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    token = request_id_var.set(rid)
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response
    finally:
        request_id_var.reset(token)

TMP_BASE = Path("/tmp/openvino-worker")
MAX_FILE_SIZE = 1024 * 1024 * 1024
MAX_POINTER_OBJECT_BYTES = 64 * 1024
MAX_INFER_TIMEOUT_SECONDS = 86400 * 7
CONFIDENCE_FALLBACK_FIXED = os.environ.get("CONFIDENCE_FALLBACK_FIXED", "true").lower() == "true"

MODEL_REGISTRY_BUCKET = os.environ.get("MODEL_REGISTRY_BUCKET", "models")
MODEL_POINTER_KEY = os.environ.get("MODEL_POINTER_KEY", "latest")
WHISPER_MODEL_CACHE_DIR = Path(
    os.environ.get("WHISPER_MODEL_CACHE_DIR", "/var/cache/openvino-models")
)


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


def _parse_poll_interval_seconds(env_val: str | None) -> int:
    if env_val is None or not str(env_val).strip():
        return 60
    raw = str(env_val).strip()
    try:
        value = int(raw, 10)
    except ValueError as exc:
        raise RuntimeError(
            f"Invalid MODEL_POLL_INTERVAL_SECONDS={env_val!r}; expected positive integer seconds"
        ) from exc
    if value <= 0:
        raise RuntimeError(
            f"Invalid MODEL_POLL_INTERVAL_SECONDS={value}; must be positive"
        )
    if value > 86400:
        raise RuntimeError(
            "Invalid MODEL_POLL_INTERVAL_SECONDS; must be <= 86400 (1 day)"
        )
    return value


_DEFAULT_MAX_MODEL_TREE_TOTAL_BYTES = 10 * 1024 * 1024 * 1024


def _parse_max_model_tree_total_bytes(env_val: str | None) -> int:
    """Sum of object sizes allowed when syncing a model prefix from MinIO."""
    if env_val is None or not str(env_val).strip():
        return _DEFAULT_MAX_MODEL_TREE_TOTAL_BYTES
    raw = str(env_val).strip()
    try:
        value = int(raw, 10)
    except ValueError as exc:
        raise RuntimeError(
            f"Invalid MAX_MODEL_TREE_TOTAL_BYTES={env_val!r}; expected positive integer bytes"
        ) from exc
    if value <= 0:
        raise RuntimeError(
            "Invalid MAX_MODEL_TREE_TOTAL_BYTES; must be positive"
        )
    return value


INFER_TIMEOUT_SECONDS = _parse_infer_timeout_seconds(os.environ.get("INFER_TIMEOUT_SECONDS"))
MODEL_POLL_INTERVAL_SECONDS = _parse_poll_interval_seconds(
    os.environ.get("MODEL_POLL_INTERVAL_SECONDS")
)
MAX_MODEL_TREE_TOTAL_BYTES = _parse_max_model_tree_total_bytes(
    os.environ.get("MAX_MODEL_TREE_TOTAL_BYTES")
)

required_env = ["MINIO_ENDPOINT", "MINIO_ACCESS_KEY", "MINIO_SECRET_KEY"]
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
        logger.warning(
            "OPENVINO_WORKER_TEST_MODE ignored in production (ENVIRONMENT=%s)",
            os.environ.get("ENVIRONMENT"),
        )
        return False
    return True


def normalize_pointer_content(raw: str) -> str:
    """Normalize registry pointer body to a version prefix used for MinIO list."""
    text = raw.strip().strip('"').strip("'").strip()
    if not text:
        raise ValueError("empty model registry pointer")
    return text if text.endswith("/") else text + "/"


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
            raise RuntimeError(f"Model path does not exist: {self.model_path}")

        self.pipeline = ov_genai.WhisperPipeline(self.model_path, self.device)
        self.model_loaded = True

    def retire_pipeline(self) -> None:
        """Best-effort release of native handles; safe if another thread still holds the engine."""
        self.pipeline = None
        self.model_loaded = False

    def transcribe(self, input_path: Path) -> list[dict[str, Any]]:
        if not self.model_loaded and not _test_mode_enabled():
            raise RuntimeError("Model not loaded")

        if _test_mode_enabled():
            return [
                {
                    "start": 0.0,
                    "end": 1.0,
                    "text": "test segment",
                    "confidence": 0.75,
                    "hallucination_risk": 0.0,
                }
            ]

        assert self.pipeline is not None
        import numpy as np
        import wave

        with wave.open(str(input_path), "rb") as wf:
            frames = wf.readframes(wf.getnframes())
            samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0

        result = self.pipeline.generate(samples, return_timestamps=True)

        chunks = getattr(result, "chunks", None)
        if chunks:
            segments: list[dict[str, Any]] = []
            for chunk in chunks:
                text = str(getattr(chunk, "text", "")).strip()
                start_ts = float(getattr(chunk, "start_ts", 0.0))
                end_ts = float(getattr(chunk, "end_ts", 0.0))
                duration = max(0.0, end_ts - start_ts)
                base_conf = _extract_confidence(chunk)
                risk = _segment_hallucination_risk(text, duration_sec=duration)
                conf = round(
                    base_conf * max(0.05, 1.0 - min(1.0, risk * 1.15)),
                    4,
                )
                segments.append(
                    {
                        "start": start_ts,
                        "end": end_ts,
                        "text": text,
                        "confidence": conf,
                        "hallucination_risk": round(risk, 4),
                    }
                )
            return segments

        texts = getattr(result, "texts", None)
        if texts and texts[0].strip():
            full_text = texts[0].strip()
            duration = float(len(samples)) / 16000.0
            risk = _segment_hallucination_risk(full_text, duration_sec=duration)
            base_conf = 0.75 if CONFIDENCE_FALLBACK_FIXED else 0.0
            conf = round(
                base_conf * max(0.05, 1.0 - min(1.0, risk * 1.15)),
                4,
            )
            return [
                {
                    "start": 0.0,
                    "end": duration,
                    "text": full_text,
                    "confidence": conf,
                    "hallucination_risk": round(risk, 4),
                }
            ]

        return []


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


def _detect_repetition_ratio(text: str) -> float:
    """Return 0.0 (no repetition) to 1.0 (entirely repetitive).

    Uses overlapping n-gram analysis to catch Whisper hallucination loops
    like "helaa, yw helaa, yw helaa, yw ...".
    """
    words = text.lower().split()
    if len(words) < 6:
        return 0.0
    ngram_size = 3
    ngrams = [tuple(words[i : i + ngram_size]) for i in range(len(words) - ngram_size + 1)]
    if not ngrams:
        return 0.0
    counts = Counter(ngrams)
    repeated = sum(c - 1 for c in counts.values() if c > 1)
    return min(1.0, repeated / len(ngrams))


def _word_domination_ratio(text: str) -> float:
    """High when one token repeats (e.g. stutter / garbage loops) without long n-grams."""
    words = text.lower().split()
    if len(words) < 6:
        return 0.0
    top_count = Counter(words).most_common(1)[0][1]
    ratio = top_count / len(words)
    if ratio <= 0.35:
        return 0.0
    return min(1.0, (ratio - 0.35) / 0.65)


def _segment_hallucination_risk(text: str, duration_sec: float = 0.0) -> float:
    """Heuristic 0–1 risk for this segment only (OpenVINO GenAI exposes no token logprobs).

    Combines local n-gram repetition, single-word dominance, and implausibly empty
    stretches for the interval duration.
    """
    ngram_r = _detect_repetition_ratio(text)
    dom_r = _word_domination_ratio(text)
    risk = max(ngram_r, dom_r)
    stripped = text.strip()
    if duration_sec > 2.5 and len(stripped) < 8:
        risk = max(risk, 0.45)
    cps = len(stripped) / duration_sec if duration_sec > 0.1 else 0.0
    if duration_sec > 4.0 and cps > 0 and cps < 2.0:
        risk = max(risk, 0.35)
    return min(1.0, risk)


model_lock = threading.Lock()


@dataclass
class WorkerState:
    engine: WhisperEngine | None = None
    model_source: str = "unknown"  # registry | local
    active_model_prefix: str | None = None
    registry_pointer_etag: str | None = None
    last_poll_utc: str | None = None
    last_reload_ok: bool = True
    reload_failures: int = 0
    last_applied_etag: str | None = None
    last_applied_body: str | None = None
    retired_engines: list[WhisperEngine] = field(default_factory=list)


state = WorkerState()


def _s3_not_found(exc: S3Error) -> bool:
    code = str(getattr(exc, "code", ""))
    return code == "NoSuchKey" or "NoSuchKey" in str(exc)


def _error(status: int, message: str, code: str | None = None) -> JSONResponse:
    body = {"error": message}
    if code:
        body["code"] = code
    return JSONResponse(status_code=status, content=body)


def fetch_registry_pointer(
    client: Minio, bucket: str, key: str
) -> tuple[str, str | None] | None:
    """Return (body, etag) or None if object missing."""
    try:
        st = client.stat_object(bucket, key)
        if st.size > MAX_POINTER_OBJECT_BYTES:
            raise RuntimeError(
                f"registry pointer {bucket}/{key} too large ({st.size} bytes)"
            )
        response = client.get_object(bucket, key)
        try:
            body_bytes = response.read()
        finally:
            response.close()
            response.release_conn()
        etag = getattr(st, "etag", None)
        return body_bytes.decode("utf-8"), etag
    except S3Error as exc:
        if _s3_not_found(exc):
            return None
        raise


def _local_path_relative_to_prefix(object_name: str, prefix: str) -> str:
    pfx = prefix.rstrip("/") + "/"
    if not object_name.startswith(pfx):
        raise RuntimeError(f"object {object_name!r} not under prefix {pfx!r}")
    return object_name[len(pfx) :]


def sync_model_prefix_to_dir(
    client: Minio, bucket: str, prefix: str, dest_dir: Path
) -> None:
    """
    Download all objects under prefix into dest_dir preserving relative paths.
    Enforces per-object MAX_FILE_SIZE and total MAX_MODEL_TREE_TOTAL_BYTES.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    total = 0
    count = 0
    for obj in client.list_objects(bucket, prefix=prefix, recursive=True):
        if getattr(obj, "is_dir", False):
            continue
        oname = obj.object_name
        if not oname:
            continue
        rel = _local_path_relative_to_prefix(oname, prefix)
        if not rel or rel.endswith("/"):
            continue
        try:
            st = client.stat_object(bucket, oname)
        except S3Error as exc:
            if _s3_not_found(exc):
                continue
            raise
        if st.size > MAX_FILE_SIZE:
            raise RuntimeError(
                f"object {oname} exceeds MAX_FILE_SIZE ({st.size} > {MAX_FILE_SIZE})"
            )
        total += st.size
        if total > MAX_MODEL_TREE_TOTAL_BYTES:
            raise RuntimeError(
                f"model tree exceeds MAX_MODEL_TREE_TOTAL_BYTES ({MAX_MODEL_TREE_TOTAL_BYTES})"
            )
        out_path = dest_dir / rel
        out_path.parent.mkdir(parents=True, exist_ok=True)
        client.fget_object(bucket, oname, str(out_path))
        count += 1
    if count == 0:
        raise RuntimeError(f"no objects downloaded for prefix {prefix!r}")


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def try_load_from_registry(
    client: Minio, device: str, cache_root: Path
) -> tuple[WhisperEngine, str, str | None] | None:
    raw = fetch_registry_pointer(client, MODEL_REGISTRY_BUCKET, MODEL_POINTER_KEY)
    if raw is None:
        return None
    body, etag = raw
    try:
        norm_prefix = normalize_pointer_content(body)
    except ValueError as exc:
        logger.warning("invalid registry pointer body: %s", exc)
        return None

    staging = cache_root / f"sync-{uuid.uuid4().hex}"
    try:
        sync_model_prefix_to_dir(client, MODEL_REGISTRY_BUCKET, norm_prefix, staging)
        eng = WhisperEngine(str(staging), device)
        eng.load()
        return eng, norm_prefix, etag
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def try_load_from_local_path(model_path: str, device: str) -> WhisperEngine | None:
    path = model_path.strip()
    if not path or not Path(path).exists():
        return None
    eng = WhisperEngine(path, device)
    eng.load()
    return eng


def _skip_registry_bootstrap() -> bool:
    """Avoid MinIO network I/O at container start (pytest / air-gapped dev)."""
    return os.environ.get("OPENVINO_REGISTRY_SKIP_BOOTSTRAP", "").lower() in (
        "1",
        "true",
        "yes",
    )


def initial_load_sync() -> None:
    device = os.environ.get("OV_DEVICE", "CPU")
    cache_root = WHISPER_MODEL_CACHE_DIR
    cache_root.mkdir(parents=True, exist_ok=True)

    reg = None
    if not _skip_registry_bootstrap():
        try:
            reg = try_load_from_registry(minio_client, device, cache_root)
        except Exception as exc:
            logger.warning(
                "registry bootstrap failed (%s/%s): %s — falling back if possible",
                MODEL_REGISTRY_BUCKET,
                MODEL_POINTER_KEY,
                exc,
            )
            reg = None
    else:
        logger.info(
            "skipping registry bootstrap (OPENVINO_REGISTRY_SKIP_BOOTSTRAP) — local path only"
        )

    if reg:
        eng, prefix, etag = reg
        with model_lock:
            state.engine = eng
            state.model_source = "registry"
            state.active_model_prefix = prefix.rstrip("/")
            state.registry_pointer_etag = etag
            state.last_applied_etag = etag
            state.last_applied_body = prefix
            state.last_reload_ok = True
        logger.info(
            "loaded whisper model from registry prefix=%s etag=%s",
            prefix,
            etag,
        )
        return

    local_path = os.environ.get("WHISPER_MODEL_PATH", "")
    eng = try_load_from_local_path(local_path, device)
    if eng:
        with model_lock:
            state.engine = eng
            state.model_source = "local"
            state.active_model_prefix = None
            state.registry_pointer_etag = None
            state.last_applied_etag = None
            state.last_applied_body = None
            state.last_reload_ok = True
        logger.info("loaded whisper model from local path=%s", eng.model_path)
        return

    raise RuntimeError(
        "Cannot start openvino-worker: registry pointer missing or invalid, and "
        "WHISPER_MODEL_PATH is unset or not a directory on disk. Seed models/latest "
        "in MinIO or mount WHISPER_MODEL_PATH."
    )


def poll_once_sync() -> None:
    """Background poll: detect pointer change and hot-swap engine. Never raises."""
    state.last_poll_utc = _utc_iso()
    try:
        raw = fetch_registry_pointer(
            minio_client, MODEL_REGISTRY_BUCKET, MODEL_POINTER_KEY
        )
    except Exception as exc:
        logger.warning(
            "registry poll read failed bucket=%s key=%s: %s",
            MODEL_REGISTRY_BUCKET,
            MODEL_POINTER_KEY,
            exc,
        )
        state.last_reload_ok = False
        state.reload_failures += 1
        return

    if raw is None:
        return

    body, etag = raw
    try:
        norm_prefix = normalize_pointer_content(body)
    except ValueError as exc:
        logger.warning("registry poll: bad pointer body: %s", exc)
        state.last_reload_ok = False
        state.reload_failures += 1
        return

    state.registry_pointer_etag = etag
    if (
        etag == state.last_applied_etag
        and norm_prefix == state.last_applied_body
    ):
        state.last_reload_ok = True
        return

    device = os.environ.get("OV_DEVICE", "CPU")
    staging = WHISPER_MODEL_CACHE_DIR / f"sync-{uuid.uuid4().hex}"
    try:
        sync_model_prefix_to_dir(
            minio_client, MODEL_REGISTRY_BUCKET, norm_prefix, staging
        )
        new_eng = WhisperEngine(str(staging), device)
        new_eng.load()
    except Exception as exc:
        shutil.rmtree(staging, ignore_errors=True)
        logger.exception(
            "model hot-reload failed prefix=%s (keeping previous model): %s",
            norm_prefix,
            exc,
        )
        state.last_reload_ok = False
        state.reload_failures += 1
        return

    old_eng: WhisperEngine | None = None
    with model_lock:
        old_eng = state.engine
        state.engine = new_eng
        state.model_source = "registry"
        state.active_model_prefix = norm_prefix.rstrip("/")
        state.last_applied_etag = etag
        state.last_applied_body = norm_prefix
        state.last_reload_ok = True

    logger.info(
        "hot-reloaded whisper model active_prefix=%s etag=%s",
        state.active_model_prefix,
        etag,
    )

    if old_eng is not None:
        old_eng.retire_pipeline()
        state.retired_engines.append(old_eng)


async def poll_loop() -> None:
    while True:
        await asyncio.sleep(MODEL_POLL_INTERVAL_SECONDS)
        await anyio.to_thread.run_sync(poll_once_sync)


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
    WHISPER_MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        await anyio.to_thread.run_sync(initial_load_sync)
    except Exception as exc:
        logger.exception("Model loading failed")
        raise RuntimeError(f"Failed to load whisper model: {exc}") from exc
    app.state.registry_poll_task = asyncio.create_task(poll_loop())


@app.on_event("shutdown")
async def shutdown_event() -> None:
    task = getattr(app.state, "registry_poll_task", None)
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


@app.get("/health")
def health() -> dict[str, Any]:
    with model_lock:
        eng = state.engine
        return {
            "status": "ok",
            "model_loaded": bool(eng and eng.model_loaded),
            "active_model_prefix": state.active_model_prefix,
            "registry_pointer_etag": state.registry_pointer_etag,
            "last_poll_utc": state.last_poll_utc,
            "last_reload_ok": state.last_reload_ok,
            "reload_failures": state.reload_failures,
            "model_source": state.model_source,
        }


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

        def _infer() -> list[dict[str, Any]]:
            with model_lock:
                eng = state.engine
                if eng is None:
                    raise RuntimeError("Model not available")
                return eng.transcribe(input_path)

        try:
            with anyio.fail_after(INFER_TIMEOUT_SECONDS):
                segments = await anyio.to_thread.run_sync(_infer, abandon_on_cancel=False)
        except TimeoutError:
            return _error(504, "Inference timed out", "ERR_ASR_01")
        except Exception as exc:
            return _error(500, f"Inference failed: {exc}", "ERR_ASR_01")

        base: dict[str, Any] = {"segments": segments}
        if not segments:
            return base

        risks = [
            float(s["hallucination_risk"])
            for s in segments
            if isinstance(s.get("hallucination_risk"), (int, float))
        ]
        if risks:
            base["hallucination_max_risk"] = round(max(risks), 4)
            base["hallucination_mean_risk"] = round(sum(risks) / len(risks), 4)
        return base
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)
