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

# ─── Story 13.2: Bible verse Redis cache (opt-in) ──────────────────────────




def test_get_bible_verses_cache_hit_skips_second_db_call(mock_db):
    """Second identical GET hits Redis only; DB execute runs once (Story 13.2)."""
    v = MagicMock()
    v.verse = 16
    v.text = "Car Dieu a tant aimé le monde..."
    res = MagicMock()
    res.scalars.return_value.all.return_value = [v]
    mock_db.execute = AsyncMock(return_value=res)

    fake = _FakeRedisBible()
    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD), patch.object(
        main, "BIBLE_VERSE_CACHE_ENABLED", True
    ), patch.object(main, "BIBLE_VERSE_CACHE_TTL_SEC", 600), patch.object(main, "_redis_client", fake):
        r1 = client.get(
            "/v1/bible/verses",
            headers={"Authorization": "Bearer dummy.token.here"},
            params={"ref": "Jean 3:16", "translation": "LSG"},
        )
        r2 = client.get(
            "/v1/bible/verses",
            headers={"Authorization": "Bearer dummy.token.here"},
            params={"ref": "Jean 3:16", "translation": "LSG"},
        )

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r2.json()["reference"] == "Jean 3:16"
    assert mock_db.execute.await_count == 1
    assert fake.setex_calls == 1


def test_get_bible_verses_cache_disabled_no_redis_touch(mock_db):
    """With cache flag off, verse route does not call Redis (Story 13.2)."""
    v = MagicMock()
    v.verse = 16
    v.text = "x"
    res = MagicMock()
    res.scalars.return_value.all.return_value = [v]
    mock_db.execute = AsyncMock(return_value=res)

    redis_m = MagicMock()
    redis_m.get = AsyncMock()
    redis_m.setex = AsyncMock()

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD), patch.object(
        main, "BIBLE_VERSE_CACHE_ENABLED", False
    ), patch.object(main, "BIBLE_VERSE_CACHE_TTL_SEC", 600), patch.object(main, "_redis_client", redis_m):
        client.get(
            "/v1/bible/verses",
            headers={"Authorization": "Bearer dummy.token.here"},
            params={"ref": "Jean 3:16", "translation": "LSG"},
        )

    redis_m.get.assert_not_called()
    redis_m.setex.assert_not_called()


def test_get_bible_verses_cache_redis_get_raises_still_200(mock_db):
    """Redis read failure falls back to PostgreSQL (Story 13.2)."""
    v = MagicMock()
    v.verse = 16
    v.text = "x"
    res = MagicMock()
    res.scalars.return_value.all.return_value = [v]
    mock_db.execute = AsyncMock(return_value=res)

    redis_m = MagicMock()
    redis_m.get = AsyncMock(side_effect=RuntimeError("redis down"))
    redis_m.setex = AsyncMock()

    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD), patch.object(
        main, "BIBLE_VERSE_CACHE_ENABLED", True
    ), patch.object(main, "BIBLE_VERSE_CACHE_TTL_SEC", 600), patch.object(main, "_redis_client", redis_m):
        r = client.get(
            "/v1/bible/verses",
            headers={"Authorization": "Bearer dummy.token.here"},
            params={"ref": "Jean 3:16", "translation": "LSG"},
        )

    assert r.status_code == 200
    assert mock_db.execute.await_count == 1
    redis_m.setex.assert_called_once()


def test_get_bible_verses_404_not_cached_second_request_hits_db(mock_db):
    """404 is never stored; two identical requests both query the DB (Story 13.2)."""
    res = MagicMock()
    res.scalars.return_value.all.return_value = []
    mock_db.execute = AsyncMock(return_value=res)

    fake = _FakeRedisBible()
    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD), patch.object(
        main, "BIBLE_VERSE_CACHE_ENABLED", True
    ), patch.object(main, "BIBLE_VERSE_CACHE_TTL_SEC", 600), patch.object(main, "_redis_client", fake):
        client.get(
            "/v1/bible/verses",
            headers={"Authorization": "Bearer dummy.token.here"},
            params={"ref": "Jean 99:99"},
        )
        client.get(
            "/v1/bible/verses",
            headers={"Authorization": "Bearer dummy.token.here"},
            params={"ref": "Jean 99:99"},
        )

    assert mock_db.execute.await_count == 2
    assert fake.setex_calls == 0


def test_get_bible_verses_400_no_redis_cache_ops():
    """Bad ref returns 400 before any verse cache logic; parse fails first (Story 13.2)."""
    fake = _FakeRedisBible()
    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD), patch.object(
        main, "BIBLE_VERSE_CACHE_ENABLED", True
    ), patch.object(main, "BIBLE_VERSE_CACHE_TTL_SEC", 600), patch.object(main, "_redis_client", fake):
        client.get(
            "/v1/bible/verses",
            headers={"Authorization": "Bearer dummy.token.here"},
            params={"ref": "Not A Reference"},
        )
        client.get(
            "/v1/bible/verses",
            headers={"Authorization": "Bearer dummy.token.here"},
            params={"ref": "Not A Reference"},
        )

    assert fake.setex_calls == 0
    assert not fake._data


def test_post_bible_ingest_bumps_translation_generation(mock_db):
    """Successful ingest INCRs bible:verse:gen:{translation} once per translation (Story 13.2)."""
    mock_db.execute = AsyncMock()
    mock_db.commit = AsyncMock()

    fake = _FakeRedisBible()
    with patch.object(main, "BIBLE_VERSE_CACHE_ENABLED", True), patch.object(
        main, "BIBLE_VERSE_CACHE_TTL_SEC", 600
    ), patch.object(main, "_redis_client", fake):
        response = client.post(
            "/v1/bible/ingest",
            headers={"X-ZachAI-Golden-Set-Internal-Secret": "test-golden-set-internal-secret"},
            json={
                "verses": [
                    {"translation": "LSG", "book": "Jean", "chapter": 3, "verse": 16, "text": "A"},
                    {"translation": "LSG", "book": "Jean", "chapter": 3, "verse": 17, "text": "B"},
                    {"translation": "KJV", "book": "John", "chapter": 3, "verse": 16, "text": "C"},
                ]
            },
        )

    assert response.status_code == 201
    assert fake._data.get(f"{main.BIBLE_VERSE_GEN_PREFIX}LSG") == "1"
    assert fake._data.get(f"{main.BIBLE_VERSE_GEN_PREFIX}KJV") == "1"


def test_get_bible_verses_cache_miss_after_generation_bump(mock_db):
    """After gen INCR, lookup uses a new key — second GET hits DB again (Story 13.2)."""
    v = MagicMock()
    v.verse = 16
    v.text = "x"
    res = MagicMock()
    res.scalars.return_value.all.return_value = [v]
    mock_db.execute = AsyncMock(return_value=res)

    fake = _FakeRedisBible()
    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD), patch.object(
        main, "BIBLE_VERSE_CACHE_ENABLED", True
    ), patch.object(main, "BIBLE_VERSE_CACHE_TTL_SEC", 600), patch.object(main, "_redis_client", fake):
        client.get(
            "/v1/bible/verses",
            headers={"Authorization": "Bearer dummy.token.here"},
            params={"ref": "Jean 3:16", "translation": "LSG"},
        )
        # Simulate post-ingest generation bump (same effect as INCR)
        fake._data[f"{main.BIBLE_VERSE_GEN_PREFIX}LSG"] = "1"
        client.get(
            "/v1/bible/verses",
            headers={"Authorization": "Bearer dummy.token.here"},
            params={"ref": "Jean 3:16", "translation": "LSG"},
        )

    assert mock_db.execute.await_count == 2
