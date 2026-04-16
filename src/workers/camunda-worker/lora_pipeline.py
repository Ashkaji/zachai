"""
ZachAI — LoRA fine-tuning pipeline external tasks (Story 4.4).
Topics: lora-dataset-prep, lora-training, lora-wer-eval, lora-registry-publish
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import random
import re
import uuid
from datetime import datetime, timezone
from typing import Any

import asyncpg
import httpx
from jiwer import wer
from minio import Minio
from minio.error import S3Error

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

CAMUNDA_REST_URL = os.environ.get("CAMUNDA_REST_URL", "http://camunda7:8080/engine-rest")
WORKER_ID = "zachai-lora-pipeline-worker"
MAX_RETRIES = 3

DB_USER = os.environ.get("POSTGRES_USER", "zachai")
DB_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "zachai")
DB_NAME = os.environ.get("POSTGRES_DB", "zachai")
DB_HOST = os.environ.get("DB_HOST", "postgres")

MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "")
MINIO_SECURE = os.environ.get("MINIO_SECURE", "false").lower() == "true"

GOLDEN_SET_BUCKET = (os.environ.get("GOLDEN_SET_BUCKET") or "golden-set").strip() or "golden-set"
MODEL_REGISTRY_BUCKET = (os.environ.get("MODEL_REGISTRY_BUCKET") or "models").strip() or "models"
MODEL_POINTER_KEY = (os.environ.get("MODEL_POINTER_KEY") or "latest").strip() or "latest"

FASTAPI_INTERNAL_URL = os.environ.get("FASTAPI_INTERNAL_URL", "http://fastapi:8000").rstrip("/")
MODEL_READY_CALLBACK_SECRET = (os.environ.get("MODEL_READY_CALLBACK_SECRET") or "").strip()

_raw_max_wer = os.environ.get("LORA_MAX_WER", "0.02")
try:
    LORA_MAX_WER: float = float(_raw_max_wer)
except ValueError:
    LORA_MAX_WER = 0.02

_raw_eval_frac = os.environ.get("LORA_EVAL_FRACTION", "0.2")
try:
    LORA_EVAL_FRACTION: float = float(_raw_eval_frac)
except ValueError:
    LORA_EVAL_FRACTION = 0.2

_raw_seed = os.environ.get("LORA_SPLIT_SEED", "42")
try:
    LORA_SPLIT_SEED: int = int(_raw_seed)
except ValueError:
    LORA_SPLIT_SEED = 42

ENVIRONMENT = os.environ.get("ENVIRONMENT", "development").lower().strip()


def _is_production() -> bool:
    return ENVIRONMENT in ("production", "prod")


_raw_stub = os.environ.get("LORA_TRAINING_STUB")
if _raw_stub is None or str(_raw_stub).strip() == "":
    # Unset/empty: stub in non-prod (local Docker), off in production — avoids ENVIRONMENT=production
    # with a compose-only default of stub=true.
    LORA_TRAINING_STUB = not _is_production()
else:
    LORA_TRAINING_STUB = _raw_stub.strip().lower() == "true"

LORA_STUB_SOURCE_PREFIX = (os.environ.get("LORA_STUB_SOURCE_PREFIX") or "").strip()


def _validate_worker_env() -> None:
    if _is_production() and LORA_TRAINING_STUB:
        raise ValueError("LORA_TRAINING_STUB must not be enabled in production")
    if not MINIO_ACCESS_KEY or not MINIO_SECRET_KEY:
        raise ValueError("MINIO_ACCESS_KEY and MINIO_SECRET_KEY are required for lora_pipeline worker")
    if not MODEL_READY_CALLBACK_SECRET:
        raise ValueError("MODEL_READY_CALLBACK_SECRET is required for lora_registry_publish")


minio_client = Minio(
    endpoint=MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=MINIO_SECURE,
)


def normalize_pointer_content(raw: str) -> str:
    """Match openvino-worker: pointer body is a version prefix with trailing slash."""
    text = raw.strip().strip('"').strip("'").strip()
    if not text:
        raise ValueError("empty model registry pointer")
    return text if text.endswith("/") else text + "/"


def train_eval_split_indices(n: int, eval_fraction: float, seed: int) -> tuple[set[int], set[int]]:
    """
    Deterministic shuffle of row indices 0..n-1.
    Policy: hold out round(n * eval_fraction) rows for eval, at least 0, at most n-1 when n > 1
    (keeps ≥1 training row). Documented in README.
    """
    if n <= 0:
        return set(), set()
    order = list(range(n))
    rng = random.Random(seed)
    rng.shuffle(order)
    n_eval = int(round(n * eval_fraction))
    if n > 1:
        n_eval = max(0, min(n_eval, n - 1))
    else:
        n_eval = 0
    eval_ix = set(order[:n_eval])
    train_ix = set(order[n_eval:])
    return train_ix, eval_ix


def short_process_suffix(process_instance_id: str) -> str:
    alnum = re.sub(r"[^a-zA-Z0-9]", "", process_instance_id or "")
    return (alnum[-10:] or uuid.uuid4().hex[:10])


def wer_eval_score_for_items(eval_items: list[dict[str, Any]], training_stub: bool) -> tuple[float | None, str | None]:
    """
    WER on eval split manifest rows. Returns (wer_score, error_message).
    If error_message is set, fail the Camunda external task (do not publish).
    Stub mode idealizes ASR as perfect (hypothesis = reference) for dev/CI only.
    """
    if not eval_items:
        return None, (
            "eval split is empty — need at least one eval row "
            "(add Golden Set entries or increase LORA_EVAL_FRACTION)"
        )
    if not training_stub:
        return None, (
            "ASR-based WER evaluation is not implemented — set LORA_TRAINING_STUB=true for dev/CI "
            "or integrate OpenVINO inference on eval audio segments"
        )
    references = [(it.get("corrected_text") or "").strip() for it in eval_items]
    ref_joined = " ".join(references)
    hyp_joined = ref_joined
    return float(wer(ref_joined, hyp_joined)), None


async def _pg_fetch_golden_rows(conn: asyncpg.Connection) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT g.id, g.audio_id, g.segment_start, g.segment_end, g.corrected_text,
               g.minio_object_key, g.weight,
               COALESCE(a.normalized_path, a.minio_path) AS audio_object_key
        FROM golden_set_entries g
        JOIN audio_files a ON g.audio_id = a.id
        ORDER BY g.id
        """
    )
    return [dict(r) for r in rows]


