"""
Unit tests for ZachAI FastAPI Gateway — Stories 1.3 & 2.1
Tests use mocked Keycloak JWT verification, mocked MinIO client, and mocked AsyncSession.
Run with: pytest test_main.py -v
"""
import os
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient

# Set required environment variables before importing main
os.environ.setdefault("KEYCLOAK_ISSUER", "http://keycloak:8080/realms/zachai")
os.environ.setdefault("MINIO_ENDPOINT", "minio:9000")
os.environ.setdefault("MINIO_ACCESS_KEY", "minioadmin")
os.environ.setdefault("MINIO_SECRET_KEY", "minioadmin")
os.environ.setdefault("MINIO_SECURE", "false")
os.environ.setdefault("MINIO_PRESIGNED_ENDPOINT", "localhost:9000")
os.environ.setdefault("POSTGRES_USER", "zachai")
os.environ.setdefault("POSTGRES_PASSWORD", "changeme")

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


# ─── Helpers for DB mocking ───────────────────────────────────────────────────


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


@pytest.fixture
def mock_db():
    """Override get_db dependency with an AsyncMock session; clean up after each test."""
    mock_session = AsyncMock()
    # add() is sync on AsyncSession
    mock_session.add = MagicMock()

    async def override():
        yield mock_session

    main.app.dependency_overrides[main.get_db] = override
    yield mock_session
    main.app.dependency_overrides.pop(main.get_db, None)


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
    response = client.get(
        "/v1/upload/request-get",
        params={"project_id": "proj-1", "object_key": "projects/proj-1/audio/test.mp3"},
    )
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
    """Presigned PUT URL must use MINIO_PRESIGNED_ENDPOINT (localhost:9000), not minio:9000."""
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


# ─── Story 2.1: POST /v1/natures ─────────────────────────────────────────────


def test_create_nature_success(mock_db):
    """POST /v1/natures returns 201 with full nature shape including label_studio_schema."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None  # no duplicate
    mock_db.execute.return_value = mock_result

    async def mock_refresh(obj):
        obj.id = 1
        obj.created_at = datetime(2026, 3, 28, tzinfo=timezone.utc)
        obj.labels = []

    mock_db.refresh.side_effect = mock_refresh

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.post(
            "/v1/natures",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"name": "Camp Biblique", "description": "Un camp annuel", "labels": []},
        )

    assert response.status_code == 201
    data = response.json()
    assert data["id"] == 1
    assert data["name"] == "Camp Biblique"
    assert data["description"] == "Un camp annuel"
    assert data["created_by"] == "user-123"
    assert "created_at" in data
    assert "labels" in data
    assert "label_studio_schema" in data
    assert "<View>" in data["label_studio_schema"]


def test_create_nature_with_labels(mock_db):
    """POST /v1/natures with labels returns 201; labels appear in response."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    label_mock = make_mock_label(label_id=1, label_name="Orateur", label_color="#FF5733", is_speech=True)
    non_speech_mock = make_mock_label(label_id=2, label_name="Pause", label_color="#999999", is_speech=False)

    async def mock_refresh(obj):
        obj.id = 1
        obj.created_at = datetime(2026, 3, 28, tzinfo=timezone.utc)
        obj.labels = [label_mock, non_speech_mock]

    mock_db.refresh.side_effect = mock_refresh

    def capture_add(obj):
        if hasattr(obj, "name") and not hasattr(obj, "nature_id"):
            obj.id = 1  # simulate flush populating nature.id

    mock_db.add.side_effect = capture_add

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.post(
            "/v1/natures",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={
                "name": "Camp Biblique",
                "description": None,
                "labels": [
                    {"name": "Orateur", "color": "#FF5733", "is_speech": True, "is_required": True},
                    {"name": "Pause", "color": "#999999", "is_speech": False, "is_required": False},
                ],
            },
        )

    assert response.status_code == 201
    data = response.json()
    assert len(data["labels"]) == 2
    # Speech labels first in XML
    xml = data["label_studio_schema"]
    assert xml.index("Orateur") < xml.index("Pause")


