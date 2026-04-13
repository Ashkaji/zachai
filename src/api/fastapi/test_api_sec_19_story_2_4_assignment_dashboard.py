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

# ─── Story 2.4 — Assignment dashboard ─────────────────────────────────────────


def test_project_close_manager_owner_success(mock_db):
    """POST /v1/projects/{id}/close closes eligible project and triggers Camunda archival."""
    af1 = MagicMock()
    af1.status = main.AudioFileStatus.VALIDATED
    af2 = MagicMock()
    af2.status = main.AudioFileStatus.VALIDATED
    mock_project = make_mock_project(project_id=1, manager_id="user-123", status_val="active", audio_files=[af1, af2])
    pr = MagicMock()
    pr.scalar_one_or_none.return_value = mock_project
    cnt_not_validated = MagicMock()
    cnt_not_validated.scalar_one.return_value = 0
    upd = MagicMock()
    upd.rowcount = 1
    refreshed = MagicMock()
    refreshed_project = make_mock_project(
        project_id=1, manager_id="user-123", status_val="completed", audio_files=[af1, af2]
    )
    refreshed.scalar_one_or_none.return_value = refreshed_project
    cnt_audio = MagicMock()
    cnt_audio.scalar_one.return_value = 2
    mock_db.execute = AsyncMock(side_effect=[pr, cnt_not_validated, upd, refreshed, cnt_audio])
    mock_db.commit = AsyncMock()

    camunda_resp = MagicMock()
    camunda_resp.status_code = 200
    camunda_resp.json.return_value = {"id": "proc-arch-1"}

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD), patch.object(
        main.camunda_client, "post", AsyncMock(return_value=camunda_resp)
    ) as camunda_post:
        response = client.post(
            "/v1/projects/1/close",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == 1
    assert body["status"] == "completed"
    assert body["idempotent"] is False
    assert body["camunda_triggered"] is True
    assert body["process_instance_id"] == "proc-arch-1"
    camunda_post.assert_awaited_once()
    assert mock_db.commit.await_count == 2


def test_project_close_admin_support_success(mock_db):
    """Admin can close project even when not owner."""
    af = MagicMock()
    af.status = main.AudioFileStatus.VALIDATED
    mock_project = make_mock_project(project_id=1, manager_id="other-manager", status_val="active", audio_files=[af])
    pr = MagicMock()
    pr.scalar_one_or_none.return_value = mock_project
    cnt_not_validated = MagicMock()
    cnt_not_validated.scalar_one.return_value = 0
    upd = MagicMock()
    upd.rowcount = 1
    refreshed = MagicMock()
    refreshed_project = make_mock_project(
        project_id=1, manager_id="other-manager", status_val="completed", audio_files=[af]
    )
    refreshed.scalar_one_or_none.return_value = refreshed_project
    cnt_audio = MagicMock()
    cnt_audio.scalar_one.return_value = 1
    mock_db.execute = AsyncMock(side_effect=[pr, cnt_not_validated, upd, refreshed, cnt_audio])
    mock_db.commit = AsyncMock()

    camunda_resp = MagicMock()
    camunda_resp.status_code = 200
    camunda_resp.json.return_value = {"id": "proc-arch-admin"}

    with patch.object(main, "decode_token", return_value=ADMIN_PAYLOAD), patch.object(
        main.camunda_client, "post", AsyncMock(return_value=camunda_resp)
    ):
        response = client.post(
            "/v1/projects/1/close",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"


def test_project_close_non_owner_manager_forbidden(mock_db):
    """Manager who does not own the project receives 403."""
    mock_project = make_mock_project(project_id=1, manager_id="owner-1", status_val="active", audio_files=[])
    pr = MagicMock()
    pr.scalar_one_or_none.return_value = mock_project
    mock_db.execute = AsyncMock(return_value=pr)
    mock_db.commit = AsyncMock()

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.post(
            "/v1/projects/1/close",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 403
    mock_db.commit.assert_not_awaited()


def test_project_close_invalid_role_forbidden(mock_db):
    """Transcripteur role is not allowed to close project."""
    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.post(
            "/v1/projects/1/close",
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert response.status_code == 403


def test_project_close_missing_project_404(mock_db):
    """Unknown project returns 404."""
    pr = MagicMock()
    pr.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=pr)

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.post(
            "/v1/projects/999/close",
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert response.status_code == 404


def test_project_close_conflict_non_validated_audio(mock_db):
    """Project close conflicts when at least one audio is not validated."""
    af1 = MagicMock()
    af1.status = main.AudioFileStatus.VALIDATED
    af2 = MagicMock()
    af2.status = main.AudioFileStatus.TRANSCRIBED
    mock_project = make_mock_project(project_id=1, manager_id="user-123", status_val="active", audio_files=[af1, af2])
    pr = MagicMock()
    pr.scalar_one_or_none.return_value = mock_project
    cnt_not_validated = MagicMock()
    cnt_not_validated.scalar_one.return_value = 1
    mock_db.execute = AsyncMock(side_effect=[pr, cnt_not_validated])
    mock_db.commit = AsyncMock()

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.post(
            "/v1/projects/1/close",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 409
    assert "all audio files are validated" in response.json()["error"]
    mock_db.commit.assert_not_awaited()


def test_project_close_idempotent_when_already_completed(mock_db):
    """Already completed project returns idempotent success and no Camunda trigger."""
    af = MagicMock()
    af.status = main.AudioFileStatus.VALIDATED
    mock_project = make_mock_project(project_id=1, manager_id="user-123", status_val="completed", audio_files=[af])
    pr = MagicMock()
    pr.scalar_one_or_none.return_value = mock_project
    mock_db.execute = AsyncMock(return_value=pr)
    mock_db.commit = AsyncMock()

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD), patch.object(
        main.camunda_client, "post", AsyncMock()
    ) as camunda_post:
        response = client.post(
            "/v1/projects/1/close",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["closed_at"] is None
    assert body["idempotent"] is True
    assert body["camunda_triggered"] is False
    assert "process_instance_id" in body
    camunda_post.assert_not_awaited()
    mock_db.commit.assert_not_awaited()


def test_project_close_camunda_failure_tolerant(mock_db):
    """Camunda outage does not fail closure response."""
    af = MagicMock()
    af.status = main.AudioFileStatus.VALIDATED
    mock_project = make_mock_project(project_id=1, manager_id="user-123", status_val="active", audio_files=[af])
    pr = MagicMock()
    pr.scalar_one_or_none.return_value = mock_project
    cnt_not_validated = MagicMock()
    cnt_not_validated.scalar_one.return_value = 0
    upd = MagicMock()
    upd.rowcount = 1
    refreshed = MagicMock()
    refreshed_project = make_mock_project(
        project_id=1, manager_id="user-123", status_val="completed", audio_files=[af]
    )
    refreshed.scalar_one_or_none.return_value = refreshed_project
    cnt_audio = MagicMock()
    cnt_audio.scalar_one.return_value = 1
    mock_db.execute = AsyncMock(side_effect=[pr, cnt_not_validated, upd, refreshed, cnt_audio])
    mock_db.commit = AsyncMock()

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD), patch.object(
        main.camunda_client, "post", AsyncMock(side_effect=httpx.ConnectError("down"))
    ):
        response = client.post(
            "/v1/projects/1/close",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["camunda_triggered"] is False
    assert mock_db.commit.await_count == 1


def test_project_close_camunda_http_error_tolerant(mock_db):
    """Camunda non-2xx response does not fail closure response."""
    af = MagicMock()
    af.status = main.AudioFileStatus.VALIDATED
    mock_project = make_mock_project(project_id=1, manager_id="user-123", status_val="active", audio_files=[af])
    pr = MagicMock()
    pr.scalar_one_or_none.return_value = mock_project
    cnt_not_validated = MagicMock()
    cnt_not_validated.scalar_one.return_value = 0
    upd = MagicMock()
    upd.rowcount = 1
    refreshed = MagicMock()
    refreshed_project = make_mock_project(
        project_id=1, manager_id="user-123", status_val="completed", audio_files=[af]
    )
    refreshed.scalar_one_or_none.return_value = refreshed_project
    cnt_audio = MagicMock()
    cnt_audio.scalar_one.return_value = 1
    mock_db.execute = AsyncMock(side_effect=[pr, cnt_not_validated, upd, refreshed, cnt_audio])
    mock_db.commit = AsyncMock()

    camunda_resp = MagicMock()
    camunda_resp.status_code = 500
    camunda_resp.json.return_value = {"type": "error"}

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD), patch.object(
        main.camunda_client, "post", AsyncMock(return_value=camunda_resp)
    ):
        response = client.post(
            "/v1/projects/1/close",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["camunda_triggered"] is False


def test_project_close_missing_sub_401(mock_db):
    """Missing sub in token returns 401 on close route."""
    payload_no_sub = {"realm_access": {"roles": ["Manager"]}, "exp": 9999999999}
    with patch.object(main, "decode_token", return_value=payload_no_sub):
        response = client.post(
            "/v1/projects/1/close",
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert response.status_code == 401


def test_project_status_not_found(mock_db):
    """GET .../status returns 404 when project missing."""
    mr = MagicMock()
    mr.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mr
    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.get(
            "/v1/projects/99/status",
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert response.status_code == 404


def test_project_status_forbidden_wrong_owner(mock_db):
    """Manager who does not own the project gets 403."""
    mock_project = make_mock_project(manager_id="someone-else")
    mr = MagicMock()
    mr.scalar_one_or_none.return_value = mock_project
    mock_db.execute.return_value = mr
    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.get(
            "/v1/projects/1/status",
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert response.status_code == 403
    assert "owner" in response.json()["error"].lower()


def test_project_status_manager_owner_success(mock_db):
    """Owner manager can read project status (AC3 happy path)."""
    mock_project = make_mock_project(manager_id="user-123")
    ts = datetime(2026, 3, 29, tzinfo=timezone.utc)
    af = MagicMock()
    af.id = 6
    af.project_id = 1
    af.filename = "owner.wav"
    af.minio_path = "projects/1/audio/owner.wav"
    af.normalized_path = "projects/1/audio/owner.normalized.wav"
    af.duration_s = 5.0
    af.status = main.AudioFileStatus.UPLOADED
    af.validation_error = None
    af.validation_attempted_at = None
    af.uploaded_at = ts
    af.updated_at = ts
    af.assignment = None
    mock_project.audio_files = [af]
    mr = MagicMock()
    mr.scalar_one_or_none.return_value = mock_project
    mock_db.execute.return_value = mr

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.get(
            "/v1/projects/1/status",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["project_status"] == "draft"
    assert body["audios"][0]["id"] == 6


def test_project_status_admin_can_view(mock_db):
    """Admin may read any project status."""
    mock_project = make_mock_project(manager_id="someone-else")
    ts = datetime(2026, 3, 29, tzinfo=timezone.utc)
    af = MagicMock()
    af.id = 5
    af.project_id = 1
    af.filename = "x.wav"
    af.minio_path = "projects/1/audio/x.wav"
    af.normalized_path = "projects/1/audio/x.normalized.wav"
    af.duration_s = 3.0
    af.status = main.AudioFileStatus.ASSIGNED
    af.validation_error = None
    af.validation_attempted_at = None
    af.uploaded_at = ts
    af.updated_at = ts
    asg = MagicMock()
    asg.transcripteur_id = "user-999"
    asg.assigned_at = ts
    af.assignment = asg
    mock_project.audio_files = [af]
    mr = MagicMock()
    mr.scalar_one_or_none.return_value = mock_project
    mock_db.execute.return_value = mr
    with patch.object(main, "decode_token", return_value=ADMIN_PAYLOAD):
        response = client.get(
            "/v1/projects/1/status",
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["project_status"] == "draft"
    assert len(body["audios"]) == 1
    a0 = body["audios"][0]
    assert a0["id"] == 5
    assert a0["status"] == "assigned"
    assert a0["assigned_to"] == "user-999"
    assert a0["normalized_path"] == "projects/1/audio/x.normalized.wav"


def test_assign_audio_success(mock_db):
    """POST assign creates assignment and sets audio to assigned."""
    mock_project = make_mock_project()
    ts = datetime(2026, 3, 29, tzinfo=timezone.utc)
    mock_audio = MagicMock()
    mock_audio.id = 10
    mock_audio.project_id = 1
    mock_audio.status = main.AudioFileStatus.UPLOADED
    mock_audio.normalized_path = "projects/1/audio/z.normalized.wav"
    mock_audio.validation_error = None
    mock_audio.filename = "z.wav"
    mock_audio.minio_path = "projects/1/audio/z.wav"
    mock_audio.duration_s = 1.0
    mock_audio.validation_attempted_at = None
    mock_audio.uploaded_at = ts
    mock_audio.updated_at = ts
    mock_audio.assignment = None

    proj_res = MagicMock()
    proj_res.scalar_one_or_none.return_value = mock_project
    audio_res = MagicMock()
    audio_res.scalar_one_or_none.return_value = mock_audio
    reloaded = MagicMock()
    reloaded.scalar_one.return_value = mock_audio

    mock_db.execute = AsyncMock(side_effect=[proj_res, audio_res, reloaded])
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()

    def capture_add(obj):
        asg = MagicMock()
        asg.transcripteur_id = getattr(obj, "transcripteur_id", "user-999")
        asg.assigned_at = ts
        mock_audio.assignment = asg

    mock_db.add = MagicMock(side_effect=capture_add)

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.post(
            "/v1/projects/1/assign",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"audio_id": 10, "transcripteur_id": "user-999"},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "assigned"
    assert data["assigned_to"] == "user-999"


def test_assign_audio_not_normalized(mock_db):
    """400 when audio has no normalized_path."""
    mock_project = make_mock_project()
    mock_audio = MagicMock()
    mock_audio.id = 11
    mock_audio.project_id = 1
    mock_audio.status = main.AudioFileStatus.UPLOADED
    mock_audio.normalized_path = None
    mock_audio.validation_error = None
    mock_audio.assignment = None

    proj_res = MagicMock()
    proj_res.scalar_one_or_none.return_value = mock_project
    audio_res = MagicMock()
    audio_res.scalar_one_or_none.return_value = mock_audio
    mock_db.execute = AsyncMock(side_effect=[proj_res, audio_res])

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.post(
            "/v1/projects/1/assign",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"audio_id": 11, "transcripteur_id": "user-999"},
        )
    assert response.status_code == 400
    assert "assignable" in response.json()["error"].lower()


def test_assign_audio_conflict_after_transcribed(mock_db):
    """409 when human workflow has reached transcribed (Story 2.4 AC4)."""
    mock_project = make_mock_project()
    mock_audio = MagicMock()
    mock_audio.id = 12
    mock_audio.project_id = 1
    mock_audio.status = main.AudioFileStatus.TRANSCRIBED
    mock_audio.normalized_path = "projects/1/audio/x.wav"
    mock_audio.validation_error = None
    mock_audio.assignment = None

    proj_res = MagicMock()
    proj_res.scalar_one_or_none.return_value = mock_project
    audio_res = MagicMock()
    audio_res.scalar_one_or_none.return_value = mock_audio
    mock_db.execute = AsyncMock(side_effect=[proj_res, audio_res])

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.post(
            "/v1/projects/1/assign",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"audio_id": 12, "transcripteur_id": "user-999"},
        )
    assert response.status_code == 409


def test_assign_audio_conflict_after_validated(mock_db):
    """409 when human workflow has reached validated (AC4 optional-409)."""
    mock_project = make_mock_project()
    mock_audio = MagicMock()
    mock_audio.id = 13
    mock_audio.project_id = 1
    mock_audio.status = main.AudioFileStatus.VALIDATED
    mock_audio.normalized_path = "projects/1/audio/v.wav"
    mock_audio.validation_error = None
    mock_audio.assignment = None

    proj_res = MagicMock()
    proj_res.scalar_one_or_none.return_value = mock_project
    audio_res = MagicMock()
    audio_res.scalar_one_or_none.return_value = mock_audio
    mock_db.execute = AsyncMock(side_effect=[proj_res, audio_res])

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.post(
            "/v1/projects/1/assign",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"audio_id": 13, "transcripteur_id": "user-999"},
        )
    assert response.status_code == 409


def test_assign_audio_not_in_project_returns_404(mock_db):
    """404 when audio id does not belong to the project in path."""
    mock_project = make_mock_project()
    proj_res = MagicMock()
    proj_res.scalar_one_or_none.return_value = mock_project
    audio_res = MagicMock()
    audio_res.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(side_effect=[proj_res, audio_res])

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.post(
            "/v1/projects/1/assign",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"audio_id": 999, "transcripteur_id": "user-999"},
        )
    assert response.status_code == 404
    assert "audio file" in response.json()["error"].lower()


def test_assign_audio_integrity_conflict_returns_409(mock_db):
    """Concurrent first assignment conflict returns explicit 409."""
    mock_project = make_mock_project()
    mock_audio = MagicMock()
    mock_audio.id = 14
    mock_audio.project_id = 1
    mock_audio.status = main.AudioFileStatus.UPLOADED
    mock_audio.normalized_path = "projects/1/audio/c.wav"
    mock_audio.validation_error = None
    mock_audio.assignment = None

    proj_res = MagicMock()
    proj_res.scalar_one_or_none.return_value = mock_project
    audio_res = MagicMock()
    audio_res.scalar_one_or_none.return_value = mock_audio
    mock_db.execute = AsyncMock(side_effect=[proj_res, audio_res])
    mock_db.commit = AsyncMock(side_effect=main.IntegrityError("stmt", "params", Exception("duplicate")))
    mock_db.rollback = AsyncMock()

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.post(
            "/v1/projects/1/assign",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"audio_id": 14, "transcripteur_id": "user-999"},
        )
    assert response.status_code == 409


def test_assign_audio_wrong_manager(mock_db):
    """403 when another manager tries to assign."""
    mock_project = make_mock_project(manager_id="owner-1")
    proj_res = MagicMock()
    proj_res.scalar_one_or_none.return_value = mock_project
    mock_db.execute.return_value = proj_res

    with patch.object(main, "decode_token", return_value=MANAGER_OTHER_PAYLOAD):
        response = client.post(
            "/v1/projects/1/assign",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"audio_id": 1, "transcripteur_id": "user-999"},
        )
    assert response.status_code == 403


def test_me_audio_tasks_transcripteur(mock_db):
    """Transcripteur sees assigned tasks."""
    ts = datetime(2026, 3, 29, tzinfo=timezone.utc)
    asg = MagicMock()
    af = MagicMock()
    af.id = 3
    af.filename = "t.wav"
    af.status = main.AudioFileStatus.ASSIGNED
    proj = MagicMock()
    proj.id = 7
    proj.name = "Proj Seven"

    mr = MagicMock()
    mr.all.return_value = [(asg, af, proj)]
    asg.assigned_at = ts
    mock_db.execute.return_value = mr

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.get(
            "/v1/me/audio-tasks",
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["audio_id"] == 3
    assert data[0]["project_id"] == 7
    assert data[0]["project_name"] == "Proj Seven"


def test_me_audio_tasks_forbidden_expert(mock_db):
    """Expert role cannot list transcripteur tasks."""
    with patch.object(main, "decode_token", return_value=EXPERT_PAYLOAD):
        response = client.get(
            "/v1/me/audio-tasks",
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert response.status_code == 403


def test_me_audio_tasks_admin_override_target_sub(mock_db):
    """Admin can inspect another transcripteur task list via query override."""
    ts = datetime(2026, 3, 29, tzinfo=timezone.utc)
    asg = MagicMock()
    asg.assigned_at = ts
    af = MagicMock()
    af.id = 8
    af.filename = "override.wav"
    af.status = main.AudioFileStatus.ASSIGNED
    proj = MagicMock()
    proj.id = 2
    proj.name = "Admin Debug"

    mr = MagicMock()
    mr.all.return_value = [(asg, af, proj)]
    mock_db.execute = AsyncMock(return_value=mr)

    with patch.object(main, "decode_token", return_value=ADMIN_PAYLOAD):
        response = client.get(
            "/v1/me/audio-tasks?transcripteur_id=user-999",
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert response.status_code == 200
    assert response.json()[0]["audio_id"] == 8


def test_expert_tasks_expert_success(mock_db):
    """Expert can list expert dashboard tasks."""
    ts = datetime(2026, 4, 1, tzinfo=timezone.utc)
    gse = MagicMock()
    gse.source = "label_studio"
    gse.weight = "high"
    gse.created_at = ts
    asg = MagicMock()
    asg.transcripteur_id = "user-456"
    asg.assigned_at = ts
    af = MagicMock()
    af.id = 11
    af.filename = "expert.wav"
    af.status = main.AudioFileStatus.TRANSCRIBED
    proj = MagicMock()
    proj.id = 3
    proj.name = "Expert Project"

    mr = MagicMock()
    mr.all.return_value = [(gse, af, proj, asg)]
    mock_db.execute.return_value = mr

    with patch.object(main, "decode_token", return_value=EXPERT_PAYLOAD):
        response = client.get(
            "/v1/expert/tasks",
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["audio_id"] == 11
    assert payload[0]["project_id"] == 3
    assert payload[0]["source"] == "label_studio"
    assert payload[0]["priority"] == "high"
    assert payload[0]["expert_id"] == "user-456"


def test_expert_tasks_admin_success(mock_db):
    """Admin can list expert dashboard tasks."""
    ts = datetime(2026, 4, 1, tzinfo=timezone.utc)
    gse = MagicMock()
    gse.source = "label_studio"
    gse.weight = "standard"
    gse.created_at = ts
    asg = MagicMock()
    asg.transcripteur_id = "user-999"
    asg.assigned_at = ts
    af = MagicMock()
    af.id = 15
    af.filename = "admin-debug.wav"
    af.status = main.AudioFileStatus.VALIDATED
    proj = MagicMock()
    proj.id = 4
    proj.name = "Admin Project"

    mr = MagicMock()
    mr.all.return_value = [(gse, af, proj, asg)]
    mock_db.execute.return_value = mr

    with patch.object(main, "decode_token", return_value=ADMIN_PAYLOAD):
        response = client.get(
            "/v1/expert/tasks",
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["audio_id"] == 15
    assert payload[0]["priority"] == "standard"


def test_expert_tasks_manager_forbidden(mock_db):
    """Manager cannot access expert dashboard tasks endpoint."""
    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.get(
            "/v1/expert/tasks",
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert response.status_code == 403


def test_expert_tasks_transcripteur_forbidden(mock_db):
    """Transcripteur cannot access expert dashboard tasks endpoint."""
    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.get(
            "/v1/expert/tasks",
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert response.status_code == 403


def test_expert_tasks_no_token_unauthorized():
    """No token returns 401."""
    response = client.get("/v1/expert/tasks")
    assert response.status_code == 401


def test_expert_tasks_empty_list(mock_db):
    """Expert endpoint returns 200 with [] when no tasks exist."""
    mr = MagicMock()
    mr.all.return_value = []
    mock_db.execute.return_value = mr
    with patch.object(main, "decode_token", return_value=EXPERT_PAYLOAD):
        response = client.get(
            "/v1/expert/tasks",
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert response.status_code == 200
    assert response.json() == []


def test_expert_tasks_expert_scope_isolation(mock_db):
    """Expert only sees rows matching own assignment sub."""
    ts = datetime(2026, 4, 1, tzinfo=timezone.utc)

    gse_ok = MagicMock()
    gse_ok.source = "label_studio"
    gse_ok.weight = "high"
    gse_ok.created_at = ts
    af_ok = MagicMock()
    af_ok.id = 21
    af_ok.filename = "own.wav"
    af_ok.status = main.AudioFileStatus.TRANSCRIBED
    proj_ok = MagicMock()
    proj_ok.id = 8
    proj_ok.name = "Own Project"
    asg_ok = MagicMock()
    asg_ok.transcripteur_id = "user-456"
    asg_ok.assigned_at = ts

    gse_other = MagicMock()
    gse_other.source = "label_studio"
    gse_other.weight = "high"
    gse_other.created_at = ts
    af_other = MagicMock()
    af_other.id = 22
    af_other.filename = "other.wav"
    af_other.status = main.AudioFileStatus.TRANSCRIBED
    proj_other = MagicMock()
    proj_other.id = 9
    proj_other.name = "Other Project"
    asg_other = MagicMock()
    asg_other.transcripteur_id = "someone-else"
    asg_other.assigned_at = ts

    mr = MagicMock()
    mr.all.return_value = [
        (gse_ok, af_ok, proj_ok, asg_ok),
        (gse_other, af_other, proj_other, asg_other),
    ]
    mock_db.execute.return_value = mr

    with patch.object(main, "decode_token", return_value=EXPERT_PAYLOAD):
        response = client.get(
            "/v1/expert/tasks",
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["audio_id"] == 21


def test_project_status_transcripteur_forbidden(mock_db):
    """Transcripteur cannot call manager status endpoint."""
    mock_project = make_mock_project()
    mr = MagicMock()
    mr.scalar_one_or_none.return_value = mock_project
    mock_db.execute.return_value = mr
    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.get(
            "/v1/projects/1/status",
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert response.status_code == 403


def test_list_projects_include_audio_summary(mock_db):
    """?include=audio_summary adds aggregate fields without per-project N+1."""
    mock_project = make_mock_project()
    r1 = MagicMock()
    r1.scalars.return_value.all.return_value = [mock_project]
    r2 = MagicMock()
    mock_row = MagicMock()
    mock_row.project_id = 1
    mock_row.uploaded = 2
    mock_row.assigned = 1
    mock_row.in_progress = 0
    mock_row.transcribed = 0
    mock_row.validated = 0
    r2.all.return_value = [mock_row]
    r3 = MagicMock()
    r3.all.return_value = [(1, 1)]
    mock_db.execute = AsyncMock(side_effect=[r1, r2, r3])

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.get(
            "/v1/projects?include=audio_summary",
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["audio_counts_by_status"]["uploaded"] == 2
    assert payload[0]["unassigned_normalized_count"] == 1


def test_register_completed_project_forbidden(mock_db):
    """Cannot register audio on completed project."""
    mock_project = make_mock_project(status_val="completed")
    mr = MagicMock()
    mr.scalar_one_or_none.return_value = mock_project
    mock_db.execute.return_value = mr
    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.post(
            "/v1/projects/1/audio-files/register",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"object_key": "projects/1/audio/x.mp3"},
        )
    assert response.status_code == 403


