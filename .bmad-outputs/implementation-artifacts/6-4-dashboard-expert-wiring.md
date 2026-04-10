# Story US-05: Expert Dashboard API + UI wiring

Status: done

## Story

As an Expert or Admin,  
I want to fetch expert task data from a dedicated API endpoint and see it rendered in the Expert dashboard with robust UX states,  
so that expert reconciliation and Golden Set work can be tracked and acted on reliably.

## Acceptance Criteria

1. **New endpoint**  
   Implement `GET /v1/expert/tasks` in FastAPI.
   - Allowed roles: `expert`, `admin`.
   - `expert`: only own tasks.
   - `admin`: full list (optionally filter by expert id).
   - Return `200` with a JSON list (possibly empty).

2. **Role enforcement and auth errors**  
   - `401` without valid bearer token.
   - `403` for roles outside `expert|admin` (including `manager`, `transcriber`).

3. **Response contract (minimum fields)**  
   Each item includes at least:
   - `audio_id: number`
   - `project_id: number`
   - `project_name: string`
   - `filename: string`
   - `status: string`
   - `assigned_at: string | null`
   - `expert_id: string | null`
   - `source: "label_studio" | "frontend_correction" | string` (if available from current model)
   - `priority: string | null` (optional if model supports it)
   Keep naming and serialization style consistent with existing dashboard/task endpoints.

4. **Frontend API wiring**  
   Add dashboard API function in `src/frontend/src/features/dashboard/dashboardApi.ts`:
   - `fetchExpertTasks(token: string): Promise<ExpertTask[]>`
   - Uses shared `apiJson` helper and `GET /v1/expert/tasks`.

5. **Expert dashboard implementation**  
   Replace placeholder in `ExpertDashboard` in `src/frontend/src/features/dashboard/RoleDashboards.tsx`:
   - Fetch data when token is available.
   - Render metrics derived from returned list.
   - Handle **loading**, **error**, and **empty** states explicitly.

6. **UI state behavior**  
   - **Loading:** visible progress/info text before first successful response.
   - **Error:** clear backend/user-readable error message.
   - **Empty:** friendly no-task message when list is empty.
   - **Success:** table with expert tasks.

7. **Tests: backend**  
   Add tests in `src/api/fastapi/test_main.py` for:
   - expert happy path (`200`, scoped to self)
   - admin happy path (`200`, broader scope)
   - manager/transcriber forbidden (`403`)
   - no token unauthorized (`401`)
   - empty list response (`200`, `[]`)

8. **Tests: frontend**  
   Add/update tests for dashboard API + component behavior:
   - `fetchExpertTasks` parses success payload and raises `ApiError` on non-2xx.
   - `ExpertDashboard` renders loading, error, empty, and success states.

9. **Non-regression**  
   Existing endpoints and dashboards (Admin/Manager/Transcriber) remain behaviorally unchanged.

## Tasks / Subtasks

- [x] **Task 1: Backend contract and route** (AC: 1, 2, 3)
  - [x] Add response schema/type for expert tasks near existing dashboard/task models.
  - [x] Implement `GET /v1/expert/tasks` in `src/api/fastapi/main.py`.
  - [x] Reuse existing token decoding + role helpers for RBAC consistency.
  - [x] Implement expert/admin scoping logic.

- [x] **Task 2: Frontend API function** (AC: 4)
  - [x] Define `ExpertTask` type in `dashboardApi.ts`.
  - [x] Implement `fetchExpertTasks(token)` with `apiJson`.

- [x] **Task 3: ExpertDashboard wiring** (AC: 5, 6)
  - [x] Replace static placeholders with stateful data fetch flow.
  - [x] Implement loading/error/empty/success UI states.
  - [x] Keep visual style aligned with existing dashboard components (`Card`, `Metric`, `DataTable`, `DashboardInfo` pattern).

- [x] **Task 4: Backend tests** (AC: 7)
  - [x] Add focused tests in `src/api/fastapi/test_main.py` following existing style and fixtures.

- [x] **Task 5: Frontend tests** (AC: 8)
  - [x] Add/update tests for API utility and ExpertDashboard rendering states.

- [x] **Task 6: Regression verification** (AC: 9)
  - [x] Run backend test subset for dashboard/task routes.
  - [x] Run frontend test subset for dashboard module.

## Dev Notes

### Architecture and RBAC guardrails

- Roles come from Keycloak-backed JWT and are already resolved in backend auth utilities. Keep role checks aligned with existing patterns used by `GET /v1/me/audio-tasks` and dashboard routes.
- Preserve zero-trust behavior: no fallback role inference from untrusted client payload.
- Keep API error shape and message style consistent with current FastAPI handlers.

### Integration points (existing code)

