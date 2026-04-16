# Story 16.5: UI Manager — invite Transcripteur / Expert

Status: done

<!-- Ultimate context engine analysis completed — comprehensive developer guide created. -->

## Story

**En:** As a Manager, I can invite Transcripteur and Expert users within my scope from the web UI, so that my team is provisioned without IAM console access.

**Fr:** En tant que Manager, je peux inviter des utilisateurs Transcripteur et Expert dans mon périmètre depuis l’interface web, pour provisionner mon équipe sans console IAM.

**Scope note (product vs implementation):** Story 16.3 provisions users immediately via `POST /v1/iam/users` (Keycloak + `ManagerMembership`). There is no separate email-invite service in scope for 16.5 unless you add one deliberately; the UI should treat “invite” as **in-product account creation** with clear success copy (optional: mention that credentials / onboarding follow your org process).

## Acceptance Criteria / Critères d’acceptation

1. **Manager-only visibility**  
   **En:** The “invite team member” entry point appears only on the **Manager** dashboard (same routing/role gating as today’s `ManagerDashboard` in `RoleDashboards.tsx`). It must **not** appear on Admin, Transcripteur, or Expert dashboards.  
   **Fr:** Le point d’entrée « inviter un membre » n’apparaît que sur le tableau de bord **Manager**, pas sur Admin / Transcripteur / Expert.

2. **Role choice (Transcripteur | Expert)**  
   **En:** The manager selects **one** role: `Transcripteur` or `Expert`. The UI must **not** offer `Admin` or `Manager` (API would return 403 if attempted — avoid useless calls). Backend provisioning rule: selecting `Expert` provisions a composite IAM profile (`Expert` + `Transcripteur` realm roles).  
   **Fr:** Choix d’un seul rôle : Transcripteur ou Expert ; pas Admin ni Manager.

3. **Form contract**  
   **En:** Collect `username`, `email`, `firstName`, `lastName`, and honor `UserCreate` / `createUser` JSON shape (`camelCase` fields per Story 16.3). `enabled` defaults to `true` unless you add a visible control; stay consistent with `CreateManagerModal.tsx`.  
   **Fr:** Même contrat que `UserCreate` / Story 16.3, aligné sur le modal Manager existant.

4. **API**  
   **En:** Call `POST /v1/iam/users` with the session JWT via existing `createUser` in `dashboardApi.ts`, passing `role: "Transcripteur"` or `role: "Expert"` according to selection.  
   **Fr:** Appel `createUser` → `POST /v1/iam/users` avec le rôle choisi.

5. **UX**  
   **En:** Use `GlassModal` (or the same modal primitive as `CreateManagerModal`), French labels acceptable to match surrounding Manager UI, loading state on submit, inline error for failures, reset state on close. Success closes modal and clears error; optionally call `onSuccess` to clear parent error banners (mirror Admin pattern).  
   **Fr:** Modal glass, chargement / erreurs / reset à la fermeture.

6. **Label Studio / Expert**  
   **En:** **No** Label Studio linking, SSO, or deep-link work in this story — that is **Story 16.6**. Creating an `Expert` user here only creates the Keycloak identity and manager scope row; document that in UI helper text if useful (one line).  
   **Fr:** Aucun travail Label Studio dans 16.5 (réservé à 16.6).

7. **Tests**  
   **En:** Add Vitest tests analogous to `CreateManagerModal.test.tsx`: submit sends `createUser` with each role; role forbidden paths not exposed in UI (optional snapshot/assert no Admin/Manager options); error propagation from `apiJson`. Extend or mirror `dashboardApi.test.ts` only if you change `createUser` behavior.  
   **Fr:** Tests unitaires sur le modal et l’appel API.

## Tasks / Subtasks

- [x] **Component** (AC: 2–5, 6)  
  - [x] Add `InviteTeamMemberModal.tsx` (or equivalent name) in `src/frontend/src/features/dashboard/`, modeled on `CreateManagerModal.tsx`: role control (radio or `<select>`), shared field layout, `createUser({ ...form, role }, token)`.
