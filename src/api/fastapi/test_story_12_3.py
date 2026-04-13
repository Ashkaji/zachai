import hashlib
import base64
import json
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import HTTPException

# Environment required before importing main (same pattern as test_main.py)
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
    mock_httpx.return_value.__aenter__ = AsyncMock(return_value=MagicMock(get=AsyncMock(return_value=mock_resp)))
    mock_httpx.return_value.__aexit__ = AsyncMock(return_value=False)
    from main import (
        AudioFileStatus,
        EditorTicketRequest,
        DocumentRestoreRequest,
        DocumentRestoreFailureCode,
        _document_restore_failed_signal,
        _restore_document_from_snapshot_core,
        post_editor_ticket,
        restore_document_from_snapshot,
        restore_snapshot_by_id,
    )


@pytest.mark.asyncio
async def test_restore_document_logic():
    mock_redis = AsyncMock()
    mock_db = AsyncMock(spec=AsyncSession)
    mock_user = {"sub": "user-123", "name": "Test User"}

    yjs_bytes = base64.b64decode("YmFzZTY0ZGF0YQ==", validate=True)
    integrity_sha = hashlib.sha256(yjs_bytes).hexdigest()

    mock_snap = MagicMock()
    mock_snap.json_object_key = "snapshots/snap-1.json"
    mock_snap.yjs_sha256 = integrity_sha

    mock_asg = MagicMock()
    mock_asg.transcripteur_id = "user-123"

    mock_af = MagicMock()
    mock_af.project_id = 1
    mock_af.assignment = mock_asg
    mock_af.status = AudioFileStatus.ASSIGNED

    mock_minio_resp = MagicMock()
    mock_minio_resp.read.return_value = json.dumps(
        {"yjs_state_binary": "YmFzZTY0ZGF0YQ=="}
    ).encode("utf-8")

    nested_cm = AsyncMock()
    nested_cm.__aenter__ = AsyncMock(return_value=None)
    nested_cm.__aexit__ = AsyncMock(return_value=None)
    mock_db.begin_nested = MagicMock(return_value=nested_cm)
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.add = MagicMock()

    with patch("main._redis_client", mock_redis), patch("main.get_current_user", return_value=mock_user), patch(
        "main.internal_client"
    ) as mock_minio, patch("main.get_roles", return_value=["Transcripteur"]), patch(
        "main.log_audit_action", new_callable=AsyncMock
    ):

        mock_minio.get_object.return_value = mock_minio_resp
        mock_redis.set.return_value = True

        mock_db.execute = AsyncMock()
        mock_db.execute.side_effect = [
            MagicMock(scalar_one_or_none=lambda: mock_af),
            MagicMock(scalar_one_or_none=lambda: mock_snap),
            MagicMock(scalar_one_or_none=lambda: mock_af),
            MagicMock(),
            MagicMock(),
        ]

        body = DocumentRestoreRequest(snapshot_id="snap-123")

        response = await restore_document_from_snapshot(
            audio_id=1, body=body, payload=mock_user, db=mock_db
        )

        assert response["status"] == "ok"
        assert "restoration successful" in response["message"].lower()

        mock_redis.set.assert_called_once()
        assert "lock:document:1:restoring" in mock_redis.set.call_args[0][0]

        mock_minio.get_object.assert_called_with("snapshots", "snap-1.json")

        pub_calls = [c[0][1] for c in mock_redis.publish.call_args_list]
        assert any("document_locked" in p for p in pub_calls)
        assert json.dumps({"type": "reload", "document_id": 1}) in pub_calls
        assert any("document_unlocked" in p for p in pub_calls)

        mock_redis.delete.assert_called_with("lock:document:1:restoring")


@pytest.mark.asyncio
async def test_restore_snapshot_by_id_canonical_path():
    """POST /v1/snapshots/{snapshot_id}/restore — snapshot lookup then auth then shared core."""
    mock_redis = AsyncMock()
    mock_db = AsyncMock(spec=AsyncSession)
    mock_user = {"sub": "user-123", "name": "Test User"}

    yjs_bytes = base64.b64decode("YmFzZTY0ZGF0YQ==", validate=True)
    integrity_sha = hashlib.sha256(yjs_bytes).hexdigest()

    mock_snap = MagicMock()
    mock_snap.document_id = 1
    mock_snap.snapshot_id = "snap-123"
    mock_snap.json_object_key = "snapshots/snap-1.json"
    mock_snap.yjs_sha256 = integrity_sha

    mock_asg = MagicMock()
    mock_asg.transcripteur_id = "user-123"

    mock_af = MagicMock()
    mock_af.project_id = 1
    mock_af.assignment = mock_asg
    mock_af.status = AudioFileStatus.ASSIGNED

    mock_minio_resp = MagicMock()
    mock_minio_resp.read.return_value = json.dumps(
        {"yjs_state_binary": "YmFzZTY0ZGF0YQ=="}
    ).encode("utf-8")

    nested_cm = AsyncMock()
    nested_cm.__aenter__ = AsyncMock(return_value=None)
    nested_cm.__aexit__ = AsyncMock(return_value=None)
    mock_db.begin_nested = MagicMock(return_value=nested_cm)
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.add = MagicMock()

    with patch("main._redis_client", mock_redis), patch("main.internal_client") as mock_minio, patch(
        "main.get_roles", return_value=["Transcripteur"]
    ), patch("main.log_audit_action", new_callable=AsyncMock):
        mock_minio.get_object.return_value = mock_minio_resp
        mock_redis.set.return_value = True

        mock_db.execute = AsyncMock()
        mock_db.execute.side_effect = [
            MagicMock(scalar_one_or_none=lambda: mock_snap),
            MagicMock(scalar_one_or_none=lambda: mock_af),
            MagicMock(scalar_one_or_none=lambda: mock_snap),
            MagicMock(scalar_one_or_none=lambda: mock_af),
            MagicMock(),
            MagicMock(),
        ]

        response = await restore_snapshot_by_id(
            snapshot_id="snap-123",
            payload=mock_user,
            db=mock_db,
        )

        assert response["status"] == "ok"
        assert response["snapshot_id"] == "snap-123"

        mock_redis.set.assert_called_once()
        assert "lock:document:1:restoring" in mock_redis.set.call_args[0][0]

        mock_minio.get_object.assert_called_with("snapshots", "snap-1.json")

        pub_calls = [c[0][1] for c in mock_redis.publish.call_args_list]
        assert any("document_locked" in p for p in pub_calls)
        assert json.dumps({"type": "reload", "document_id": 1}) in pub_calls
        assert any("document_unlocked" in p for p in pub_calls)

        mock_redis.delete.assert_called_with("lock:document:1:restoring")