def test_create_nature_duplicate(mock_db):
    """POST /v1/natures returns 400 when name already exists."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = make_mock_nature()  # duplicate found
    mock_db.execute.return_value = mock_result

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.post(
            "/v1/natures",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"name": "Camp Biblique", "description": None, "labels": []},
        )

    assert response.status_code == 400
    assert response.json() == {"error": "Nature name already exists"}


def test_create_nature_transcripteur_forbidden(mock_db):
    """POST /v1/natures returns 403 for Transcripteur role."""
    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.post(
            "/v1/natures",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"name": "Test", "description": None, "labels": []},
        )
    assert response.status_code == 403
    assert "error" in response.json()


def test_create_nature_expert_forbidden(mock_db):
    """POST /v1/natures returns 403 for Expert role."""
    with patch.object(main, "decode_token", return_value=EXPERT_PAYLOAD):
        response = client.post(
            "/v1/natures",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"name": "Test", "description": None, "labels": []},
        )
    assert response.status_code == 403
    assert "error" in response.json()


def test_create_nature_no_token():
    """POST /v1/natures without token returns 401."""
    response = client.post(
        "/v1/natures",
        json={"name": "Test", "description": None, "labels": []},
    )
    assert response.status_code == 401
    assert "error" in response.json()


# ─── Story 2.1: GET /v1/natures ──────────────────────────────────────────────


def test_list_natures_success(mock_db):
    """GET /v1/natures returns 200 with list including label_count."""
    mock_nature = make_mock_nature(labels=[make_mock_label()])

    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [mock_nature]
    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars
    mock_db.execute.return_value = mock_result

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.get(
            "/v1/natures",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["id"] == 1
    assert data[0]["name"] == "Camp Biblique"
    assert data[0]["label_count"] == 1


def test_list_natures_empty(mock_db):
    """GET /v1/natures returns 200 with empty list when no natures exist."""
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = []
    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars
    mock_db.execute.return_value = mock_result

    with patch.object(main, "decode_token", return_value=ADMIN_PAYLOAD):
        response = client.get(
            "/v1/natures",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 200
    assert response.json() == []


def test_list_natures_transcripteur_forbidden(mock_db):
    """GET /v1/natures returns 403 for Transcripteur role."""
    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.get(
            "/v1/natures",
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert response.status_code == 403
    assert "error" in response.json()


# ─── Story 2.1: GET /v1/natures/{nature_id} ──────────────────────────────────


def test_get_nature_success(mock_db):
    """GET /v1/natures/{id} returns 200 with full nature including label_studio_schema."""
    mock_nature = make_mock_nature(
        labels=[
            make_mock_label(label_id=1, label_name="Orateur", label_color="#FF5733", is_speech=True),
        ]
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_nature
    mock_db.execute.return_value = mock_result

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.get(
            "/v1/natures/1",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 1
    assert "label_studio_schema" in data
    assert len(data["labels"]) == 1


def test_get_nature_not_found(mock_db):
    """GET /v1/natures/{id} returns 404 when nature does not exist."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.get(
            "/v1/natures/999",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 404
    assert response.json() == {"error": "Nature not found"}


def test_get_nature_expert_forbidden(mock_db):
    """GET /v1/natures/{id} returns 403 for Expert role."""
    with patch.object(main, "decode_token", return_value=EXPERT_PAYLOAD):
        response = client.get(
            "/v1/natures/1",
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert response.status_code == 403
    assert "error" in response.json()


# ─── Story 2.1: PUT /v1/natures/{nature_id}/labels ───────────────────────────


def test_update_labels_success(mock_db):
    """PUT /v1/natures/{id}/labels returns 200 with updated nature."""
    mock_nature = make_mock_nature(labels=[])
    updated_nature = make_mock_nature(
        labels=[make_mock_label(label_id=10, label_name="Traducteur", label_color="#33FF57", is_speech=True)]
    )

    mock_result_find = MagicMock()
    mock_result_find.scalar_one_or_none.return_value = mock_nature

    mock_result_delete = MagicMock()

    mock_result_reload = MagicMock()
    mock_result_reload.scalar_one.return_value = updated_nature

    mock_db.execute.side_effect = [mock_result_find, mock_result_delete, mock_result_reload]

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.put(
            "/v1/natures/1/labels",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={
                "labels": [
                    {"name": "Traducteur", "color": "#33FF57", "is_speech": True, "is_required": False}
                ]
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert len(data["labels"]) == 1
    assert data["labels"][0]["name"] == "Traducteur"
    assert "label_studio_schema" in data


def test_update_labels_not_found(mock_db):
    """PUT /v1/natures/{id}/labels returns 404 when nature does not exist."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.put(
            "/v1/natures/999/labels",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"labels": []},
        )

    assert response.status_code == 404
    assert response.json() == {"error": "Nature not found"}


def test_update_labels_transcripteur_forbidden(mock_db):
    """PUT /v1/natures/{id}/labels returns 403 for Transcripteur role."""
    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.put(
            "/v1/natures/1/labels",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"labels": []},
        )
    assert response.status_code == 403
    assert "error" in response.json()


# ─── Story 2.1: label_studio_schema XML structure ────────────────────────────


def test_generate_xml_contains_expected_tags():
    """generate_label_studio_xml produces valid Label Studio XML with required elements."""
    labels = [
        make_mock_label(label_name="Orateur", label_color="#FF5733", is_speech=True),
        make_mock_label(label_name="Pause", label_color="#999999", is_speech=False),
    ]
    xml = main.generate_label_studio_xml(labels)
    assert "<View>" in xml
    assert "<AudioPlus" in xml
    assert 'name="audio"' in xml
    assert 'value="$audio"' in xml
    assert "<Labels" in xml
    assert 'toName="audio"' in xml
    assert "<Label" in xml
    assert "Orateur" in xml
    assert "Pause" in xml
    assert "<TextArea" in xml
    assert 'placeholder="Transcription..."' in xml


def test_generate_xml_speech_labels_first():
    """generate_label_studio_xml orders speech labels before non-speech labels."""
    labels = [
        make_mock_label(label_id=1, label_name="Pause", label_color="#999999", is_speech=False),
        make_mock_label(label_id=2, label_name="Orateur", label_color="#FF5733", is_speech=True),
        make_mock_label(label_id=3, label_name="Bruit", label_color="#555555", is_speech=False),
        make_mock_label(label_id=4, label_name="Traducteur", label_color="#33FF57", is_speech=True),
    ]
    xml = main.generate_label_studio_xml(labels)
    # Both speech labels must appear before both non-speech labels
    orateur_pos = xml.index("Orateur")
    traducteur_pos = xml.index("Traducteur")
    pause_pos = xml.index("Pause")
    bruit_pos = xml.index("Bruit")
    assert orateur_pos < pause_pos
    assert orateur_pos < bruit_pos
    assert traducteur_pos < pause_pos
    assert traducteur_pos < bruit_pos
