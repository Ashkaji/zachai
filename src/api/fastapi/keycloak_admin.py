import os
import time
import logging
import asyncio
import httpx
from jose import jwt

logger = logging.getLogger(__name__)


class KeycloakAdminTokenError(Exception):
    """Failed to obtain an admin API access token from Keycloak (client_credentials)."""


# Cache for the admin token
# Stores {"token": "...", "expires_at": <timestamp>}
_admin_token_cache: dict = {}
_admin_token_lock = asyncio.Lock()


def _validate_config():
    """Validate mandatory Keycloak environment variables."""
    mandatory = ["KEYCLOAK_ISSUER", "KEYCLOAK_ADMIN_CLIENT_ID", "KEYCLOAK_ADMIN_CLIENT_SECRET"]
    missing = [var for var in mandatory if var not in os.environ]
    if missing:
        raise RuntimeError(f"Missing mandatory Keycloak environment variables: {', '.join(missing)}")
    
    issuer = os.environ["KEYCLOAK_ISSUER"]
    if not issuer.startswith("http"):
         raise RuntimeError(f"KEYCLOAK_ISSUER must start with http/https: {issuer}")
    if "/realms/" not in issuer:
         raise RuntimeError(f"KEYCLOAK_ISSUER must contain '/realms/{{realm}}': {issuer}")


# Validate on module import
_validate_config()


async def get_admin_token() -> str:
    """
    Retrieve a Keycloak Admin REST API token using client_credentials flow.
    Includes in-process TTL caching to avoid repeated token requests.
    Uses asyncio.Lock to prevent concurrent token requests on a cold cache.
    """
    global _admin_token_cache

    async with _admin_token_lock:
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


def _get_keycloak_admin_urls():
    """Centralized URL construction for Keycloak Admin API."""
    issuer = os.environ["KEYCLOAK_ISSUER"].rstrip("/")
    realm = issuer.split("/")[-1]
    admin_base = issuer.replace(f"/realms/{realm}", "/admin")
    return realm, f"{admin_base}/realms/{realm}"


async def create_keycloak_user(
    user_data: dict,
    role: str | None = None,
    role_names: list[str] | None = None,
) -> str:
    """
    Create a user in Keycloak and return their new ID (sub).
    If role or role_names are provided, they are assigned immediately after creation.
    Raises HTTPException 409 if user already exists, or 502 on Keycloak error.
    """
    from fastapi import HTTPException

    token = await get_admin_token()
    _, base_url = _get_keycloak_admin_urls()
    users_url = f"{base_url}/users"

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
            
            # Assign requested realm roles (single role kept for backward compatibility).
            requested_roles: list[str] = []
            if role_names:
                requested_roles.extend(role_names)
            if role:
                requested_roles.append(role)
            for role_name in sorted(set(requested_roles)):
                role_obj = await get_realm_role(role_name)
                if not role_obj:
                    raise HTTPException(
                        status_code=500,
                        detail={"error": f"Role {role_name} configuration mismatch"},
                    )
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
    """Helper to find user ID by exact username search."""
    from fastapi import HTTPException

    token = await get_admin_token()
    _, base_url = _get_keycloak_admin_urls()
    search_url = f"{base_url}/users"

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                search_url,
                params={"username": username, "exact": "true"},
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0,
            )
        except httpx.RequestError as exc:
            logger.error("Keycloak connection error: %s", exc)
            raise HTTPException(status_code=502, detail={"error": "Keycloak unreachable"})

        if resp.status_code == 200:
            users = resp.json()
            if len(users) == 1:
                return users[0]["id"]
            if len(users) > 1:
                logger.error("Keycloak returned multiple users for exact username '%s'", username)
                raise HTTPException(status_code=502, detail={"error": "Ambiguous user ID returned by Keycloak"})

    raise HTTPException(status_code=502, detail={"error": "Failed to retrieve user ID from Keycloak"})


async def get_realm_role(role_name: str) -> dict:
    """Fetch realm role details (including its ID)."""
    from fastapi import HTTPException

    token = await get_admin_token()
    _, base_url = _get_keycloak_admin_urls()
    role_url = f"{base_url}/roles/{role_name}"

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
            logger.error("Role '%s' not found in Keycloak", role_name)
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
    _, base_url = _get_keycloak_admin_urls()
    mapping_url = f"{base_url}/users/{user_id}/role-mappings/realm"

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

        if resp.status_code not in (200, 201, 204):
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
    _, base_url = _get_keycloak_admin_urls()
    user_url = f"{base_url}/users/{user_id}"

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


async def delete_keycloak_user(user_id: str):
    """Delete a user from Keycloak (used for cleanup)."""
    from fastapi import HTTPException

    token = await get_admin_token()
    _, base_url = _get_keycloak_admin_urls()
    user_url = f"{base_url}/users/{user_id}"

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.delete(
                user_url,
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0,
            )
        except httpx.RequestError as exc:
            logger.error("Keycloak connection error during delete: %s", exc)
            return  # Silent failure for cleanup

        if resp.status_code not in (204, 404):
            logger.error("Keycloak user deletion failed: %s %s", resp.status_code, resp.text)
