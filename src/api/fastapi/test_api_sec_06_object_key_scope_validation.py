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


