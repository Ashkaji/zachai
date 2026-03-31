"""
Unit tests for ZachAI FastAPI Gateway — Stories 1.3, 2.1 & 2.2
Tests use mocked Keycloak JWT verification, mocked MinIO client, and mocked AsyncSession.
Run with: pytest test_main.py -v
"""
import os
import pytest
import httpx
import fakeredis.aioredis
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
from fastapi import HTTPException

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
# Unreachable Redis so lifespan leaves _redis_client None; per-test editor ticket tests patch FakeRedis
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:63999/0")

# Mock JWKS fetch at module import time so startup doesn't hit Keycloak
MOCK_JWKS = {"keys": [{"kid": "test-key", "kty": "RSA", "alg": "RS256", "use": "sig"}]}

with patch("httpx.AsyncClient") as mock_httpx:
    mock_resp = MagicMock()
    mock_resp.json.return_value = MOCK_JWKS
    mock_resp.raise_for_status = MagicMock()
    mock_httpx.return_value.__aenter__ = AsyncMock(return_value=MagicMock(get=AsyncMock(return_value=mock_resp)))
    mock_httpx.return_value.__aexit__ = AsyncMock(return_value=False)
    import main  # noqa: E402
    import editor_ticket as editor_ticket_mod  # noqa: E402

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

MANAGER_OTHER_PAYLOAD = {
    "sub": "manager-other",
    "realm_access": {"roles": ["Manager"]},
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


class _FakeNestedTransaction:
    """Mimics the async context manager returned by session.begin_nested()."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False


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
    """POST /v1/natures returns 400 when name already exists (IntegrityError on flush)."""
    from sqlalchemy.exc import IntegrityError as SAIntegrityError

    mock_db.flush.side_effect = SAIntegrityError("duplicate key", params=None, orig=Exception())

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.post(
            "/v1/natures",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"name": "Camp Biblique", "description": None, "labels": []},
        )

    assert response.status_code == 400
    assert "already exists" in response.json()["error"]


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
    mock_result_reload.scalar_one_or_none.return_value = updated_nature

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
    assert 'perRegion="true"' in xml
    assert 'displayMode="region-list"' in xml
    assert "SPEAKER_00" in xml
    assert "SPEAKER_09" in xml


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


# ─── Helpers for Project mocking (Story 2.2) ────────────────────────────────


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


# ─── Story 2.2: POST /v1/projects ──────────────────────────────────────────


def test_create_project_success(mock_db):
    """POST /v1/projects returns 201 with full project shape."""
    mock_nature = make_mock_nature(labels=[])
    # First execute: nature lookup (found)
    nature_result = MagicMock()
    nature_result.scalar_one_or_none.return_value = mock_nature
    # Second execute: duplicate name check (not found)
    dup_result = MagicMock()
    dup_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(side_effect=[nature_result, dup_result])

    mock_project = make_mock_project(nature=mock_nature)

    async def mock_refresh(obj):
        obj.id = 1
        obj.name = "Camp 2026"
        obj.description = None
        obj.nature_id = 1
        obj.production_goal = "livre"
        obj.status = MagicMock(value="draft")
        obj.manager_id = "user-123"
        obj.process_instance_id = None
        obj.label_studio_project_id = None
        obj.created_at = datetime(2026, 3, 29, tzinfo=timezone.utc)
        obj.updated_at = datetime(2026, 3, 29, tzinfo=timezone.utc)
        obj.nature = mock_nature
        obj.audio_files = []

    mock_db.refresh.side_effect = mock_refresh

    # Mock Camunda client to fail gracefully (no Camunda in test)
    mock_camunda_resp = MagicMock()
    mock_camunda_resp.status_code = 200
    mock_camunda_resp.json.return_value = {"id": "proc-123"}

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD), \
         patch.object(main, "camunda_client") as mock_camunda:
        mock_camunda.post = AsyncMock(return_value=mock_camunda_resp)
        response = client.post(
            "/v1/projects",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={
                "name": "Camp 2026",
                "nature_id": 1,
                "production_goal": "livre",
            },
        )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Camp 2026"
    assert data["production_goal"] == "livre"
    assert data["status"] == "draft"
    assert "labels" in data
    assert "nature_name" in data
    assert "created_at" in data


def test_create_project_nature_not_found(mock_db):
    """POST /v1/projects returns 400 when nature doesn't exist."""
    nature_result = MagicMock()
    nature_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=nature_result)

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.post(
            "/v1/projects",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"name": "P1", "nature_id": 999, "production_goal": "livre"},
        )

    assert response.status_code == 400
    assert "not found" in response.json()["error"]


def test_create_project_duplicate_name(mock_db):
    """POST /v1/projects returns 400 when name already exists (IntegrityError on flush)."""
    from sqlalchemy.exc import IntegrityError as SAIntegrityError

    mock_nature = make_mock_nature()
    nature_result = MagicMock()
    nature_result.scalar_one_or_none.return_value = mock_nature
    mock_db.execute = AsyncMock(return_value=nature_result)

    # Simulate duplicate name: flush() raises IntegrityError
    from sqlalchemy.pool import NullPool
    mock_db.flush = AsyncMock(side_effect=SAIntegrityError(
        "UNIQUE constraint failed", None, None
    ))
    mock_db.rollback = AsyncMock()

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.post(
            "/v1/projects",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"name": "Existing", "nature_id": 1, "production_goal": "livre"},
        )

    assert response.status_code == 400
    assert "already exists" in response.json()["error"]


def test_create_project_transcripteur_forbidden(mock_db):
    """POST /v1/projects returns 403 for Transcripteur role."""
    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.post(
            "/v1/projects",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"name": "P1", "nature_id": 1, "production_goal": "livre"},
        )
    assert response.status_code == 403


def test_create_project_expert_forbidden(mock_db):
    """POST /v1/projects returns 403 for Expert role."""
    with patch.object(main, "decode_token", return_value=EXPERT_PAYLOAD):
        response = client.post(
            "/v1/projects",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"name": "P1", "nature_id": 1, "production_goal": "livre"},
        )
    assert response.status_code == 403


