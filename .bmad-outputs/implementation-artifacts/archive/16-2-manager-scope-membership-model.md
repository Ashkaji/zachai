# Story 16.2: Modèle de périmètre Manager / Manager Scope Membership Model

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

**En:** As a Maintainer, I want to persist which users belong to which manager’s scope (PostgreSQL mapping), so that the API can enforce that a Manager only provisions and manages users inside their perimeter.

**Fr:** En tant que Mainteneur, je veux persister quels utilisateurs appartiennent au périmètre de quel manager (mapping PostgreSQL), afin que l'API puisse garantir qu'un Manager ne provisionne et ne gère que les utilisateurs de son propre périmètre.

## Acceptance Criteria / Critères d'Acceptation

1.  **PostgreSQL Model (ManagerMembership)**: A new SQLAlchemy model `ManagerMembership` is implemented in `src/api/fastapi/main.py`.
    *   `id`: Integer primary key.
    *   `manager_id`: String (Keycloak `sub`), indexed. Represents the manager.
    *   `member_id`: String (Keycloak `sub`), unique and indexed. A user can only belong to ONE manager's scope in this model.
    *   `created_at`: DateTime (timezone=True) with server default.
2.  **Database Initialization**: The table is automatically created via `Base.metadata.create_all` at application startup (existing pattern in `main.py`).
3.  **Membership API Endpoints**:
    *   `POST /v1/iam/memberships`: Associate a user to a manager.
        *   **Auth**: Admin only: `roles = get_roles(payload)` then `if "Admin" not in roles: raise HTTPException(403, ...)` (same pattern as `admin_purge_user` in `main.py`).
        *   **Validation**: `manager_id` and `member_id` must be provided and different. If `member_id` is already mapped to a **different** `manager_id`, return **409 Conflict**. If the row already exists for the **same** pair, return **200** with the existing record (idempotent POST) or **204**—pick one and document in OpenAPI; avoid relying on a raw DB unique violation for the “same pair” case if you implement upsert explicitly.
    *   `GET /v1/iam/memberships/{manager_id}`: List all `member_id` values (or full rows) for that manager.
        *   **Auth**: Admin **or** Manager whose `payload["sub"]` equals path `manager_id` (string match). Any other Manager → **403**.
    *   `DELETE /v1/iam/memberships/{manager_id}/{member_id}`: Remove mapping.
        *   **Auth**: Admin only (same `get_roles` check). **404** if no row matches.
4.  **Data Integrity**: Enforce `UniqueConstraint` on `member_id` to ensure a strict hierarchy (one user -> one manager).
5.  **Testing**:
    *   `src/api/fastapi/test_story_16_2.py` verifies successful CRUD operations and 403/409/404 error cases.
    *   Use `client` + `patch("main.decode_token", ...)` (or equivalent) with `ADMIN_PAYLOAD`, `MANAGER_PAYLOAD`, `MANAGER_OTHER_PAYLOAD`, `TRANSCRIPTEUR_PAYLOAD` from `fastapi_test_app.py`—same style as other route tests.
    *   **Required cases**: Admin CRUD happy path; second manager assignment to same `member_id` → 409; Manager can `GET` only their own `manager_id`; another Manager `GET` → 403; Transcripteur/Expert denied on these routes → 403; `DELETE` missing row → 404.

## Tasks / Subtasks

- [x] **Define Database Model** (AC: 1, 4)
  - [x] Add `ManagerMembership` class to `src/api/fastapi/main.py` inheriting from `Base`.
  - [x] Add indices on `manager_id` and `member_id`.
  - [x] Add `UniqueConstraint("member_id")`.
- [x] **Implement Membership Endpoints** (AC: 3)
  - [x] Define `ManagerMembershipCreate` Pydantic model for request body.
  - [x] Implement `POST /v1/iam/memberships` with `get_roles` + Admin check.
  - [x] Implement `GET /v1/iam/memberships/{manager_id}` with Admin bypass or `payload["sub"] == manager_id`.
  - [x] Implement `DELETE /v1/iam/memberships/{manager_id}/{member_id}` with `get_roles` + Admin check.
- [x] **Verification & Tests** (AC: 5)
  - [x] Create `src/api/fastapi/test_story_16_2.py`.
  - [x] Test successful assignment of multiple transcripteurs to one manager.
  - [x] Test rejection when assigning the same transcripteur to a second manager (409).
  - [x] Test RBAC: Transcripteur cannot access `/v1/iam/memberships`.

### Review Findings

