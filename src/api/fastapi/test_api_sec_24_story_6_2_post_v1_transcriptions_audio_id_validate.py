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

# ─── Story 6.2: POST /v1/transcriptions/{audio_id}/validate ─────────────────


def test_transcription_validate_manager_owner_approval_success(mock_db):
    """Project owner Manager can approve submitted transcription."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="user-999", status_val="transcribed")
    mock_audio.assignment.manager_validated_at = None
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    pr_r = MagicMock()
    pr_r.scalar_one_or_none.return_value = make_mock_project(project_id=1, manager_id="user-123")
    upd_r = MagicMock()
    upd_r.rowcount = 1
    mock_db.execute = AsyncMock(side_effect=[af_r, pr_r, upd_r])
    mock_db.commit = AsyncMock()

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.post(
            "/v1/transcriptions/1/validate",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"approved": True},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["audio_id"] == 1
    assert body["status"] == "validated"
    assert body["approved"] is True
    assert body["comment"] is None
    assert body["manager_validated_at"] is not None
    assert mock_audio.status == main.AudioFileStatus.VALIDATED
    assert mock_audio.assignment.manager_validated_at is not None
    mock_db.commit.assert_awaited()


def test_transcription_validate_rejection_requires_comment(mock_db):
    """Reject path requires a non-empty comment."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="user-999", status_val="transcribed")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    pr_r = MagicMock()
    pr_r.scalar_one_or_none.return_value = make_mock_project(project_id=1, manager_id="user-123")
    mock_db.execute = AsyncMock(side_effect=[af_r, pr_r])
    mock_db.commit = AsyncMock()

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.post(
            "/v1/transcriptions/1/validate",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"approved": False, "comment": "   "},
        )

    assert response.status_code == 400
    assert response.json()["error"] == "Comment is required when approved is false"
    mock_db.commit.assert_not_awaited()


def test_transcription_validate_non_owner_manager_forbidden(mock_db):
    """Non-owner Manager gets explicit 403 semantics."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="user-999", status_val="transcribed")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    pr_r = MagicMock()
    pr_r.scalar_one_or_none.return_value = make_mock_project(project_id=1, manager_id="user-123")
    mock_db.execute = AsyncMock(side_effect=[af_r, pr_r])
    mock_db.commit = AsyncMock()

    with patch.object(main, "decode_token", return_value=MANAGER_OTHER_PAYLOAD):
        response = client.post(
            "/v1/transcriptions/1/validate",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"approved": True},
        )

    assert response.status_code == 403
    assert response.json()["error"] == "Not the project owner"
    mock_db.commit.assert_not_awaited()


def test_transcription_validate_admin_support_path(mock_db):
    """Admin can validate regardless of project ownership."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="user-999", status_val="transcribed")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    pr_r = MagicMock()
    pr_r.scalar_one_or_none.return_value = make_mock_project(project_id=1, manager_id="someone-else")
    upd_r = MagicMock()
    upd_r.rowcount = 1
    mock_db.execute = AsyncMock(side_effect=[af_r, pr_r, upd_r])
    mock_db.commit = AsyncMock()

    with patch.object(main, "decode_token", return_value=ADMIN_PAYLOAD):
        response = client.post(
            "/v1/transcriptions/1/validate",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"approved": True},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "validated"
    assert response.json()["approved"] is True


def test_transcription_validate_missing_audio_404(mock_db):
    """Unknown audio returns 404 on validation route."""
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=af_r)

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.post(
            "/v1/transcriptions/999/validate",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"approved": True},
        )

    assert response.status_code == 404


def test_transcription_validate_missing_assignment_404(mock_db):
    """Audio without assignment returns 404 for validation route."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="user-999", status_val="transcribed")
    mock_audio.assignment = None
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    mock_db.execute = AsyncMock(return_value=af_r)
    mock_db.commit = AsyncMock()

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.post(
            "/v1/transcriptions/1/validate",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"approved": True},
        )

    assert response.status_code == 404
    mock_db.commit.assert_not_awaited()


@pytest.mark.parametrize("status_val", ["uploaded", "assigned", "in_progress", "validated"])
def test_transcription_validate_invalid_source_status_conflict(mock_db, status_val):
    """Only transcribed status is eligible for manager validation."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="user-999", status_val=status_val)
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    pr_r = MagicMock()
    pr_r.scalar_one_or_none.return_value = make_mock_project(project_id=1, manager_id="user-123")
    upd_r = MagicMock()
    upd_r.rowcount = 0
    mock_db.execute = AsyncMock(side_effect=[af_r, pr_r, upd_r])
    mock_db.commit = AsyncMock()

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.post(
            "/v1/transcriptions/1/validate",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"approved": True},
        )

    assert response.status_code == 409
    mock_db.commit.assert_not_awaited()


