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