- [x] **Integration** (AC: 1)  
  - [x] Wire modal + trigger button into `ManagerDashboard` header in `RoleDashboards.tsx` (e.g. next to “+ Nouveau Projet” when `onCreateProject` is present, or in a sensible fixed position — avoid Admin-only code paths).
- [x] **Tests** (AC: 7)  
  - [x] `InviteTeamMemberModal.test.tsx` — mock `createUser`, assert payloads for `Transcripteur` and `Expert`, error display, disabled submit while loading.
- [x] **Copy / a11y** (AC: 5, 6)  
  - [x] Clear title (“Inviter un membre d’équipe” / similar), optional short note for Expert about LS access coming in 16.6, labels associated with inputs (`za-label` pattern).

## Dev Notes

### Technical requirements

- **Reuse, don’t fork API:** `createUser` already posts to `/v1/iam/users`. Do not add a second client for the same endpoint.
- **RBAC is server-side:** Manager can only create `Transcripteur`/`Expert` (Story 16.3). UI must not send other roles.
- **Expert semantics:** In IAM, `Expert` is a superset profile and receives both `Expert` and `Transcripteur` realm roles at account creation.
- **Errors:** Expect `400`, `403`, `409`, `502` — surface `Error.message` from `apiJson` like `CreateManagerModal` (same user-visible pattern).
- **Membership:** Successful create from a Manager JWT must already persist `ManagerMembership` (16.3); no extra frontend call.

### Architecture compliance

- **Epic 16 hierarchy:** Admin creates Managers (16.4); Manager creates team roles (this story). See [Source: `.bmad-outputs/planning-artifacts/epics.md` — Epic 16, Story 16.5].
- **IAM API contract:** [Source: `.bmad-outputs/implementation-artifacts/16-3-api-user-provisioning-and-rbac.md`].
- **Test design hooks (optional regression IDs):** [Source: `.bmad-outputs/test-artifacts/test-design-epic-16.md` — 16.5 API/E2E ideas].

### Library / framework

- **React** `^18.3.0`, **Vitest** for unit tests (existing frontend toolchain). No new dependencies expected.

### File structure requirements

| Area | Path |
|------|------|
| Modal (new) | `src/frontend/src/features/dashboard/InviteTeamMemberModal.tsx` (name adjustable but keep colocated with dashboard feature) |
| Integration | `src/frontend/src/features/dashboard/RoleDashboards.tsx` — `ManagerDashboard` |
| API | `src/frontend/src/features/dashboard/dashboardApi.ts` — `createUser`, `UserCreate` |
| Modal primitive | `src/frontend/src/shared/ui/Modals.tsx` — `GlassModal` |
| Tests | `src/frontend/src/features/dashboard/InviteTeamMemberModal.test.tsx` |

### Testing requirements

- Run frontend unit tests for the new spec (e.g. `npm test` / project’s Vitest command from `src/frontend`).
- After implementation, repo workflow expects API tests still green: `./scripts/run-api-pytest.sh` before commit.

### Project structure notes

- Prefer **small duplication** over a large shared abstraction: if you extract shared form fields, keep it minimal (e.g. one shared component used by Admin and Manager modals) to avoid churn in `CreateManagerModal` unless you need a single source of truth for validation messages.
- Keep Azure Flow / `za-btn`, `za-input`, `za-label` classes consistent with `CreateManagerModal`.

### References

- [Source: `docs/epics-and-stories.md` — Epic 16, Story 16.5]
- [Source: `.bmad-outputs/implementation-artifacts/16-4-ui-admin-create-managers.md`]
- [Source: `.bmad-outputs/implementation-artifacts/16-3-api-user-provisioning-and-rbac.md`]
- [Source: `src/frontend/src/features/dashboard/CreateManagerModal.tsx`]
- [Source: `src/frontend/src/features/dashboard/RoleDashboards.tsx` — `ManagerDashboard`]
- [Source: `src/frontend/src/features/dashboard/dashboardApi.ts` — `createUser`]