- Backend route file: `src/api/fastapi/main.py`
- Backend tests: `src/api/fastapi/test_main.py`
- Dashboard API client: `src/frontend/src/features/dashboard/dashboardApi.ts`
- Dashboard UI: `src/frontend/src/features/dashboard/RoleDashboards.tsx`
- Shared frontend API helper: `src/frontend/src/shared/api/zachaiApi.ts`
- Navigation/role routes already include Expert dashboard (`dashboard-expert`).

### Data source strategy for `/v1/expert/tasks`

- Prefer reusing existing persisted entities already used by expert validation flow and assignment dashboard.
- Do not invent new persistence tables in this story unless strictly required.
- If exact expert ownership field is absent in current model, implement the minimal deterministic scoping rule and document it in completion notes.

### UX expectations for Expert dashboard

- Keep messages concise and operational:
  - loading: "Chargement dashboard expert..."
  - empty: "Aucune tache experte pour le moment."
  - error: backend error text if available, fallback generic.
- Keep table density similar to transcriber dashboard for consistency.

### Testing standards

- Backend tests should follow current `test_main.py` fixture style (`mock_db`, dependency overrides, role token headers).
- Frontend tests should assert visible user state text and state transitions, not implementation details.
- Focus on deterministic tests with explicit mocked API outcomes.

## References

- `docs/epics-and-stories.md` (roles and dashboard intent across stories)
- `docs/prd.md` (`§2` roles, `§4.1` dashboard behavior, `§4.4` expert workflow)
- `docs/architecture.md` (`§5` security/RBAC principles)
- Existing implementation patterns:
  - `src/api/fastapi/main.py` (`GET /v1/me/audio-tasks`, `GET /v1/projects?include=audio_summary`)
  - `src/frontend/src/features/dashboard/RoleDashboards.tsx`
  - `src/frontend/src/features/dashboard/dashboardApi.ts`

## Git Intelligence Summary

Recent commits follow `feat(validation): ...` style and complete-story batching.  
For this story, keep implementation scoped to API + dashboard wiring + tests in one coherent change set.

## Story Completion Status

- Generated: 2026-04-02
- Story key: `us-05-dashboard-expert-branche-api-ui`
- Status: `done`
- Scope: backend endpoint + frontend wiring + UI states + tests

---

## Traduction FR (résume operationnel)

- **Objectif:** ajouter `GET /v1/expert/tasks` (roles Expert/Admin) et brancher le `ExpertDashboard` sur des donnees reelles.
- **UI obligatoire:** gerer les 4 etats `loading`, `error`, `empty`, `success`.
- **Qualite:** tests backend + frontend couvrant RBAC, erreurs auth, liste vide et rendu nominal.

## Dev Agent Record

### Completion Notes

- Implemented `GET /v1/expert/tasks` with strict RBAC (`Expert|Admin`) and 401/403 behavior aligned with existing auth dependencies.
- Reused existing persistence (`GoldenSetEntry` + `AudioFile` + `Project` + `Assignment`) to return expert dashboard rows without introducing schema migrations.
- Applied Expert isolation fix after review: Expert responses are filtered to the caller scope via `Assignment.transcripteur_id == token sub`; Admin keeps global view.
- Wired `ExpertDashboard` to live API data with explicit loading/error/empty/success states and table rendering on success.
- Added `fetchExpertTasks` and `ExpertTask` in dashboard API client.
- Added backend tests for success (Expert/Admin), forbidden roles (Manager/Transcripteur), no token (401), empty list, and explicit Expert scope isolation.
- Added frontend tests for API function behavior plus rendered Expert dashboard state content (`loading`, `error`, `empty`, `success`) using server-side React rendering.
- Validation run:
  - `pytest test_main.py -k "expert_tasks or me_audio_tasks"` (9 passed)
  - `pytest test_main.py -k "expert_tasks"` (7 passed)
  - `npm test` in `src/frontend` (4 files, 24 tests passed)
- Note on `expert_id`: endpoint now returns `expert_id` from assignment (`Assignment.transcripteur_id`) when available.

### File List

- `.bmad-outputs/implementation-artifacts/us-05-dashboard-expert-branche-api-ui.md`
- `src/api/fastapi/main.py`
- `src/api/fastapi/test_main.py`
- `src/frontend/src/features/dashboard/dashboardApi.ts`
- `src/frontend/src/features/dashboard/RoleDashboards.tsx`
- `src/frontend/src/features/dashboard/dashboardApi.test.ts`
- `src/frontend/src/features/dashboard/RoleDashboards.test.ts`

### Change Log

- 2026-04-02: Implemented US-05 backend endpoint, frontend expert dashboard wiring, and backend/frontend test coverage.
- 2026-04-02: Applied review follow-ups for Expert scope isolation and strengthened frontend rendered-state tests.
- 2026-04-02: Story marked `done` after review; ready to commit.
