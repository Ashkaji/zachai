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

# ─── Story 6.1: POST /v1/transcriptions/{audio_id}/submit ───────────────────


def test_transcription_submit_happy_path_assigned_transcripteur(mock_db):
    """Assigned Transcripteur can submit and audio becomes transcribed."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="user-999", status_val="assigned")
    mock_audio.assignment.submitted_at = None
    mock_audio.assignment.manager_validated_at = None
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    mock_db.execute = AsyncMock(return_value=af_r)
    mock_db.commit = AsyncMock()

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.post(
            "/v1/transcriptions/1/submit",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["audio_id"] == 1
    assert body["status"] == "transcribed"
    assert body["idempotent"] is False
    assert body["submitted_at"] is not None
    assert mock_audio.status == main.AudioFileStatus.TRANSCRIBED
    assert mock_audio.assignment.submitted_at is not None
    assert mock_audio.assignment.manager_validated_at is None
    mock_db.commit.assert_awaited()


def test_transcription_submit_admin_bypass_assignment(mock_db):
    """Admin can submit even when not assigned."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="other-user", status_val="in_progress")
    mock_audio.assignment.submitted_at = None
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    mock_db.execute = AsyncMock(return_value=af_r)
    mock_db.commit = AsyncMock()

    with patch.object(main, "decode_token", return_value=ADMIN_PAYLOAD):
        response = client.post(
            "/v1/transcriptions/1/submit",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "transcribed"
    assert response.json()["idempotent"] is False


def test_transcription_submit_wrong_user_403(mock_db):
    """Transcripteur not assigned to audio receives 403."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="other-user", status_val="assigned")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    mock_db.execute = AsyncMock(return_value=af_r)

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.post(
            "/v1/transcriptions/1/submit",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 403


def test_transcription_submit_wrong_role_403(mock_db):
    """Manager role cannot submit transcripteur transcription."""
    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.post(
            "/v1/transcriptions/1/submit",
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert response.status_code == 403


def test_transcription_submit_missing_audio_404(mock_db):
    """Missing audio returns 404."""
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=af_r)

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.post(
            "/v1/transcriptions/999/submit",
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert response.status_code == 404


def test_transcription_submit_missing_assignment_404(mock_db):
    """Audio without assignment returns 404 for submission endpoint."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="user-999", status_val="assigned")
    mock_audio.assignment = None
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    mock_db.execute = AsyncMock(return_value=af_r)

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.post(
            "/v1/transcriptions/1/submit",
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert response.status_code == 404


def test_transcription_submit_invalid_status_409(mock_db):
    """Uploaded audio cannot be submitted."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="user-999", status_val="uploaded")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    mock_db.execute = AsyncMock(return_value=af_r)

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.post(
            "/v1/transcriptions/1/submit",
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert response.status_code == 409


def test_transcription_submit_idempotent_repeat(mock_db):
    """Already submitted transcribed audio returns idempotent success."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="user-999", status_val="transcribed")
    mock_audio.assignment.submitted_at = datetime(2026, 3, 31, tzinfo=timezone.utc)
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    mock_db.execute = AsyncMock(return_value=af_r)
    mock_db.commit = AsyncMock()

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.post(
            "/v1/transcriptions/1/submit",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "transcribed"
    assert body["idempotent"] is True
    assert body["submitted_at"] is not None
    mock_db.commit.assert_not_awaited()