- [x] [Review][Patch] Idempotent POST (same manager_id + member_id) still returns **201**; AC 3 asks for **200** (or 204) and OpenAPI should match. [`main.py` — `post_membership` idempotent branches] — **fixed 2026-04-13:** `JSONResponse` **200** for idempotent paths, **201** for create; `responses` documented in OpenAPI.
- [x] [Review][Patch] AC 5 requires **Transcripteur/Expert** denied on **these routes** (plural); tests cover Manager POST 403 but not Transcripteur/Expert on **GET** and **DELETE**, and **Expert** is not covered. [`test_story_16_2.py`] — **fixed 2026-04-13:** added POST/GET/DELETE **403** tests for Transcripteur and Expert.
- [x] [Review][Patch] No test for **idempotent POST** when the row already exists for the same pair (should return existing record with chosen success status). [`test_story_16_2.py`] — **fixed 2026-04-13:** `test_post_membership_idempotent_same_pair`.
- [x] [Review][Patch] Minor style: mis-indented `return {` block in `IntegrityError` handler (PEP 8 / consistency). [`main.py` ~3652] — **fixed 2026-04-13:** refactored to shared `body` + `JSONResponse`.

## Dev Notes

- **Hierarchy**: Epic 16.2 allows “Keycloak groups and/or PostgreSQL mapping”; this story is **PostgreSQL-only**. Story 16.3 will enforce provisioning using these rows plus `keycloak_admin.py` from 16.1.
- **Reuse**: `get_db`, `get_current_user`, `get_roles`, async `select` / `db.execute` / `db.commit` like existing models and `admin_purge_user`.
- **Naming**: SQLAlchemy model class `ManagerMembership`, table name e.g. `manager_memberships`; columns mirror `Project.manager_id` style (`String(255)` subs).
- **Do not invent** a `role_required()` helper unless you add it as a shared dependency used project-wide; today every endpoint inlines `get_roles(payload)`.

### Implementation guardrails

- **RBAC pattern**: Copy the `admin_purge_user` guard (`get_roles` + `"Admin" not in roles` + `HTTPException` 403 with `detail={"error": "..."}`).
- **Manager read scope**: For `GET`, Admin sees any `manager_id`; Manager only if `payload.get("sub") == manager_id`.
- **Concurrency**: Unique constraint on `member_id` may raise `IntegrityError` on race; map to **409** for duplicate `member_id` under another manager.
- **OpenAPI**: Use a dedicated tag (e.g. `IAM`) for `/v1/iam/*` so generated docs stay grouped.
- **Story 16.1 dependency**: `member_id` / `manager_id` are Keycloak user subs; align with JWT `sub` claims used everywhere else in `main.py`.

### Previous story intelligence (16.1)

- `get_admin_token()` and `KeycloakAdminTokenError` live in `keycloak_admin.py`; 16.2 does **not** call Keycloak Admin API—only persists mappings for 16.3+.
- Tests that import `main` must set `KEYCLOAK_ADMIN_*` env vars before import (see `fastapi_test_app.py` / 16.1 completion notes).

### Project Structure Notes

- **Backend**: `src/api/fastapi/main.py` is the main entry point for models and routes.
- **Tests**: `src/api/fastapi/` for pytest files.

### References

- [Source: docs/epics-and-stories.md — Epic 16, Story 16.2]
- [Source: src/api/fastapi/main.py — `Nature` / `Project` models, `get_roles`, `admin_purge_user`]
- [Source: src/api/fastapi/fastapi_test_app.py — JWT role payloads]
- [Source: .bmad-outputs/implementation-artifacts/16-1-keycloak-admin-client-and-service-account.md]

## Dev Agent Record

### Agent Model Used

gemini-2.0-pro-exp-02-05

### Debug Log References

- AttributeError: 'NoneType' object has no attribute 'isoformat' in `post_membership` (fixed by handling `created_at` fallback for tests).

### Completion Notes List

- Implemented `ManagerMembership` SQLAlchemy model in `src/api/fastapi/main.py`.
- Added `manager_memberships` table DDL to application lifespan for brownfield compatibility.
- Implemented `POST /v1/iam/memberships` (Admin only), `GET /v1/iam/memberships/{manager_id}` (Admin or Manager scope), and `DELETE /v1/iam/memberships/{manager_id}/{member_id}` (Admin only).
- Added `IAM` tag to OpenAPI documentation.
- Created exhaustive test suite in `src/api/fastapi/test_story_16_2.py` covering all AC scenarios.

### File List

- src/api/fastapi/main.py
- src/api/fastapi/test_story_16_2.py
- .bmad-outputs/implementation-artifacts/sprint-status.yaml
