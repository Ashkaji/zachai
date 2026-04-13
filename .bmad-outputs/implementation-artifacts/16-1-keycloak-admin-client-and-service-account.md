# Story 16.1: Keycloak Admin Client & service account

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a Security Admin,
I want to configure a confidential Keycloak client with a service account and least-privilege roles for user management,
so that FastAPI can call the Admin REST API without exposing credentials to the browser.

## Acceptance Criteria

1. **Keycloak Configuration (JSON)**: `src/config/realms/zachai-realm.json` includes a new confidential client `zachai-admin-cli` with `serviceAccountsEnabled: true` and `publicClient: false`.
2. **Service Account Roles**: The `zachai-admin-cli` service account is assigned the following roles from the `realm-management` client: `manage-users`, `view-users`, and `query-groups`.
3. **Environment Variables**: `src/.env.example` documents `KEYCLOAK_ADMIN_CLIENT_ID` and `KEYCLOAK_ADMIN_CLIENT_SECRET` (defaults: `zachai-admin-cli` and a placeholder secret), placed next to `KEYCLOAK_ISSUER`, with a short comment that these are for the **backend service account** (not Keycloak bootstrap admin — see existing `KC_BOOTSTRAP_ADMIN_*` note in that file).
4. **FastAPI Admin Auth**: A new utility (e.g., `src/api/fastapi/keycloak_admin.py`) implements `get_admin_token()` using the OIDC `client_credentials` flow via **`httpx`** (already used in `main.py`).
5. **Token Caching**: **v1:** in-process TTL cache (refresh shortly before `exp`). **Do not** require Redis for this cache; Redis is already used elsewhere but per-process cache is sufficient for 16.1. **Multi-worker note:** each Uvicorn worker holds its own cache; that is acceptable for this story.
6. **Validation**: A pytest `src/api/fastapi/test_keycloak_admin.py` verifies that:
    - `get_admin_token()` successfully retrieves a JWT (with the token endpoint mocked).
    - The JWT payload includes the expected `realm-management` roles under **`resource_access["realm-management"]["roles"]`** (list must contain `manage-users`, `view-users`, and `query-groups`). Use the same JWT decode approach as elsewhere in the API (e.g. `jose` / existing helpers) for consistency.
    - Errors (e.g., wrong secret, non-200 from token endpoint) are handled gracefully (clear exception or structured error; no unhandled blowups).

**Definition of done (AC1–6):** Realm JSON imports on compose startup; app starts with new env vars set; `get_admin_token()` returns a usable access token in tests; role assertions use the claim path above. No Keycloak **Admin REST** user CRUD in this story — only token acquisition (16.3+).

## Tasks / Subtasks

- [ ] **Configure Keycloak Realm** (AC: 1, 2)
  - [ ] Modify `src/config/realms/zachai-realm.json` to add the `zachai-admin-cli` client (`serviceAccountsEnabled: true`, `publicClient: false`, `clientAuthenticatorType` / secret as required for Keycloak 26 confidential clients).
  - [ ] Assign `realm-management` client roles to this client’s **service account** using structures Keycloak 26 accepts on realm import (follow a **realm export** from a reference instance if needed: service account user + client role mappings). If JSON-only mappings are brittle, document one fallback (e.g. one-time Admin API or operator runbook step) and keep compose dev path working.
- [ ] **Update Environment** (AC: 3)
  - [ ] Add `KEYCLOAK_ADMIN_CLIENT_ID` and `KEYCLOAK_ADMIN_CLIENT_SECRET` to `src/.env.example` (next to `KEYCLOAK_ISSUER`, with comments as in AC3).
  - [ ] Add both to `src/api/fastapi/main.py`’s `REQUIRED_ENV_VARS` **policy:** fail fast at startup if unset/empty, same as other secrets (`MINIO_*`, etc.), so misconfigured deployments cannot silently omit the admin client. Local and CI must set placeholders where needed.
- [ ] **Implement Admin Auth Service** (AC: 4, 5)
  - [ ] Create `src/api/fastapi/keycloak_admin.py`.
  - [ ] Implement `get_admin_token()`: `POST` to **`{KEYCLOAK_ISSUER}/protocol/openid-connect/token`** with `grant_type=client_credentials`, `client_id`/`client_secret` from env (`KEYCLOAK_ADMIN_CLIENT_ID`, `KEYCLOAK_ADMIN_CLIENT_SECRET`). `KEYCLOAK_ISSUER` is already required in `main.py` (no duplicate base-URL env var). Normalize issuer URL (no double slashes if joining paths).
  - [ ] Add in-process TTL caching per AC5.
- [ ] **Verification & Tests** (AC: 6)
  - [ ] Create `src/api/fastapi/test_keycloak_admin.py`.
  - [ ] Set required env vars **before** importing modules that trigger `validate_env()` (same pattern as `test_main.py`: `os.environ.setdefault` / `patch.dict` for `KEYCLOAK_ISSUER`, `KEYCLOAK_ADMIN_*`, and any other vars `main` needs when imported).
  - [ ] Mock the token HTTP call with `unittest.mock` / `patch` on `httpx.AsyncClient` (same style as `test_main.py` / `test_story_12_2.py`).
  - [ ] (Optional) Script or manual runbook note to hit a live Keycloak instance.

## Implementation guardrails

- **Keycloak 26:** Client and import format must match the version used in `src/compose.yml` / project Keycloak image.
- **Least privilege:** Only `manage-users`, `view-users`, `query-groups` from `realm-management`. Do **not** assign `realm-admin`.
- **Scope boundary:** This story delivers **client credentials token + cache + tests** only. Stories **16.2–16.3** add perimeter model and Admin REST provisioning; keep `keycloak_admin.py` easy to import from those routes later.
- **Reuse:** `httpx`, `KEYCLOAK_ISSUER`, and JWT libraries already present in `main.py` / tests — extend patterns; do not add a second HTTP stack for the same flow.

### Project structure

- **Backend:** `src/api/fastapi/`.
- **Realm:** `src/config/realms/`.
- **Docker:** No Dockerfile change; Keycloak service already imports realm JSON on startup.

### References

- [Source: docs/architecture.md — diagram IAM / Keycloak OIDC (§2)]
- [Source: docs/prd.md — stack IAM / Keycloak]
- [Source: docs/epics-and-stories.md — Epic 16]
- [Source: src/compose.yml — keycloak service]

## Dev Agent Record

### Agent Model Used

gemini-2.0-pro-exp-02-05

### Debug Log References

### Completion Notes List

### File List
- src/config/realms/zachai-realm.json
- src/.env.example
- src/api/fastapi/main.py
- src/api/fastapi/keycloak_admin.py
- src/api/fastapi/test_keycloak_admin.py
