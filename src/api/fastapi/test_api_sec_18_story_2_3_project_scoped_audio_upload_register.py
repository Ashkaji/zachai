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

# ─── Story 2.3: Project-scoped audio upload & register ──────────────────────


def test_project_audio_upload_manager_success(mock_db):
    """POST .../audio-files/upload returns presigned URL for draft project."""
    mock_project = make_mock_project(status_val="draft")
    mr = MagicMock()
    mr.scalar_one_or_none.return_value = mock_project
    mock_db.execute.return_value = mr
    fake_url = "http://localhost:9000/projects/1/audio/abc.mp3?X-Amz-Algorithm=AWS4"
    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD), \
         patch.object(main.presigned_client, "presigned_put_object", return_value=fake_url):
        response = client.post(
            "/v1/projects/1/audio-files/upload",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"filename": "clip.mp3", "content_type": "audio/mpeg"},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["presigned_url"] == fake_url
    assert data["expires_in"] == 3600
    assert data["object_key"].startswith("projects/1/audio/")
    assert data["object_key"].endswith(".mp3")


def test_project_audio_upload_admin_success(mock_db):
    """Admin may request project-scoped upload URL."""
    mock_project = make_mock_project(status_val="active")
    mr = MagicMock()
    mr.scalar_one_or_none.return_value = mock_project
    mock_db.execute.return_value = mr
    fake_url = "http://localhost:9000/x"
    with patch.object(main, "decode_token", return_value=ADMIN_PAYLOAD), \
         patch.object(main.presigned_client, "presigned_put_object", return_value=fake_url):
        response = client.post(
            "/v1/projects/1/audio-files/upload",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"filename": "a.wav", "content_type": "audio/wav"},
        )
    assert response.status_code == 200


def test_project_audio_upload_transcripteur_forbidden(mock_db):
    """Transcripteur cannot request upload URL (Story 2.3)."""
    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.post(
            "/v1/projects/1/audio-files/upload",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"filename": "a.mp3", "content_type": "audio/mpeg"},
        )
    assert response.status_code == 403


def test_project_audio_upload_project_not_found(mock_db):
    """404 when project missing."""
    mr = MagicMock()
    mr.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mr
    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD), \
         patch.object(main.presigned_client, "presigned_put_object", return_value="http://x"):
        response = client.post(
            "/v1/projects/999/audio-files/upload",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"filename": "a.mp3", "content_type": "audio/mpeg"},
        )
    assert response.status_code == 404
    assert response.json()["error"] == "Project not found"


def test_project_audio_upload_completed_forbidden(mock_db):
    """Completed project cannot accept new uploads (403)."""
    mock_project = make_mock_project(status_val="completed")
    mr = MagicMock()
    mr.scalar_one_or_none.return_value = mock_project
    mock_db.execute.return_value = mr
    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.post(
            "/v1/projects/1/audio-files/upload",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"filename": "a.mp3", "content_type": "audio/mpeg"},
        )
    assert response.status_code == 403
    assert "draft or active" in response.json()["error"]


def test_project_audio_upload_invalid_content_type(mock_db):
    """Invalid content_type returns 400."""
    mock_project = make_mock_project()
    mr = MagicMock()
    mr.scalar_one_or_none.return_value = mock_project
    mock_db.execute.return_value = mr
    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.post(
            "/v1/projects/1/audio-files/upload",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"filename": "a.mp3", "content_type": "text/plain"},
        )
    assert response.status_code == 400


def test_register_audio_wrong_prefix(mock_db):
    """Register rejects object_key outside projects/{id}/audio/."""
    mock_project = make_mock_project()
    mr = MagicMock()
    mr.scalar_one_or_none.return_value = mock_project
    mock_db.execute.return_value = mr
    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.post(
            "/v1/projects/1/audio-files/register",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"object_key": "projects/2/audio/foo.mp3"},
        )
    assert response.status_code == 400


def test_register_audio_not_in_minio(mock_db):
    """Register returns 400 when object not in MinIO."""
    from minio.error import S3Error

    mock_project = make_mock_project()
    mr = MagicMock()
    mr.scalar_one_or_none.return_value = mock_project
    mock_db.execute.return_value = mr
    err = S3Error(
        MagicMock(),
        "NoSuchKey",
        "not found",
        "projects/1/audio/x.mp3",
        "req-1",
        "host-1",
        "projects",
        "1/audio/x.mp3",
    )
    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD), \
         patch.object(main.internal_client, "stat_object", side_effect=err):
        response = client.post(
            "/v1/projects/1/audio-files/register",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"object_key": "projects/1/audio/x.mp3"},
        )
    assert response.status_code == 400
    assert "not found" in response.json()["error"].lower()