def _put_json(bucket: str, key: str, payload: dict) -> None:
    data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    minio_client.put_object(bucket, key, io.BytesIO(data), length=len(data), content_type="application/json")


def _get_json(bucket: str, key: str) -> dict:
    resp = minio_client.get_object(bucket, key)
    try:
        return json.loads(resp.read().decode("utf-8"))
    finally:
        resp.close()
        resp.release_conn()


def _copy_prefix_to_prefix(src_bucket: str, src_prefix: str, dst_bucket: str, dst_prefix: str) -> None:
    """Copy all objects under src_prefix to dst_prefix (both prefixes end with /)."""
    if not src_prefix.endswith("/"):
        src_prefix += "/"
    if not dst_prefix.endswith("/"):
        dst_prefix += "/"
    for obj in minio_client.list_objects(src_bucket, prefix=src_prefix, recursive=True):
        name = obj.object_name
        if not name or name.endswith("/"):
            continue
        suffix = name[len(src_prefix) :] if name.startswith(src_prefix) else name
        dest_key = dst_prefix + suffix
        data = minio_client.get_object(src_bucket, name)
        try:
            body = data.read()
        finally:
            data.close()
            data.release_conn()
        minio_client.put_object(dst_bucket, dest_key, io.BytesIO(body), length=len(body))


def _remove_prefix(bucket: str, prefix: str) -> None:
    if not prefix.endswith("/"):
        prefix += "/"
    for obj in minio_client.list_objects(bucket, prefix=prefix, recursive=True):
        if obj.object_name and not obj.is_dir:
            try:
                minio_client.remove_object(bucket, obj.object_name)
            except S3Error:
                pass


