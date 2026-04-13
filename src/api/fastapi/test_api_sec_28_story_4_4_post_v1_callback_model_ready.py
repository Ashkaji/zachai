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

# ─── Story 4.4: POST /v1/callback/model-ready ─────────────────────────────────


def _model_ready_headers():
    return {"X-ZachAI-Model-Ready-Secret": os.environ["MODEL_READY_CALLBACK_SECRET"]}


_MODEL_READY_BODY = {
    "model_version": "whisper-cmci-test-1",
    "wer_score": 0.01,
    "minio_path": "models/whisper-cmci-test-1/",
    "training_run_id": "camunda-proc-abc123",
}


def test_model_ready_callback_no_secret(mock_db):
    response = client.post("/v1/callback/model-ready", json=_MODEL_READY_BODY)
    assert response.status_code == 401


def test_model_ready_callback_wrong_secret(mock_db):
    response = client.post(
        "/v1/callback/model-ready",
        headers={"X-ZachAI-Model-Ready-Secret": "wrong"},
        json=_MODEL_READY_BODY,
    )
    assert response.status_code == 403


def test_model_ready_callback_invalid_body(mock_db):
    response = client.post(
        "/v1/callback/model-ready",
        headers=_model_ready_headers(),
        json={"model_version": "x"},
    )
    assert response.status_code == 422


def test_model_ready_callback_success_updates_counter(mock_db):
    ins_r = MagicMock()
    ins_r.scalar_one_or_none.return_value = "camunda-proc-abc123"
    mock_ctr = MagicMock()
    mock_ctr.count = 50
    mock_ctr.threshold = 1000
    ctr_r = MagicMock()
    ctr_r.scalar_one_or_none.return_value = mock_ctr
    mock_db.execute = AsyncMock(side_effect=[ins_r, ctr_r])
    mock_db.commit = AsyncMock()

    response = client.post(
        "/v1/callback/model-ready",
        headers=_model_ready_headers(),
        json=_MODEL_READY_BODY,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["idempotent"] is False
    assert "last_training_at" in data
    assert mock_ctr.count == 0
    assert mock_ctr.last_training_at is not None
    mock_db.commit.assert_called_once()


def test_model_ready_callback_idempotent_duplicate(mock_db):
    ins_r = MagicMock()
    ins_r.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=ins_r)
    mock_db.commit = AsyncMock()

    response = client.post(
        "/v1/callback/model-ready",
        headers=_model_ready_headers(),
        json=_MODEL_READY_BODY,
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "idempotent": True}
    mock_db.commit.assert_called_once()