def test_create_project_invalid_production_goal():
    """POST /v1/projects returns 422 for invalid production_goal."""
    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.post(
            "/v1/projects",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"name": "P1", "nature_id": 1, "production_goal": "invalid"},
        )
    assert response.status_code == 400  # Invalid production_goal per AC 6
    assert "production_goal must be one of" in response.json()["error"]


def test_create_project_camunda_unavailable(mock_db):
    """POST /v1/projects returns 201 even when Camunda is unreachable."""
    mock_nature = make_mock_nature(labels=[])
    nature_result = MagicMock()
    nature_result.scalar_one_or_none.return_value = mock_nature
    dup_result = MagicMock()
    dup_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(side_effect=[nature_result, dup_result])

    async def mock_refresh(obj):
        obj.id = 1
        obj.name = "Camp 2026"
        obj.description = None
        obj.nature_id = 1
        obj.production_goal = "livre"
        obj.status = MagicMock(value="draft")
        obj.manager_id = "user-123"
        obj.process_instance_id = None
        obj.label_studio_project_id = None
        obj.created_at = datetime(2026, 3, 29, tzinfo=timezone.utc)
        obj.updated_at = datetime(2026, 3, 29, tzinfo=timezone.utc)
        obj.nature = mock_nature
        obj.audio_files = []

    mock_db.refresh.side_effect = mock_refresh

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD), \
         patch.object(main, "camunda_client") as mock_camunda:
        mock_camunda.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        response = client.post(
            "/v1/projects",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"name": "Camp 2026", "nature_id": 1, "production_goal": "livre"},
        )

    assert response.status_code == 201
    data = response.json()
    assert data["process_instance_id"] is None  # Camunda was down


# ─── Story 2.2: GET /v1/projects ────────────────────────────────────────────