async def process_dataset_prep(client: httpx.AsyncClient, task: dict) -> None:
    task_id = task["id"]
    retries = task.get("retries")
    process_instance_id = task.get("processInstanceId") or "unknown"

    conn = await asyncpg.connect(
        user=DB_USER, password=DB_PASSWORD, database=DB_NAME, host=DB_HOST
    )
    try:
        rows = await _pg_fetch_golden_rows(conn)
    finally:
        await conn.close()

    if not rows:
        await client.post(
            f"{CAMUNDA_REST_URL}/external-task/{task_id}/failure",
            json={
                "workerId": WORKER_ID,
                "errorMessage": "golden_set_entries empty — cannot build training dataset",
                "retries": 0,
                "retryTimeout": 0,
            },
        )
        return

    items = []
    for i, r in enumerate(rows):
        items.append(
            {
                "index": i,
                "golden_entry_id": r["id"],
                "audio_id": r["audio_id"],
                "segment_start": float(r["segment_start"]),
                "segment_end": float(r["segment_end"]),
                "corrected_text": r["corrected_text"],
                "golden_json_object_key": r["minio_object_key"],
                "audio_object_key": r["audio_object_key"],
                "weight": r["weight"],
            }
        )

    train_ix, eval_ix = train_eval_split_indices(len(items), LORA_EVAL_FRACTION, LORA_SPLIT_SEED)
    for i, it in enumerate(items):
        it["split"] = "eval" if i in eval_ix else "train"

    manifest = {
        "version": 1,
        "process_instance_id": process_instance_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "eval_fraction": LORA_EVAL_FRACTION,
        "split_seed": LORA_SPLIT_SEED,
        "split_policy": "Seeded shuffle of row indices; eval count = round(n * LORA_EVAL_FRACTION), "
        "capped so at least one training row remains when n > 1.",
        "items": items,
    }

    manifest_key = f"lora-work/{process_instance_id}/dataset_manifest.json"
    await asyncio.to_thread(_put_json, GOLDEN_SET_BUCKET, manifest_key, manifest)
    dataset_manifest_key = f"{GOLDEN_SET_BUCKET}/{manifest_key}"

    await client.post(
        f"{CAMUNDA_REST_URL}/external-task/{task_id}/complete",
        json={
            "workerId": WORKER_ID,
            "variables": {
                "datasetManifestKey": {"value": dataset_manifest_key, "type": "String"},
            },
        },
    )
    logger.info("dataset_prep complete task=%s manifest=%s", task_id, dataset_manifest_key)


