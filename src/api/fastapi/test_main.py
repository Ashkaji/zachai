"""
Unit tests for ZachAI FastAPI Gateway — Story 1.3: Presigned URL Engine
Tests use mocked Keycloak JWT verification and mocked MinIO client.
Run with: pytest test_main.py -v
"""
import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient

# Set required environment variables before importing main
os.environ.setdefault("KEYCLOAK_ISSUER", "http://keycloak:8080/realms/zachai")
os.environ.setdefault("MINIO_ENDPOINT", "minio:9000")
os.environ.setdefault("MINIO_ACCESS_KEY", "minioadmin")
os.environ.setdefault("MINIO_SECRET_KEY", "minioadmin")
os.environ.setdefault("MINIO_SECURE", "false")
os.environ.setdefault("MINIO_PRESIGNED_ENDPOINT", "localhost:9000")

# Mock JWKS fetch at module import time so startup doesn't hit Keycloak
MOCK_JWKS = {"keys": [{"kid": "test-key", "kty": "RSA", "alg": "RS256", "use": "sig"}]}

with patch("httpx.AsyncClient") as mock_httpx:
    mock_resp = MagicMock()
    mock_resp.json.return_value = MOCK_JWKS
    mock_resp.raise_for_status = MagicMock()
    mock_httpx.return_value.__aenter__ = AsyncMock(return_value=MagicMock(get=AsyncMock(return_value=mock_resp)))
    mock_httpx.return_value.__aexit__ = AsyncMock(return_value=False)
    import main  # noqa: E402

client = TestClient(main.app)

# Seed the JWKS cache with mock data so decode_token attempts RS256 decode (and fails on bad tokens)
main._jwks_cache = MOCK_JWKS

# --- Shared payloads ---

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


# ─── AC 2: Health endpoint ────────────────────────────────────────────────────


