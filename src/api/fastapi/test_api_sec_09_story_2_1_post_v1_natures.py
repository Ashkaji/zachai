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


