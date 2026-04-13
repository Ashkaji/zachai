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

# ─── Story 4.2: Frontend correction route & transcription read ───────────────



FRONTEND_CORRECTION_BODY = {
    "audio_id": 1,
    "segment_start": 0.5,
    "segment_end": 2.0,
    "original_text": "bonjour",
    "corrected_text": "Bonjour",
}


def test_frontend_correction_happy_path_transcripteur(mock_db):
    """POST /v1/golden-set/frontend-correction: assigned Transcripteur → 200 + counter increment."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="user-999")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    dup_r = MagicMock()
    dup_r.scalar_one_or_none.return_value = None
    persist_af_r = MagicMock()
    persist_af_r.scalar_one_or_none.return_value = mock_audio
    mock_ctr = MagicMock()
    mock_ctr.count = 5
    mock_ctr.threshold = 1000
    ctr_r = MagicMock()
    ctr_r.scalar_one_or_none.return_value = mock_ctr
    mock_db.execute = AsyncMock(side_effect=[af_r, dup_r, persist_af_r, ctr_r])
    mock_db.commit = AsyncMock()

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD), \
         patch.object(main.internal_client, "put_object") as mock_put, \
         patch.object(main, "camunda_client") as mock_camunda:
        mock_camunda.post = AsyncMock()
        response = client.post(
            "/v1/golden-set/frontend-correction",
            headers={"Authorization": "Bearer dummy.token.here"},
            json=FRONTEND_CORRECTION_BODY,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["idempotent"] is False
    mock_put.assert_called_once()
    assert mock_ctr.count == 6
    mock_camunda.post.assert_not_called()


def test_frontend_correction_wrong_user_403(mock_db):
    """POST /v1/golden-set/frontend-correction: Transcripteur not assigned → 403."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="other-user")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    mock_db.execute = AsyncMock(return_value=af_r)

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.post(
            "/v1/golden-set/frontend-correction",
            headers={"Authorization": "Bearer dummy.token.here"},
            json=FRONTEND_CORRECTION_BODY,
        )

    assert response.status_code == 403
    assert "assigned" in response.json()["error"].lower()


def test_frontend_correction_wrong_role_403(mock_db):
    """POST /v1/golden-set/frontend-correction: Manager-only → 403."""
    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.post(
            "/v1/golden-set/frontend-correction",
            headers={"Authorization": "Bearer dummy.token.here"},
            json=FRONTEND_CORRECTION_BODY,
        )

    assert response.status_code == 403
    assert "role" in response.json()["error"].lower()


def test_frontend_correction_missing_audio_404(mock_db):
    """POST /v1/golden-set/frontend-correction: non-existent audio_id → 404."""
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=af_r)

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.post(
            "/v1/golden-set/frontend-correction",
            headers={"Authorization": "Bearer dummy.token.here"},
            json=FRONTEND_CORRECTION_BODY,
        )

    assert response.status_code == 404


def test_frontend_correction_idempotent_duplicate(mock_db):
    """POST /v1/golden-set/frontend-correction: same client_mutation_id → idempotent no-op."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="user-999")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    dup_r = MagicMock()
    dup_r.scalar_one_or_none.return_value = 42  # existing row
    mock_db.execute = AsyncMock(side_effect=[af_r, dup_r])
    mock_db.commit = AsyncMock()

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD), \
         patch.object(main.internal_client, "put_object") as mock_put:
        response = client.post(
            "/v1/golden-set/frontend-correction",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={**FRONTEND_CORRECTION_BODY, "client_mutation_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["idempotent"] is True
    mock_put.assert_not_called()


def test_frontend_correction_admin_bypass_assignment(mock_db):
    """POST /v1/golden-set/frontend-correction: Admin bypasses assignment check."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="other-user")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    dup_r = MagicMock()
    dup_r.scalar_one_or_none.return_value = None
    persist_af_r = MagicMock()
    persist_af_r.scalar_one_or_none.return_value = mock_audio
    mock_ctr = MagicMock()
    mock_ctr.count = 0
    mock_ctr.threshold = 1000
    ctr_r = MagicMock()
    ctr_r.scalar_one_or_none.return_value = mock_ctr
    mock_db.execute = AsyncMock(side_effect=[af_r, dup_r, persist_af_r, ctr_r])
    mock_db.commit = AsyncMock()

    with patch.object(main, "decode_token", return_value=ADMIN_PAYLOAD), \
         patch.object(main.internal_client, "put_object"), \
         patch.object(main, "camunda_client") as mock_camunda:
        mock_camunda.post = AsyncMock()
        response = client.post(
            "/v1/golden-set/frontend-correction",
            headers={"Authorization": "Bearer dummy.token.here"},
            json=FRONTEND_CORRECTION_BODY,
        )

    assert response.status_code == 200
    mock_camunda.post.assert_not_called()


def test_frontend_correction_status_409_after_submit(mock_db):
    """POST /v1/golden-set/frontend-correction: transcribed audio → 409."""
    mock_audio = _make_mock_audio_with_assignment(
        transcripteur_id="user-999", status_val="transcribed"
    )
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    mock_db.execute = AsyncMock(return_value=af_r)

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.post(
            "/v1/golden-set/frontend-correction",
            headers={"Authorization": "Bearer dummy.token.here"},
            json=FRONTEND_CORRECTION_BODY,
        )

    assert response.status_code == 409


