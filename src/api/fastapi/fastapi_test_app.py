"""
Shared FastAPI test bootstrap: env, JWKS mock, TestClient, and cross-suite helpers.

Imported for side effects by conftest and split API test modules (formerly test_main).
"""
from __future__ import annotations

import os
import httpx
from datetime import datetime, timezone
from typing import Annotated
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import Depends, HTTPException, Request
from fastapi.testclient import TestClient
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

os.environ.setdefault("KEYCLOAK_ISSUER", "http://keycloak:8080/realms/zachai")
os.environ.setdefault("KEYCLOAK_ADMIN_CLIENT_ID", "zachai-admin-cli")
os.environ.setdefault("KEYCLOAK_ADMIN_CLIENT_SECRET", "test-secret")
os.environ.setdefault("MINIO_ENDPOINT", "minio:9000")
os.environ.setdefault("MINIO_ACCESS_KEY", "minioadmin")
os.environ.setdefault("MINIO_SECRET_KEY", "minioadmin")
os.environ.setdefault("MINIO_SECURE", "false")
os.environ.setdefault("MINIO_PRESIGNED_ENDPOINT", "localhost:9000")
os.environ.setdefault("POSTGRES_USER", "zachai")
os.environ.setdefault("POSTGRES_PASSWORD", "changeme")
os.environ.setdefault("CAMUNDA_REST_URL", "http://camunda7:8080/engine-rest")
os.environ.setdefault("FFMPEG_WORKER_URL", "http://ffmpeg-worker:8765")
os.environ.setdefault("LABEL_STUDIO_WEBHOOK_SECRET", "test-label-studio-webhook-secret")
os.environ.setdefault("GOLDEN_SET_INTERNAL_SECRET", "test-golden-set-internal-secret")
os.environ.setdefault("GOLDEN_SET_BUCKET", "golden-set")
os.environ.setdefault("MODEL_READY_CALLBACK_SECRET", "test-model-ready-secret")
os.environ.setdefault("SNAPSHOT_CALLBACK_SECRET", "test-snapshot-secret")
os.environ.setdefault("EXPORT_WORKER_URL", "http://export-worker:8780")
os.environ.setdefault("WHISPER_OPEN_API_KEY", "test-whisper-open-api-key")
os.environ.setdefault("OPENVINO_WORKER_URL", "http://openvino-worker:8770")
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:63999/0")

MOCK_JWKS = {"keys": [{"kid": "test-key", "kty": "RSA", "alg": "RS256", "use": "sig"}]}

with patch("httpx.AsyncClient") as mock_httpx:
    mock_resp = MagicMock()
    mock_resp.json.return_value = MOCK_JWKS
    mock_resp.raise_for_status = MagicMock()
    mock_httpx.return_value.__aenter__ = AsyncMock(
        return_value=MagicMock(get=AsyncMock(return_value=mock_resp))
    )
    mock_httpx.return_value.__aexit__ = AsyncMock(return_value=False)
    import main  # noqa: E402
    import editor_ticket as editor_ticket_mod  # noqa: E402


async def get_current_user_test_override(
    _request: Request,
    db: Annotated[AsyncSession, Depends(main.get_db)],
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(main._bearer_scheme)
    ],
) -> dict:
    if credentials is None:
        raise HTTPException(status_code=401, detail={"error": "Unauthorized"})
    payload = main.decode_token(credentials.credentials)
    if not payload.get("sub"):
        for alt in ("preferred_username", "username", "email", "upn"):
            v = payload.get(alt)
            if isinstance(v, str) and v.strip():
                payload["sub"] = v
                break
    return payload


client = TestClient(main.app)
main.app.dependency_overrides[main.get_current_user] = get_current_user_test_override
main._jwks_cache = MOCK_JWKS

MANAGER_PAYLOAD = {
    "sub": "user-123",
    "realm_access": {"roles": ["Manager"]},
    "exp": 9999999999,
}
EXPERT_PAYLOAD = {
    "sub": "user-456",
    "realm_access": {"roles": ["Expert"]},
    "exp": 9999999999,
}
ADMIN_PAYLOAD = {
    "sub": "user-789",
    "realm_access": {"roles": ["Admin"]},
    "exp": 9999999999,
}
TRANSCRIPTEUR_PAYLOAD = {
    "sub": "user-999",
    "realm_access": {"roles": ["Transcripteur"]},
    "exp": 9999999999,
}
MANAGER_OTHER_PAYLOAD = {
    "sub": "manager-other",
    "realm_access": {"roles": ["Manager"]},
    "exp": 9999999999,
}


