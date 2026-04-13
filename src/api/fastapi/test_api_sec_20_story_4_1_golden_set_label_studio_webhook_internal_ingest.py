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

# ─── Story 4.1: Golden Set — Label Studio webhook & internal ingest ─────────


LS_WEBHOOK_BODY_ONE_SEGMENT = {
    "action": "ANNOTATION_UPDATED",
    "task": {"id": 42, "data": {"audio_id": 7}},
    "annotation": {
        "id": 99,
        "result": [
            {
                "type": "labels",
                "value": {"start": 0.0, "end": 1.5, "labels": ["Orateur"]},
            },
            {"type": "textarea", "value": {"text": ["corrected hello"]}},
        ],
    },
}


def _webhook_headers():
    return {"X-ZachAI-Webhook-Secret": os.environ["LABEL_STUDIO_WEBHOOK_SECRET"]}


def test_expert_validation_webhook_no_secret_header(mock_db):
    """Missing webhook secret → 401."""
    response = client.post(
        "/v1/callback/expert-validation",
        json=LS_WEBHOOK_BODY_ONE_SEGMENT,
    )
    assert response.status_code == 401


def test_expert_validation_webhook_wrong_secret(mock_db):
    """Wrong webhook secret → 403."""
    response = client.post(
        "/v1/callback/expert-validation",
        headers={"X-ZachAI-Webhook-Secret": "not-the-secret"},
        json=LS_WEBHOOK_BODY_ONE_SEGMENT,
    )
    assert response.status_code == 403


def test_expert_validation_webhook_missing_audio(mock_db):
    """Unknown audio_id → 404."""
    dup_r = MagicMock()
    dup_r.scalar_one_or_none.return_value = None
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(side_effect=[dup_r, af_r])
    with patch.object(main.internal_client, "put_object") as mock_put:
        response = client.post(
            "/v1/callback/expert-validation",
            headers=_webhook_headers(),
            json=LS_WEBHOOK_BODY_ONE_SEGMENT,
        )
    assert response.status_code == 404
    mock_put.assert_not_called()


def test_expert_validation_webhook_writes_golden_set(mock_db):
    """Valid webhook: MinIO put + DB commit path (mocked)."""
    dup_r = MagicMock()
    dup_r.scalar_one_or_none.return_value = None
    mock_af = MagicMock()
    mock_af.project_id = 1
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_af
    mock_ctr = MagicMock()
    mock_ctr.count = 3
    mock_ctr.threshold = 1000
    ctr_r = MagicMock()
    ctr_r.scalar_one_or_none.return_value = mock_ctr
    mock_db.execute = AsyncMock(side_effect=[dup_r, af_r, ctr_r])
    mock_db.commit = AsyncMock()

    with patch.object(main.internal_client, "put_object") as mock_put, \
         patch.object(main, "camunda_client") as mock_camunda:
        mock_camunda.post = AsyncMock()
        response = client.post(
            "/v1/callback/expert-validation",
            headers=_webhook_headers(),
            json=LS_WEBHOOK_BODY_ONE_SEGMENT,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["entries_written"] == 1
    assert data["idempotency_hits"] == 0
    mock_put.assert_called_once()
    assert mock_ctr.count == 4
    mock_db.commit.assert_called_once()
    mock_camunda.post.assert_not_called()


def test_expert_validation_webhook_idempotent_repeat(mock_db):
    """Duplicate delivery: idempotency hit, no second MinIO put."""
    dup_r = MagicMock()
    dup_r.scalar_one_or_none.return_value = 123  # existing row
    mock_db.execute = AsyncMock(return_value=dup_r)
    mock_db.commit = AsyncMock()

    with patch.object(main.internal_client, "put_object") as mock_put:
        response = client.post(
            "/v1/callback/expert-validation",
            headers=_webhook_headers(),
            json=LS_WEBHOOK_BODY_ONE_SEGMENT,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["entries_written"] == 0
    assert data["idempotency_hits"] == 1
    mock_put.assert_not_called()
    mock_db.commit.assert_not_called()


def test_golden_set_internal_entry_no_auth_header(mock_db):
    """Missing auth header entirely → 401."""
    response = client.post(
        "/v1/golden-set/entry",
        json={
            "audio_id": 1,
            "segment_start": 0.0,
            "segment_end": 1.0,
            "corrected_text": "hi",
            "source": "frontend_correction",
            "weight": "standard",
        },
    )
    assert response.status_code == 401


def test_golden_set_internal_entry_wrong_secret(mock_db):
    response = client.post(
        "/v1/golden-set/entry",
        headers={"X-ZachAI-Golden-Set-Internal-Secret": "nope"},
        json={
            "audio_id": 1,
            "segment_start": 0.0,
            "segment_end": 1.0,
            "corrected_text": "hi",
            "source": "frontend_correction",
            "weight": "standard",
        },
    )
    assert response.status_code == 403


def test_golden_set_internal_entry_success(mock_db):
    dup_r = MagicMock()
    dup_r.scalar_one_or_none.return_value = None
    mock_af = MagicMock()
    mock_af.project_id = 1
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_af
    mock_ctr = MagicMock()
    mock_ctr.count = 10
    mock_ctr.threshold = 1000
    ctr_r = MagicMock()
    ctr_r.scalar_one_or_none.return_value = mock_ctr
    mock_db.execute = AsyncMock(side_effect=[dup_r, af_r, ctr_r])
    mock_db.commit = AsyncMock()

    with patch.object(main.internal_client, "put_object") as mock_put, \
         patch.object(main, "camunda_client") as mock_camunda:
        mock_camunda.post = AsyncMock()
        response = client.post(
            "/v1/golden-set/entry",
            headers={
                "X-ZachAI-Golden-Set-Internal-Secret": os.environ["GOLDEN_SET_INTERNAL_SECRET"]
            },
            json={
                "audio_id": 1,
                "segment_start": 0.0,
                "segment_end": 1.0,
                "corrected_text": "hi",
                "source": "frontend_correction",
                "weight": "standard",
            },
        )

    assert response.status_code == 200
    assert response.json()["idempotent"] is False
    mock_put.assert_called_once()
    assert mock_ctr.count == 11
    mock_camunda.post.assert_not_called()


