import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json
import base64
from sqlalchemy.ext.asyncio import AsyncSession

# Import the function to test
from main import restore_document_from_snapshot, DocumentRestoreRequest, AudioFile, SnapshotArtifact, YjsLog

@pytest.mark.asyncio
async def test_restore_document_logic():
    # Mocking redis, db, user, and snap
    mock_redis = AsyncMock()
    mock_db = AsyncMock(spec=AsyncSession)
    mock_user = {"sub": "user-123"}

    # Mock snapshot artifact
    mock_snap = MagicMock()
    mock_snap.json_object_key = "snapshots/snap-1.json"

    # Mock assignment
    mock_asg = MagicMock()
    mock_asg.transcripteur_id = "user-123"

    # Mock audio file
    mock_af = MagicMock()
    mock_af.project_id = 1
    mock_af.assignment = mock_asg

    # Mock minio response
    mock_minio_resp = MagicMock()
    mock_minio_resp.read.return_value = json.dumps({
        "yjs_state_binary": "YmFzZTY0ZGF0YQ==" # "base64data"
    }).encode("utf-8")

    with patch("main._redis_client", mock_redis), \
         patch("main.get_current_user", return_value=mock_user), \
         patch("main.internal_client") as mock_minio, \
         patch("main.get_roles", return_value=["Transcripteur"]):
        
        mock_minio.get_object.return_value = mock_minio_resp
        mock_redis.set.return_value = True # Lock acquired
        
        # Mock DB results
        mock_db.execute = AsyncMock()
        mock_db.execute.side_effect = [
            MagicMock(scalar_one_or_none=lambda: mock_af), # audio file check
            MagicMock(scalar_one_or_none=lambda: mock_snap), # snapshot fetch
            MagicMock(), # SELECT FOR UPDATE
            MagicMock(), # DELETE YjsLog
        ]

        body = DocumentRestoreRequest(snapshot_id="snap-123")
        
        response = await restore_document_from_snapshot(
            audio_id=1,
            body=body,
            payload=mock_user,
            db=mock_db
        )

        assert response["status"] == "ok"
        assert "restoration successful" in response["message"].lower()
        
        # Verify Redis Lock
        mock_redis.set.assert_called_once()
        assert "lock:document:1:restoring" in mock_redis.set.call_args[0][0]
        
        # Verify MinIO fetch
        mock_minio.get_object.assert_called_with("snapshots", "snap-1.json")
        
        # Verify reload signal
        mock_redis.publish.assert_called_with("hocuspocus:signals", json.dumps({"type": "reload", "document_id": 1}))
        
        # Verify lock release
        mock_redis.delete.assert_called_with("lock:document:1:restoring")
