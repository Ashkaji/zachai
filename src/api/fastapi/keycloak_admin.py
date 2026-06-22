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


async def get_admin_token() -> str:
    """
    Retrieve a Keycloak Admin REST API token using client_credentials flow.
    Includes in-process TTL caching to avoid repeated token requests.
    Uses asyncio.Lock to prevent concurrent token requests on a cold cache.
    """
    global _admin_token_cache

    async with _admin_token_lock:
        _validate_config()  # Fast env-var guard; raises RuntimeError at first use, inside the lock so concurrent callers don't pile on
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


def _keycloak_user_create_http_exception(status_code: int, body: str):
    """
    Map Keycloak Admin API failures on POST /users to a 502 with an actionable French message.
    FastAPI remains the single entrypoint;502 = erreur amont (Keycloak).
    """
    from fastapi import HTTPException

    client_id = os.environ.get("KEYCLOAK_ADMIN_CLIENT_ID", "zachai-admin-cli")

    if status_code == 401:
        return HTTPException(
            status_code=502,
            detail={
                "error": (
                    "Keycloak a rejeté le jeton utilisé pour l’API d’administration (HTTP 401). "
                    f"Vérifiez KEYCLOAK_ADMIN_CLIENT_ID / KEYCLOAK_ADMIN_CLIENT_SECRET pour le client "
                    f"« {client_id} » (secret identique à celui du realm, issu de l’import realm)."
                ),
                "keycloak_status": 401,
            },
        )

    if status_code == 403:
        return HTTPException(
            status_code=502,
            detail={
                "error": (
                    "Keycloak refuse la création d’utilisateur via l’API admin (HTTP 403) : le compte de service "
                    f"du client confidentiel « {client_id} » n’a probablement pas les bons droits. "
                    "Dans Keycloak (realm cible) : Clients → ce client → Onglet « Service accounts roles » → "
                    "« realm-management » : assigner au minimum « manage-users », « view-users » et « query-users » (voir "
                    "import `zachai-realm.json`). Vérifiez aussi que KEYCLOAK_ISSUER pointe vers le bon realm."
                ),
                "keycloak_status": 403,
            },
        )

    return HTTPException(
        status_code=502,
        detail={
            "error": (
                f"Échec Keycloak lors de la création d’utilisateur (HTTP {status_code}). "
                "Consultez les logs du conteneur `fastapi` et `keycloak` pour le corps de réponse détaillé."
            ),
            "keycloak_status": status_code,
        },
    )


async def get_user_id_by_email(email: str) -> str | None:
    """Helper to find user ID by exact email search."""
    from fastapi import HTTPException

    token = await get_admin_token()
    _, base_url = _get_keycloak_admin_urls()
    search_url = f"{base_url}/users"

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                search_url,
                params={"email": email, "exact": "true"},
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0,
            )
        except httpx.RequestError as exc:
            logger.error("Keycloak connection error: %s", exc)
            raise HTTPException(status_code=502, detail={"error": "Keycloak unreachable"})

        if resp.status_code == 200:
            try:
                users = resp.json()
            except ValueError as exc:
                logger.error("Keycloak email search response not valid JSON: %s", exc)
                raise HTTPException(status_code=502, detail={"error": "Keycloak returned invalid JSON for email search"})
            if len(users) == 1:
                uid = users[0].get("id")
                if not uid:
                    raise HTTPException(status_code=502, detail={"error": "Keycloak user object missing id field"})
                return uid
            if len(users) > 1:
                logger.error("Keycloak returned multiple users for exact email '%s'", email)
                raise HTTPException(status_code=502, detail={"error": "Ambiguous user ID returned by Keycloak for email"})
            return None  # 0 results = not found, not a Keycloak fault
        logger.error("Keycloak email search failed: %s %s", resp.status_code, resp.text)
        raise HTTPException(status_code=502, detail={"error": f"Keycloak email search failed: {resp.status_code}"})