def test_register_audio_success_with_normalize(mock_db):
    """After register, normalization succeeds: status stays uploaded with normalized_path (Story 2.4 AC1)."""
    mock_project = make_mock_project()
    proj_res = MagicMock()
    proj_res.scalar_one_or_none.return_value = mock_project
    mock_db.execute.return_value = proj_res

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "status": "ok",
        "output_key": "1/audio/abc.normalized.wav",
        "duration_s": 42.5,
    }
    ffmpeg_client = AsyncMock()
    ffmpeg_client.post = AsyncMock(return_value=mock_resp)
    ffmpeg_client.get = AsyncMock(return_value=MagicMock(status_code=200))

    stored_audio = None

    def capture_add(obj):
        nonlocal stored_audio
        if hasattr(obj, "minio_path"):
            stored_audio = obj
            obj.id = 100
            ts = datetime(2026, 3, 29, tzinfo=timezone.utc)
            obj.uploaded_at = ts
            obj.updated_at = ts

    mock_db.add = MagicMock(side_effect=capture_add)
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD), \
         patch.object(main.internal_client, "stat_object", return_value=None), \
         patch.object(main, "_ffmpeg_client", ffmpeg_client):
        response = client.post(
            "/v1/projects/1/audio-files/register",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"object_key": "projects/1/audio/abc.mp3"},
        )

    assert response.status_code == 201
    data = response.json()
    assert data["id"] == 100
    assert data["status"] == "uploaded"
    assert data["normalized_path"] == "projects/1/audio/abc.normalized.wav"
    assert data["duration_s"] == 42.5
    assert stored_audio is not None
    assert stored_audio.status == main.AudioFileStatus.UPLOADED


def test_register_audio_success_invalid_duration_s(mock_db):
    """Non-numeric duration_s from worker does not crash; stored as null."""
    mock_project = make_mock_project()
    proj_res = MagicMock()
    proj_res.scalar_one_or_none.return_value = mock_project
    mock_db.execute.return_value = proj_res

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "status": "ok",
        "output_key": "1/audio/abc.normalized.wav",
        "duration_s": "not-a-number",
    }
    ffmpeg_client = AsyncMock()
    ffmpeg_client.post = AsyncMock(return_value=mock_resp)

    def capture_add(obj):
        if hasattr(obj, "minio_path"):
            obj.id = 102
            ts = datetime(2026, 3, 29, tzinfo=timezone.utc)
            obj.uploaded_at = ts
            obj.updated_at = ts

    mock_db.add = MagicMock(side_effect=capture_add)
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD), \
         patch.object(main.internal_client, "stat_object", return_value=None), \
         patch.object(main, "_ffmpeg_client", ffmpeg_client):
        response = client.post(
            "/v1/projects/1/audio-files/register",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"object_key": "projects/1/audio/abc.mp3"},
        )

    assert response.status_code == 201
    assert response.json()["duration_s"] is None
    assert response.json()["status"] == "uploaded"


def test_register_audio_ffmpeg_422(mock_db):
    """FFmpeg worker 422 surfaces as 422 after register commits."""
    mock_project = make_mock_project()
    proj_res = MagicMock()
    proj_res.scalar_one_or_none.return_value = mock_project
    mock_db.execute.return_value = proj_res

    mock_resp = MagicMock()
    mock_resp.status_code = 422
    mock_resp.json.return_value = {"error": "FFmpeg failed: corrupt"}
    ffmpeg_client = AsyncMock()
    ffmpeg_client.post = AsyncMock(return_value=mock_resp)

    def capture_add(obj):
        if hasattr(obj, "minio_path"):
            obj.id = 101

    mock_db.add = MagicMock(side_effect=capture_add)
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD), \
         patch.object(main.internal_client, "stat_object", return_value=None), \
         patch.object(main, "_ffmpeg_client", ffmpeg_client):
        response = client.post(
            "/v1/projects/1/audio-files/register",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"object_key": "projects/1/audio/bad.mp3"},
        )

    assert response.status_code == 422
    assert "corrupt" in response.json()["error"]


def test_normalize_on_demand_not_uploaded(mock_db):
    """On-demand normalize rejects non-uploaded status."""
    mock_project = make_mock_project()
    mock_audio = MagicMock()
    mock_audio.id = 1
    mock_audio.project_id = 1
    mock_audio.status = main.AudioFileStatus.IN_PROGRESS

    proj_res = MagicMock()
    proj_res.scalar_one_or_none.return_value = mock_project
    af_res = MagicMock()
    af_res.scalar_one_or_none.return_value = mock_audio

    mock_db.execute = AsyncMock(side_effect=[proj_res, af_res])

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.post(
            "/v1/projects/1/audio-files/1/normalize",
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert response.status_code == 400
    assert "uploaded" in response.json()["error"]


def test_normalize_on_demand_success(mock_db):
    """On-demand normalize returns updated audio file."""
    mock_project = make_mock_project()
    mock_audio = MagicMock()
    mock_audio.id = 7
    mock_audio.project_id = 1
    mock_audio.status = main.AudioFileStatus.UPLOADED
    mock_audio.minio_path = "projects/1/audio/u.mp3"
    mock_audio.filename = "u.mp3"
    mock_audio.normalized_path = None
    mock_audio.duration_s = None
    mock_audio.validation_error = None
    mock_audio.validation_attempted_at = None
    mock_audio.uploaded_at = datetime(2026, 3, 29, tzinfo=timezone.utc)
    mock_audio.updated_at = datetime(2026, 3, 29, tzinfo=timezone.utc)

    proj_res = MagicMock()
    proj_res.scalar_one_or_none.return_value = mock_project
    af_res = MagicMock()
    af_res.scalar_one_or_none.return_value = mock_audio

    mock_db.execute = AsyncMock(side_effect=[proj_res, af_res])
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "status": "ok",
        "output_key": "1/audio/u.normalized.wav",
        "duration_s": 9.0,
    }
    ffmpeg_client = AsyncMock()
    ffmpeg_client.post = AsyncMock(return_value=mock_resp)

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD), \
         patch.object(main, "_ffmpeg_client", ffmpeg_client):
        response = client.post(
            "/v1/projects/1/audio-files/7/normalize",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "uploaded"
    assert mock_audio.status == main.AudioFileStatus.UPLOADED


