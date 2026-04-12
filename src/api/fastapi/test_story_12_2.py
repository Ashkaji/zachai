import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

# Set required environment variables before importing main
os.environ.setdefault("KEYCLOAK_ISSUER", "http://keycloak:8080/realms/zachai")
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

# Mock JWKS fetch at module import time
MOCK_JWKS = {"keys": [{"kid": "test-key", "kty": "RSA", "alg": "RS256", "use": "sig"}]}

with patch("httpx.AsyncClient") as mock_httpx:
    mock_resp = MagicMock()
    mock_resp.json.return_value = MOCK_JWKS
    mock_resp.raise_for_status = MagicMock()
    mock_httpx.return_value.__aenter__ = AsyncMock(return_value=MagicMock(get=AsyncMock(return_value=mock_resp)))
    mock_httpx.return_value.__aexit__ = AsyncMock(return_value=False)
    from src.api.fastapi.main import app, get_db, get_current_user, SnapshotArtifact, AudioFile, Project, Assignment
    import src.api.fastapi.main as main

from fastapi.testclient import TestClient
import json
import base64

client = TestClient(app)

# Seed the JWKS cache
main._jwks_cache = MOCK_JWKS

class _FakeNestedTransaction:
    """Mimics the async context manager returned by session.begin_nested()."""
    async def __aenter__(self): return self
    async def __aexit__(self, exc_type, exc_val, exc_tb): return False

@pytest.fixture
def mock_db():
    """Override get_db dependency with an AsyncMock session; clean up after each test."""
    mock_session = AsyncMock()
    # Sync methods on AsyncSession — must be plain MagicMock, not AsyncMock
    mock_session.add = MagicMock()
    mock_session.expire = MagicMock()
    # begin_nested() must return an async context manager, not a coroutine
    mock_session.begin_nested = MagicMock(return_value=_FakeNestedTransaction())

    async def override():
        yield mock_session

    app.dependency_overrides[main.get_db] = override
    yield mock_session
    app.dependency_overrides.pop(main.get_db, None)

ADMIN_PAYLOAD = {"sub": "admin-id", "realm_access": {"roles": ["Admin"]}}
MANAGER_PAYLOAD = {"sub": "manager-id", "realm_access": {"roles": ["Manager"]}}
TRANSRIPTEUR_PAYLOAD = {"sub": "transcripteur-id", "realm_access": {"roles": ["Transcripteur"]}}

def _make_mock_audio(project_id=1, audio_id=1):
    af = MagicMock(spec=AudioFile)
    af.id = audio_id
    af.project_id = project_id
    af.assignment = None
    return af

def _make_mock_project(manager_id="manager-id"):
    p = MagicMock(spec=Project)
    p.id = 1
    p.manager_id = manager_id
    return p

def _make_mock_snapshot(snapshot_id="snap-123", document_id=1):
    s = MagicMock(spec=SnapshotArtifact)
    s.snapshot_id = snapshot_id
    s.document_id = document_id
    s.json_object_key = f"snapshots/{document_id}/{snapshot_id}.json"
    s.yjs_sha256 = "dummy-sha"
    return s

@pytest.mark.asyncio
async def test_get_snapshot_yjs_not_found(mock_db):
    # Mock DB to return None for snapshot
    res = MagicMock()
    res.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = res
    
    app.dependency_overrides[get_current_user] = lambda: ADMIN_PAYLOAD
    
    response = client.get("/v1/snapshots/snap-unknown/yjs")
    assert response.status_code == 404
    assert response.json()["error"] == "Snapshot not found"

@pytest.mark.asyncio
async def test_get_snapshot_yjs_success(mock_db):
    snapshot_id = "snap-123"
    doc_id = 1
    yjs_data = b"fake-yjs-binary"
    yjs_b64 = base64.b64encode(yjs_data).decode("ascii")
    
    mock_snap = _make_mock_snapshot(snapshot_id, doc_id)
    mock_audio = _make_mock_audio(audio_id=doc_id)
    
    # Mock DB calls
    # 1. select SnapshotArtifact
    # 2. select AudioFile
    res_snap = MagicMock()
    res_snap.scalar_one_or_none.return_value = mock_snap
    res_audio = MagicMock()
    res_audio.scalar_one_or_none.return_value = mock_audio
    
    mock_db.execute.side_effect = [res_snap, res_audio]
    
    app.dependency_overrides[get_current_user] = lambda: ADMIN_PAYLOAD
    
    # Mock MinIO response
    mock_minio = MagicMock()
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({"yjs_state_binary": yjs_b64}).encode("utf-8")
    mock_minio.get_object.return_value = mock_response
    
    with patch("src.api.fastapi.main.internal_client", mock_minio):
        response = client.get(f"/v1/snapshots/{snapshot_id}/yjs")
    
    assert response.status_code == 200
    assert response.content == yjs_data

@pytest.mark.asyncio
async def test_get_snapshot_yjs_forbidden(mock_db):
    snapshot_id = "snap-123"
    doc_id = 1
    
    mock_snap = _make_mock_snapshot(snapshot_id, doc_id)
    mock_audio = _make_mock_audio(audio_id=doc_id)
    mock_audio.assignment = MagicMock(transcripteur_id="other-id")
    
    res_snap = MagicMock()
    res_snap.scalar_one_or_none.return_value = mock_snap
    res_audio = MagicMock()
    res_audio.scalar_one_or_none.return_value = mock_audio
    
    mock_db.execute.side_effect = [res_snap, res_audio]
    
    app.dependency_overrides[get_current_user] = lambda: TRANSRIPTEUR_PAYLOAD # transcripteur-id
    
    response = client.get(f"/v1/snapshots/{snapshot_id}/yjs")
    assert response.status_code == 403
    assert response.json()["error"] == "Not assigned to this audio file"

@pytest.mark.asyncio
async def test_list_audio_snapshots_success(mock_db):
    audio_id = 1
    mock_audio = _make_mock_audio(audio_id=audio_id)
    
    snap1 = _make_mock_snapshot("snap-1", audio_id)
    snap1.created_at = MagicMock()
    snap1.created_at.isoformat.return_value = "2026-04-12T10:00:00Z"
    snap1.source = "manual"
    
    snap2 = _make_mock_snapshot("snap-2", audio_id)
    snap2.created_at = MagicMock()
    snap2.created_at.isoformat.return_value = "2026-04-12T11:00:00Z"
    snap2.source = "idle"
    
    # Mock DB calls
    # 1. select AudioFile
    # 2. select SnapshotArtifact
    res_audio = MagicMock()
    res_audio.scalar_one_or_none.return_value = mock_audio
    res_snaps = MagicMock()
    res_snaps.scalars.return_value.all.return_value = [snap2, snap1]
    
    mock_db.execute.side_effect = [res_audio, res_snaps]
    
    app.dependency_overrides[get_current_user] = lambda: ADMIN_PAYLOAD
    
    response = client.get(f"/v1/audio-files/{audio_id}/snapshots")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["snapshot_id"] == "snap-2"
    assert data[1]["snapshot_id"] == "snap-1"
