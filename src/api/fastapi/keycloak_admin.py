import os
import time
import logging
import httpx
from jose import jwt

logger = logging.getLogger(__name__)


class KeycloakAdminTokenError(Exception):
    """Failed to obtain an admin API access token from Keycloak (client_credentials)."""


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
        except httpx.RequestError as exc:
            logger.error("HTTP request error while fetching admin token: %s", exc)
            raise KeycloakAdminTokenError(
                f"Failed to reach Keycloak for admin token: {exc}"
            ) from exc

        if resp.status_code != 200:
            logger.error(
                "Failed to retrieve admin token: %s %s", resp.status_code, resp.text
            )
            raise KeycloakAdminTokenError(
                f"Keycloak token request failed with status {resp.status_code}"
            )

        try:
            body = resp.json()
        except ValueError as exc:
            raise KeycloakAdminTokenError(
                "Keycloak token response was not valid JSON"
            ) from exc

        token = body.get("access_token")
        if not token:
            raise KeycloakAdminTokenError("Keycloak response missing access_token")

        expires_in = body.get("expires_in")
        if expires_in is not None:
            expires_at = now + int(expires_in)
        else:
            decoded = jwt.get_unverified_claims(token)
            expires_at = decoded.get("exp", now + 60)

        _admin_token_cache = {
            "token": token,
            "expires_at": expires_at,
        }

        return token


async def create_keycloak_user(user_data: dict, role: str | None = None) -> str:
    """
    Create a user in Keycloak and return their new ID (sub).
    If role is provided, it is assigned immediately after creation.
    Raises HTTPException 409 if user already exists, or 502 on Keycloak error.
    """
    from fastapi import HTTPException

    token = await get_admin_token()
    issuer = os.environ["KEYCLOAK_ISSUER"].rstrip("/")
    realm = issuer.split("/")[-1]
    admin_base = issuer.replace(f"/realms/{realm}", "/admin")
    users_url = f"{admin_base}/realms/{realm}/users"

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                users_url,
                json=user_data,
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0,
            )
        except httpx.RequestError as exc:
            logger.error("Keycloak connection error: %s", exc)
            raise HTTPException(status_code=502, detail={"error": "Keycloak unreachable"})

        if resp.status_code == 201:
            # Created. User ID is in Location header: .../users/{id}
            location = resp.headers.get("Location")
            if not location:
                user_id = await get_user_id_by_username(user_data["username"])
            else:
                user_id = location.split("/")[-1]
            
            # Story 16.3 AC 3: Assign role if requested
            if role:
                role_obj = await get_realm_role(role)
                await add_realm_role_to_user(user_id, role_obj)
            
            return user_id

        if resp.status_code == 409:
            raise HTTPException(
                status_code=409, detail={"error": "User already exists in Keycloak"}
            )

        logger.error("Keycloak user creation failed: %s %s", resp.status_code, resp.text)
        raise HTTPException(
            status_code=502,
            detail={"error": f"Keycloak error during user creation: {resp.status_code}"},
        )


async def get_keycloak_role_id(role_name: str) -> str:
    """Helper to get internal ID for a realm role."""
    role = await get_realm_role(role_name)
    return role["id"]


async def get_user_id_by_username(username: str) -> str:
    """Helper to find user ID if Location header was missing."""
    from fastapi import HTTPException

    token = await get_admin_token()
    issuer = os.environ["KEYCLOAK_ISSUER"].rstrip("/")
    realm = issuer.split("/")[-1]
    admin_base = issuer.replace(f"/realms/{realm}", "/admin")
    search_url = f"{admin_base}/realms/{realm}/users"

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            search_url,
            params={"username": username, "exact": "true"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=10.0,
        )
        if resp.status_code == 200:
            users = resp.json()
            if users:
                return users[0]["id"]

    raise HTTPException(status_code=502, detail={"error": "Failed to retrieve user ID"})


async def get_realm_role(role_name: str) -> dict:
    """Fetch realm role details (including its ID)."""
    from fastapi import HTTPException

    token = await get_admin_token()
    issuer = os.environ["KEYCLOAK_ISSUER"].rstrip("/")
    realm = issuer.split("/")[-1]
    admin_base = issuer.replace(f"/realms/{realm}", "/admin")
    role_url = f"{admin_base}/realms/{realm}/roles/{role_name}"

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                role_url, headers={"Authorization": f"Bearer {token}"}, timeout=10.0
            )
        except httpx.RequestError as exc:
            logger.error("Keycloak connection error: %s", exc)
            raise HTTPException(status_code=502, detail={"error": "Keycloak unreachable"})

        if resp.status_code == 200:
            return resp.json()

        if resp.status_code == 404:
            raise HTTPException(
                status_code=500, detail={"error": f"Role {role_name} not found in Keycloak"}
            )

        logger.error("Keycloak role fetch failed: %s %s", resp.status_code, resp.text)
        raise HTTPException(
            status_code=502,
            detail={"error": f"Keycloak error during role fetch: {resp.status_code}"},
        )


async def add_realm_role_to_user(user_id: str, role: dict):
    """Assign a realm role to a user."""
    from fastapi import HTTPException

    token = await get_admin_token()
    issuer = os.environ["KEYCLOAK_ISSUER"].rstrip("/")
    realm = issuer.split("/")[-1]
    admin_base = issuer.replace(f"/realms/{realm}", "/admin")
    # POST /admin/realms/{realm}/users/{id}/role-mappings/realm
    mapping_url = f"{admin_base}/realms/{realm}/users/{user_id}/role-mappings/realm"

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                mapping_url,
                json=[role],  # Keycloak expects a list of role objects
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0,
            )
        except httpx.RequestError as exc:
            logger.error("Keycloak connection error: %s", exc)
            raise HTTPException(status_code=502, detail={"error": "Keycloak unreachable"})

        if resp.status_code not in (200, 204):
            logger.error(
                "Keycloak role mapping failed: %s %s", resp.status_code, resp.text
            )
            raise HTTPException(
                status_code=502,
                detail={
                    "error": f"Keycloak error during role mapping: {resp.status_code}"
                },
            )


async def update_keycloak_user(user_id: str, update_data: dict):
    """Update user attributes (e.g., enabled/disabled)."""
    from fastapi import HTTPException

    token = await get_admin_token()
    issuer = os.environ["KEYCLOAK_ISSUER"].rstrip("/")
    realm = issuer.split("/")[-1]
    admin_base = issuer.replace(f"/realms/{realm}", "/admin")
    user_url = f"{admin_base}/realms/{realm}/users/{user_id}"

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.put(
                user_url,
                json=update_data,
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0,
            )
        except httpx.RequestError as exc:
            logger.error("Keycloak connection error: %s", exc)
            raise HTTPException(status_code=502, detail={"error": "Keycloak unreachable"})

        if resp.status_code == 204:
            return

        if resp.status_code == 404:
            raise HTTPException(
                status_code=404, detail={"error": "User not found in Keycloak"}
            )

        logger.error("Keycloak user update failed: %s %s", resp.status_code, resp.text)
        raise HTTPException(
            status_code=502,
            detail={"error": f"Keycloak error during user update: {resp.status_code}"},
        )