async def create_keycloak_user(
    user_data: dict,
    role: str | None = None,
    role_names: list[str] | None = None,
) -> str:
    """
    Create a user in Keycloak and return their new ID (sub).
    If role or role_names are provided, they are assigned immediately after creation.
    Raises HTTPException 409 with PRECISE message if user/email already exists.
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
            
            # Assign requested realm roles
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

        # If 409 (Conflict) or 400 (Bad Request usually due to duplicate), 
        # we perform targeted checks to give a precise message.
        if resp.status_code in (400, 409):
            username = user_data.get("username")
            email = user_data.get("email")

            if username:
                try:
                    if await get_user_id_by_username(username):
                        raise HTTPException(
                            status_code=409,
                            detail={"error": f"Le nom d’utilisateur « {username} » est déjà utilisé."}
                        )
                except HTTPException as e:
                    if e.status_code == 409: raise e
                    logger.warning("Keycloak username lookup returned %s during conflict diagnosis; falling back to generic 409", e.status_code)
                except KeycloakAdminTokenError as e:
                    logger.error("Keycloak admin token error during conflict diagnosis; falling back to generic 409: %s", e)
                except Exception: pass

            if email:
                try:
                    if await get_user_id_by_email(email):
                        raise HTTPException(
                            status_code=409,
                            detail={"error": f"L’adresse e-mail « {email} » est déjà utilisée."}
                        )
                except HTTPException as e:
                    if e.status_code == 409: raise e
                    logger.warning("Keycloak email lookup returned %s during conflict diagnosis; falling back to generic 409", e.status_code)
                except KeycloakAdminTokenError as e:
                    logger.error("Keycloak admin token error during conflict diagnosis; falling back to generic 409: %s", e)
                except Exception: pass

            # Fallback for generic 409
            raise HTTPException(
                status_code=409,
                detail={"error": "Un utilisateur avec ce nom ou cet e-mail existe déjà."}
            )

        if resp.status_code in (401, 403):
            logger.error(
                "Keycloak user creation forbidden/unauthorized: %s %s",
                resp.status_code,
                resp.text,
            )
            raise _keycloak_user_create_http_exception(resp.status_code, resp.text)

        logger.error("Keycloak user creation failed: %s %s", resp.status_code, resp.text)
        raise _keycloak_user_create_http_exception(resp.status_code, resp.text)


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
            try:
                users = resp.json()
            except ValueError as exc:
                logger.error("Keycloak username search response not valid JSON: %s", exc)
                raise HTTPException(status_code=502, detail={"error": "Keycloak returned invalid JSON for username search"})
            if len(users) == 1:
                uid = users[0].get("id")
                if not uid:
                    raise HTTPException(status_code=502, detail={"error": "Keycloak user object missing id field"})
                return uid
            if len(users) > 1:
                logger.error("Keycloak returned multiple users for exact username '%s'", username)
                raise HTTPException(status_code=502, detail={"error": "Ambiguous user ID returned by Keycloak"})
            return None  # 0 results = user not found, not a Keycloak fault
        logger.error("Keycloak username search failed: %s %s", resp.status_code, resp.text)
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


async def list_keycloak_users() -> list[dict]:
    """Fetch all users from Keycloak."""
    from fastapi import HTTPException

    token = await get_admin_token()
    _, base_url = _get_keycloak_admin_urls()
    users_url = f"{base_url}/users"

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                users_url,
                params={"max": 1000},
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0,
            )
        except httpx.RequestError as exc:
            logger.error("Keycloak connection error: %s", exc)
            raise HTTPException(status_code=502, detail={"error": "Keycloak unreachable"})

        if resp.status_code == 200:
            try:
                return resp.json()
            except ValueError as exc:
                logger.error("Keycloak users response not valid JSON: %s", exc)
                raise HTTPException(status_code=502, detail={"error": "Keycloak returned invalid JSON for user list"})

    logger.error("Keycloak user list failed: %s %s", resp.status_code, resp.text)
    raise HTTPException(status_code=502, detail={"error": "Failed to list users from Keycloak"})


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
