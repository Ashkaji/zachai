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