def test_list_projects_success(mock_db):
    """GET /v1/projects returns 200 with list of projects."""
    mock_project = make_mock_project()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [mock_project]
    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars
    mock_db.execute.return_value = mock_result

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.get(
            "/v1/projects",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["name"] == "Camp 2026"
    assert data[0]["nature_name"] == "Camp Biblique"


def test_list_projects_empty(mock_db):
    """GET /v1/projects returns 200 with empty list."""
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = []
    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars
    mock_db.execute.return_value = mock_result

    with patch.object(main, "decode_token", return_value=ADMIN_PAYLOAD):
        response = client.get(
            "/v1/projects",
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert response.status_code == 200
    assert response.json() == []


def test_list_projects_transcripteur_forbidden(mock_db):
    """GET /v1/projects returns 403 for Transcripteur."""
    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.get(
            "/v1/projects",
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert response.status_code == 403


# ─── Story 2.2: GET /v1/projects/{id} ──────────────────────────────────────


def test_get_project_success(mock_db):
    """GET /v1/projects/{id} returns 200 with full project."""
    mock_project = make_mock_project()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_project
    mock_db.execute.return_value = mock_result

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.get(
            "/v1/projects/1",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 1
    assert data["name"] == "Camp 2026"
    assert "labels" in data


def test_get_project_not_found(mock_db):
    """GET /v1/projects/{id} returns 404 when not found."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.get(
            "/v1/projects/999",
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert response.status_code == 404
    assert response.json() == {"error": "Project not found"}


def test_get_project_expert_forbidden(mock_db):
    """GET /v1/projects/{id} returns 403 for Expert."""
    with patch.object(main, "decode_token", return_value=EXPERT_PAYLOAD):
        response = client.get(
            "/v1/projects/1",
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert response.status_code == 403


# ─── Story 2.2: PUT /v1/projects/{id}/status ────────────────────────────────


def test_update_status_draft_to_active(mock_db):
    """PUT /v1/projects/{id}/status transitions draft → active."""
    mock_project = make_mock_project(status_val="draft")
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_project
    mock_db.execute.return_value = mock_result

    # After commit+refresh, project.status should be active
    async def mock_refresh(obj):
        obj.status = MagicMock(value="active")

    mock_db.refresh.side_effect = mock_refresh

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.put(
            "/v1/projects/1/status",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"status": "active"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "active"


def test_update_status_invalid_transition(mock_db):
    """PUT /v1/projects/{id}/status rejects completed → draft."""
    mock_project = make_mock_project(status_val="completed")
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_project
    mock_db.execute.return_value = mock_result

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.put(
            "/v1/projects/1/status",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"status": "draft"},
        )

    assert response.status_code == 400
    assert "Cannot transition" in response.json()["error"]


def test_update_status_not_found(mock_db):
    """PUT /v1/projects/{id}/status returns 404 when not found."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.put(
            "/v1/projects/999/status",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"status": "active"},
        )
    assert response.status_code == 404


def test_update_status_transcripteur_forbidden(mock_db):
    """PUT /v1/projects/{id}/status returns 403 for Transcripteur."""
    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.put(
            "/v1/projects/1/status",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"status": "active"},
        )
    assert response.status_code == 403


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


# ─── Story 2.4 — Assignment dashboard ─────────────────────────────────────────


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


# ─── Story 4.1: Golden Set — Label Studio webhook & internal ingest ─────────


LS_WEBHOOK_BODY_ONE_SEGMENT = {
    "action": "ANNOTATION_UPDATED",
    "task": {"id": 42, "data": {"audio_id": 7}},
    "annotation": {
        "id": 99,
        "result": [
            {
                "type": "labels",
                "value": {"start": 0.0, "end": 1.5, "labels": ["Orateur"]},
            },
            {"type": "textarea", "value": {"text": ["corrected hello"]}},
        ],
    },
}


def _webhook_headers():
    return {"X-ZachAI-Webhook-Secret": os.environ["LABEL_STUDIO_WEBHOOK_SECRET"]}


def test_expert_validation_webhook_no_secret_header(mock_db):
    """Missing webhook secret → 401."""
    response = client.post(
        "/v1/callback/expert-validation",
        json=LS_WEBHOOK_BODY_ONE_SEGMENT,
    )
    assert response.status_code == 401


def test_expert_validation_webhook_wrong_secret(mock_db):
    """Wrong webhook secret → 403."""
    response = client.post(
        "/v1/callback/expert-validation",
        headers={"X-ZachAI-Webhook-Secret": "not-the-secret"},
        json=LS_WEBHOOK_BODY_ONE_SEGMENT,
    )
    assert response.status_code == 403


def test_expert_validation_webhook_missing_audio(mock_db):
    """Unknown audio_id → 404."""
    dup_r = MagicMock()
    dup_r.scalar_one_or_none.return_value = None
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(side_effect=[dup_r, af_r])
    with patch.object(main.internal_client, "put_object") as mock_put:
        response = client.post(
            "/v1/callback/expert-validation",
            headers=_webhook_headers(),
            json=LS_WEBHOOK_BODY_ONE_SEGMENT,
        )
    assert response.status_code == 404
    mock_put.assert_not_called()


def test_expert_validation_webhook_writes_golden_set(mock_db):
    """Valid webhook: MinIO put + DB commit path (mocked)."""
    dup_r = MagicMock()
    dup_r.scalar_one_or_none.return_value = None
    mock_af = MagicMock()
    mock_af.project_id = 1
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_af
    mock_ctr = MagicMock()
    mock_ctr.count = 3
    mock_ctr.threshold = 1000
    ctr_r = MagicMock()
    ctr_r.scalar_one_or_none.return_value = mock_ctr
    mock_db.execute = AsyncMock(side_effect=[dup_r, af_r, ctr_r])
    mock_db.commit = AsyncMock()

    with patch.object(main.internal_client, "put_object") as mock_put, \
         patch.object(main, "camunda_client") as mock_camunda:
        mock_camunda.post = AsyncMock()
        response = client.post(
            "/v1/callback/expert-validation",
            headers=_webhook_headers(),
            json=LS_WEBHOOK_BODY_ONE_SEGMENT,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["entries_written"] == 1
    assert data["idempotency_hits"] == 0
    mock_put.assert_called_once()
    assert mock_ctr.count == 4
    mock_db.commit.assert_called_once()
    mock_camunda.post.assert_not_called()


def test_expert_validation_webhook_idempotent_repeat(mock_db):
    """Duplicate delivery: idempotency hit, no second MinIO put."""
    dup_r = MagicMock()
    dup_r.scalar_one_or_none.return_value = 123  # existing row
    mock_db.execute = AsyncMock(return_value=dup_r)
    mock_db.commit = AsyncMock()

    with patch.object(main.internal_client, "put_object") as mock_put:
        response = client.post(
            "/v1/callback/expert-validation",
            headers=_webhook_headers(),
            json=LS_WEBHOOK_BODY_ONE_SEGMENT,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["entries_written"] == 0
    assert data["idempotency_hits"] == 1
    mock_put.assert_not_called()
    mock_db.commit.assert_not_called()


def test_golden_set_internal_entry_no_auth_header(mock_db):
    """Missing auth header entirely → 401."""
    response = client.post(
        "/v1/golden-set/entry",
        json={
            "audio_id": 1,
            "segment_start": 0.0,
            "segment_end": 1.0,
            "corrected_text": "hi",
            "source": "frontend_correction",
            "weight": "standard",
        },
    )
    assert response.status_code == 401


def test_golden_set_internal_entry_wrong_secret(mock_db):
    response = client.post(
        "/v1/golden-set/entry",
        headers={"X-ZachAI-Golden-Set-Internal-Secret": "nope"},
        json={
            "audio_id": 1,
            "segment_start": 0.0,
            "segment_end": 1.0,
            "corrected_text": "hi",
            "source": "frontend_correction",
            "weight": "standard",
        },
    )
    assert response.status_code == 403


def test_golden_set_internal_entry_success(mock_db):
    dup_r = MagicMock()
    dup_r.scalar_one_or_none.return_value = None
    mock_af = MagicMock()
    mock_af.project_id = 1
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_af
    mock_ctr = MagicMock()
    mock_ctr.count = 10
    mock_ctr.threshold = 1000
    ctr_r = MagicMock()
    ctr_r.scalar_one_or_none.return_value = mock_ctr
    mock_db.execute = AsyncMock(side_effect=[dup_r, af_r, ctr_r])
    mock_db.commit = AsyncMock()

    with patch.object(main.internal_client, "put_object") as mock_put, \
         patch.object(main, "camunda_client") as mock_camunda:
        mock_camunda.post = AsyncMock()
        response = client.post(
            "/v1/golden-set/entry",
            headers={
                "X-ZachAI-Golden-Set-Internal-Secret": os.environ["GOLDEN_SET_INTERNAL_SECRET"]
            },
            json={
                "audio_id": 1,
                "segment_start": 0.0,
                "segment_end": 1.0,
                "corrected_text": "hi",
                "source": "frontend_correction",
                "weight": "standard",
            },
        )

    assert response.status_code == 200
    assert response.json()["idempotent"] is False
    mock_put.assert_called_once()
    assert mock_ctr.count == 11
    mock_camunda.post.assert_not_called()


# ─── Story 4.3: Golden Set threshold → Camunda lora-fine-tuning ─────────────


def test_golden_set_internal_entry_triggers_camunda_on_threshold_crossing(mock_db):
    """Counter crosses threshold → POST .../lora-fine-tuning/start with typed variables."""
    dup_r = MagicMock()
    dup_r.scalar_one_or_none.return_value = None
    mock_af = MagicMock()
    mock_af.project_id = 1
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_af
    mock_ctr = MagicMock()
    mock_ctr.count = 9
    mock_ctr.threshold = 10
    ctr_r = MagicMock()
    ctr_r.scalar_one_or_none.return_value = mock_ctr
    mock_db.execute = AsyncMock(side_effect=[dup_r, af_r, ctr_r])
    mock_db.commit = AsyncMock()
    mock_camunda_resp = MagicMock()
    mock_camunda_resp.status_code = 200
    mock_camunda_resp.json.return_value = {"id": "proc-lora-1"}

    with patch.object(main.internal_client, "put_object"), \
         patch.object(main, "camunda_client") as mock_camunda:
        mock_camunda.post = AsyncMock(return_value=mock_camunda_resp)
        response = client.post(
            "/v1/golden-set/entry",
            headers={
                "X-ZachAI-Golden-Set-Internal-Secret": os.environ["GOLDEN_SET_INTERNAL_SECRET"]
            },
            json={
                "audio_id": 1,
                "segment_start": 0.0,
                "segment_end": 1.0,
                "corrected_text": "hi",
                "source": "frontend_correction",
                "weight": "standard",
            },
        )

    assert response.status_code == 200
    mock_camunda.post.assert_called_once()
    url = mock_camunda.post.call_args[0][0]
    assert "lora-fine-tuning/start" in url
    variables = mock_camunda.post.call_args[1]["json"]["variables"]
    assert variables["goldenSetCount"] == {"value": 10, "type": "Integer"}
    assert variables["threshold"] == {"value": 10, "type": "Integer"}
    assert variables["triggeredAt"]["type"] == "String"
    assert len(variables["triggeredAt"]["value"]) > 10


def test_golden_set_internal_entry_idempotent_no_camunda(mock_db):
    """Idempotent short-circuit → no Camunda start."""
    dup_r = MagicMock()
    dup_r.scalar_one_or_none.return_value = 999
    mock_db.execute = AsyncMock(return_value=dup_r)

    with patch.object(main.internal_client, "put_object") as mock_put, \
         patch.object(main, "camunda_client") as mock_camunda:
        mock_camunda.post = AsyncMock()
        response = client.post(
            "/v1/golden-set/entry",
            headers={
                "X-ZachAI-Golden-Set-Internal-Secret": os.environ["GOLDEN_SET_INTERNAL_SECRET"]
            },
            json={
                "audio_id": 1,
                "segment_start": 0.0,
                "segment_end": 1.0,
                "corrected_text": "hi",
                "source": "frontend_correction",
                "weight": "standard",
            },
        )

    assert response.status_code == 200
    assert response.json()["idempotent"] is True
    mock_put.assert_not_called()
    mock_camunda.post.assert_not_called()


def test_golden_set_internal_entry_below_threshold_no_camunda(mock_db):
    """Increment does not cross threshold → no Camunda."""
    dup_r = MagicMock()
    dup_r.scalar_one_or_none.return_value = None
    mock_af = MagicMock()
    mock_af.project_id = 1
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_af
    mock_ctr = MagicMock()
    mock_ctr.count = 3
    mock_ctr.threshold = 100
    ctr_r = MagicMock()
    ctr_r.scalar_one_or_none.return_value = mock_ctr
    mock_db.execute = AsyncMock(side_effect=[dup_r, af_r, ctr_r])
    mock_db.commit = AsyncMock()

    with patch.object(main.internal_client, "put_object"), \
         patch.object(main, "camunda_client") as mock_camunda:
        mock_camunda.post = AsyncMock()
        response = client.post(
            "/v1/golden-set/entry",
            headers={
                "X-ZachAI-Golden-Set-Internal-Secret": os.environ["GOLDEN_SET_INTERNAL_SECRET"]
            },
            json={
                "audio_id": 1,
                "segment_start": 0.0,
                "segment_end": 1.0,
                "corrected_text": "hi",
                "source": "frontend_correction",
                "weight": "standard",
            },
        )

    assert response.status_code == 200
    mock_camunda.post.assert_not_called()


def test_golden_set_internal_entry_camunda_connect_error_still_2xx(mock_db):
    """Camunda ConnectError → ingest still 2xx; commit already done."""
    dup_r = MagicMock()
    dup_r.scalar_one_or_none.return_value = None
    mock_af = MagicMock()
    mock_af.project_id = 1
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_af
    mock_ctr = MagicMock()
    mock_ctr.count = 9
    mock_ctr.threshold = 10
    ctr_r = MagicMock()
    ctr_r.scalar_one_or_none.return_value = mock_ctr
    mock_db.execute = AsyncMock(side_effect=[dup_r, af_r, ctr_r])
    mock_db.commit = AsyncMock()

    with patch.object(main.internal_client, "put_object"), \
         patch.object(main, "camunda_client") as mock_camunda:
        mock_camunda.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
        response = client.post(
            "/v1/golden-set/entry",
            headers={
                "X-ZachAI-Golden-Set-Internal-Secret": os.environ["GOLDEN_SET_INTERNAL_SECRET"]
            },
            json={
                "audio_id": 1,
                "segment_start": 0.0,
                "segment_end": 1.0,
                "corrected_text": "hi",
                "source": "frontend_correction",
                "weight": "standard",
            },
        )

    assert response.status_code == 200
    mock_db.commit.assert_called_once()


def test_golden_set_internal_entry_camunda_invalid_json_still_2xx(mock_db):
    """Camunda 200 with unparseable body → ingest still 2xx; commit already done."""
    dup_r = MagicMock()
    dup_r.scalar_one_or_none.return_value = None
    mock_af = MagicMock()
    mock_af.project_id = 1
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_af
    mock_ctr = MagicMock()
    mock_ctr.count = 9
    mock_ctr.threshold = 10
    ctr_r = MagicMock()
    ctr_r.scalar_one_or_none.return_value = mock_ctr
    mock_db.execute = AsyncMock(side_effect=[dup_r, af_r, ctr_r])
    mock_db.commit = AsyncMock()

    mock_camunda_resp = MagicMock()
    mock_camunda_resp.status_code = 200
    mock_camunda_resp.json.side_effect = ValueError("not json")

    with patch.object(main.internal_client, "put_object"), \
         patch.object(main, "camunda_client") as mock_camunda:
        mock_camunda.post = AsyncMock(return_value=mock_camunda_resp)
        response = client.post(
            "/v1/golden-set/entry",
            headers={
                "X-ZachAI-Golden-Set-Internal-Secret": os.environ["GOLDEN_SET_INTERNAL_SECRET"]
            },
            json={
                "audio_id": 1,
                "segment_start": 0.0,
                "segment_end": 1.0,
                "corrected_text": "hi",
                "source": "frontend_correction",
                "weight": "standard",
            },
        )

    assert response.status_code == 200
    mock_db.commit.assert_called_once()


def test_golden_set_status_manager_ok(mock_db):
    """GET /v1/golden-set/status — Manager sees counter fields."""
    mock_row = MagicMock()
    mock_row.count = 42
    mock_row.threshold = 1000
    mock_row.last_training_at = None
    ctr_r = MagicMock()
    ctr_r.scalar_one_or_none.return_value = mock_row
    mock_db.execute = AsyncMock(return_value=ctr_r)

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.get(
            "/v1/golden-set/status",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "count": 42,
        "threshold": 1000,
        "last_training_at": None,
        "next_trigger_at": None,
    }


def test_golden_set_status_missing_row_defaults(mock_db):
    """No GoldenSetCounter row → 200 with zeros and env threshold default."""
    ctr_r = MagicMock()
    ctr_r.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=ctr_r)

    with patch.object(main, "decode_token", return_value=ADMIN_PAYLOAD):
        response = client.get(
            "/v1/golden-set/status",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 0
    assert data["threshold"] == main.GOLDEN_SET_THRESHOLD
    assert data["last_training_at"] is None
    assert data["next_trigger_at"] is None


def test_golden_set_status_transcripteur_forbidden(mock_db):
    """GET /v1/golden-set/status — Transcripteur → 403."""
    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.get(
            "/v1/golden-set/status",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 403


# ─── Story 4.2: Frontend correction route & transcription read ───────────────


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


FRONTEND_CORRECTION_BODY = {
    "audio_id": 1,
    "segment_start": 0.5,
    "segment_end": 2.0,
    "original_text": "bonjour",
    "corrected_text": "Bonjour",
}


def test_frontend_correction_happy_path_transcripteur(mock_db):
    """POST /v1/golden-set/frontend-correction: assigned Transcripteur → 200 + counter increment."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="user-999")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    dup_r = MagicMock()
    dup_r.scalar_one_or_none.return_value = None
    persist_af_r = MagicMock()
    persist_af_r.scalar_one_or_none.return_value = mock_audio
    mock_ctr = MagicMock()
    mock_ctr.count = 5
    mock_ctr.threshold = 1000
    ctr_r = MagicMock()
    ctr_r.scalar_one_or_none.return_value = mock_ctr
    mock_db.execute = AsyncMock(side_effect=[af_r, dup_r, persist_af_r, ctr_r])
    mock_db.commit = AsyncMock()

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD), \
         patch.object(main.internal_client, "put_object") as mock_put, \
         patch.object(main, "camunda_client") as mock_camunda:
        mock_camunda.post = AsyncMock()
        response = client.post(
            "/v1/golden-set/frontend-correction",
            headers={"Authorization": "Bearer dummy.token.here"},
            json=FRONTEND_CORRECTION_BODY,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["idempotent"] is False
    mock_put.assert_called_once()
    assert mock_ctr.count == 6
    mock_camunda.post.assert_not_called()


def test_frontend_correction_wrong_user_403(mock_db):
    """POST /v1/golden-set/frontend-correction: Transcripteur not assigned → 403."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="other-user")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    mock_db.execute = AsyncMock(return_value=af_r)

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.post(
            "/v1/golden-set/frontend-correction",
            headers={"Authorization": "Bearer dummy.token.here"},
            json=FRONTEND_CORRECTION_BODY,
        )

    assert response.status_code == 403
    assert "assigned" in response.json()["error"].lower()


def test_frontend_correction_wrong_role_403(mock_db):
    """POST /v1/golden-set/frontend-correction: Manager-only → 403."""
    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.post(
            "/v1/golden-set/frontend-correction",
            headers={"Authorization": "Bearer dummy.token.here"},
            json=FRONTEND_CORRECTION_BODY,
        )

    assert response.status_code == 403
    assert "role" in response.json()["error"].lower()


def test_frontend_correction_missing_audio_404(mock_db):
    """POST /v1/golden-set/frontend-correction: non-existent audio_id → 404."""
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=af_r)

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.post(
            "/v1/golden-set/frontend-correction",
            headers={"Authorization": "Bearer dummy.token.here"},
            json=FRONTEND_CORRECTION_BODY,
        )

    assert response.status_code == 404


def test_frontend_correction_idempotent_duplicate(mock_db):
    """POST /v1/golden-set/frontend-correction: same client_mutation_id → idempotent no-op."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="user-999")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    dup_r = MagicMock()
    dup_r.scalar_one_or_none.return_value = 42  # existing row
    mock_db.execute = AsyncMock(side_effect=[af_r, dup_r])
    mock_db.commit = AsyncMock()

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD), \
         patch.object(main.internal_client, "put_object") as mock_put:
        response = client.post(
            "/v1/golden-set/frontend-correction",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={**FRONTEND_CORRECTION_BODY, "client_mutation_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["idempotent"] is True
    mock_put.assert_not_called()


def test_frontend_correction_admin_bypass_assignment(mock_db):
    """POST /v1/golden-set/frontend-correction: Admin bypasses assignment check."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="other-user")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    dup_r = MagicMock()
    dup_r.scalar_one_or_none.return_value = None
    persist_af_r = MagicMock()
    persist_af_r.scalar_one_or_none.return_value = mock_audio
    mock_ctr = MagicMock()
    mock_ctr.count = 0
    mock_ctr.threshold = 1000
    ctr_r = MagicMock()
    ctr_r.scalar_one_or_none.return_value = mock_ctr
    mock_db.execute = AsyncMock(side_effect=[af_r, dup_r, persist_af_r, ctr_r])
    mock_db.commit = AsyncMock()

    with patch.object(main, "decode_token", return_value=ADMIN_PAYLOAD), \
         patch.object(main.internal_client, "put_object"), \
         patch.object(main, "camunda_client") as mock_camunda:
        mock_camunda.post = AsyncMock()
        response = client.post(
            "/v1/golden-set/frontend-correction",
            headers={"Authorization": "Bearer dummy.token.here"},
            json=FRONTEND_CORRECTION_BODY,
        )

    assert response.status_code == 200
    mock_camunda.post.assert_not_called()


def test_frontend_correction_status_409_after_submit(mock_db):
    """POST /v1/golden-set/frontend-correction: transcribed audio → 409."""
    mock_audio = _make_mock_audio_with_assignment(
        transcripteur_id="user-999", status_val="transcribed"
    )
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    mock_db.execute = AsyncMock(return_value=af_r)

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.post(
            "/v1/golden-set/frontend-correction",
            headers={"Authorization": "Bearer dummy.token.here"},
            json=FRONTEND_CORRECTION_BODY,
        )

    assert response.status_code == 409


# ─── Story 4.2: GET /v1/audio-files/{id}/transcription ──────────────────────


def test_transcription_get_happy_path(mock_db):
    """GET /v1/audio-files/{id}/transcription: assigned Transcripteur → 200 with empty segments."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="user-999")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    mock_db.execute = AsyncMock(return_value=af_r)

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.get(
            "/v1/audio-files/1/transcription",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 200
    assert response.json() == {"segments": []}


def test_transcription_get_wrong_user_403(mock_db):
    """GET /v1/audio-files/{id}/transcription: unassigned Transcripteur → 403."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="other-user")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    mock_db.execute = AsyncMock(return_value=af_r)

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.get(
            "/v1/audio-files/1/transcription",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 403


def test_transcription_get_missing_audio_404(mock_db):
    """GET /v1/audio-files/{id}/transcription: unknown audio → 404."""
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=af_r)

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.get(
            "/v1/audio-files/999/transcription",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 404


def test_transcription_get_manager_forbidden(mock_db):
    """GET /v1/audio-files/{id}/transcription: Manager role → 403."""
    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.get(
            "/v1/audio-files/1/transcription",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 403


def test_transcription_get_admin_can_view(mock_db):
    """GET /v1/audio-files/{id}/transcription: Admin bypasses assignment check."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="other-user")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    mock_db.execute = AsyncMock(return_value=af_r)

    with patch.object(main, "decode_token", return_value=ADMIN_PAYLOAD):
        response = client.get(
            "/v1/audio-files/1/transcription",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 200
    assert response.json() == {"segments": []}


# ─── Story 5.3: GET /v1/audio-files/{id}/media ──────────────────────────────


def test_audio_media_happy_path_transcripteur_assigned(mock_db):
    """GET /v1/audio-files/{id}/media: assigned Transcripteur + normalized audio → 200."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="user-999", status_val="assigned")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    mock_db.execute = AsyncMock(return_value=af_r)

    fake_url = "http://localhost:9000/projects/1/audio/test.normalized.wav?X-Amz-Signature=abc"
    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD), \
         patch.object(main.presigned_client, "presigned_get_object", return_value=fake_url):
        response = client.get(
            "/v1/audio-files/1/media",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 200
    assert response.json()["presigned_url"] == fake_url
    assert response.json()["expires_in"] == 3600


def test_audio_media_wrong_user_403(mock_db):
    """GET /v1/audio-files/{id}/media: Transcripteur not assigned → 403."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="other-user", status_val="assigned")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    mock_db.execute = AsyncMock(return_value=af_r)

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.get(
            "/v1/audio-files/1/media",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 403
    assert "error" in response.json()


def test_audio_media_wrong_role_403(mock_db):
    """GET /v1/audio-files/{id}/media: Manager role forbidden → 403."""
    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.get(
            "/v1/audio-files/1/media",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 403
    assert "error" in response.json()


def test_audio_media_missing_audio_404(mock_db):
    """GET /v1/audio-files/{id}/media: unknown audio → 404."""
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=af_r)

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.get(
            "/v1/audio-files/999/media",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 404
    assert "error" in response.json()


def test_audio_media_normalized_missing_409(mock_db):
    """GET /v1/audio-files/{id}/media: normalized_path missing → 409."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="user-999", status_val="assigned")
    mock_audio.normalized_path = None  # not eligible for playback
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    mock_db.execute = AsyncMock(return_value=af_r)

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.get(
            "/v1/audio-files/1/media",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 409
    assert "error" in response.json()


def test_audio_media_presigned_generation_failure_503(mock_db):
    """GET /v1/audio-files/{id}/media: presigned_get_object fails → 503."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="user-999", status_val="assigned")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    mock_db.execute = AsyncMock(return_value=af_r)

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD), \
         patch.object(main.presigned_client, "presigned_get_object", side_effect=Exception("minio down")):
        response = client.get(
            "/v1/audio-files/1/media",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 503
    assert "error" in response.json()


# ─── Story 4.4: POST /v1/callback/model-ready ─────────────────────────────────


def _model_ready_headers():
    return {"X-ZachAI-Model-Ready-Secret": os.environ["MODEL_READY_CALLBACK_SECRET"]}


_MODEL_READY_BODY = {
    "model_version": "whisper-cmci-test-1",
    "wer_score": 0.01,
    "minio_path": "models/whisper-cmci-test-1/",
    "training_run_id": "camunda-proc-abc123",
}


def test_model_ready_callback_no_secret(mock_db):
    response = client.post("/v1/callback/model-ready", json=_MODEL_READY_BODY)
    assert response.status_code == 401


def test_model_ready_callback_wrong_secret(mock_db):
    response = client.post(
        "/v1/callback/model-ready",
        headers={"X-ZachAI-Model-Ready-Secret": "wrong"},
        json=_MODEL_READY_BODY,
    )
    assert response.status_code == 403


def test_model_ready_callback_invalid_body(mock_db):
    response = client.post(
        "/v1/callback/model-ready",
        headers=_model_ready_headers(),
        json={"model_version": "x"},
    )
    assert response.status_code == 422


def test_model_ready_callback_success_updates_counter(mock_db):
    ins_r = MagicMock()
    ins_r.scalar_one_or_none.return_value = "camunda-proc-abc123"
    mock_ctr = MagicMock()
    mock_ctr.count = 50
    mock_ctr.threshold = 1000
    ctr_r = MagicMock()
    ctr_r.scalar_one_or_none.return_value = mock_ctr
    mock_db.execute = AsyncMock(side_effect=[ins_r, ctr_r])
    mock_db.commit = AsyncMock()

    response = client.post(
        "/v1/callback/model-ready",
        headers=_model_ready_headers(),
        json=_MODEL_READY_BODY,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["idempotent"] is False
    assert "last_training_at" in data
    assert mock_ctr.count == 0
    assert mock_ctr.last_training_at is not None
    mock_db.commit.assert_called_once()


def test_model_ready_callback_idempotent_duplicate(mock_db):
    ins_r = MagicMock()
    ins_r.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=ins_r)
    mock_db.commit = AsyncMock()

    response = client.post(
        "/v1/callback/model-ready",
        headers=_model_ready_headers(),
        json=_MODEL_READY_BODY,
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "idempotent": True}
    mock_db.commit.assert_called_once()


# ─── Story 5.2: POST /v1/editor/ticket ─────────────────────────────────────────

EDITOR_TICKET_BODY = {"document_id": 1, "permissions": ["read", "write"]}


def test_get_roles_merges_realm_and_resource_access():
    payload = {
        "realm_access": {"roles": ["Admin"]},
        "resource_access": {"zachai-frontend": {"roles": ["Transcripteur"]}},
    }
    assert set(main.get_roles(payload)) == {"Admin", "Transcripteur"}


def test_get_roles_dedupes_across_sources():
    payload = {
        "realm_access": {"roles": ["Transcripteur"]},
        "resource_access": {"account": {"roles": ["Transcripteur", "manage-account"]}},
    }
    r = main.get_roles(payload)
    assert r.count("Transcripteur") == 1
    assert "manage-account" in r


@pytest.fixture
def fake_redis():
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with patch.object(main, "_redis_client", r):
        yield r


def _make_mock_project(project_id=1, status_val="active"):
    p = MagicMock()
    p.id = project_id
    p.status = {
        "draft": main.ProjectStatus.DRAFT,
        "active": main.ProjectStatus.ACTIVE,
        "completed": main.ProjectStatus.COMPLETED,
    }[status_val]
    return p


@pytest.mark.asyncio
async def test_editor_ticket_transcripteur_happy(mock_db, fake_redis):
    """Mint ticket; payload in Redis; single-use consume (async client = same loop as fakeredis)."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="user-999")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    mock_db.execute = AsyncMock(return_value=af_r)

    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
            response = await ac.post(
                "/v1/editor/ticket",
                headers={"Authorization": "Bearer dummy.token.here"},
                json=EDITOR_TICKET_BODY,
            )

    assert response.status_code == 200
    data = response.json()
    assert data["ttl"] == editor_ticket_mod.WSS_TICKET_TTL_SEC
    tid = data["ticket_id"]
    assert len(tid) == 36

    out = await editor_ticket_mod.consume_wss_ticket(fake_redis, tid)
    assert out == {
        "sub": "user-999",
        "document_id": 1,
        "permissions": ["read", "write"],
    }
    assert await editor_ticket_mod.consume_wss_ticket(fake_redis, tid) is None


def test_editor_ticket_expert_active_project(mock_db, fake_redis):
    """Expert: no assignment check; project must be active."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="other", status_val="uploaded")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    mock_proj = _make_mock_project(status_val="active")
    proj_r = MagicMock()
    proj_r.scalar_one_or_none.return_value = mock_proj
    mock_db.execute = AsyncMock(side_effect=[af_r, proj_r])

    with patch.object(main, "decode_token", return_value=EXPERT_PAYLOAD):
        response = client.post(
            "/v1/editor/ticket",
            headers={"Authorization": "Bearer dummy.token.here"},
            json=EDITOR_TICKET_BODY,
        )

    assert response.status_code == 200
    assert response.json()["ttl"] == editor_ticket_mod.WSS_TICKET_TTL_SEC


def test_editor_ticket_expert_inactive_project_403(mock_db, fake_redis):
    mock_audio = _make_mock_audio_with_assignment()
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    mock_proj = _make_mock_project(status_val="draft")
    proj_r = MagicMock()
    proj_r.scalar_one_or_none.return_value = mock_proj
    mock_db.execute = AsyncMock(side_effect=[af_r, proj_r])

    with patch.object(main, "decode_token", return_value=EXPERT_PAYLOAD):
        response = client.post(
            "/v1/editor/ticket",
            headers={"Authorization": "Bearer dummy.token.here"},
            json=EDITOR_TICKET_BODY,
        )

    assert response.status_code == 403
    assert "active" in response.json()["error"].lower()


def test_editor_ticket_admin_bypass(mock_db, fake_redis):
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="other-user", status_val="uploaded")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    mock_db.execute = AsyncMock(return_value=af_r)

    with patch.object(main, "decode_token", return_value=ADMIN_PAYLOAD):
        response = client.post(
            "/v1/editor/ticket",
            headers={"Authorization": "Bearer dummy.token.here"},
            json=EDITOR_TICKET_BODY,
        )

    assert response.status_code == 200


def test_editor_ticket_transcripteur_wrong_user_403(mock_db, fake_redis):
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="other-user")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    mock_db.execute = AsyncMock(return_value=af_r)

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.post(
            "/v1/editor/ticket",
            headers={"Authorization": "Bearer dummy.token.here"},
            json=EDITOR_TICKET_BODY,
        )

    assert response.status_code == 403


def test_editor_ticket_transcripteur_bad_status_409(mock_db, fake_redis):
    """Parity with POST /v1/golden-set/frontend-correction (409 when status not assigned/in_progress)."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="user-999", status_val="transcribed")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    mock_db.execute = AsyncMock(return_value=af_r)

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.post(
            "/v1/editor/ticket",
            headers={"Authorization": "Bearer dummy.token.here"},
            json=EDITOR_TICKET_BODY,
        )

    assert response.status_code == 409


def test_editor_ticket_no_token_401():
    """POST /v1/editor/ticket without Authorization returns 401 (Story 5.2 AC6)."""
    response = client.post("/v1/editor/ticket", json=EDITOR_TICKET_BODY)
    assert response.status_code == 401
    assert "error" in response.json()


def test_editor_ticket_sub_fallback_to_preferred_username_happy(mock_db, fake_redis):
    """If Keycloak token omits `sub` but provides `preferred_username`, we should still mint the ticket."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="user-999", status_val="assigned")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    mock_db.execute = AsyncMock(return_value=af_r)

    payload_without_sub = {
        # `sub` missing on purpose
        "preferred_username": "user-999",
        "realm_access": {"roles": ["Transcripteur"]},
        "exp": 9999999999,
    }

    with patch.object(main, "decode_token", return_value=payload_without_sub):
        response = client.post(
            "/v1/editor/ticket",
            headers={"Authorization": "Bearer dummy.token.here"},
            json=EDITOR_TICKET_BODY,
        )

    assert response.status_code == 200


def test_editor_ticket_invalid_token_401():
    """POST /v1/editor/ticket with garbled bearer returns 401 (Story 5.2 AC6)."""
    response = client.post(
        "/v1/editor/ticket",
        headers={"Authorization": "Bearer not.a.valid.token"},
        json=EDITOR_TICKET_BODY,
    )
    assert response.status_code == 401
    assert "error" in response.json()


def test_editor_ticket_manager_forbidden(mock_db, fake_redis):
    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.post(
            "/v1/editor/ticket",
            headers={"Authorization": "Bearer dummy.token.here"},
            json=EDITOR_TICKET_BODY,
        )

    assert response.status_code == 403


def test_editor_ticket_missing_audio_404(mock_db, fake_redis):
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=af_r)

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.post(
            "/v1/editor/ticket",
            headers={"Authorization": "Bearer dummy.token.here"},
            json=EDITOR_TICKET_BODY,
        )

    assert response.status_code == 404


def test_editor_ticket_redis_unavailable_503(mock_db):
    """No FakeRedis patch — module _redis_client stays None after failed startup ping."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="user-999")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    mock_db.execute = AsyncMock(return_value=af_r)

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.post(
            "/v1/editor/ticket",
            headers={"Authorization": "Bearer dummy.token.here"},
            json=EDITOR_TICKET_BODY,
        )

    assert response.status_code == 503
    assert "redis" in response.json()["error"].lower()


def test_editor_ticket_redis_store_error_503(mock_db, fake_redis):
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="user-999")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    mock_db.execute = AsyncMock(return_value=af_r)

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD), patch.object(
        main.editor_ticket, "store_ticket", new=AsyncMock(side_effect=RuntimeError("redis down"))
    ):
        response = client.post(
            "/v1/editor/ticket",
            headers={"Authorization": "Bearer dummy.token.here"},
            json=EDITOR_TICKET_BODY,
        )

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_editor_ticket_expired_or_removed_returns_none_on_consume(mock_db, fake_redis):
    """After mint, deleting the key mimics TTL expiry — GETDEL yields None."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="user-999")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    mock_db.execute = AsyncMock(return_value=af_r)

    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
            response = await ac.post(
                "/v1/editor/ticket",
                headers={"Authorization": "Bearer dummy.token.here"},
                json=EDITOR_TICKET_BODY,
            )

    tid = response.json()["ticket_id"]
    await fake_redis.delete(editor_ticket_mod.ticket_key(tid))
    assert await editor_ticket_mod.consume_wss_ticket(fake_redis, tid) is None


def test_editor_ticket_invalid_permission_422(mock_db, fake_redis):
    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.post(
            "/v1/editor/ticket",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"document_id": 1, "permissions": ["read", "admin"]},
        )

    assert response.status_code == 422


# ─── Story 5.4: POST /v1/editor/callback/snapshot ────────────────────────────

SNAPSHOT_CALLBACK_BODY = {
    "document_id": 1,
    "yjs_state_binary": "ZmFrZS15anMtc3RhdGU=",
}


def _snapshot_headers():
    return {"X-ZachAI-Snapshot-Secret": os.environ["SNAPSHOT_CALLBACK_SECRET"]}


def test_snapshot_callback_no_secret(mock_db):
    response = client.post("/v1/editor/callback/snapshot", json=SNAPSHOT_CALLBACK_BODY)
    assert response.status_code == 401


def test_snapshot_callback_wrong_secret(mock_db):
    response = client.post(
        "/v1/editor/callback/snapshot",
        headers={"X-ZachAI-Snapshot-Secret": "wrong"},
        json=SNAPSHOT_CALLBACK_BODY,
    )
    assert response.status_code == 403


def test_snapshot_callback_invalid_body_422(mock_db):
    response = client.post(
        "/v1/editor/callback/snapshot",
        headers=_snapshot_headers(),
        json={"document_id": 1, "yjs_state_binary": "!!!"},
    )
    assert response.status_code == 422


def test_snapshot_callback_missing_audio_404(mock_db):
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=af_r)
    response = client.post(
        "/v1/editor/callback/snapshot",
        headers=_snapshot_headers(),
        json=SNAPSHOT_CALLBACK_BODY,
    )
    assert response.status_code == 404


def test_snapshot_callback_worker_unavailable_503(mock_db):
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = _make_mock_audio_with_assignment()
    mock_db.execute = AsyncMock(return_value=af_r)
    with patch.object(main, "_export_worker_client", None):
        response = client.post(
            "/v1/editor/callback/snapshot",
            headers=_snapshot_headers(),
            json=SNAPSHOT_CALLBACK_BODY,
        )
    assert response.status_code == 503


def test_snapshot_callback_export_failure_502(mock_db):
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = _make_mock_audio_with_assignment()
    mock_db.execute = AsyncMock(return_value=af_r)
    with patch.object(main, "_export_snapshot_via_worker", new=AsyncMock(side_effect=HTTPException(status_code=502, detail={"error": "Snapshot export failed"}))):
        response = client.post(
            "/v1/editor/callback/snapshot",
            headers=_snapshot_headers(),
            json=SNAPSHOT_CALLBACK_BODY,
        )
    assert response.status_code == 502


def test_snapshot_callback_success_persists_metadata(mock_db):
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = _make_mock_audio_with_assignment()
    mock_db.execute = AsyncMock(return_value=af_r)
    mock_db.commit = AsyncMock()
    worker_ok = {
        "snapshot_id": "20260330T120000Z-abc123def0",
        "json_object_key": "snapshots/1/20260330T120000Z-abc123def0.json",
        "docx_object_key": "snapshots/1/20260330T120000Z-abc123def0.docx",
        "yjs_sha256": "a" * 64,
        "json_sha256": "b" * 64,
        "docx_sha256": "c" * 64,
    }
    with patch.object(main, "_export_snapshot_via_worker", new=AsyncMock(return_value=worker_ok)):
        response = client.post(
            "/v1/editor/callback/snapshot",
            headers=_snapshot_headers(),
            json=SNAPSHOT_CALLBACK_BODY,
        )
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "snapshot_id": worker_ok["snapshot_id"]}
    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()
