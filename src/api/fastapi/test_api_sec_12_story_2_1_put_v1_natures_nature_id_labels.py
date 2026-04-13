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

# ─── Story 2.1: PUT /v1/natures/{nature_id}/labels ───────────────────────────


def test_update_labels_success(mock_db):
    """PUT /v1/natures/{id}/labels returns 200 with updated nature."""
    mock_nature = make_mock_nature(labels=[])
    updated_nature = make_mock_nature(
        labels=[make_mock_label(label_id=10, label_name="Traducteur", label_color="#33FF57", is_speech=True)]
    )

    mock_result_find = MagicMock()
    mock_result_find.scalar_one_or_none.return_value = mock_nature

    mock_result_delete = MagicMock()

    mock_result_reload = MagicMock()
    mock_result_reload.scalar_one_or_none.return_value = updated_nature

    mock_db.execute.side_effect = [mock_result_find, mock_result_delete, mock_result_reload]

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.put(
            "/v1/natures/1/labels",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={
                "labels": [
                    {"name": "Traducteur", "color": "#33FF57", "is_speech": True, "is_required": False}
                ]
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert len(data["labels"]) == 1
    assert data["labels"][0]["name"] == "Traducteur"
    assert "label_studio_schema" in data


def test_update_labels_not_found(mock_db):
    """PUT /v1/natures/{id}/labels returns 404 when nature does not exist."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.put(
            "/v1/natures/999/labels",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"labels": []},
        )

    assert response.status_code == 404
    assert response.json() == {"error": "Nature not found"}


def test_update_labels_transcripteur_forbidden(mock_db):
    """PUT /v1/natures/{id}/labels returns 403 for Transcripteur role."""
    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.put(
            "/v1/natures/1/labels",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"labels": []},
        )
    assert response.status_code == 403
    assert "error" in response.json()


