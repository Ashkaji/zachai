
import pytest
import json
import io
import zipfile
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient

# Set env vars before import
import os
os.environ["KEYCLOAK_ISSUER"] = "http://test"
os.environ["KEYCLOAK_ADMIN_CLIENT_ID"] = "zachai-admin-cli"
os.environ["KEYCLOAK_ADMIN_CLIENT_SECRET"] = "test-secret"
os.environ["MINIO_ENDPOINT"] = "localhost:9000"
os.environ["MINIO_ACCESS_KEY"] = "minio"
os.environ["MINIO_SECRET_KEY"] = "minio"
os.environ["MINIO_SECURE"] = "false"
os.environ["MINIO_PRESIGNED_ENDPOINT"] = "localhost:9000"
os.environ["POSTGRES_USER"] = "p"
os.environ["POSTGRES_PASSWORD"] = "p"
os.environ["REDIS_URL"] = "redis://localhost"
os.environ["CAMUNDA_REST_URL"] = "http://c"
os.environ["FFMPEG_WORKER_URL"] = "http://f"

# Mock AsyncSessionLocal before importing main to avoid engine creation issues
with patch("sqlalchemy.ext.asyncio.create_async_engine"), \
     patch("sqlalchemy.ext.asyncio.async_sessionmaker"):
    import main
    from main import app, UserConsent, AuditLog, Assignment, AudioFile, Project

client = TestClient(app)

# Payloads for different roles
ADMIN_PAYLOAD = {"sub": "admin-1", "realm_access": {"roles": ["Admin"]}, "exp": 9999999999}
USER_PAYLOAD = {"sub": "user-1", "realm_access": {"roles": ["Transcripteur"]}, "exp": 9999999999}

@pytest.fixture
def mock_db():
    db = AsyncMock()
    
    async def override_get_db():
        yield db
        
    app.dependency_overrides[main.get_db] = override_get_db
    yield db
    app.dependency_overrides.clear()

def test_get_profile_lazy_init(mock_db):
    """Profile GET should initialize UserConsent if not exists."""
    res = MagicMock()
    res.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = res
    
    # Mock refresh to set required fields
    async def mock_refresh(obj):
        obj.updated_at = datetime.now(timezone.utc)
        obj.ml_usage_approved = False
        obj.biometric_data_approved = False
    mock_db.refresh.side_effect = mock_refresh

    with patch("main.decode_token", return_value=USER_PAYLOAD):
        response = client.get("/v1/me/profile", headers={"Authorization": "Bearer t"})
    
    assert response.status_code == 200
    data = response.json()
    assert data["sub"] == "user-1"
    assert data["consents"]["ml_usage"] is False
    assert mock_db.add.called

def test_update_consents_ml_purge(mock_db):
    """Withdrawing ML consent should purge frontend corrections."""
    consent = UserConsent(
        user_id="user-1", 
        ml_usage_approved=True, 
        biometric_data_approved=True,
        updated_at=datetime.now(timezone.utc)
    )
    res = MagicMock()
    res.scalar_one_or_none.return_value = consent
    mock_db.execute.return_value = res
    
    # Mock refresh to ensure updated_at is there
    async def mock_refresh(obj):
        obj.updated_at = datetime.now(timezone.utc)
    mock_db.refresh.side_effect = mock_refresh

    with patch("main.decode_token", return_value=USER_PAYLOAD):
        response = client.put(
            "/v1/me/consents", 
            json={"ml_usage": False, "biometric_data": True},
            headers={"Authorization": "Bearer t"}
        )
    
    assert response.status_code == 200
    assert response.json()["ml_usage"] is False
    assert mock_db.execute.call_count >= 3

def test_account_deletion_flow(mock_db):
    """Test request and cancel deletion."""
    consent = UserConsent(
        user_id="user-1", 
        deletion_pending_at=None,
        updated_at=datetime.now(timezone.utc),
        ml_usage_approved=False,
        biometric_data_approved=False
    )
    res = MagicMock()
    res.scalar_one_or_none.return_value = consent
    mock_db.execute.return_value = res
    
    # Mock refresh
    async def mock_refresh(obj):
        obj.updated_at = datetime.now(timezone.utc)
    mock_db.refresh.side_effect = mock_refresh

    with patch("main.decode_token", return_value=USER_PAYLOAD):
        # 1. Request deletion
        resp1 = client.delete("/v1/me/account", headers={"Authorization": "Bearer t"})
        assert resp1.status_code == 200
        assert resp1.json()["deletion_pending"] is True
        
        # 2. Cancel deletion
        resp2 = client.post("/v1/me/delete-cancel", headers={"Authorization": "Bearer t"})
        assert resp2.status_code == 200
        assert resp2.json()["deletion_pending"] is False

def test_access_guard_blocks_when_pending(mock_db):
    """Access Guard should block write operations when deletion is pending."""
    consent = UserConsent(
        user_id="user-1", 
        deletion_pending_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        ml_usage_approved=False,
        biometric_data_approved=False
    )
    res = MagicMock()
    res.scalar_one_or_none.return_value = consent
    mock_db.execute.return_value = res
    
    with patch("main.decode_token", return_value=USER_PAYLOAD):
        # PUT should be blocked (403)
        response = client.put("/v1/me/consents", json={"ml_usage": True, "biometric_data": True}, headers={"Authorization": "Bearer t"})
        assert response.status_code == 403
        # Response body for 403 might vary depending on how Starlette handles HTTPException
        # If detail is a dict, it should be in ["detail"]
        data = response.json()
        assert "Account deletion pending" in str(data)
        
        # Profile GET should NOT be blocked (200)
        response_get = client.get("/v1/me/profile", headers={"Authorization": "Bearer t"})
        assert response_get.status_code == 200

def test_export_data_redis_lock(mock_db):
    """Export data should check for Redis lock."""
    res_guard = MagicMock()
    res_guard.scalar_one_or_none.return_value = None
    
    # Mock result for get_current_user check (no deletion pending)
    res_consent = MagicMock()
    res_consent.scalar_one_or_none.return_value = None
    
    # We'll use a side_effect to handle multiple calls to execute
    mock_db.execute.side_effect = [
        res_guard, # get_current_user
        res_consent, # export_my_data profile consent
        MagicMock(all=MagicMock(return_value=[])), # assignments
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))), # corrections
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))), # audit logs
    ]

    with patch("main.decode_token", return_value=USER_PAYLOAD):
        with patch("main._redis_client") as mock_redis:
            mock_redis.set = AsyncMock(return_value=False) # Lock already held
            response = client.get("/v1/me/export-data", headers={"Authorization": "Bearer t"})
            assert response.status_code == 429

def test_admin_purge_user(mock_db):
    """Admin should be able to trigger immediate purge."""
    res_guard = MagicMock()
    res_guard.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = res_guard

    with patch("main.decode_token", return_value=ADMIN_PAYLOAD):
        response = client.delete("/v1/admin/purge-user/user-target", headers={"Authorization": "Bearer t"})
        assert response.status_code == 200
        assert response.json()["status"] == "purged"
        assert mock_db.execute.called
