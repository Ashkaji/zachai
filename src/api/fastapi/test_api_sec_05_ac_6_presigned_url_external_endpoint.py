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