async def process_training(client: httpx.AsyncClient, task: dict) -> None:
    task_id = task["id"]
    retries = task.get("retries")
    variables = task.get("variables", {})
    process_instance_id = task.get("processInstanceId") or "unknown"
    manifest_full = variables.get("datasetManifestKey", {}).get("value")
    if not manifest_full or "/" not in manifest_full:
        await client.post(
            f"{CAMUNDA_REST_URL}/external-task/{task_id}/failure",
            json={
                "workerId": WORKER_ID,
                "errorMessage": "missing datasetManifestKey variable",
                "retries": 0,
                "retryTimeout": 0,
            },
        )
        return

    bucket, _, key = manifest_full.partition("/")
    key = key.lstrip("/")

    try:
        await asyncio.to_thread(_get_json, bucket, key)
    except Exception as exc:
        remaining = (retries if retries is not None else MAX_RETRIES) - 1
        await client.post(
            f"{CAMUNDA_REST_URL}/external-task/{task_id}/failure",
            json={
                "workerId": WORKER_ID,
                "errorMessage": f"manifest read failed: {exc}",
                "retries": max(remaining, 0),
                "retryTimeout": 300_000,
            },
        )
        return

    staging_prefix = f"lora-staging/{process_instance_id}/"

    if _is_production():
        await client.post(
            f"{CAMUNDA_REST_URL}/external-task/{task_id}/failure",
            json={
                "workerId": WORKER_ID,
                "errorMessage": "Real LoRA training is not wired in this MVP build — use non-prod with LORA_TRAINING_STUB",
                "retries": 0,
                "retryTimeout": 0,
            },
        )
        return

    if not LORA_TRAINING_STUB:
        await client.post(
            f"{CAMUNDA_REST_URL}/external-task/{task_id}/failure",
            json={
                "workerId": WORKER_ID,
                "errorMessage": "Set LORA_TRAINING_STUB=true for dev/CI or implement real training",
                "retries": 0,
                "retryTimeout": 0,
            },
        )
        return

    if not LORA_STUB_SOURCE_PREFIX:
        await client.post(
            f"{CAMUNDA_REST_URL}/external-task/{task_id}/failure",
            json={
                "workerId": WORKER_ID,
                "errorMessage": "LORA_STUB_SOURCE_PREFIX must point to an existing OpenVINO model prefix in MinIO",
                "retries": 0,
                "retryTimeout": 0,
            },
        )
        return

    try:
        await asyncio.to_thread(_remove_prefix, MODEL_REGISTRY_BUCKET, staging_prefix)
        src = LORA_STUB_SOURCE_PREFIX
        if not src.endswith("/"):
            src = src + "/"
        await asyncio.to_thread(
            _copy_prefix_to_prefix, MODEL_REGISTRY_BUCKET, src, MODEL_REGISTRY_BUCKET, staging_prefix
        )
    except Exception as exc:
        remaining = (retries if retries is not None else MAX_RETRIES) - 1
        logger.exception("training stub copy failed")
        await client.post(
            f"{CAMUNDA_REST_URL}/external-task/{task_id}/failure",
            json={
                "workerId": WORKER_ID,
                "errorMessage": f"training stub failed: {exc}",
                "retries": max(remaining, 0),
                "retryTimeout": 300_000,
            },
        )
        return

    trained_prefix = f"{MODEL_REGISTRY_BUCKET}/{staging_prefix}"
    await client.post(
        f"{CAMUNDA_REST_URL}/external-task/{task_id}/complete",
        json={
            "workerId": WORKER_ID,
            "variables": {
                "trainedModelStagingPrefix": {"value": trained_prefix, "type": "String"},
            },
        },
    )
    logger.info("training complete task=%s staging=%s", task_id, trained_prefix)


async def process_wer_eval(client: httpx.AsyncClient, task: dict) -> None:
    task_id = task["id"]
    retries = task.get("retries")
    variables = task.get("variables", {})
    manifest_full = variables.get("datasetManifestKey", {}).get("value")
    staging_full = variables.get("trainedModelStagingPrefix", {}).get("value")

    if not manifest_full:
        await client.post(
            f"{CAMUNDA_REST_URL}/external-task/{task_id}/failure",
            json={
                "workerId": WORKER_ID,
                "errorMessage": "missing datasetManifestKey",
                "retries": 0,
                "retryTimeout": 0,
            },
        )
        return
    if not staging_full:
        await client.post(
            f"{CAMUNDA_REST_URL}/external-task/{task_id}/failure",
            json={
                "workerId": WORKER_ID,
                "errorMessage": "missing trainedModelStagingPrefix",
                "retries": 0,
                "retryTimeout": 0,
            },
        )
        return

    mb, _, mk = manifest_full.partition("/")
    mk = mk.lstrip("/")
    try:
        manifest = await asyncio.to_thread(_get_json, mb, mk)
    except Exception as exc:
        remaining = (retries if retries is not None else MAX_RETRIES) - 1
        await client.post(
            f"{CAMUNDA_REST_URL}/external-task/{task_id}/failure",
            json={
                "workerId": WORKER_ID,
                "errorMessage": f"manifest read failed: {exc}",
                "retries": max(remaining, 0),
                "retryTimeout": 300_000,
            },
        )
        return

    eval_items = [it for it in manifest.get("items", []) if it.get("split") == "eval"]
    wer_score, wer_err = wer_eval_score_for_items(eval_items, LORA_TRAINING_STUB)
    if wer_err is not None or wer_score is None:
        await client.post(
            f"{CAMUNDA_REST_URL}/external-task/{task_id}/failure",
            json={
                "workerId": WORKER_ID,
                "errorMessage": wer_err or "WER evaluation failed",
                "retries": 0,
                "retryTimeout": 0,
            },
        )
        return

    wer_accepted = wer_score <= LORA_MAX_WER

    await client.post(
        f"{CAMUNDA_REST_URL}/external-task/{task_id}/complete",
        json={
            "workerId": WORKER_ID,
            "variables": {
                "werScore": {"value": wer_score, "type": "Double"},
                "werAccepted": {"value": wer_accepted, "type": "Boolean"},
            },
        },
    )
    logger.info(
        "wer_eval complete task=%s wer_score=%s accepted=%s (threshold=%s)",
        task_id,
        wer_score,
        wer_accepted,
        LORA_MAX_WER,
    )


