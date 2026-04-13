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

# ─── Story 4.2: GET /v1/audio-files/{id}/transcription ──────────────────────


def test_transcription_get_happy_path(mock_db):
    """GET /v1/audio-files/{id}/transcription: assigned Transcripteur → 200 with empty segments."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="user-999")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    mock_db.execute = AsyncMock(return_value=af_r)

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.get(
            "/v1/audio-files/1/transcription",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 200
    assert response.json() == {"segments": []}


def test_transcription_get_wrong_user_403(mock_db):
    """GET /v1/audio-files/{id}/transcription: unassigned Transcripteur → 403."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="other-user")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    mock_db.execute = AsyncMock(return_value=af_r)

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.get(
            "/v1/audio-files/1/transcription",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 403


def test_transcription_get_missing_audio_404(mock_db):
    """GET /v1/audio-files/{id}/transcription: unknown audio → 404."""
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=af_r)

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.get(
            "/v1/audio-files/999/transcription",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 404


def test_transcription_get_manager_forbidden(mock_db):
    """GET /v1/audio-files/{id}/transcription: Manager role → 403."""
    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.get(
            "/v1/audio-files/1/transcription",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 403


def test_transcription_get_admin_can_view(mock_db):
    """GET /v1/audio-files/{id}/transcription: Admin bypasses assignment check."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="other-user")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    mock_db.execute = AsyncMock(return_value=af_r)

    with patch.object(main, "decode_token", return_value=ADMIN_PAYLOAD):
        response = client.get(
            "/v1/audio-files/1/transcription",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 200
    assert response.json() == {"segments": []}


