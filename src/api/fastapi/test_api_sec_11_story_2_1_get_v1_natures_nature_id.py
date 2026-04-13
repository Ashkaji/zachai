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

# ─── Story 2.1: GET /v1/natures/{nature_id} ──────────────────────────────────


def test_get_nature_success(mock_db):
    """GET /v1/natures/{id} returns 200 with full nature including label_studio_schema."""
    mock_nature = make_mock_nature(
        labels=[
            make_mock_label(label_id=1, label_name="Orateur", label_color="#FF5733", is_speech=True),
        ]
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_nature
    mock_db.execute.return_value = mock_result

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.get(
            "/v1/natures/1",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 1
    assert "label_studio_schema" in data
    assert len(data["labels"]) == 1


def test_get_nature_not_found(mock_db):
    """GET /v1/natures/{id} returns 404 when nature does not exist."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.get(
            "/v1/natures/999",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 404
    assert response.json() == {"error": "Nature not found"}


def test_get_nature_expert_forbidden(mock_db):
    """GET /v1/natures/{id} returns 403 for Expert role."""
    with patch.object(main, "decode_token", return_value=EXPERT_PAYLOAD):
        response = client.get(
            "/v1/natures/1",
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert response.status_code == 403
    assert "error" in response.json()


