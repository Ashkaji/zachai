"""
Golden Set ingestion helpers — Story 4.1 (Label Studio expert loop).
Pure functions / no SQLAlchemy imports to keep cycles clear.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
from typing import Any

logger = logging.getLogger(__name__)


def canonical_json_bytes(obj: dict[str, Any]) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def idempotency_key_from_parts(parts: dict[str, Any]) -> str:
    return sha256_hex(canonical_json_bytes(parts))


def _coerce_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _textarea_text(item: dict[str, Any]) -> str | None:
    val = item.get("value") or {}
    if isinstance(val, dict):
        t = val.get("text")
        if isinstance(t, list):
            inner = "".join(str(x) for x in t if x is not None)
            return inner if inner else None
        if isinstance(t, str):
            return t or None
    return None


def _labels_segment(item: dict[str, Any]) -> tuple[float | None, float | None, list[str]]:
    val = item.get("value") or {}
    if not isinstance(val, dict):
        return None, None, []
    start = _coerce_float(val.get("start"))
    end = _coerce_float(val.get("end"))
    labels = val.get("labels") or []
    if isinstance(labels, list):
        lab = [str(x) for x in labels if x is not None]
    else:
        lab = []
    return start, end, lab


def _extract_original_from_task(task: dict[str, Any]) -> str | None:
    data = task.get("data") if isinstance(task.get("data"), dict) else {}
    if not isinstance(data, dict):
        data = {}
    for key in ("original_transcription", "whisper_text", "pre_annotation_text"):
        ox = data.get(key)
        if isinstance(ox, str) and ox.strip():
            return ox
    preds = task.get("predictions") if isinstance(task.get("predictions"), list) else []
    for p in preds:
        if not isinstance(p, dict):
            continue
        for r in p.get("result") or []:
            if not isinstance(r, dict):
                continue
            if r.get("type") == "textarea":
                t = _textarea_text(r)
                if t:
                    return t
    return None


def segments_from_annotation_result(
    result: list[dict[str, Any]], *, original_text_hint: str | None
) -> list[dict[str, Any]]:
    """
    Build segment dicts from Label Studio `annotation[\"result\"]` list.
    Each segment: segment_start, segment_end, corrected_text, label, original_text (hint).
    """
    if not result:
        return []

    textareas: list[str] = []
    for item in result:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "textarea":
            t = _textarea_text(item)
            if t is not None:
                textareas.append(t)

    segments_out: list[dict[str, Any]] = []
    ti = 0
    for item in result:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "labels":
            continue
        start, end, labs = _labels_segment(item)
        if start is None or end is None:
            continue

        val = item.get("value") if isinstance(item.get("value"), dict) else {}
        corrected = None
        tlist = val.get("text") if isinstance(val, dict) else None
        if isinstance(tlist, list):
            corrected = "".join(str(x) for x in tlist if x is not None) or None
        if corrected is None and textareas:
            if len(textareas) == 1:
                corrected = textareas[0]
            elif ti < len(textareas):
                corrected = textareas[ti]
                ti += 1
            else:
                corrected = textareas[-1]
        if corrected is None:
            corrected = ""

        label_val = labs[0] if labs else None
        segments_out.append(
            {
                "segment_start": start,
                "segment_end": end,
                "corrected_text": corrected,
                "label": label_val,
                "original_text": original_text_hint,
            }
        )

    if segments_out:
        return segments_out

    # No time-coded labels found; textarea-only annotations are not valid segments.
    if textareas:
        logger.debug(
            "golden_set_textarea_only_annotation: %d textareas but no labels-type regions; skipping",
            len(textareas),
        )
    return []


def resolve_audio_id_from_body(body: dict[str, Any], task: dict[str, Any]) -> int | None:
    if "audio_id" in body and body["audio_id"] is not None:
        try:
            return int(body["audio_id"])
        except (TypeError, ValueError):
            return None
    data = task.get("data") if isinstance(task.get("data"), dict) else {}
    if isinstance(data, dict) and data.get("audio_id") is not None:
        try:
            return int(data["audio_id"])
        except (TypeError, ValueError):
            return None
    return None


def label_studio_project_id_from_task(task: dict[str, Any]) -> int | None:
    p = task.get("project")
    if p is None and isinstance(task.get("project_id"), int):
        return int(task["project_id"])
    if isinstance(p, int):
        return p
    if isinstance(p, dict) and p.get("id") is not None:
        try:
            return int(p["id"])
        except (TypeError, ValueError):
            return None
    return None


def normalize_expert_validation_payload(body: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize Label Studio webhook envelope or minimal `{task_id, annotation, audio_id}` into:
    {
      "task_id": int | None,
      "annotation_id": int | None,
      "audio_id": int | None,
      "label_studio_project_id": int | None,
      "segments": list[segment dict],
      "action": str | None,
    }
    """
    action = body.get("action")
    task = body.get("task") if isinstance(body.get("task"), dict) else {}
    annotation = body.get("annotation") if isinstance(body.get("annotation"), dict) else None

    task_id = body.get("task_id")
    if task_id is None and task:
        task_id = task.get("id")
    try:
        task_id_i = int(task_id) if task_id is not None else None
    except (TypeError, ValueError):
        task_id_i = None

    if annotation is None:
        annotation = body if "result" in body else {}

    annotation = annotation if isinstance(annotation, dict) else {}
    ann_id = annotation.get("id")
    try:
        annotation_id_i = int(ann_id) if ann_id is not None else None
    except (TypeError, ValueError):
        annotation_id_i = None

    result = annotation.get("result") if isinstance(annotation.get("result"), list) else []

    original_hint = _extract_original_from_task(task) if task else None
    if original_hint is None:
        logger.debug("golden_set_no_original_transcription_hint task_id=%s", task_id_i)

    segments = segments_from_annotation_result(
        [x for x in result if isinstance(x, dict)],
        original_text_hint=original_hint,
    )

    audio_id = resolve_audio_id_from_body(body, task)
    ls_proj = label_studio_project_id_from_task(task) if task else None

    return {
        "task_id": task_id_i,
        "annotation_id": annotation_id_i,
        "audio_id": audio_id,
        "label_studio_project_id": ls_proj,
        "segments": segments,
        "action": str(action) if action is not None else None,
    }
