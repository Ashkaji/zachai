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


