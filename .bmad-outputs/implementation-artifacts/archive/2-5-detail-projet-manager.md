# Story 2.5: Detail Projet Manager (US-07)

Status: done

## Story

As a **Manager** or **Admin**,  
I want to view a detailed page for a specific project with its full list of audios and their real-time statuses,  
so that I can effectively monitor progress, verify assignments, and prepare for validation.

## Acceptance Criteria

1. **Frontend API wiring**  
   Add `fetchProjectStatus(id: number, token: string)` in `src/frontend/src/features/dashboard/dashboardApi.ts`.
   - Uses `GET /v1/projects/${id}/status`.
   - **Critical:** Handles the backend wrapper object: `{ project_status: string, audios: AudioRow[] }`.

2. **ProjectDetailManager component**  
   Create `ProjectDetailManager` in `src/frontend/src/features/projects/ProjectDetailManager.tsx`.
   - Fetches data using `fetchProjectStatus` on mount and when `projectId` changes.
   - **Reuse:** Move/reuse the `formatIso` helper from `RoleDashboards.tsx` for consistent date rendering.
   - Implements 4 visual states: **loading**, **error**, **empty**, **success**.

3. **UI state behavior**  
   - **Loading:** Display "Chargement du projet..." placeholder.
   - **Error:** Display backend error or "Erreur lors de la récupération du projet".
   - **Empty:** "Aucun fichier audio n'a été ajouté à ce projet."
   - **Success:** Render project status as a `Metric` card and the list of audios in a `DataTable`.

4. **Audio Table, Filters & Sorting**  
   - Columns: **Filename**, **Status**, **Assigned To**, **Uploaded At**.
   - **Filters:** Provide a dropdown to filter by audio status (e.g., All, Uploaded, Assigned, etc.).
   - **Sorting:** Enable client-side sorting on the `DataTable` for filename and upload date.

5. **Navigation & Routing**  
   - Update `src/frontend/src/app/navigation.ts` to include `project-detail` in `AppRouteId`.
   - Update `src/frontend/src/app/AppShell.tsx` to manage `selectedProjectId` state and render the detail page.
   - Add a **"Retour"** button in the detail page header to return to `dashboard-manager`.

6. **Dashboard Integration**  
   - In `src/frontend/src/features/dashboard/RoleDashboards.tsx`, add a **"Voir"** button to each project row.
   - On click: set `selectedProjectId` and switch `activeRoute` to `project-detail`.

7. **Tests**  
   - API: Validate `fetchProjectStatus` correctly parses the `{ project_status, audios }` response.
   - UI: Verify rendering of all 4 states and the status filter logic.

## Tasks / Subtasks

- [x] **Step 1: Research & Setup**
  - [x] Identify existing `formatIso` usage and move to shared utility if needed.
  - [x] Map `AudioRow` type to backend contract in `docs/api-mapping.md`.

- [x] **Step 2: API & Routing** (AC: 1, 5)
  - [x] Implement `fetchProjectStatus` in `dashboardApi.ts`.
  - [x] Register `project-detail` in `navigation.ts` and wire `AppShell.tsx`.

- [x] **Step 3: UI Implementation** (AC: 2, 3, 4, 6)
  - [x] Build `ProjectDetailManager` with loading/error/empty/success logic.
  - [x] Implement project metadata cards and audio `DataTable`.
  - [x] Add status filtering and sorting to the audio list.
  - [x] Add the navigation link in `ManagerDashboard`.

- [x] **Step 4: Validation** (AC: 7)
  - [x] Add unit tests for API client and component rendering states.
  - [x] Verify sorting and filtering behavior with mocked data.

## Dev Notes

### Architecture and UX patterns
- **Design System:** Follow "Azure Flow" (Clear & Serene, Blue cobalt).
- **Primitives:** Use `Card`, `DataTable`, `Metric` from `src/frontend/src/shared/ui/Primitives.tsx`.
- **Backend:** `GET /v1/projects/{project_id}/status` is ready. Ensure the frontend handles the project-level status wrapper correctly.

### References
- `docs/api-mapping.md#Section` (API contract for project status)
- `docs/architecture.md` (Security/RBAC principles)
- `src/frontend/src/features/dashboard/RoleDashboards.tsx` (Previous dashboard patterns)

## Dev Agent Record

### Agent Model Used
Gemini 2.0 Flash

### Debug Log References
- Tests passing in `src/frontend`: `vitest run` (30 passed; 2026-04-07 after code-review fixes)
- `formatIso` successfully moved to `shared/utils/dateUtils.ts`
- `AppShell.tsx` updated with `selectedProjectId` state and `handleViewProject` callback

### Completion Notes List
- Implemented `ProjectDetailManager` with all requested visual states.
- Connected `ManagerDashboard` "Voir" buttons to the new detail page.
- Added client-side sorting and filtering for the project's audio files.
- Verified that `fetchProjectStatus` correctly maps the backend response.

### File List
- `src/frontend/src/shared/utils/dateUtils.ts` (New)
- `src/frontend/src/features/dashboard/dashboardApi.ts` (Modified: types and `fetchProjectStatus`)
- `src/frontend/src/features/dashboard/RoleDashboards.tsx` (Modified: `ManagerDashboard` UI)
- `src/frontend/src/app/navigation.ts` (Modified: `AppRouteId`)
- `src/frontend/src/app/AppShell.tsx` (Modified: route handling)
- `src/frontend/src/features/projects/ProjectDetailManager.tsx` (New)
- `src/frontend/src/shared/ui/Primitives.tsx` (Modified: `DataTable` type safety)
- `src/frontend/src/features/dashboard/dashboardApi.test.ts` (Modified: unit tests)
- `src/frontend/src/features/projects/ProjectDetailManager.test.ts` (New)

### Review Findings

- [x] [Review][Patch] No-token / auth-loading paths — Gated UI on `auth.isLoading` and `!token`; fetch effect skips until auth settled; initial `loading` is true for fetch lifecycle. [src/frontend/src/features/projects/ProjectDetailManager.tsx]
- [x] [Review][Patch] AC7 — Expanded jsdom tests: OIDC loading, session missing, fetch loading→empty, fetch error, filter-by-status. [src/frontend/src/features/projects/ProjectDetailManager.test.ts]
- [x] [Review][Patch] `onBack` clears `selectedProjectId` when returning to manager dashboard. [src/frontend/src/app/AppShell.tsx]

---

## Traduction FR (résumé opérationnel)

- **Objectif:** Créer une page de détail projet pour les Managers/Admin.
- **Fonctionnalités:**
  - Enveloppe API: `{ project_status, audios }`.
  - Métriques projet + Tableau audios (Nom, Statut, Assigné, Date).
  - Filtres par statut et tri par date/nom.
  - États UI: `loading`, `error`, `empty`, `success`.
- **Navigation:** Intégration dans `AppShell` et lien "Voir" depuis le Dashboard Manager.
- **Qualité:** Tests unitaires API et rendu UI.
