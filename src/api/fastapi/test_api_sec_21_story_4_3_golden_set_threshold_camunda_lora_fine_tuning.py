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

# ─── Story 4.3: Golden Set threshold → Camunda lora-fine-tuning ─────────────


def test_golden_set_internal_entry_triggers_camunda_on_threshold_crossing(mock_db):
    """Counter crosses threshold → POST .../lora-fine-tuning/start with typed variables."""
    dup_r = MagicMock()
    dup_r.scalar_one_or_none.return_value = None
    mock_af = MagicMock()
    mock_af.project_id = 1
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_af
    mock_ctr = MagicMock()
    mock_ctr.count = 9
    mock_ctr.threshold = 10
    ctr_r = MagicMock()
    ctr_r.scalar_one_or_none.return_value = mock_ctr
    mock_db.execute = AsyncMock(side_effect=[dup_r, af_r, ctr_r])
    mock_db.commit = AsyncMock()
    mock_camunda_resp = MagicMock()
    mock_camunda_resp.status_code = 200
    mock_camunda_resp.json.return_value = {"id": "proc-lora-1"}

    with patch.object(main.internal_client, "put_object"), \
         patch.object(main, "camunda_client") as mock_camunda:
        mock_camunda.post = AsyncMock(return_value=mock_camunda_resp)
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
    mock_camunda.post.assert_called_once()
    url = mock_camunda.post.call_args[0][0]
    assert "lora-fine-tuning/start" in url
    variables = mock_camunda.post.call_args[1]["json"]["variables"]
    assert variables["goldenSetCount"] == {"value": 10, "type": "Integer"}
    assert variables["threshold"] == {"value": 10, "type": "Integer"}
    assert variables["triggeredAt"]["type"] == "String"
    assert len(variables["triggeredAt"]["value"]) > 10


def test_golden_set_internal_entry_idempotent_no_camunda(mock_db):
    """Idempotent short-circuit → no Camunda start."""
    dup_r = MagicMock()
    dup_r.scalar_one_or_none.return_value = 999
    mock_db.execute = AsyncMock(return_value=dup_r)

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
    assert response.json()["idempotent"] is True
    mock_put.assert_not_called()
    mock_camunda.post.assert_not_called()


def test_golden_set_internal_entry_below_threshold_no_camunda(mock_db):
    """Increment does not cross threshold → no Camunda."""
    dup_r = MagicMock()
    dup_r.scalar_one_or_none.return_value = None
    mock_af = MagicMock()
    mock_af.project_id = 1
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_af
    mock_ctr = MagicMock()
    mock_ctr.count = 3
    mock_ctr.threshold = 100
    ctr_r = MagicMock()
    ctr_r.scalar_one_or_none.return_value = mock_ctr
    mock_db.execute = AsyncMock(side_effect=[dup_r, af_r, ctr_r])
    mock_db.commit = AsyncMock()

    with patch.object(main.internal_client, "put_object"), \
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
    mock_camunda.post.assert_not_called()


def test_golden_set_internal_entry_camunda_connect_error_still_2xx(mock_db):
    """Camunda ConnectError → ingest still 2xx; commit already done."""
    dup_r = MagicMock()
    dup_r.scalar_one_or_none.return_value = None
    mock_af = MagicMock()
    mock_af.project_id = 1
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_af
    mock_ctr = MagicMock()
    mock_ctr.count = 9
    mock_ctr.threshold = 10
    ctr_r = MagicMock()
    ctr_r.scalar_one_or_none.return_value = mock_ctr
    mock_db.execute = AsyncMock(side_effect=[dup_r, af_r, ctr_r])
    mock_db.commit = AsyncMock()

    with patch.object(main.internal_client, "put_object"), \
         patch.object(main, "camunda_client") as mock_camunda:
        mock_camunda.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
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
    mock_db.commit.assert_called_once()


def test_golden_set_internal_entry_camunda_invalid_json_still_2xx(mock_db):
    """Camunda 200 with unparseable body → ingest still 2xx; commit already done."""
    dup_r = MagicMock()
    dup_r.scalar_one_or_none.return_value = None
    mock_af = MagicMock()
    mock_af.project_id = 1
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_af
    mock_ctr = MagicMock()
    mock_ctr.count = 9
    mock_ctr.threshold = 10
    ctr_r = MagicMock()
    ctr_r.scalar_one_or_none.return_value = mock_ctr
    mock_db.execute = AsyncMock(side_effect=[dup_r, af_r, ctr_r])
    mock_db.commit = AsyncMock()

    mock_camunda_resp = MagicMock()
    mock_camunda_resp.status_code = 200
    mock_camunda_resp.json.side_effect = ValueError("not json")

    with patch.object(main.internal_client, "put_object"), \
         patch.object(main, "camunda_client") as mock_camunda:
        mock_camunda.post = AsyncMock(return_value=mock_camunda_resp)
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
    mock_db.commit.assert_called_once()


def test_golden_set_status_manager_ok(mock_db):
    """GET /v1/golden-set/status — Manager sees counter fields."""
    mock_row = MagicMock()
    mock_row.count = 42
    mock_row.threshold = 1000
    mock_row.last_training_at = None
    ctr_r = MagicMock()
    ctr_r.scalar_one_or_none.return_value = mock_row
    mock_db.execute = AsyncMock(return_value=ctr_r)

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.get(
            "/v1/golden-set/status",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "count": 42,
        "threshold": 1000,
        "last_training_at": None,
        "next_trigger_at": None,
    }


def test_golden_set_status_missing_row_defaults(mock_db):
    """No GoldenSetCounter row → 200 with zeros and env threshold default."""
    ctr_r = MagicMock()
    ctr_r.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=ctr_r)

    with patch.object(main, "decode_token", return_value=ADMIN_PAYLOAD):
        response = client.get(
            "/v1/golden-set/status",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 0
    assert data["threshold"] == main.GOLDEN_SET_THRESHOLD
    assert data["last_training_at"] is None
    assert data["next_trigger_at"] is None


def test_golden_set_status_transcripteur_forbidden(mock_db):
    """GET /v1/golden-set/status — Transcripteur → 403."""
    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.get(
            "/v1/golden-set/status",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 403


