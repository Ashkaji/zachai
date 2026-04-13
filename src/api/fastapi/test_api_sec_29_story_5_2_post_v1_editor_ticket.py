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

# ─── Story 5.2: POST /v1/editor/ticket ─────────────────────────────────────────

EDITOR_TICKET_BODY = {"document_id": 1, "permissions": ["read", "write"]}


def test_get_roles_merges_realm_and_resource_access():
    payload = {
        "realm_access": {"roles": ["Admin"]},
        "resource_access": {"zachai-frontend": {"roles": ["Transcripteur"]}},
    }
    assert set(main.get_roles(payload)) == {"Admin", "Transcripteur"}


def test_get_roles_dedupes_across_sources():
    payload = {
        "realm_access": {"roles": ["Transcripteur"]},
        "resource_access": {"account": {"roles": ["Transcripteur", "manage-account"]}},
    }
    r = main.get_roles(payload)
    assert r.count("Transcripteur") == 1
    assert "manage-account" in r


@pytest.fixture
def fake_redis():
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with patch.object(main, "_redis_client", r):
        yield r


def _editor_minimal_project(project_id=1, status_val="active"):
    p = MagicMock()
    p.id = project_id
    p.status = {
        "draft": main.ProjectStatus.DRAFT,
        "active": main.ProjectStatus.ACTIVE,
        "completed": main.ProjectStatus.COMPLETED,
    }[status_val]
    return p


@pytest.mark.asyncio
async def test_editor_ticket_transcripteur_happy(mock_db, fake_redis):
    """Mint ticket; payload in Redis; single-use consume (async client = same loop as fakeredis)."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="user-999")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    mock_db.execute = AsyncMock(return_value=af_r)

    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
            response = await ac.post(
                "/v1/editor/ticket",
                headers={"Authorization": "Bearer dummy.token.here"},
                json=EDITOR_TICKET_BODY,
            )

    assert response.status_code == 200
    data = response.json()
    assert data["ttl"] == editor_ticket_mod.WSS_TICKET_TTL_SEC
    tid = data["ticket_id"]
    assert len(tid) == 36

    out = await editor_ticket_mod.consume_wss_ticket(fake_redis, tid)
    assert out == {
        "sub": "user-999",
        "document_id": 1,
        "permissions": ["read", "write"],
    }
    assert await editor_ticket_mod.consume_wss_ticket(fake_redis, tid) is None


def test_editor_ticket_expert_active_project(mock_db, fake_redis):
    """Expert: no assignment check; project must be active."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="other", status_val="uploaded")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    mock_proj = _editor_minimal_project(status_val="active")
    proj_r = MagicMock()
    proj_r.scalar_one_or_none.return_value = mock_proj
    mock_db.execute = AsyncMock(side_effect=[af_r, proj_r])

    with patch.object(main, "decode_token", return_value=EXPERT_PAYLOAD):
        response = client.post(
            "/v1/editor/ticket",
            headers={"Authorization": "Bearer dummy.token.here"},
            json=EDITOR_TICKET_BODY,
        )

    assert response.status_code == 200
    assert response.json()["ttl"] == editor_ticket_mod.WSS_TICKET_TTL_SEC


def test_editor_ticket_expert_inactive_project_403(mock_db, fake_redis):
    mock_audio = _make_mock_audio_with_assignment()
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    mock_proj = _editor_minimal_project(status_val="draft")
    proj_r = MagicMock()
    proj_r.scalar_one_or_none.return_value = mock_proj
    mock_db.execute = AsyncMock(side_effect=[af_r, proj_r])

    with patch.object(main, "decode_token", return_value=EXPERT_PAYLOAD):
        response = client.post(
            "/v1/editor/ticket",
            headers={"Authorization": "Bearer dummy.token.here"},
            json=EDITOR_TICKET_BODY,
        )

    assert response.status_code == 403
    assert "active" in response.json()["error"].lower()


def test_editor_ticket_admin_bypass(mock_db, fake_redis):
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="other-user", status_val="uploaded")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    mock_db.execute = AsyncMock(return_value=af_r)

    with patch.object(main, "decode_token", return_value=ADMIN_PAYLOAD):
        response = client.post(
            "/v1/editor/ticket",
            headers={"Authorization": "Bearer dummy.token.here"},
            json=EDITOR_TICKET_BODY,
        )

    assert response.status_code == 200


def test_editor_ticket_transcripteur_wrong_user_403(mock_db, fake_redis):
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="other-user")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    mock_db.execute = AsyncMock(return_value=af_r)

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.post(
            "/v1/editor/ticket",
            headers={"Authorization": "Bearer dummy.token.here"},
            json=EDITOR_TICKET_BODY,
        )

    assert response.status_code == 403