def test_transcription_validate_rejection_sets_assigned_and_echoes_comment(mock_db):
    """Reject transitions status to assigned and returns feedback comment."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="user-999", status_val="transcribed")
    mock_audio.assignment.submitted_at = datetime(2026, 3, 31, tzinfo=timezone.utc)
    mock_audio.assignment.manager_validated_at = None
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    pr_r = MagicMock()
    pr_r.scalar_one_or_none.return_value = make_mock_project(project_id=1, manager_id="user-123")
    upd_r = MagicMock()
    upd_r.rowcount = 1
    mock_db.execute = AsyncMock(side_effect=[af_r, pr_r, upd_r])
    mock_db.commit = AsyncMock()

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.post(
            "/v1/transcriptions/1/validate",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"approved": False, "comment": "Needs cleanup on speaker labels"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "assigned"
    assert body["approved"] is False
    assert body["comment"] == "Needs cleanup on speaker labels"
    assert body["manager_validated_at"] is None
    assert mock_audio.status == main.AudioFileStatus.ASSIGNED
    assert mock_audio.assignment.submitted_at is None
    assert mock_audio.assignment.manager_validated_at is None
    mock_db.commit.assert_awaited()


def test_transcription_validate_conflict_on_concurrent_transition(mock_db):
    """Concurrent transition should return 409 when conditional status update loses race."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="user-999", status_val="transcribed")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    pr_r = MagicMock()
    pr_r.scalar_one_or_none.return_value = make_mock_project(project_id=1, manager_id="user-123")
    upd_r = MagicMock()
    upd_r.rowcount = 0
    mock_db.execute = AsyncMock(side_effect=[af_r, pr_r, upd_r])
    mock_db.commit = AsyncMock()

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.post(
            "/v1/transcriptions/1/validate",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"approved": True},
        )

    assert response.status_code == 409
    assert response.json()["error"] == "Audio file status does not allow validation"
    mock_db.commit.assert_not_awaited()


def test_transcription_validate_project_missing_404(mock_db):
    """Project lookup missing for an existing audio returns 404."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="user-999", status_val="transcribed")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    pr_r = MagicMock()
    pr_r.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(side_effect=[af_r, pr_r])
    mock_db.commit = AsyncMock()

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.post(
            "/v1/transcriptions/1/validate",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"approved": True},
        )

    assert response.status_code == 404
    assert response.json()["error"] == "Project not found for audio file"
    mock_db.commit.assert_not_awaited()


def test_transcription_validate_wrong_role_403(mock_db):
    """Transcripteur role cannot validate manager workflow."""
    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.post(
            "/v1/transcriptions/1/validate",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"approved": True},
        )
    assert response.status_code == 403


def test_transcription_validate_missing_sub_401(mock_db):
    """Manager/Admin token without sub is rejected."""
    payload_no_sub = {"realm_access": {"roles": ["Manager"]}, "exp": 9999999999}
    with patch.object(main, "decode_token", return_value=payload_no_sub):
        response = client.post(
            "/v1/transcriptions/1/validate",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"approved": True},
        )
    assert response.status_code == 401


def test_transcription_validate_log_hides_comment_text(mock_db):
    """Handoff log should include metadata, not raw rejection comment text."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="user-999", status_val="transcribed")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    pr_r = MagicMock()
    pr_r.scalar_one_or_none.return_value = make_mock_project(project_id=1, manager_id="user-123")
    upd_r = MagicMock()
    upd_r.rowcount = 1
    mock_db.execute = AsyncMock(side_effect=[af_r, pr_r, upd_r])
    mock_db.commit = AsyncMock()

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD), patch.object(main.logger, "info") as log_info:
        response = client.post(
            "/v1/transcriptions/1/validate",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"approved": False, "comment": "Sensitive reviewer comment"},
        )

    assert response.status_code == 200
    # log_info is called twice: once for audit log, once for handoff log.
    assert log_info.call_count >= 1
    # Check all log calls to ensure sensitive comment is not leaked in handoff log args.
    for call in log_info.call_args_list:
        _, *args = call[0]
        assert "Sensitive reviewer comment" not in [str(x) for x in args]