## Previous story intelligence (16-4)

- **Pattern:** `CreateManagerModal` hard-codes `role: "Manager"` on submit; your modal parameterizes role.
- **Admin vs Manager:** Admin dashboard owns “+ Créer Manager”; Manager dashboard owns team invites — do not show the invite flow on `AdminDashboard`.
- **Lifecycle:** `useEffect` reset when `isOpen` becomes false was hardened in recent work (see commit `3ba3db9`); mirror that pattern to avoid stale errors.

## Git intelligence summary

- Recent IAM/UI work: retroactive story doc `16-4`, manager modal hardening (`3ba3db9`), Epic 16 test design artifact. Implementation should extend the same dashboard feature folder and testing style.

## Latest tech information

- No version upgrades required; stay on existing React 18 + Vitest stack in `src/frontend/package.json`.

## Project context reference

- No `project-context.md` found in repo; rely on artifacts above and in-repo sources.

## Change Log

- 2026-04-16: Implemented `InviteTeamMemberModal`, Manager dashboard integration, Vitest coverage; full frontend + API test suites green.

## Dev Agent Record

### Agent Model Used

Composer (Cursor agent)

### Debug Log References

### Completion Notes List

- Manager dashboard header: “+ Inviter un membre” (`za-btn--ghost`) opens modal; “+ Nouveau Projet” unchanged when `onCreateProject` is provided.
- Modal: radio roles Transcripteur / Expert, helper text for Expert → LS in story 16.6, `htmlFor` / ids on fields for a11y.
- Tests: default role Transcripteur, Expert branch, no Admin/Manager in copy, API error surface, reopen clears state.

### File List

- `src/frontend/src/features/dashboard/InviteTeamMemberModal.tsx`
- `src/frontend/src/features/dashboard/InviteTeamMemberModal.test.tsx`
- `src/frontend/src/features/dashboard/RoleDashboards.tsx`
- `.bmad-outputs/implementation-artifacts/sprint-status.yaml`
- `.bmad-outputs/implementation-artifacts/16-5-ui-manager-invite-transcripteur-expert.md`

### Review Findings

- [x] [Review][Decision] Success Feedback — Resolved: NotificationProvider is used to show a success toast.
- [x] [Review][Patch] Redundant State Reset — Resolved: Consolidated into resetForm callback and removed redundant finally block.
- [x] [Review][Patch] Unauthenticated API Call Potential — Resolved: Added disabled prop and guard clause for token.
- [x] [Review][Patch] Accessibility: Missing Fieldset for Radios — Resolved: Added fieldset and legend to role selection.
- [x] [Review][Patch] Aggressive autoComplete="off" — Resolved: Removed and verified clean behavior.
- [x] [Review][Patch] Internal Object Allocation — Resolved: Used lazy initializer function for useState.
- [x] [Review][Patch] Race Condition: Close while in-flight — Resolved: handleClose now checks loading state.
- [x] [Review][Patch] Input Sanitation: Missing Trimming — Resolved: Added trim() to all submitted string fields.
- [x] [Review][Defer] Hardcoded Localization [src/frontend/src/features/dashboard/InviteTeamMemberModal.tsx] — deferred, pre-existing pattern
- [x] [Review][Defer] Extensive Inline Styles [src/frontend/src/features/dashboard/InviteTeamMemberModal.tsx] — deferred, pre-existing pattern


---

**Fr (synthèse)** : Implémenter un modal Manager pour créer des comptes **Transcripteur** ou **Expert** via `POST /v1/iam/users`, réutiliser `createUser` et les primitives UI existantes, ne pas toucher à Label Studio (16.6), et ajouter des tests Vitest calqués sur le modal Manager Admin.