async def process_registry_publish(client: httpx.AsyncClient, task: dict) -> None:
    task_id = task["id"]
    retries = task.get("retries")
    variables = task.get("variables", {})
    process_instance_id = task.get("processInstanceId") or "unknown"

    staging_full = variables.get("trainedModelStagingPrefix", {}).get("value")
    wer_score = variables.get("werScore", {}).get("value")
    if staging_full is None or wer_score is None:
        await client.post(
            f"{CAMUNDA_REST_URL}/external-task/{task_id}/failure",
            json={
                "workerId": WORKER_ID,
                "errorMessage": "missing trainedModelStagingPrefix or werScore",
                "retries": 0,
                "retryTimeout": 0,
            },
        )
        return

    parts = staging_full.split("/", 1)
    if len(parts) != 2:
        await client.post(
            f"{CAMUNDA_REST_URL}/external-task/{task_id}/failure",
            json={
                "workerId": WORKER_ID,
                "errorMessage": "trainedModelStagingPrefix must be bucket/prefix/",
                "retries": 0,
                "retryTimeout": 0,
            },
        )
        return
    src_bucket, src_prefix = parts[0], parts[1]
    if not src_prefix.endswith("/"):
        src_prefix += "/"

    date_part = datetime.now(timezone.utc).strftime("%Y%m%d")
    short_id = short_process_suffix(process_instance_id)
    version_folder = f"whisper-cmci-{date_part}-{short_id}"
    dst_prefix = f"{version_folder}/"

    try:
        await asyncio.to_thread(_copy_prefix_to_prefix, src_bucket, src_prefix, MODEL_REGISTRY_BUCKET, dst_prefix)
        pointer_body = normalize_pointer_content(version_folder)
        await asyncio.to_thread(
            minio_client.put_object,
            MODEL_REGISTRY_BUCKET,
            MODEL_POINTER_KEY,
            io.BytesIO(pointer_body.encode("utf-8")),
            length=len(pointer_body.encode("utf-8")),
            content_type="text/plain; charset=utf-8",
        )
    except Exception as exc:
        remaining = (retries if retries is not None else MAX_RETRIES) - 1
        logger.exception("registry publish MinIO phase failed")
        await client.post(
            f"{CAMUNDA_REST_URL}/external-task/{task_id}/failure",
            json={
                "workerId": WORKER_ID,
                "errorMessage": f"registry publish failed: {exc}",
                "retries": max(remaining, 0),
                "retryTimeout": 300_000,
            },
        )
        return

    minio_path = f"{MODEL_REGISTRY_BUCKET}/{dst_prefix}"
    model_version = version_folder
    callback_body = {
        "model_version": model_version,
        "wer_score": float(wer_score),
        "minio_path": minio_path,
        "training_run_id": process_instance_id,
    }

    headers = {"X-ZachAI-Model-Ready-Secret": MODEL_READY_CALLBACK_SECRET}
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            resp = await client.post(
                f"{FASTAPI_INTERNAL_URL}/v1/callback/model-ready",
                json=callback_body,
                headers=headers,
                timeout=30.0,
            )
            if 200 <= resp.status_code < 300:
                await client.post(
                    f"{CAMUNDA_REST_URL}/external-task/{task_id}/complete",
                    json={
                        "workerId": WORKER_ID,
                        "variables": {
                            "publishedModelVersion": {"value": model_version, "type": "String"},
                            "publishedMinioPath": {"value": minio_path, "type": "String"},
                        },
                    },
                )
                logger.info("registry_publish complete task=%s version=%s", task_id, model_version)
                return
            last_exc = RuntimeError(f"callback HTTP {resp.status_code}: {resp.text[:500]}")
            logger.error("model-ready callback failed attempt %s: %s", attempt + 1, last_exc)
        except Exception as exc:
            last_exc = exc
            logger.error("model-ready callback error attempt %s: %s", attempt + 1, exc)
        await asyncio.sleep(2**attempt)

    logger.error(
        "model-ready callback exhausted retries — registry pointer already updated; ops should retry callback "
        "or reconcile manually. training_run_id=%s",
        process_instance_id,
    )
    remaining = (retries if retries is not None else MAX_RETRIES) - 1
    await client.post(
        f"{CAMUNDA_REST_URL}/external-task/{task_id}/failure",
        json={
            "workerId": WORKER_ID,
            "errorMessage": f"model-ready callback failed after MinIO success: {last_exc}",
            "retries": max(remaining, 0),
            "retryTimeout": 300_000,
        },
    )


