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

# ─── Story 5.5 — POST /v1/proxy/grammar ───────────────────────────────────────


def test_grammar_proxy_manager_forbidden():
    with patch.object(main, "decode_token", return_value=MANAGER_PAYLOAD):
        r = client.post(
            "/v1/proxy/grammar",
            json={"text": "hello", "language": "en"},
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert r.status_code == 403


def test_grammar_proxy_subject_missing_401():
    no_sub = {k: v for k, v in ADMIN_PAYLOAD.items() if k != "sub"}
    with patch.object(main, "decode_token", return_value=no_sub):
        r = client.post(
            "/v1/proxy/grammar",
            json={"text": "hello", "language": "en"},
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert r.status_code == 401


def test_grammar_proxy_rejects_external_languagetool_url():
    with patch.object(main, "decode_token", return_value=ADMIN_PAYLOAD), patch.object(
        main, "_LANGUAGETOOL_BASE_URL", "https://external.example.com"
    ):
        r = client.post(
            "/v1/proxy/grammar",
            json={"text": "hello", "language": "en"},
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert r.status_code == 503
    assert "internal url" in str(r.json().get("error", "")).lower()


def test_grammar_proxy_rate_limit_429():
    redis_mock = MagicMock()
    redis_mock.incr = AsyncMock(side_effect=[121])
    redis_mock.expire = AsyncMock(return_value=True)

    with patch.object(main, "decode_token", return_value=ADMIN_PAYLOAD), patch.object(
        main, "_redis_client", redis_mock
    ), patch.object(main, "GRAMMAR_RATE_LIMIT_PER_MIN", 120):
        r = client.post(
            "/v1/proxy/grammar",
            json={"text": "hello", "language": "en"},
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert r.status_code == 429
    assert "too many grammar requests" in str(r.json().get("error", "")).lower()


def test_grammar_proxy_empty_text_422():
    with patch.object(main, "decode_token", return_value=ADMIN_PAYLOAD):
        r = client.post(
            "/v1/proxy/grammar",
            json={"text": "   ", "language": "en"},
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert r.status_code == 422


def test_grammar_proxy_invalid_language_422():
    with patch.object(main, "decode_token", return_value=ADMIN_PAYLOAD):
        r = client.post(
            "/v1/proxy/grammar",
            json={"text": "hi", "language": "!nope"},
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert r.status_code == 422


def test_grammar_proxy_text_too_long_422():
    with patch.object(main, "decode_token", return_value=ADMIN_PAYLOAD), patch.object(
        main, "GRAMMAR_MAX_TEXT_LEN", 5
    ):
        r = client.post(
            "/v1/proxy/grammar",
            json={"text": "123456", "language": "en"},
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert r.status_code == 422


def test_grammar_proxy_lt_success_normalizes_matches():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "matches": [
            {
                "offset": 0,
                "length": 3,
                "message": "msg",
                "shortMessage": "s",
                "replacements": [{"value": "the"}],
                "rule": {"id": "R1", "issueType": "misspelling"},
                "category": {"id": "CAT"},
            }
        ]
    }
    mock_inner = MagicMock()
    mock_inner.post = AsyncMock(return_value=mock_response)
    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD), patch(
        "main.httpx.AsyncClient"
    ) as mock_ac:
        mock_ac.return_value.__aenter__ = AsyncMock(return_value=mock_inner)
        mock_ac.return_value.__aexit__ = AsyncMock(return_value=False)
        r = client.post(
            "/v1/proxy/grammar",
            json={"text": "teh", "language": "en"},
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert r.status_code == 200
    data = r.json()
    assert data["degraded"] is False
    assert len(data["matches"]) == 1
    assert data["matches"][0]["issueType"] == "spelling"
    assert data["matches"][0]["replacements"] == ["the"]


def test_grammar_proxy_cache_hit_only_one_upstream_call():
    """Use an in-memory AsyncMock Redis — fakeredis can disagree with TestClient event loops."""
    cache_store: dict[str, str] = {}

    async def _redis_get(key: str):
        return cache_store.get(key)

    async def _redis_setex(key: str, _ttl: int, val: str):
        cache_store[key] = val

    redis_mock = MagicMock()
    redis_mock.get = AsyncMock(side_effect=_redis_get)
    redis_mock.setex = AsyncMock(side_effect=_redis_setex)
    redis_mock.set = AsyncMock(return_value=True)
    redis_mock.eval = AsyncMock(return_value=1)
    redis_mock.exists = AsyncMock(return_value=1)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"matches": []}
    mock_inner = MagicMock()
    mock_inner.post = AsyncMock(return_value=mock_response)
    with patch.object(main, "decode_token", return_value=ADMIN_PAYLOAD), patch.object(
        main, "_redis_client", redis_mock
    ), patch("main.httpx.AsyncClient") as mock_ac:
        mock_ac.return_value.__aenter__ = AsyncMock(return_value=mock_inner)
        mock_ac.return_value.__aexit__ = AsyncMock(return_value=False)
        body = {"text": "cache-hit-unique-string-abc", "language": "fr"}
        h = {"Authorization": "Bearer dummy.token.here"}
        assert client.post("/v1/proxy/grammar", json=body, headers=h).status_code == 200
        assert client.post("/v1/proxy/grammar", json=body, headers=h).status_code == 200
        assert mock_inner.post.call_count == 1


def test_grammar_proxy_invalid_cached_payload_recomputes():
    cache_key = main._grammar_cache_key("bad-cached-payload", "fr")
    cache_store: dict[str, str] = {cache_key: '{"matches":"not-a-list","degraded":"nope"}'}

    async def _redis_get(key: str):
        return cache_store.get(key)

    async def _redis_setex(key: str, _ttl: int, val: str):
        cache_store[key] = val

    async def _redis_delete(key: str):
        cache_store.pop(key, None)
        return 1

    redis_mock = MagicMock()
    redis_mock.get = AsyncMock(side_effect=_redis_get)
    redis_mock.setex = AsyncMock(side_effect=_redis_setex)
    redis_mock.delete = AsyncMock(side_effect=_redis_delete)
    redis_mock.set = AsyncMock(return_value=True)
    redis_mock.eval = AsyncMock(return_value=1)
    redis_mock.exists = AsyncMock(return_value=1)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"matches": []}
    mock_inner = MagicMock()
    mock_inner.post = AsyncMock(return_value=mock_response)

    with patch.object(main, "decode_token", return_value=ADMIN_PAYLOAD), patch.object(
        main, "_redis_client", redis_mock
    ), patch("main.httpx.AsyncClient") as mock_ac:
        mock_ac.return_value.__aenter__ = AsyncMock(return_value=mock_inner)
        mock_ac.return_value.__aexit__ = AsyncMock(return_value=False)
        r = client.post(
            "/v1/proxy/grammar",
            json={"text": "bad-cached-payload", "language": "fr"},
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert r.status_code == 200
    assert mock_inner.post.call_count == 1
    redis_mock.delete.assert_called()


def test_grammar_proxy_fetch_lock_nx_on_cache_miss():
    cache_store: dict[str, str] = {}

    async def _redis_get(key: str):
        return cache_store.get(key)

    async def _redis_setex(key: str, _ttl: int, val: str):
        cache_store[key] = val

    redis_mock = MagicMock()
    redis_mock.get = AsyncMock(side_effect=_redis_get)
    redis_mock.setex = AsyncMock(side_effect=_redis_setex)
    redis_mock.set = AsyncMock(return_value=True)
    redis_mock.eval = AsyncMock(return_value=1)
    redis_mock.exists = AsyncMock(return_value=1)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"matches": []}
    mock_inner = MagicMock()
    mock_inner.post = AsyncMock(return_value=mock_response)
    with patch.object(main, "decode_token", return_value=ADMIN_PAYLOAD), patch.object(
        main, "_redis_client", redis_mock
    ), patch("main.httpx.AsyncClient") as mock_ac:
        mock_ac.return_value.__aenter__ = AsyncMock(return_value=mock_inner)
        mock_ac.return_value.__aexit__ = AsyncMock(return_value=False)
        body = {"text": "lock-miss-unique-xyz", "language": "fr"}
        assert (
            client.post("/v1/proxy/grammar", json=body, headers={"Authorization": "Bearer dummy.token.here"}).status_code
            == 200
        )
    redis_mock.set.assert_called()
    assert redis_mock.set.call_args.kwargs.get("nx") is True


def test_grammar_proxy_lock_ttl_tracks_timeout_budget():
    cache_store: dict[str, str] = {}

    async def _redis_get(key: str):
        return cache_store.get(key)

    async def _redis_setex(key: str, _ttl: int, val: str):
        cache_store[key] = val

    redis_mock = MagicMock()
    redis_mock.get = AsyncMock(side_effect=_redis_get)
    redis_mock.setex = AsyncMock(side_effect=_redis_setex)
    redis_mock.set = AsyncMock(return_value=True)
    redis_mock.eval = AsyncMock(return_value=1)
    redis_mock.exists = AsyncMock(return_value=1)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"matches": []}
    mock_inner = MagicMock()
    mock_inner.post = AsyncMock(return_value=mock_response)
    with patch.object(main, "decode_token", return_value=ADMIN_PAYLOAD), patch.object(
        main, "_redis_client", redis_mock
    ), patch.object(main, "GRAMMAR_HTTP_TIMEOUT", 41.0), patch("main.httpx.AsyncClient") as mock_ac:
        mock_ac.return_value.__aenter__ = AsyncMock(return_value=mock_inner)
        mock_ac.return_value.__aexit__ = AsyncMock(return_value=False)
        body = {"text": "lock-ttl-timeout-budget", "language": "fr"}
        assert (
            client.post("/v1/proxy/grammar", json=body, headers={"Authorization": "Bearer dummy.token.here"}).status_code
            == 200
        )
    assert redis_mock.set.call_args.kwargs.get("ex") >= 50


def test_grammar_proxy_lock_release_uses_token_safe_eval():
    redis_mock = MagicMock()
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.set = AsyncMock(return_value=True)
    redis_mock.setex = AsyncMock(return_value=True)
    redis_mock.eval = AsyncMock(return_value=1)
    redis_mock.exists = AsyncMock(return_value=1)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"matches": []}
    mock_inner = MagicMock()
    mock_inner.post = AsyncMock(return_value=mock_response)
    with patch.object(main, "decode_token", return_value=ADMIN_PAYLOAD), patch.object(
        main, "_redis_client", redis_mock
    ), patch("main.httpx.AsyncClient") as mock_ac:
        mock_ac.return_value.__aenter__ = AsyncMock(return_value=mock_inner)
        mock_ac.return_value.__aexit__ = AsyncMock(return_value=False)
        r = client.post(
            "/v1/proxy/grammar",
            json={"text": "safe-release-token", "language": "fr"},
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert r.status_code == 200
    redis_mock.eval.assert_called_once()


def test_grammar_proxy_follower_waits_and_uses_coalesced_cache():
    cache_key = main._grammar_cache_key("coalesced-wait", "fr")
    cached_payload = '{"matches":[],"degraded":false}'
    calls = {"n": 0}

    async def _redis_get(key: str):
        if key != cache_key:
            return None
        calls["n"] += 1
        if calls["n"] < 3:
            return None
        return cached_payload

    redis_mock = MagicMock()
    redis_mock.get = AsyncMock(side_effect=_redis_get)
    redis_mock.set = AsyncMock(return_value=False)
    redis_mock.exists = AsyncMock(return_value=1)
    redis_mock.setex = AsyncMock(return_value=True)
    redis_mock.eval = AsyncMock(return_value=0)

    mock_inner = MagicMock()
    mock_inner.post = AsyncMock(return_value=MagicMock(status_code=200, json=MagicMock(return_value={"matches": []})))
    with patch.object(main, "decode_token", return_value=ADMIN_PAYLOAD), patch.object(
        main, "_redis_client", redis_mock
    ), patch("main.httpx.AsyncClient") as mock_ac:
        mock_ac.return_value.__aenter__ = AsyncMock(return_value=mock_inner)
        mock_ac.return_value.__aexit__ = AsyncMock(return_value=False)
        r = client.post(
            "/v1/proxy/grammar",
            json={"text": "coalesced-wait", "language": "fr"},
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert r.status_code == 200
    assert r.json()["matches"] == []
    mock_inner.post.assert_not_called()


def test_grammar_proxy_follower_returns_503_while_same_key_lock_active():
    redis_mock = MagicMock()
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.set = AsyncMock(return_value=False)
    redis_mock.exists = AsyncMock(return_value=1)
    redis_mock.setex = AsyncMock(return_value=True)
    redis_mock.eval = AsyncMock(return_value=0)

    mock_inner = MagicMock()
    mock_inner.post = AsyncMock(return_value=MagicMock(status_code=200, json=MagicMock(return_value={"matches": []})))
    with patch.object(main, "decode_token", return_value=ADMIN_PAYLOAD), patch.object(
        main, "_redis_client", redis_mock
    ), patch("main.httpx.AsyncClient") as mock_ac, patch.object(main, "GRAMMAR_HTTP_TIMEOUT", -4.0):
        mock_ac.return_value.__aenter__ = AsyncMock(return_value=mock_inner)
        mock_ac.return_value.__aexit__ = AsyncMock(return_value=False)
        r = client.post(
            "/v1/proxy/grammar",
            json={"text": "same-lock-still-active", "language": "fr"},
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert r.status_code == 503
    assert "retry shortly" in str(r.json().get("error", "")).lower()
    mock_inner.post.assert_not_called()


def test_grammar_proxy_follower_tries_reacquire_after_lock_drops():
    redis_mock = MagicMock()
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.set = AsyncMock(side_effect=[False, True])
    redis_mock.exists = AsyncMock(return_value=0)
    redis_mock.setex = AsyncMock(return_value=True)
    redis_mock.eval = AsyncMock(return_value=1)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"matches": []}
    mock_inner = MagicMock()
    mock_inner.post = AsyncMock(return_value=mock_response)

    with patch.object(main, "decode_token", return_value=ADMIN_PAYLOAD), patch.object(
        main, "_redis_client", redis_mock
    ), patch("main.httpx.AsyncClient") as mock_ac, patch.object(main, "GRAMMAR_HTTP_TIMEOUT", -4.0):
        mock_ac.return_value.__aenter__ = AsyncMock(return_value=mock_inner)
        mock_ac.return_value.__aexit__ = AsyncMock(return_value=False)
        r = client.post(
            "/v1/proxy/grammar",
            json={"text": "reacquire-after-drop", "language": "fr"},
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert r.status_code == 200
    assert redis_mock.set.call_count >= 2
    mock_inner.post.assert_called_once()


def test_grammar_proxy_drops_malformed_offsets():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "matches": [
            {
                "offset": 50,
                "length": 3,
                "message": "bad",
                "rule": {"id": "X"},
                "category": {"id": "C"},
            }
        ]
    }
    mock_inner = MagicMock()
    mock_inner.post = AsyncMock(return_value=mock_response)
    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD), patch(
        "main.httpx.AsyncClient"
    ) as mock_ac:
        mock_ac.return_value.__aenter__ = AsyncMock(return_value=mock_inner)
        mock_ac.return_value.__aexit__ = AsyncMock(return_value=False)
        r = client.post(
            "/v1/proxy/grammar",
            json={"text": "hi", "language": "en"},
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert r.status_code == 200
    assert r.json()["matches"] == []


def test_grammar_proxy_clamps_match_past_text_end():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "matches": [
            {
                "offset": 0,
                "length": 999,
                "message": "m",
                "shortMessage": "",
                "replacements": [],
                "rule": {"id": "R1", "issueType": "typographical"},
                "category": {"id": "CAT"},
            }
        ]
    }
    mock_inner = MagicMock()
    mock_inner.post = AsyncMock(return_value=mock_response)
    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD), patch(
        "main.httpx.AsyncClient"
    ) as mock_ac:
        mock_ac.return_value.__aenter__ = AsyncMock(return_value=mock_inner)
        mock_ac.return_value.__aexit__ = AsyncMock(return_value=False)
        r = client.post(
            "/v1/proxy/grammar",
            json={"text": "ab", "language": "en"},
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert r.status_code == 200
    m = r.json()["matches"]
    assert len(m) == 1
    assert m[0]["offset"] == 0
    assert m[0]["length"] == 2


def test_grammar_proxy_category_prefers_rule_category():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "matches": [
            {
                "offset": 0,
                "length": 2,
                "message": "m",
                "replacements": [],
                "rule": {"id": "R1", "category": {"id": "FROM_RULE"}},
                "category": {"id": "FROM_TOP"},
            }
        ]
    }
    mock_inner = MagicMock()
    mock_inner.post = AsyncMock(return_value=mock_response)
    with patch.object(main, "decode_token", return_value=TRANSCRIPTEUR_PAYLOAD), patch(
        "main.httpx.AsyncClient"
    ) as mock_ac:
        mock_ac.return_value.__aenter__ = AsyncMock(return_value=mock_inner)
        mock_ac.return_value.__aexit__ = AsyncMock(return_value=False)
        r = client.post(
            "/v1/proxy/grammar",
            json={"text": "ab", "language": "en"},
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert r.status_code == 200
    assert r.json()["matches"][0]["category"] == "FROM_RULE"


def test_grammar_proxy_upstream_connect_503():
    mock_inner = MagicMock()
    mock_inner.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
    with patch.object(main, "decode_token", return_value=ADMIN_PAYLOAD), patch(
        "main.httpx.AsyncClient"
    ) as mock_ac:
        mock_ac.return_value.__aenter__ = AsyncMock(return_value=mock_inner)
        mock_ac.return_value.__aexit__ = AsyncMock(return_value=False)
        r = client.post(
            "/v1/proxy/grammar",
            json={"text": "hello", "language": "en"},
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert r.status_code == 503


def test_grammar_proxy_429_degraded():
    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_inner = MagicMock()
    mock_inner.post = AsyncMock(return_value=mock_response)
    with patch.object(main, "decode_token", return_value=ADMIN_PAYLOAD), patch(
        "main.httpx.AsyncClient"
    ) as mock_ac:
        mock_ac.return_value.__aenter__ = AsyncMock(return_value=mock_inner)
        mock_ac.return_value.__aexit__ = AsyncMock(return_value=False)
        r = client.post(
            "/v1/proxy/grammar",
            json={"text": "a  b", "language": "en"},
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert r.status_code == 429
    data = r.json()
    assert data.get("degraded") is True
    assert isinstance(data.get("matches"), list)


def test_grammar_proxy_upstream_http_502():
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "err"
    mock_inner = MagicMock()
    mock_inner.post = AsyncMock(return_value=mock_response)
    with patch.object(main, "decode_token", return_value=ADMIN_PAYLOAD), patch(
        "main.httpx.AsyncClient"
    ) as mock_ac:
        mock_ac.return_value.__aenter__ = AsyncMock(return_value=mock_inner)
        mock_ac.return_value.__aexit__ = AsyncMock(return_value=False)
        r = client.post(
            "/v1/proxy/grammar",
            json={"text": "hello", "language": "en"},
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert r.status_code == 502


def test_grammar_proxy_upstream_json_non_object_502():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = ["not-an-object"]
    mock_inner = MagicMock()
    mock_inner.post = AsyncMock(return_value=mock_response)
    with patch.object(main, "decode_token", return_value=ADMIN_PAYLOAD), patch(
        "main.httpx.AsyncClient"
    ) as mock_ac:
        mock_ac.return_value.__aenter__ = AsyncMock(return_value=mock_inner)
        mock_ac.return_value.__aexit__ = AsyncMock(return_value=False)
        r = client.post(
            "/v1/proxy/grammar",
            json={"text": "hello", "language": "en"},
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert r.status_code == 502


def test_grammar_proxy_does_not_touch_db(mock_db):
    """Regression: grammar path must not open Golden Set / assignment DB flows."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"matches": []}
    mock_inner = MagicMock()
    mock_inner.post = AsyncMock(return_value=mock_response)
    with patch.object(main, "decode_token", return_value=ADMIN_PAYLOAD), patch(
        "main.httpx.AsyncClient"
    ) as mock_ac:
        mock_ac.return_value.__aenter__ = AsyncMock(return_value=mock_inner)
        mock_ac.return_value.__aexit__ = AsyncMock(return_value=False)
        r = client.post(
            "/v1/proxy/grammar",
            json={"text": "hello", "language": "en"},
            headers={"Authorization": "Bearer dummy.token.here"},
        )
    assert r.status_code == 200
    mock_db.execute.assert_not_called()

