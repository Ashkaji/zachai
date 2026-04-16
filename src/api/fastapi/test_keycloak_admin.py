import os
import time
import pytest
import httpx
from unittest.mock import patch, AsyncMock
from jose import jwt

import keycloak_admin
from keycloak_admin import (
    get_admin_token,
    KeycloakAdminTokenError,
    _admin_token_cache,
)


def _access_token_jwt_with_realm_management_roles() -> str:
    """HS256 token; claims match Keycloak client_credentials shape for AC6 checks."""
    claims = {
        "exp": int(time.time()) + 3600,
        "resource_access": {
            "realm-management": {
                "roles": ["manage-users", "view-users", "query-groups"],
            }
        },
    }
    return jwt.encode(claims, "test-secret", algorithm="HS256")


@pytest.fixture(autouse=True)
def setup_env():
    with patch.dict(
        os.environ,
        {
            "KEYCLOAK_ISSUER": "http://keycloak:8080/realms/zachai",
            "KEYCLOAK_ADMIN_CLIENT_ID": "test-client",
            "KEYCLOAK_ADMIN_CLIENT_SECRET": "test-secret",
        },
    ):
        import keycloak_admin

        keycloak_admin._admin_token_cache = {}
        yield


@pytest.mark.asyncio
async def test_get_admin_token_first_fetch():
    access_token = _access_token_jwt_with_realm_management_roles()
    mock_response = {"access_token": access_token, "expires_in": 3600}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = httpx.Response(200, json=mock_response)

        token = await get_admin_token()

        assert token == access_token
        mock_post.assert_called_once()

        import keycloak_admin

        assert keycloak_admin._admin_token_cache["token"] == access_token
        assert keycloak_admin._admin_token_cache["expires_at"] > time.time()

        decoded = jwt.get_unverified_claims(token)
        roles = (
            decoded.get("resource_access", {})
            .get("realm-management", {})
            .get("roles", [])
        )
        assert "manage-users" in roles
        assert "view-users" in roles
        assert "query-groups" in roles


@pytest.mark.asyncio
async def test_get_admin_token_cache_hit():
    import keycloak_admin

    keycloak_admin._admin_token_cache = {
        "token": "cached-token",
        "expires_at": time.time() + 1000,
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        token = await get_admin_token()

        assert token == "cached-token"
        mock_post.assert_not_called()


@pytest.mark.asyncio
async def test_get_admin_token_refresh_on_expiry():
    import keycloak_admin

    keycloak_admin._admin_token_cache = {
        "token": "old-token",
        "expires_at": time.time() + 10,
    }

    access_token = _access_token_jwt_with_realm_management_roles()
    mock_response = {"access_token": access_token, "expires_in": 3600}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = httpx.Response(200, json=mock_response)

        token = await get_admin_token()

        assert token == access_token
        mock_post.assert_called_once()


@pytest.mark.asyncio
async def test_get_admin_token_error_handling():
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = httpx.Response(500, text="Internal Server Error")

        with pytest.raises(KeycloakAdminTokenError) as excinfo:
            await get_admin_token()

        assert "Keycloak token request failed" in str(excinfo.value)


class _MockAsyncClient403:
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def post(self, *a, **k):
        return httpx.Response(403, text='{"error":"HTTP 403 Forbidden"}')


class _MockAsyncClient401(_MockAsyncClient403):
    async def post(self, *a, **k):
        return httpx.Response(401, text="Unauthorized")


class _MockAsyncClient418(_MockAsyncClient403):
    async def post(self, *a, **k):
        return httpx.Response(418, text="teapot")


@pytest.mark.asyncio
async def test_create_keycloak_user_keycloak_403_actionable_502(setup_env):
    from fastapi import HTTPException

    with patch.object(keycloak_admin, "get_admin_token", new_callable=AsyncMock, return_value="tok"):
        with patch.object(keycloak_admin.httpx, "AsyncClient", _MockAsyncClient403):
            with pytest.raises(HTTPException) as exc_info:
                await keycloak_admin.create_keycloak_user(
                    {
                        "username": "u1",
                        "email": "u1@test.local",
                        "firstName": "A",
                        "lastName": "B",
                        "enabled": True,
                    }
                )
    assert exc_info.value.status_code == 502
    d = exc_info.value.detail
    assert isinstance(d, dict)
    assert d["keycloak_status"] == 403
    assert "manage-users" in d["error"]
    assert "zachai-admin-cli" in d["error"] or "test-client" in d["error"]


@pytest.mark.asyncio
async def test_create_keycloak_user_keycloak_401_actionable_502(setup_env):
    from fastapi import HTTPException

    with patch.object(keycloak_admin, "get_admin_token", new_callable=AsyncMock, return_value="tok"):
        with patch.object(keycloak_admin.httpx, "AsyncClient", _MockAsyncClient401):
            with pytest.raises(HTTPException) as exc_info:
                await keycloak_admin.create_keycloak_user(
                    {
                        "username": "u2",
                        "email": "u2@test.local",
                        "firstName": "A",
                        "lastName": "B",
                        "enabled": True,
                    }
                )
    assert exc_info.value.status_code == 502
    assert exc_info.value.detail["keycloak_status"] == 401
    assert "KEYCLOAK_ADMIN_CLIENT_SECRET" in exc_info.value.detail["error"]


@pytest.mark.asyncio
async def test_create_keycloak_user_keycloak_other_status_generic_502(setup_env):
    from fastapi import HTTPException

    with patch.object(keycloak_admin, "get_admin_token", new_callable=AsyncMock, return_value="tok"):
        with patch.object(keycloak_admin.httpx, "AsyncClient", _MockAsyncClient418):
            with pytest.raises(HTTPException) as exc_info:
                await keycloak_admin.create_keycloak_user(
                    {
                        "username": "u3",
                        "email": "u3@test.local",
                        "firstName": "A",
                        "lastName": "B",
                        "enabled": True,
                    }
                )
    assert exc_info.value.status_code == 502
    assert exc_info.value.detail["keycloak_status"] == 418
    assert "418" in exc_info.value.detail["error"]
