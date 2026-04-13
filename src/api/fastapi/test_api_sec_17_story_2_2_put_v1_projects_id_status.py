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


def test_update_status_completed_must_use_close_endpoint(mock_db):
    """PUT /status cannot set completed directly; must use close endpoint."""
    mock_project = make_mock_project(status_val="active")
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_project
    mock_db.execute.return_value = mock_result

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.put(
            "/v1/projects/1/status",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"status": "completed"},
        )

    assert response.status_code == 400
    assert "POST /v1/projects/{project_id}/close" in response.json()["error"]


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