def test_editor_ticket_transcripteur_bad_status_409(mock_db, fake_redis):
    """Parity with POST /v1/golden-set/frontend-correction (409 when status not assigned/in_progress)."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="user-999", status_val="transcribed")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    mock_db.execute = AsyncMock(return_value=af_r)

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.post(
            "/v1/editor/ticket",
            headers={"Authorization": "Bearer dummy.token.here"},
            json=EDITOR_TICKET_BODY,
        )

    assert response.status_code == 409


def test_editor_ticket_no_token_401():
    """POST /v1/editor/ticket without Authorization returns 401 (Story 5.2 AC6)."""
    response = client.post("/v1/editor/ticket", json=EDITOR_TICKET_BODY)
    assert response.status_code == 401
    assert "error" in response.json()


def test_editor_ticket_sub_fallback_to_preferred_username_happy(mock_db, fake_redis):
    """If Keycloak token omits `sub` but provides `preferred_username`, we should still mint the ticket."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="user-999", status_val="assigned")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    mock_db.execute = AsyncMock(return_value=af_r)

    payload_without_sub = {
        # `sub` missing on purpose
        "preferred_username": "user-999",
        "realm_access": {"roles": ["Transcripteur"]},
        "exp": 9999999999,
    }

    with patch.object(main, "decode_token", return_value=payload_without_sub):
        response = client.post(
            "/v1/editor/ticket",
            headers={"Authorization": "Bearer dummy.token.here"},
            json=EDITOR_TICKET_BODY,
        )

    assert response.status_code == 200


def test_editor_ticket_invalid_token_401():
    """POST /v1/editor/ticket with garbled bearer returns 401 (Story 5.2 AC6)."""
    response = client.post(
        "/v1/editor/ticket",
        headers={"Authorization": "Bearer not.a.valid.token"},
        json=EDITOR_TICKET_BODY,
    )
    assert response.status_code == 401
    assert "error" in response.json()


def test_editor_ticket_manager_forbidden(mock_db, fake_redis):
    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        response = client.post(
            "/v1/editor/ticket",
            headers={"Authorization": "Bearer dummy.token.here"},
            json=EDITOR_TICKET_BODY,
        )

    assert response.status_code == 403


def test_editor_ticket_missing_audio_404(mock_db, fake_redis):
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=af_r)

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.post(
            "/v1/editor/ticket",
            headers={"Authorization": "Bearer dummy.token.here"},
            json=EDITOR_TICKET_BODY,
        )

    assert response.status_code == 404


def test_editor_ticket_redis_unavailable_503(mock_db):
    """No FakeRedis patch — module _redis_client stays None after failed startup ping."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="user-999")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    mock_db.execute = AsyncMock(return_value=af_r)

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.post(
            "/v1/editor/ticket",
            headers={"Authorization": "Bearer dummy.token.here"},
            json=EDITOR_TICKET_BODY,
        )

    assert response.status_code == 503
    assert "redis" in response.json()["error"].lower()


def test_editor_ticket_redis_store_error_503(mock_db, fake_redis):
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="user-999")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    mock_db.execute = AsyncMock(return_value=af_r)

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD), patch.object(
        main.editor_ticket, "store_ticket", new=AsyncMock(side_effect=RuntimeError("redis down"))
    ):
        response = client.post(
            "/v1/editor/ticket",
            headers={"Authorization": "Bearer dummy.token.here"},
            json=EDITOR_TICKET_BODY,
        )

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_editor_ticket_expired_or_removed_returns_none_on_consume(mock_db, fake_redis):
    """After mint, deleting the key mimics TTL expiry — GETDEL yields None."""
    mock_audio = _make_mock_audio_with_assignment(transcripteur_id="user-999")
    af_r = MagicMock()
    af_r.scalar_one_or_none.return_value = mock_audio
    mock_db.execute = AsyncMock(return_value=af_r)

    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
            response = await ac.post(
                "/v1/editor/ticket",
                headers={"Authorization": "Bearer dummy.token.here"},
                json=EDITOR_TICKET_BODY,
            )

    tid = response.json()["ticket_id"]
    await fake_redis.delete(editor_ticket_mod.ticket_key(tid))
    assert await editor_ticket_mod.consume_wss_ticket(fake_redis, tid) is None


def test_editor_ticket_invalid_permission_422(mock_db, fake_redis):
    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD):
        response = client.post(
            "/v1/editor/ticket",
            headers={"Authorization": "Bearer dummy.token.here"},
            json={"document_id": 1, "permissions": ["read", "admin"]},
        )

    assert response.status_code == 422