def make_mock_label(
    label_id=1,
    label_name="Orateur",
    label_color="#FF5733",
    is_speech=True,
    is_required=False,
):
    lb = MagicMock()
    lb.id = label_id
    lb.label_name = label_name
    lb.label_color = label_color
    lb.is_speech = is_speech
    lb.is_required = is_required
    return lb


def make_mock_nature(
    nature_id=1,
    name="Camp Biblique",
    description=None,
    labels=None,
    created_by="user-123",
    created_at=None,
):
    if created_at is None:
        created_at = datetime(2026, 3, 28, tzinfo=timezone.utc)
    if labels is None:
        labels = []
    n = MagicMock()
    n.id = nature_id
    n.name = name
    n.description = description
    n.created_by = created_by
    n.created_at = created_at
    n.labels = labels
    return n


class _FakeNestedTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False


def make_mock_project(
    project_id=1,
    name="Camp 2026",
    description=None,
    nature_id=1,
    production_goal="livre",
    status_val="draft",
    manager_id="user-123",
    process_instance_id=None,
    label_studio_project_id=None,
    nature=None,
    audio_files=None,
    created_at=None,
    updated_at=None,
):
    if created_at is None:
        created_at = datetime(2026, 3, 29, tzinfo=timezone.utc)
    if updated_at is None:
        updated_at = created_at
    if nature is None:
        nature = make_mock_nature()
    if audio_files is None:
        audio_files = []
    p = MagicMock()
    p.id = project_id
    p.name = name
    p.description = description
    p.nature_id = nature_id
    p.production_goal = production_goal
    p.status = {
        "draft": main.ProjectStatus.DRAFT,
        "active": main.ProjectStatus.ACTIVE,
        "completed": main.ProjectStatus.COMPLETED,
    }.get(status_val, main.ProjectStatus.DRAFT)
    p.manager_id = manager_id
    p.process_instance_id = process_instance_id
    p.label_studio_project_id = label_studio_project_id
    p.nature = nature
    p.audio_files = audio_files
    p.created_at = created_at
    p.updated_at = updated_at
    return p


def _make_mock_audio_with_assignment(
    audio_id=1,
    project_id=1,
    transcripteur_id="user-999",
    status_val="assigned",
):
    ts = datetime(2026, 3, 29, tzinfo=timezone.utc)
    af = MagicMock()
    af.id = audio_id
    af.project_id = project_id
    af.filename = "test.wav"
    af.minio_path = f"projects/{project_id}/audio/test.wav"
    af.normalized_path = f"projects/{project_id}/audio/test.normalized.wav"
    af.duration_s = 10.0
    af.validation_error = None
    af.validation_attempted_at = None
    af.uploaded_at = ts
    af.updated_at = ts
    af.status = {
        "uploaded": main.AudioFileStatus.UPLOADED,
        "assigned": main.AudioFileStatus.ASSIGNED,
        "in_progress": main.AudioFileStatus.IN_PROGRESS,
        "transcribed": main.AudioFileStatus.TRANSCRIBED,
        "validated": main.AudioFileStatus.VALIDATED,
    }[status_val]
    asg = MagicMock()
    asg.transcripteur_id = transcripteur_id
    asg.assigned_at = ts
    af.assignment = asg
    return af


def _make_mock_snapshot(
    payload_key_json="snapshots/1/latest.json",
    payload_key_docx="snapshots/1/latest.docx",
):
    snap = MagicMock()
    snap.json_object_key = payload_key_json
    snap.docx_object_key = payload_key_docx
    return snap


class _FakeMinioObject:
    def __init__(self, data: bytes):
        self._data = data

    def read(self):
        return self._data

    def close(self):
        return None

    def release_conn(self):
        return None


class _FakeRedisBible:
    def __init__(self) -> None:
        self._data: dict[str, str] = {}
        self.setex_calls = 0

    async def get(self, key: str):
        return self._data.get(key)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.setex_calls += 1
        self._data[key] = value

    async def delete(self, key: str) -> None:
        self._data.pop(key, None)

    async def incr(self, key: str) -> int:
        cur = int(self._data.get(key) or 0)
        n = cur + 1
        self._data[key] = str(n)
        return n
