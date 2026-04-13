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

# ─── Story 5.3: GET /v1/audio-files/{id}/media ──────────────────────────────


def test_audio_media_happy_path_transcripteur_assigned(mock_db):
    """GET /v1/audio-files/{id}/media: assigned Transcripteur + normalized audio → 200."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="user-999", status_val="assigned")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    mock_db.execute = AsyncMock(return_value=af_r)

    fake_url = "http://localhost:9000/projects/1/audio/test.normalized.wav?X-Amz-Signature=abc"
    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD), \
         patch.object(main.presigned_client, "presigned_get_object", return_value=fake_url):
        response = client.get(
            "/v1/audio-files/1/media",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 200
    assert response.json()["presigned_url"] == fake_url
    assert response.json()["expires_in"] == 3600


def test_audio_media_wrong_user_403(mock_db):
    """GET /v1/audio-files/{id}/media: Transcripteur not assigned → 403."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="other-user", status_val="assigned")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    mock_db.execute = AsyncMock(return_value=af_r)

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.get(
            "/v1/audio-files/1/media",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 403
    assert "error" in response.json()


def test_audio_media_wrong_role_403(mock_db):
    """GET /v1/audio-files/{id}/media: Manager role forbidden → 403."""
    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.get(
            "/v1/audio-files/1/media",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 403
    assert "error" in response.json()


def test_audio_media_missing_audio_404(mock_db):
    """GET /v1/audio-files/{id}/media: unknown audio → 404."""
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=af_r)

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.get(
            "/v1/audio-files/999/media",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 404
    assert "error" in response.json()


def test_audio_media_normalized_missing_409(mock_db):
    """GET /v1/audio-files/{id}/media: normalized_path missing → 409."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="user-999", status_val="assigned")
    mock_audio.normalized_path = None  # not eligible for playback
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    mock_db.execute = AsyncMock(return_value=af_r)

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.get(
            "/v1/audio-files/1/media",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 409
    assert "error" in response.json()


def test_audio_media_presigned_generation_failure_503(mock_db):
    """GET /v1/audio-files/{id}/media: presigned_get_object fails → 503."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="user-999", status_val="assigned")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    mock_db.execute = AsyncMock(return_value=af_r)

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD), \
         patch.object(main.presigned_client, "presigned_get_object", side_effect=Exception("minio down")):
        response = client.get(
            "/v1/audio-files/1/media",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 503
    assert "error" in response.json()


