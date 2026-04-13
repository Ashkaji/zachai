import os
import time
import pytest
import httpx
from unittest.mock import patch, AsyncMock
from keycloak_admin import get_admin_token, _admin_token_cache

@pytest.fixture(autouse=True)
def setup_env():
    with patch.dict(os.environ, {
        "KEYCLOAK_ISSUER": "http://keycloak:8080/realms/zachai",
        "KEYCLOAK_ADMIN_CLIENT_ID": "test-client",
        "KEYCLOAK_ADMIN_CLIENT_SECRET": "test-secret"
    }):
        # Clear cache before each test
        global _admin_token_cache
        import keycloak_admin
        keycloak_admin._admin_token_cache = {}
        yield

@pytest.mark.asyncio
async def test_get_admin_token_first_fetch():
    mock_response = {
        "access_token": "mock-token-123",
        "expires_in": 3600
    }
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = httpx.Response(200, json=mock_response)
        
        token = await get_admin_token()
        
        assert token == "mock-token-123"
        mock_post.assert_called_once()
        
        # Check cache was populated
        import keycloak_admin
        assert keycloak_admin._admin_token_cache["token"] == "mock-token-123"
        assert keycloak_admin._admin_token_cache["expires_at"] > time.time()

@pytest.mark.asyncio
async def test_get_admin_token_cache_hit():
    import keycloak_admin
    keycloak_admin._admin_token_cache = {
        "token": "cached-token",
        "expires_at": time.time() + 1000
    }
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        token = await get_admin_token()
        
        assert token == "cached-token"
        mock_post.assert_not_called()

@pytest.mark.asyncio
async def test_get_admin_token_refresh_on_expiry():
    import keycloak_admin
    # Set cache to expire very soon
    keycloak_admin._admin_token_cache = {
        "token": "old-token",
        "expires_at": time.time() + 10  # Less than 30s buffer
    }
    
    mock_response = {
        "access_token": "new-token",
        "expires_in": 3600
    }
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = httpx.Response(200, json=mock_response)
        
        token = await get_admin_token()
        
        assert token == "new-token"
        mock_post.assert_called_once()

@pytest.mark.asyncio
async def test_get_admin_token_error_handling():
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = httpx.Response(500, text="Internal Server Error")
        
        with pytest.raises(Exception) as excinfo:
            await get_admin_token()
        
        assert "Keycloak token request failed" in str(excinfo.value)