def test_health_unauthenticated():
    """GET /health must be accessible without any token."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ─── AC 3: JWT authentication enforcement ────────────────────────────────────


def test_request_put_no_token():
    """POST /v1/upload/request-put without token returns 401."""
    response = client.post(
        "/v1/upload/request-put",
        json={"project_id": "proj-1", "filename": "test.mp3", "content_type": "audio/mpeg"},
    )
    assert response.status_code == 401
    assert "error" in response.json()


def test_request_put_invalid_token():
    """POST /v1/upload/request-put with garbled token returns 401."""
    response = client.post(
        "/v1/upload/request-put",
        headers={"Authorization": "Bearer not.a.valid.token"},
        json={"project_id": "proj-1", "filename": "test.mp3", "content_type": "audio/mpeg"},
    )
    assert response.status_code == 401
    assert "error" in response.json()


def test_request_get_no_token():
    """GET /v1/upload/request-get without token returns 401."""
    response = client.get("/v1/upload/request-get", params={"project_id": "proj-1", "object_key": "projects/proj-1/audio/test.mp3"})
    assert response.status_code == 401
    assert "error" in response.json()


# ─── AC 4: Presigned PUT — Manager role required ─────────────────────────────


def test_request_put_manager_success():
    """Manager role gets a valid presigned PUT URL."""
    fake_url = "http://localhost:9000/projects/proj-1/audio/test.mp3?X-Amz-Signature=abc"

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD), \
         patch.object(main.presigned_client, "presigned_put_object", return_value=fake_url):
        response = client.post(
            "/v1/upload/request-put",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"project_id": "proj-1", "filename": "test.mp3", "content_type": "audio/mpeg"},
        )

    assert response.status_code == 200
    data = response.json()
    assert "presigned_url" in data
    assert "object_key" in data
    assert "expires_in" in data
    assert data["expires_in"] == 3600
    assert data["object_key"] == "projects/proj-1/audio/test.mp3"
    assert data["presigned_url"] == fake_url


def test_request_put_expert_forbidden():
    """Expert role is forbidden from requesting PUT URLs."""
    with patch.object(main, "decode_token", return_value=EXPERT_PAYLOAD):
        response = client.post(
            "/v1/upload/request-put",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"project_id": "proj-1", "filename": "test.mp3", "content_type": "audio/mpeg"},
        )
    assert response.status_code == 403
    assert "error" in response.json()


def test_request_put_transcripteur_forbidden():
    """Transcripteur role is forbidden from requesting PUT URLs."""
    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.post(
            "/v1/upload/request-put",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"project_id": "proj-1", "filename": "test.mp3", "content_type": "audio/mpeg"},
        )
    assert response.status_code == 403
    assert "error" in response.json()


# ─── AC 5: Presigned GET — any authenticated role ────────────────────────────


@pytest.mark.parametrize("payload", [MANAGER_PAYLOAD, ADMIN_PAYLOAD, EXPERT_PAYLOAD, TRANSCRIPTEUR_PAYLOAD])
def test_request_get_all_roles_succeed(payload):
    """All 4 roles (Admin, Manager, Transcripteur, Expert) can get a presigned GET URL."""
    fake_url = "http://localhost:9000/projects/proj-1/audio/test.mp3?X-Amz-Signature=xyz"

    with patch.object(main, "decode_token", return_value=payload), \
         patch.object(main.presigned_client, "presigned_get_object", return_value=fake_url):
        response = client.get(
            "/v1/upload/request-get",
            headers={"Authorization": "Bearer dummy.token.here"},
            params={"project_id": "proj-1", "object_key": "projects/proj-1/audio/test.mp3"},
        )

    assert response.status_code == 200
    data = response.json()
    assert "presigned_url" in data
    assert data["expires_in"] == 3600
    assert data["presigned_url"] == fake_url


# ─── AC 6: Presigned URL external endpoint ───────────────────────────────────


def test_presigned_url_uses_external_endpoint():
    """Presigned PUT URL must use MINIO_PRESIGNED_ENDPOINT (localhost:9000), not minio:9000.
    The presigned_client is configured with localhost:9000 and region cache pre-seeded,
    so presigned URLs are generated without any network call and contain localhost:9000.
    """
    external_url = "http://localhost:9000/projects/proj-1/audio/a.mp3?X-Amz-Signature=abc"
    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD), \
         patch.object(main.presigned_client, "presigned_put_object", return_value=external_url):
        response = client.post(
            "/v1/upload/request-put",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"project_id": "proj-1", "filename": "a.mp3", "content_type": "audio/mpeg"},
        )
    assert response.status_code == 200
    url = response.json()["presigned_url"]
    assert "localhost:9000" in url
    assert "minio:9000" not in url


# ─── Object key scope validation ─────────────────────────────────────────────


def test_request_get_invalid_object_key_scope():
    """GET request with object_key outside allowed prefixes returns 403."""
    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.get(
            "/v1/upload/request-get",
            headers={"Authorization": "Bearer dummy.token.here"},
            params={"project_id": "proj-1", "object_key": "../../etc/passwd"},
        )
    assert response.status_code == 403
    assert "error" in response.json()


def test_request_get_object_key_must_start_with_bucket():
    """GET request with object_key in unauthorized bucket returns 403."""
    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.get(
            "/v1/upload/request-get",
            headers={"Authorization": "Bearer dummy.token.here"},
            params={"project_id": "proj-1", "object_key": "models/whisper-v1/weights.bin"},
        )
    assert response.status_code == 403


# ─── Role extraction utility ─────────────────────────────────────────────────


def test_get_roles_from_payload():
    """get_roles returns the list of realm_access.roles from JWT payload."""
    payload = {"realm_access": {"roles": ["Manager", "offline_access"]}}
    roles = main.get_roles(payload)
    assert "Manager" in roles


def test_get_roles_empty_payload():
    """get_roles returns empty list when realm_access missing."""
    roles = main.get_roles({})
    assert roles == []


# ─── Env var validation ───────────────────────────────────────────────────────


def test_startup_validates_env_vars():
    """validate_env() raises ValueError for missing required env vars."""
    with patch.dict(os.environ, {"KEYCLOAK_ISSUER": ""}, clear=False):
        with pytest.raises((ValueError, SystemExit, Exception)):
            main.validate_env()
