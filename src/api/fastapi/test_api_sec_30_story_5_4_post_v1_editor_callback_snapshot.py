"""API gateway tests — auto-split from legacy test_main (see fastapi_test_app)."""
import os
import pytest
import httpx
import fakeredis.aioredis
from datetime import datetime, timezone
from typing import Annotated
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import Depends, HTTPException, Request
from fastapi.testclient import TestClient
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_test_app import (
    client,
    main,
    editor_ticket_mod,
    MANAGER_PAYLOAD,
    EXPERT_PAYLOAD,
    ADMIN_PAYLOAD,
    TRANSCRIPTEUR_PAYLOAD,
    MANAGER_OTHER_PAYLOAD,
    MOCK_JWKS,
    make_mock_label,
    make_mock_nature,
    make_mock_project,
    _make_mock_audio_with_assignment,
    _make_mock_snapshot,
    _FakeMinioObject,
    _FakeRedisBible,
)

# ─── Story 5.4: POST /v1/editor/callback/snapshot ────────────────────────────

SNAPSHOT_CALLBACK_BODY = {
    "document_id": 1,
    "yjs_state_binary": "ZmFrZS15anMtc3RhdGU=",
}


def _snapshot_headers():
    return {"X-ZachAI-Snapshot-Secret": os.environ["SNAPSHOT_CALLBACK_SECRET"]}


def test_snapshot_callback_no_secret(mock_db):
    response = client.post("/v1/editor/callback/snapshot", json=SNAPSHOT_CALLBACK_BODY)
    assert response.status_code == 401


def test_snapshot_callback_wrong_secret(mock_db):
    response = client.post(
        "/v1/editor/callback/snapshot",
        headers={"X-ZachAI-Snapshot-Secret": "wrong"},
        json=SNAPSHOT_CALLBACK_BODY,
    )
    assert response.status_code == 403


def test_snapshot_callback_invalid_body_422(mock_db):
    response = client.post(
        "/v1/editor/callback/snapshot",
        headers=_snapshot_headers(),
        json={"document_id": 1, "yjs_state_binary": "!!!"},
    )
    assert response.status_code == 422


def test_snapshot_callback_missing_audio_404(mock_db):
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=af_r)
    response = client.post(
        "/v1/editor/callback/snapshot",
        headers=_snapshot_headers(),
        json=SNAPSHOT_CALLBACK_BODY,
    )
    assert response.status_code == 404


def test_snapshot_callback_worker_unavailable_503(mock_db):
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = _make_mock_audio_with_assignment()
    mock_db.execute = AsyncMock(return_value=af_r)
    with patch.object(main, "_export_worker_client", None):
        response = client.post(
            "/v1/editor/callback/snapshot",
            headers=_snapshot_headers(),
            json=SNAPSHOT_CALLBACK_BODY,
        )
    assert response.status_code == 503


def test_snapshot_callback_export_failure_502(mock_db):
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = _make_mock_audio_with_assignment()
    mock_db.execute = AsyncMock(return_value=af_r)
    with patch.object(main, "_export_snapshot_via_worker", new=AsyncMock(side_effect=HTTPException(status_code=502, detail={"error": "Snapshot export failed"}))):
        response = client.post(
            "/v1/editor/callback/snapshot",
            headers=_snapshot_headers(),
            json=SNAPSHOT_CALLBACK_BODY,
        )
    assert response.status_code == 502


def test_snapshot_callback_success_persists_metadata(mock_db):
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = _make_mock_audio_with_assignment()
    mock_db.execute = AsyncMock(return_value=af_r)
    mock_db.commit = AsyncMock()
    worker_ok = {
        "snapshot_id": "20260330T120000Z-abc123def0",
        "json_object_key": "snapshots/1/20260330T120000Z-abc123def0.json",
        "docx_object_key": "snapshots/1/20260330T120000Z-abc123def0.docx",
        "yjs_sha256": "a" * 64,
        "json_sha256": "b" * 64,
        "docx_sha256": "c" * 64,
    }
    with patch.object(main, "_export_snapshot_via_worker", new=AsyncMock(return_value=worker_ok)):
        response = client.post(
            "/v1/editor/callback/snapshot",
            headers=_snapshot_headers(),
            json=SNAPSHOT_CALLBACK_BODY,
        )
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "snapshot_id": worker_ok["snapshot_id"]}
    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()


