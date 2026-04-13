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

# ─── Story 2.1: GET /v1/natures ──────────────────────────────────────────────


def test_list_natures_success(mock_db):
    """GET /v1/natures returns 200 with list including label_count."""
    mock_nature = make_mock_nature(labels=[make_mock_label()])

    mock_result = MagicMock()
    # Mock result.all() returning a list of (Nature, count) tuples
    mock_result.all.return_value = [(mock_nature, 1)]
    mock_db.execute.return_value = mock_result

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.get(
            "/v1/natures",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["id"] == 1
    assert data[0]["name"] == "Camp Biblique"
    assert data[0]["label_count"] == 1


def test_list_natures_empty(mock_db):
    """GET /v1/natures returns 200 with empty list when no natures exist."""
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_db.execute.return_value = mock_result

    with patch.object(main, "decode_token", return_value=ADMIN_PAYLOAD):
        response = client.get(
            "/v1/natures",
            headers={"Authorization": "Bearer dummy.token.here"},
        )

    assert response.status_code == 200
    assert response.json() == []


def test_list_natures_transcripteur_forbidden(mock_db):
    """GET /v1/natures returns 403 for Transcripteur role."""
    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.get(
            "/v1/natures",
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert response.status_code == 403
    assert "error" in response.json()


