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

# ─── Story 11.5: Bible Engine ──────────────────────────────────────────────


def test_get_bible_verses_exact_success(mock_db):
    """GET /v1/bible/verses returns 200 for exact reference."""
    v = MagicMock()
    v.verse = 16
    v.text = "Car Dieu a tant aimé le monde..."
    
    res = MagicMock()
    res.scalars.return_value.all.return_value = [v]
    mock_db.execute = AsyncMock(return_value=res)

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.get(
            "/v1/bible/verses",
            headers={"Authorization": "Bearer dummy.token.here"},
            params={"ref": "Jean 3:16", "translation": "LSG"}
        )

    assert response.status_code == 200
    data = response.json()
    assert data["reference"] == "Jean 3:16"
    assert data["verses"][0]["verse"] == 16
    assert "aimé le monde" in data["verses"][0]["text"]


def test_get_bible_verses_kjv_john_3_16_golden_snippet(mock_db):
    """GET /v1/bible/verses KJV John 3:16 matches operator smoke golden (Story 15.3)."""
    v = MagicMock()
    v.verse = 16
    v.text = "For God so loved the world, that he gave his only begotten Son..."

    res = MagicMock()
    res.scalars.return_value.all.return_value = [v]
    mock_db.execute = AsyncMock(return_value=res)

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.get(
            "/v1/bible/verses",
            headers={"Authorization": "Bearer dummy.token.here"},
            params={"ref": "John 3:16", "translation": "KJV"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["translation"] == "KJV"
    assert "For God so loved the world" in data["verses"][0]["text"]


def test_get_bible_verses_range_success(mock_db):
    """GET /v1/bible/verses returns 200 for range reference."""
    v1 = MagicMock(); v1.verse = 1; v1.text = "Au commencement..."
    v2 = MagicMock(); v2.verse = 2; v2.text = "La terre était informe..."
    
    res = MagicMock()
    res.scalars.return_value.all.return_value = [v1, v2]
    mock_db.execute = AsyncMock(return_value=res)

    with patch.object(main, "decode_token", return_value=EXPERT_PAYLOAD):
        response = client.get(
            "/v1/bible/verses",
            headers={"Authorization": "Bearer dummy.token.here"},
            params={"ref": "Genèse 1:1-2"}
        )

    assert response.status_code == 200
    data = response.json()
    assert len(data["verses"]) == 2
    assert data["verses"][0]["verse"] == 1


def test_get_bible_verses_invalid_format():
    """GET /v1/bible/verses returns 400 for bad reference format."""
    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.get(
            "/v1/bible/verses",
            headers={"Authorization": "Bearer dummy.token.here"},
            params={"ref": "Not A Reference"}
        )
    assert response.status_code == 400
    assert "format" in response.json()["error"]


def test_get_bible_verses_not_found(mock_db):
    """GET /v1/bible/verses returns 404 when verse missing in DB."""
    res = MagicMock()
    res.scalars.return_value.all.return_value = []
    mock_db.execute = AsyncMock(return_value=res)

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.get(
            "/v1/bible/verses",
            headers={"Authorization": "Bearer dummy.token.here"},
            params={"ref": "Jean 99:99"}
        )
    assert response.status_code == 404


def test_post_bible_ingest_success(mock_db):
    """POST /v1/bible/ingest returns 201 for valid batch."""
    mock_db.execute = AsyncMock()
    mock_db.commit = AsyncMock()

    response = client.post(
        "/v1/bible/ingest",
        headers={"X-ZachAI-Golden-Set-Internal-Secret": "test-golden-set-internal-secret"},
        json={
            "verses": [
                {"translation": "LSG", "book": "Jean", "chapter": 3, "verse": 16, "text": "Test text"}
            ]
        }
    )

    assert response.status_code == 201
    assert response.json()["status"] == "ok"
    assert response.json()["count"] == 1


def test_post_bible_ingest_forbidden():
    """POST /v1/bible/ingest returns 403 for bad secret."""
    response = client.post(
        "/v1/bible/ingest",
        headers={"X-ZachAI-Golden-Set-Internal-Secret": "wrong-secret"},
        json={
            "verses": [
                {"translation": "LSG", "book": "Jean", "chapter": 3, "verse": 16, "text": "Test"}
            ]
        }
    )
    assert response.status_code == 403


def test_post_bible_ingest_unauthorized_missing_secret():
    """POST /v1/bible/ingest returns 401 when internal secret header is absent (Story 15.3 runbook)."""
    response = client.post(
        "/v1/bible/ingest",
        json={
            "verses": [
                {"translation": "LSG", "book": "Jean", "chapter": 3, "verse": 16, "text": "x"}
            ]
        },
    )
    assert response.status_code == 401