async def dispatch_task(client: httpx.AsyncClient, task: dict) -> None:
    topic = task.get("topicName")
    try:
        if topic == "lora-dataset-prep":
            await process_dataset_prep(client, task)
        elif topic == "lora-training":
            await process_training(client, task)
        elif topic == "lora-wer-eval":
            await process_wer_eval(client, task)
        elif topic == "lora-registry-publish":
            await process_registry_publish(client, task)
        else:
            tid = task.get("id")
            if tid:
                await client.post(
                    f"{CAMUNDA_REST_URL}/external-task/{tid}/failure",
                    json={
                        "workerId": WORKER_ID,
                        "errorMessage": (
                            f"unsupported topicName={topic!r}; "
                            "expected lora-dataset-prep, lora-training, lora-wer-eval, or lora-registry-publish"
                        ),
                        "retries": 0,
                        "retryTimeout": 0,
                    },
                )
            else:
                logger.error("unknown topic %s and missing task id", topic)
    except Exception as exc:
        logger.exception("unhandled error in dispatch task=%s", task.get("id"))
        tid = task.get("id")
        if tid:
            retries = task.get("retries")
            remaining = (retries if retries is not None else MAX_RETRIES) - 1
            try:
                await client.post(
                    f"{CAMUNDA_REST_URL}/external-task/{tid}/failure",
                    json={
                        "workerId": WORKER_ID,
                        "errorMessage": str(exc),
                        "retries": max(remaining, 0),
                        "retryTimeout": 300_000,
                    },
                )
            except Exception as inner:
                logger.error("failed to report failure: %s", inner)


async def run() -> None:
    _validate_worker_env()
    logger.info("LoRA pipeline worker starting (%s)", WORKER_ID)
    async with httpx.AsyncClient(timeout=120.0) as client:
        while True:
            try:
                resp = await client.post(
                    f"{CAMUNDA_REST_URL}/external-task/fetchAndLock",
                    json={
                        "workerId": WORKER_ID,
                        "maxTasks": 3,
                        "asyncResponseTimeout": 30_000,
                        "topics": [
                            {"topicName": "lora-dataset-prep", "lockDuration": 1_800_000},
                            {"topicName": "lora-training", "lockDuration": 3_600_000},
                            {"topicName": "lora-wer-eval", "lockDuration": 1_800_000},
                            {"topicName": "lora-registry-publish", "lockDuration": 1_800_000},
                        ],
                    },
                )
                if resp.status_code == 200:
                    for task in resp.json():
                        await dispatch_task(client, task)
                else:
                    logger.warning("lora fetchAndLock returned %s", resp.status_code)
            except httpx.ConnectError:
                logger.warning("Camunda not reachable (lora worker) — retrying in 10s")
                await asyncio.sleep(10)
                continue
            except Exception as exc:
                logger.error("lora worker poll error: %s", exc)

            await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(run())
