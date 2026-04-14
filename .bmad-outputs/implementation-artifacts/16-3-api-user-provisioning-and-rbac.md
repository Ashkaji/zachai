# Story 16.3: API provisioning utilisateurs & RBAC

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

**En:** As the System, I expose authenticated FastAPI endpoints to create/disable users and assign realm roles according to hierarchy rules (Admin vs Manager), returning clear errors for forbidden operations.

**Fr:** En tant que Système, j'expose des points de terminaison FastAPI authentifiés pour créer/désactiver des utilisateurs et attribuer des rôles de royaume selon les règles de hiérarchie (Admin vs Manager), en renvoyant des erreurs claires pour les opérations interdites.

## Acceptance Criteria / Critères d'Acceptation

1.  **Create User Endpoint (`POST /v1/iam/users`)**:
    *   **Auth**: Admin or Manager role required. Transcripteur/Expert denied (403).
    *   **Admin Scope**: Can create any user with any role (`Admin`, `Manager`, `Transcripteur`, `Expert`).
    *   **Manager Scope**: Can only create users with roles `Transcripteur` or `Expert`. Any attempt to create an `Admin` or `Manager` returns **403 Forbidden**.
    *   **Manager Persistence**: If a Manager creates a user, a `ManagerMembership` row (from Story 16.2) must be automatically created in PostgreSQL to map the new user to this manager.
    *   **Keycloak Integration**: Calls the Keycloak Admin API `POST /admin/realms/{realm}/users` using the service account token from Story 16.1.
    *   **Body**: `username`, `email`, `firstName`, `lastName`, `enabled` (default true), `role` (one of the four roles).
    *   **Conflict**: If the user (username or email) already exists in Keycloak, return **409 Conflict**.
2.  **Disable/Enable User Endpoint (`PATCH /v1/iam/users/{user_id}`)**:
    *   **Auth**: Admin or Manager role required. Transcripteur/Expert denied (**403**).
    *   **`user_id` semantics**: Path parameter is the Keycloak user identifier used by the Admin REST API (UUID string). In this realm it matches JWT `sub` and `ManagerMembership.member_id` (Story 16.2). Scope checks compare `user_id` to `member_id` rows for the calling Manager’s `payload["sub"]`.
    *   **Scope Enforcement**:
        *   Admin can update any user.
        *   Manager can only update users that belong to their scope in `ManagerMembership`. Any attempt to update an out-of-scope user (including other Managers or Admins) returns **403 Forbidden**.
    *   **Action**: Updates the `enabled` field in Keycloak.
    *   **Not found**: If Keycloak has no user for `user_id`, return **404 Not Found** (for both Admin and Manager once the caller is authorized to hit the route).
3.  **Role Mapping**:
    *   The API must map ZachAI roles (`Admin`, `Manager`, `Transcripteur`, `Expert`) to their corresponding Keycloak realm roles.
    *   Roles are assigned during creation or via a separate `POST /v1/iam/users/{user_id}/roles` (optional if handled in create, but must be robust). **Decision:** Handle initial role assignment in `POST /v1/iam/users` for efficiency.
4.  **Error Handling**:
    *   **400 Bad Request**: Invalid email format or missing fields.
    *   **403 Forbidden**: Role hierarchy violation or out-of-scope management.
    *   **409 Conflict**: User already exists.
    *   **502 Bad Gateway**: Keycloak Admin API is unreachable or returns 5xx.
5.  **Testing**:
    *   `src/api/fastapi/test_story_16_3.py` verifies:
        *   Admin creating a Manager.
        *   Manager creating a Transcripteur (check Keycloak mock + PostgreSQL mapping).
        *   Manager forbidden from creating an Admin (403).
        *   Manager forbidden from disabling a user not in their scope (403).
        *   Keycloak 409 conflict mapping to ZachAI 409.
        *   PATCH with unknown `user_id` → **404** (mock Keycloak empty/not found).

## Tasks / Subtasks

- [x] **Implement Keycloak Admin REST Client** (AC: 1, 4)
  - [x] Add `create_keycloak_user(user_data, role)` to `src/api/fastapi/keycloak_admin.py`.
  - [x] Add `update_keycloak_user(user_id, update_data)` to `src/api/fastapi/keycloak_admin.py`.
  - [x] Add `get_keycloak_role_id(role_name)` helper (Keycloak roles need their internal ID for some operations, or use the name-based endpoint if available).
- [x] **Define Pydantic Models** (AC: 1, 2)
  - [x] `UserCreate`: `username`, `email`, `firstName` / `lastName` (use `Field(alias=...)` or equivalent so request JSON matches AC camelCase), `enabled` optional default true, `role`.
  - [x] `UserUpdate`: `enabled`.