@pytest.mark.asyncio
async def test_restore_integrity_mismatch_returns_502():
    """SHA-256 of MinIO bytes must match SnapshotArtifact.yjs_sha256."""
    mock_redis = AsyncMock()
    mock_db = AsyncMock(spec=AsyncSession)
    mock_user = {"sub": "user-123", "name": "Test User"}

    yjs_bytes = base64.b64decode("YmFzZTY0ZGF0YQ==", validate=True)
    wrong_sha = "0" * 64

    mock_snap = MagicMock()
    mock_snap.json_object_key = "snapshots/snap-1.json"
    mock_snap.yjs_sha256 = wrong_sha

    mock_minio_resp = MagicMock()
    mock_minio_resp.read.return_value = json.dumps(
        {"yjs_state_binary": "YmFzZTY0ZGF0YQ=="}
    ).encode("utf-8")

    with patch("main._redis_client", mock_redis), patch("main.internal_client") as mock_minio, patch(
        "main.log_audit_action", new_callable=AsyncMock
    ):
        mock_minio.get_object.return_value = mock_minio_resp
        mock_redis.set.return_value = True

        mock_db.execute = AsyncMock()
        mock_db.execute.side_effect = [MagicMock(scalar_one_or_none=lambda: mock_snap)]

        with pytest.raises(HTTPException) as ei:
            await _restore_document_from_snapshot_core(
                audio_id=1,
                snapshot_id="snap-123",
                payload=mock_user,
                db=mock_db,
            )

        assert ei.value.status_code == 502
        detail = ei.value.detail
        err_text = detail.get("error", "") if isinstance(detail, dict) else str(detail)
        assert "integrity" in err_text.lower() or "hash" in err_text.lower()

        pub_calls = [c[0][1] for c in mock_redis.publish.call_args_list]
        fail_idx = next(i for i, p in enumerate(pub_calls) if "document_restore_failed" in p)
        unlock_idx = next(i for i, p in enumerate(pub_calls) if "document_unlocked" in p)
        assert fail_idx < unlock_idx
        fail_payload = json.loads(pub_calls[fail_idx])
        assert fail_payload["type"] == "document_restore_failed"
        assert fail_payload["schema_version"] == 1
        assert fail_payload["document_id"] == 1
        assert fail_payload["code"] == "INTEGRITY_MISMATCH"
        assert any("document_unlocked" in p for p in pub_calls)
        mock_redis.delete.assert_called_with("lock:document:1:restoring")


def test_document_restore_failed_signal_structured_http_detail():
    exc = HTTPException(
        status_code=502,
        detail={
            "error": "Snapshot Yjs payload does not match stored integrity hash",
            "code": DocumentRestoreFailureCode.INTEGRITY_MISMATCH,
        },
    )
    payload = _document_restore_failed_signal(42, exc, restore_id="test-id-123")
    assert payload["type"] == "document_restore_failed"
    assert payload["document_id"] == 42
    assert payload["code"] == "INTEGRITY_MISMATCH"
    assert payload["restore_id"] == "test-id-123"
    assert "integrity" in (payload.get("message") or "").lower()


def test_document_restore_failed_signal_list_detail_message():
    exc = HTTPException(status_code=404, detail=[{"msg": "gone", "type": "value_error"}])
    payload = _document_restore_failed_signal(3, exc)
    assert payload["code"] == DocumentRestoreFailureCode.SNAPSHOT_NOT_FOUND
    assert payload.get("message") == "gone"


def test_document_restore_failed_signal_scalar_detail():
    # Pass 2: Ensure scalar details are stringified correctly
    exc = HTTPException(status_code=404, detail=404)
    payload = _document_restore_failed_signal(1, exc)
    assert payload.get("message") == "404"


def test_document_restore_failed_signal_attributeerror_code():
    payload = _document_restore_failed_signal(9, AttributeError("'NoneType' has no attribute 'x'"))
    assert payload["code"] == DocumentRestoreFailureCode.SNAPSHOT_PAYLOAD_INVALID
    assert payload.get("message") == "Snapshot data could not be processed"


@pytest.mark.asyncio
async def test_editor_ticket_423_when_restore_lock_held():
    mock_redis = AsyncMock()
    mock_redis.exists = AsyncMock(return_value=1)
    mock_db = AsyncMock(spec=AsyncSession)

    with patch("main._redis_client", mock_redis), patch("main.get_current_user", return_value={"sub": "u1"}), patch(
        "main.get_roles", return_value=["Transcripteur"]
    ):
        with pytest.raises(HTTPException) as ei:
            await post_editor_ticket(
                EditorTicketRequest(document_id=99, permissions=["write"]),
                payload={"sub": "u1"},
                db=mock_db,
            )
        assert ei.value.status_code == 423
