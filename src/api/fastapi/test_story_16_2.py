import os
from datetime import datetime, timezone

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

# Set required environment variables before importing main
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

# Mock JWKS fetch at module import time
MOCK_JWKS = {"keys": [{"kid": "test-key", "kty": "RSA", "alg": "RS256", "use": "sig"}]}

with patch("httpx.AsyncClient") as mock_httpx:
    mock_resp = MagicMock()
    mock_resp.json.return_value = MOCK_JWKS
    mock_resp.raise_for_status = MagicMock()
    mock_httpx.return_value.__aenter__ = AsyncMock(return_value=MagicMock(get=AsyncMock(return_value=mock_resp)))
    mock_httpx.return_value.__aexit__ = AsyncMock(return_value=False)
    # We don't import ManagerMembership yet as it's not defined
    from src.api.fastapi.main import app, get_db, get_current_user
    import src.api.fastapi.main as main

from fastapi.testclient import TestClient

client = TestClient(app)

# Seed the JWKS cache
main._jwks_cache = MOCK_JWKS

@pytest.fixture
def mock_db():
    """Override get_db dependency with an AsyncMock session; clean up after each test."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.execute = AsyncMock()

    async def override():
        yield mock_session

    app.dependency_overrides[main.get_db] = override
    yield mock_session
    app.dependency_overrides.pop(main.get_db, None)

ADMIN_PAYLOAD = {"sub": "admin-id", "realm_access": {"roles": ["Admin"]}}
MANAGER_PAYLOAD = {"sub": "manager-id", "realm_access": {"roles": ["Manager"]}}
MANAGER_OTHER_PAYLOAD = {"sub": "manager-other-id", "realm_access": {"roles": ["Manager"]}}
TRANSCRIPTEUR_PAYLOAD = {"sub": "transcripteur-id", "realm_access": {"roles": ["Transcripteur"]}}
EXPERT_PAYLOAD = {"sub": "expert-id", "realm_access": {"roles": ["Expert"]}}

@pytest.mark.asyncio
async def test_post_membership_admin_success(mock_db):
    app.dependency_overrides[get_current_user] = lambda: ADMIN_PAYLOAD
    
    # Mock DB: no existing membership
    res = MagicMock()
    res.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = res
    
    response = client.post("/v1/iam/memberships", json={
        "manager_id": "manager-id",
        "member_id": "user-1"
    })

    assert response.status_code == 201
    assert response.json()["manager_id"] == "manager-id"
    assert response.json()["member_id"] == "user-1"

@pytest.mark.asyncio
async def test_post_membership_forbidden_for_manager(mock_db):
    app.dependency_overrides[get_current_user] = lambda: MANAGER_PAYLOAD
    
    response = client.post("/v1/iam/memberships", json={
        "manager_id": "manager-id",
        "member_id": "user-1"
    })
    
    assert response.status_code == 403

@pytest.mark.asyncio
async def test_post_membership_conflict(mock_db):
    app.dependency_overrides[get_current_user] = lambda: ADMIN_PAYLOAD
    
    # Mock DB: existing membership with DIFFERENT manager
    existing = MagicMock()
    existing.manager_id = "other-manager"
    existing.member_id = "user-1"
    
    res = MagicMock()
    res.scalar_one_or_none.return_value = existing
    mock_db.execute.return_value = res
    
    response = client.post("/v1/iam/memberships", json={
        "manager_id": "manager-id",
        "member_id": "user-1"
    })
    
    assert response.status_code == 409

@pytest.mark.asyncio
async def test_post_membership_idempotent_same_pair(mock_db):
    app.dependency_overrides[get_current_user] = lambda: ADMIN_PAYLOAD

    existing = MagicMock()
    existing.id = 7
    existing.manager_id = "manager-id"
    existing.member_id = "user-1"
    existing.created_at = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)

    res = MagicMock()
    res.scalar_one_or_none.return_value = existing
    mock_db.execute.return_value = res

    response = client.post("/v1/iam/memberships", json={
        "manager_id": "manager-id",
        "member_id": "user-1"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 7
    assert data["manager_id"] == "manager-id"
    assert data["member_id"] == "user-1"
    assert data["created_at"] == "2026-01-15T12:00:00+00:00"

@pytest.mark.asyncio
async def test_post_membership_forbidden_transcripteur(mock_db):
    app.dependency_overrides[get_current_user] = lambda: TRANSCRIPTEUR_PAYLOAD
    response = client.post("/v1/iam/memberships", json={
        "manager_id": "manager-id",
        "member_id": "user-1"
    })
    assert response.status_code == 403

@pytest.mark.asyncio
async def test_post_membership_forbidden_expert(mock_db):
    app.dependency_overrides[get_current_user] = lambda: EXPERT_PAYLOAD
    response = client.post("/v1/iam/memberships", json={
        "manager_id": "manager-id",
        "member_id": "user-1"
    })
    assert response.status_code == 403

@pytest.mark.asyncio
async def test_get_memberships_admin_can_read_any(mock_db):
    app.dependency_overrides[get_current_user] = lambda: ADMIN_PAYLOAD
    
    res = MagicMock()
    mock_row = MagicMock()
    mock_row.manager_id = "manager-1"
    mock_row.member_id = "user-1"
    res.scalars.return_value.all.return_value = [mock_row]
    mock_db.execute.return_value = res
    
    response = client.get("/v1/iam/memberships/manager-1")
    assert response.status_code == 200
    assert len(response.json()) == 1

@pytest.mark.asyncio
async def test_get_memberships_manager_can_read_own(mock_db):
    app.dependency_overrides[get_current_user] = lambda: MANAGER_PAYLOAD # manager-id
    
    res = MagicMock()
    res.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = res
    
    response = client.get("/v1/iam/memberships/manager-id")
    assert response.status_code == 200

@pytest.mark.asyncio
async def test_get_memberships_manager_cannot_read_other(mock_db):
    app.dependency_overrides[get_current_user] = lambda: MANAGER_PAYLOAD # manager-id
    
    response = client.get("/v1/iam/memberships/manager-other-id")
    assert response.status_code == 403

@pytest.mark.asyncio
async def test_get_memberships_transcripteur_forbidden(mock_db):
    app.dependency_overrides[get_current_user] = lambda: TRANSCRIPTEUR_PAYLOAD
    response = client.get("/v1/iam/memberships/manager-id")
    assert response.status_code == 403

@pytest.mark.asyncio
async def test_get_memberships_expert_forbidden(mock_db):
    app.dependency_overrides[get_current_user] = lambda: EXPERT_PAYLOAD
    response = client.get("/v1/iam/memberships/manager-id")
    assert response.status_code == 403

@pytest.mark.asyncio
async def test_delete_membership_admin_success(mock_db):
    app.dependency_overrides[get_current_user] = lambda: ADMIN_PAYLOAD
    
    # Mock DB: row exists
    res = MagicMock()
    res.rowcount = 1
    mock_db.execute.return_value = res
    
    response = client.delete("/v1/iam/memberships/manager-1/user-1")
    assert response.status_code == 204

@pytest.mark.asyncio
async def test_delete_membership_not_found(mock_db):
    app.dependency_overrides[get_current_user] = lambda: ADMIN_PAYLOAD
    
    # Mock DB: row does not exist
    res = MagicMock()
    res.rowcount = 0
    mock_db.execute.return_value = res
    
    response = client.delete("/v1/iam/memberships/manager-1/user-unknown")
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_delete_membership_transcripteur_forbidden(mock_db):
    app.dependency_overrides[get_current_user] = lambda: TRANSCRIPTEUR_PAYLOAD
    response = client.delete("/v1/iam/memberships/manager-1/user-1")
    assert response.status_code == 403

@pytest.mark.asyncio
async def test_delete_membership_expert_forbidden(mock_db):
    app.dependency_overrides[get_current_user] = lambda: EXPERT_PAYLOAD
    response = client.delete("/v1/iam/memberships/manager-1/user-1")
    assert response.status_code == 403