- [x] **Implement Provisioning Endpoints** (AC: 1, 2)
  - [x] `POST /v1/iam/users`: Implement RBAC hierarchy + `ManagerMembership` persistence.
  - [x] `PATCH /v1/iam/users/{user_id}`: Implement scope enforcement via `ManagerMembership`.
- [x] **Verification & Tests** (AC: 5)
  - [x] Create `src/api/fastapi/test_story_16_3.py`.
  - [x] Mock `httpx.AsyncClient` for Keycloak Admin API (user CRUD + role-mappings), consistent with `test_keycloak_admin.py` / `test_story_16_2.py` (env vars before `import main` where needed).
  - [x] Use `client` + `patch("main.decode_token", ...)` with `ADMIN_PAYLOAD`, `MANAGER_PAYLOAD`, etc. from `fastapi_test_app.py`.
  - [x] Assert `ManagerMembership` creation in DB.

## Previous story intelligence (16.2)

- **`ManagerMembership`** lives in `src/api/fastapi/main.py` (`manager_memberships` table); `manager_id` and `member_id` are Keycloak subs / user ids (`String(255)`), **`member_id` is globally unique** (one member → one manager). On manager-scoped user create, insert `(manager_id=payload["sub"], member_id=<new user id>)`; **`IntegrityError`** on duplicate `member_id` → **409** (same pattern as membership POST race).
- **RBAC style**: Inline `get_roles(payload)`; forbidden paths use `HTTPException(403, detail={"error": "..."})` like `admin_purge_user` and `/v1/iam/memberships` — do **not** introduce a new `role_required()` helper unless used project-wide.
- **OpenAPI**: Use tag **`IAM`** for new routes (same as 16.2).
- **Tests**: Reuse patterns from `test_story_16_2.py` (role payloads, dependency overrides via `fastapi_test_app.py`).

## Previous story intelligence (16.1)

- **`get_admin_token()`** and **`KeycloakAdminTokenError`** in `keycloak_admin.py`; propagate **502** when token or downstream Admin calls fail after mapping transport errors appropriately.
- Realm name: derive admin base URL from `KEYCLOAK_ISSUER` (already normalized in 16.1); no second base-url env var.

## Implementation guardrails

- **Keycloak Admin API**: Use `POST /admin/realms/{realm}/users` for creation and `GET /admin/realms/{realm}/roles/{role-name}` to find roles.
- **Role Assignment**: Role assignment in Keycloak is a separate call `POST /admin/realms/{realm}/users/{user-id}/role-mappings/realm`.
- **Statelessness**: The API should verify the Manager's role from the JWT, but verify the target user's scope from PostgreSQL.
- **Transactionality**: If Keycloak creation succeeds but PostgreSQL mapping fails (or vice-versa), we have an inconsistency. **Decision:** Create in Keycloak first, then DB. If DB fails, we have an orphaned user in Keycloak (acceptable for v1, or implement best-effort rollback).
- **New user id for membership**: After `POST .../users`, obtain the new user’s id from the **`Location`** header or follow-up **`GET .../users`** query by username/email so `ManagerMembership.member_id` matches the Keycloak user id used in PATCH and JWT `sub`.

### Project Structure Notes

- **Keycloak Admin helpers**: extend `src/api/fastapi/keycloak_admin.py` (Admin REST + token reuse); keep `get_admin_token()` as the single token path.
- **Routes & Models**: `src/api/fastapi/main.py` (`ManagerMembership` already defined here).

### References

- [Source: .bmad-outputs/implementation-artifacts/16-1-keycloak-admin-client-and-service-account.md]
- [Source: .bmad-outputs/implementation-artifacts/16-2-manager-scope-membership-model.md]
- [Source: docs/epics-and-stories.md — Epic 16, Story 16.3]
- [Source: src/api/fastapi/main.py — `ManagerMembership`, `get_roles`, `admin_purge_user`, `/v1/iam/memberships`]
- [Source: src/api/fastapi/fastapi_test_app.py — JWT test payloads]

## Dev Agent Record

### Agent Model Used
Gemini 3.1 Pro

### Debug Log References
- `POST /v1/iam/users` success logs verify both Keycloak call and `ManagerMembership` persistence.
- `IndentationError` fixed in `main.py` after initial implementation.
- `TypeError` fixed in `test_keycloak_admin_provisioning.py` (temporary) before final implementation.

### Completion Notes List
- [x] Keycloak Admin REST Client updated to support role assignment on creation.
- [x] `UserCreate` and `UserUpdate` Pydantic models verified in `main.py`.
- [x] `POST /v1/iam/users` implemented with RBAC hierarchy and scope persistence.
- [x] `PATCH /v1/iam/users/{user_id}` implemented with management scope enforcement.
- [x] Tests in `src/api/fastapi/test_story_16_3.py` passing with 100% coverage of AC.

### File List
- src/api/fastapi/keycloak_admin.py
- src/api/fastapi/main.py
- src/api/fastapi/test_story_16_3.py
