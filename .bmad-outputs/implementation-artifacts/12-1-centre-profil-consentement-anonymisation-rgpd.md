# Story 12.1: Centre de Profil & Consentement RGPD

Status: ready-for-dev

## Story
**As a User**, I want to manage my account settings, data portability, and consent preferences in a centralized profile center so that I can exercise my RGPD rights and maintain control over my sensitive data (biometric and religious opinions).

## Acceptance Criteria

### 1. User Profile & Consent Management
- [ ] **UserConsent Model**: Implement a new SQLAlchemy model `UserConsent` in `src/api/fastapi/main.py`:
    - `user_id` (String, unique, sub from Keycloak).
    - `ml_usage_approved` (Boolean, default: False).
    - `biometric_data_approved` (Boolean, default: False).
    - `deletion_pending_at` (DateTime with timezone, nullable).
    - `updated_at` (DateTime with timezone).
- [ ] **GET /v1/me/profile**: Return current user profile (from Keycloak JWT) and their consent status:
    - JSON: `{ "sub": string, "name": string, "email": string, "roles": string[], "consents": { "ml_usage": bool, "biometric_data": bool, "deletion_pending": bool, "updated_at": iso8601 } }`.
- [ ] **PUT /v1/me/consents**: Update consent preferences:
    - Body: `{ "ml_usage": bool, "biometric_data": bool }`.
    - **Consent Withdrawal**: If `ml_usage` is toggled from `True` to `False`, immediately purge user-specific `GoldenSetEntry` rows where `source` is "frontend_correction".
- [ ] **Access Guard**: Prevent any authenticated action (except Profile GET) if `deletion_pending_at` is set.

### 2. Data Portability (Right to Portability)
- [ ] **GET /v1/me/export-data**: Generate and return a ZIP archive containing all data associated with the user:
    - `profile.json`: User profile and consent history.
    - `assignments.json`: List of assignments (past and current).
    - `corrections.json`: List of Golden Set corrections (source: "frontend_correction").
    - `activity_logs.json`: Audit logs related to the user's actions.
- [ ] **Streaming Response**: Ensure the export is streamed to avoid memory issues with large datasets. Use a Redis lock `lock:export:{user_id}` to prevent concurrent exports or deletions.

### 3. Right to be Forgotten (Deletion & Anonymization)
- [ ] **DELETE /v1/me/account**: Trigger a "Right to be Forgotten" workflow:
    - **Step 1**: Set `deletion_pending_at` to now (starts the 48h grace period).
    - **Step 2 (After 48h or manual admin trigger)**:
        - Anonymize `transcripteur_id` in `assignments` (replace with `deleted_user_<hash>`).
        - Anonymize `user_id` in `audit_logs`.
        - Purge user-specific `GoldenSetEntry` rows.
        - Delete the `UserConsent` entry or mark as fully purged.
    - Log the initial deletion request in `audit_logs`.
- [ ] **Admin Purge Sync**: Reuse `DELETE /v1/media/purge/{object_key}` logic if needed for specific files associated solely with the user.

### 4. UI: Profile Center (Azure Flow)
- [ ] **Profile Page**: Create a new page `/profile` in the frontend:
    - User Info Card (Name, Role, Email).
    - Consent Switches (ML Usage, Biometric Data).
    - Export Data Section (Download button with progress state).
    - Danger Zone (Delete Account button with confirmation modal and 48h warning).
- [ ] **Navigation**: Add a "Profile" entry in the AppShell avatar menu.

## Tasks / Subtasks

- [ ] **Task 1: Backend Models & Endpoints**
  - [ ] Add `UserConsent` table to `main.py` with `deletion_pending_at`.
  - [ ] Implement `GET /v1/me/profile`.
  - [ ] Implement `PUT /v1/me/consents` with immediate ML purge logic.
  - [ ] Implement `GET /v1/me/export-data` (Zip streaming).
- [ ] **Task 2: Deletion & Anonymization Logic**
  - [ ] Implement `DELETE /v1/me/account` (Grace period vs Immediate).
  - [ ] Implement anonymization routines for `assignments` and `audit_logs`.
  - [ ] Add integration test for account deletion and anonymization.
- [ ] **Task 3: Frontend UI**
  - [ ] Build the `/profile` page using `AzureTable` or standard components.
  - [ ] Integrate with the new FastAPI endpoints.
  - [ ] Add confirmation modals for critical actions (consents, deletion).

## Dev Notes
- Keycloak `sub` is the source of truth for `user_id`.
- For portability, use `select` statements joined with `audio_files` and `projects` to gather relevant user data.
- **Security**: The 48h grace period allows for recovery, but `deletion_pending_at` MUST block all other API interactions for safety.

## References
- **PRD**: `docs/prd.md` (§8 Conformité RGPD).
- **Architecture**: `docs/architecture.md` (Security & Privacy).
- **API Mapping**: `docs/api-mapping.md` (Purge logic).
