import os
import time
import logging
import httpx
from typing import Optional
from jose import jwt

logger = logging.getLogger(__name__)

# Cache for the admin token
# Stores {"token": "...", "expires_at": <timestamp>}
_admin_token_cache: dict = {}

async def get_admin_token() -> str:
    """
    Retrieve a Keycloak Admin REST API token using client_credentials flow.
    Includes in-process TTL caching to avoid repeated token requests.
    """
    global _admin_token_cache

    now = time.time()
    
    # Check cache (refresh 30 seconds before expiration)
    if _admin_token_cache and _admin_token_cache.get("expires_at", 0) > (now + 30):
        return _admin_token_cache["token"]

    issuer = os.environ["KEYCLOAK_ISSUER"].rstrip("/")
    client_id = os.environ["KEYCLOAK_ADMIN_CLIENT_ID"]
    client_secret = os.environ["KEYCLOAK_ADMIN_CLIENT_SECRET"]
    
    token_url = f"{issuer}/protocol/openid-connect/token"
    
    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }
    
    logger.info("Requesting admin token from Keycloak: %s", token_url)
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(token_url, data=data, timeout=10.0)
            if resp.status_code != 200:
                logger.error("Failed to retrieve admin token: %s %s", resp.status_code, resp.text)
                raise Exception(f"Keycloak token request failed with status {resp.status_code}")
            
            payload = resp.json()
            token = payload.get("access_token")
            if not token:
                raise Exception("Keycloak response missing access_token")
            
            # Decode JWT to get expiration if not provided in response
            # though client_credentials usually returns expires_in
            expires_in = payload.get("expires_in")
            if expires_in:
                expires_at = now + int(expires_in)
            else:
                # Fallback: decode JWT (don't verify signature here as we just want 'exp')
                decoded = jwt.get_unverified_claims(token)
                expires_at = decoded.get("exp", now + 60)
            
            _admin_token_cache = {
                "token": token,
                "expires_at": expires_at
            }
            
            return token
            
        except httpx.RequestError as exc:
            logger.error("HTTP request error while fetching admin token: %s", exc)
            raise Exception(f"Failed to reach Keycloak for admin token: {exc}")
        except Exception as exc:
            logger.error("Unexpected error while fetching admin token: %s", exc)
            raise
