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


