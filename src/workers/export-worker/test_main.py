import base64
import json
import os
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

os.environ.setdefault("MINIO_ENDPOINT", "minio:9000")
os.environ.setdefault("MINIO_ACCESS_KEY", "minioadmin")
os.environ.setdefault("MINIO_SECRET_KEY", "minioadmin")
os.environ.setdefault("MINIO_SECURE", "false")
os.environ.setdefault("SNAPSHOT_CALLBACK_SECRET", "test-snapshot-secret")

import main  # noqa: E402

client = TestClient(main.app)


def _headers() -> dict[str, str]:
    return {"X-ZachAI-Snapshot-Secret": os.environ["SNAPSHOT_CALLBACK_SECRET"]}


def _body(document_id: int = 1) -> dict:
    raw = b"fake-yjs-state"
    return {"document_id": document_id, "yjs_state_binary": base64.b64encode(raw).decode("ascii")}


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_snapshot_export_no_secret():
    response = client.post("/snapshot-export", json=_body())
    assert response.status_code == 401


def test_snapshot_export_wrong_secret():
    response = client.post(
        "/snapshot-export",
        headers={"X-ZachAI-Snapshot-Secret": "wrong"},
        json=_body(),
    )
    assert response.status_code == 403


def test_snapshot_export_invalid_base64():
    response = client.post(
        "/snapshot-export",
        headers=_headers(),
        json={"document_id": 1, "yjs_state_binary": "!!!!"},
    )
    assert response.status_code == 422


@patch.object(main, "_upload_and_verify_object")
def test_snapshot_export_happy_path(mock_upload):
    mock_upload.side_effect = ["json-sha", "docx-sha"]
    response = client.post("/snapshot-export", headers=_headers(), json=_body())
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["json_sha256"] == "json-sha"
    assert body["docx_sha256"] == "docx-sha"
    assert body["json_object_key"].startswith("snapshots/1/")
    assert body["docx_object_key"].startswith("snapshots/1/")
    assert mock_upload.call_count == 2


def test_snapshot_export_dlq_after_retries(tmp_path: Path):
    with patch.object(main, "DLQ_DIR", tmp_path), patch.object(
        main, "_upload_and_verify_object", side_effect=RuntimeError("boom")
    ):
        response = client.post("/snapshot-export", headers=_headers(), json=_body())

    assert response.status_code == 500
    detail = response.json()["detail"]["error"]
    assert "Snapshot export failed after retries" in detail

    dlq_files = list(tmp_path.glob("*.json"))
    assert len(dlq_files) == 1
    payload = json.loads(dlq_files[0].read_text(encoding="utf-8"))
    assert payload["reason"] == "boom"
