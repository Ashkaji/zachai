# Story 6.2: manager-approval-rejection

Status: done

<!-- Ultimate context engine analysis completed - comprehensive developer guide created. -->

## Story
**As a** Manager,  
**I want** to review a submitted transcription and approve or reject it with a comment,  
**so that** transcription quality is controlled before project closure and Golden Set archival.

## Acceptance Criteria
1. **Manager validation endpoint + RBAC**
   1. Given `POST /v1/transcriptions/{audio_id}/validate` is called,
   2. Then only the project owner Manager (or Admin support role) can perform validation,
   3. And non-owner/non-authorized users are rejected with explicit 403 semantics.

2. **Approval path**
   1. Given `approved = true` on an eligible audio,
   2. Then `AudioFile.status` transitions from `transcribed` to `validated`,
   3. And `Assignment.manager_validated_at` is set,
   4. And response returns final status and validation metadata for dashboard refresh.

3. **Rejection path with mandatory comment**
   1. Given `approved = false`,
   2. Then a non-empty `comment` is required,
   3. And `AudioFile.status` transitions to a rework state consistent with existing lifecycle (`assigned`),
   4. And the payload/response preserves the rejection comment for transcripteur feedback.

4. **Eligibility and lifecycle guardrails**
   1. Validation/rejection is accepted only when audio is currently `transcribed`,
   2. And non-eligible states (`uploaded`, `assigned`, `in_progress`, `validated`) are rejected with clear conflict semantics,
   3. And missing audio/assignment returns 404.

5. **Consistency with Story 6.1 and dashboard counts**
   1. Story 6.1 submit behavior remains the prerequisite (`transcribed` before manager action),
   2. And aggregate status views remain coherent (`transcribed` decreases when validated/rejected; `validated` increases on approval).

6. **Notification handoff contract**
   1. Given either approval or rejection,
   2. Then system emits a structured notification handoff event/log for transcripteur-facing feedback (transport-agnostic),
   3. And no extra infrastructure dependency is required in this story.

7. **Out of scope (explicit)**
   1. Project close/archival trigger logic (`/v1/projects/{project_id}/close`) belongs to Story 6.3.
   2. Golden Set archival process orchestration remains unchanged in this story.

## Tasks / Subtasks
- [x] **Implement manager validation endpoint** (AC: 1, 2, 3, 4, 6)
  - [x] Add/complete `POST /v1/transcriptions/{audio_id}/validate` in `src/api/fastapi/main.py`.
  - [x] Reuse existing RBAC and project ownership patterns (`_require_project_owner_or_admin`, role checks, assignment joins).
  - [x] Resolve audio + assignment + project in one consistent query path (`select(...).options(...)` style).

- [x] **Apply lifecycle transitions and validation metadata** (AC: 2, 3, 4, 5)
  - [x] Enforce source status `transcribed` for manager action.
  - [x] Approval: set `AudioFile.status = validated` and set `Assignment.manager_validated_at`.
  - [x] Rejection: require non-empty comment and set rework target status (`assigned`) for transcripteur loop.
  - [x] Return stable response payload with `audio_id`, `status`, `approved`, `comment`, and validation timestamp fields.

- [x] **Add validation/rejection notification handoff logs** (AC: 6)
  - [x] Emit structured logs for approval and rejection outcomes (audio, project, manager, assignee, result).
  - [x] Keep notification implementation transport-agnostic; no new queue/service introduced.

- [x] **Protect regressions and status coherence** (AC: 5, 7)
  - [x] Confirm Story 6.1 submit path remains unchanged and required upstream.
  - [x] Ensure dashboard/task views remain status-consistent after approval and rejection.
  - [x] Do not implement project closure logic in this story.

- [x] **Extend backend tests (red-green-refactor)** (AC: 1-6)
  - [x] Add tests in `src/api/fastapi/test_main.py` for:
    - [x] manager owner approval success,
    - [x] manager rejection requires comment,
    - [x] non-owner manager forbidden,
    - [x] admin support path,
    - [x] missing audio/assignment 404,
    - [x] invalid source status conflict,
    - [x] status transition and timestamp assertions (`validated`, `manager_validated_at`),
    - [x] rejection transition assertion (`assigned`) and comment echo.

- [x] **Update API mapping documentation** (AC: 1, 3, 4, 6)
  - [x] Refine `POST /v1/transcriptions/{audio_id}/validate` in `docs/api-mapping.md` with exact auth, body contract, errors, and status transitions.

### Review Findings
- [x] [Review][Patch] Clear stale `manager_validated_at` on rejection and prevent contradictory metadata [`src/api/fastapi/main.py`]
- [x] [Review][Patch] Make validation transition concurrency-safe with conditional status update [`src/api/fastapi/main.py`]
- [x] [Review][Patch] Reset `submitted_at` during rejection loop and refresh it on each submit cycle [`src/api/fastapi/main.py`]
- [x] [Review][Patch] Align API mapping with implemented 400 rejection-comment validation error [`docs/api-mapping.md`]
- [x] [Review][Patch] Avoid logging raw rejection comment text in handoff logs [`src/api/fastapi/main.py`]
- [x] [Review][Patch] Extend Story 6.2 test coverage for RBAC/token/project-state/concurrency/logging edges [`src/api/fastapi/test_main.py`]

## Dev Notes
### Story foundation and dependencies
- Epic 6 chain: `6.1 submit -> 6.2 manager validation -> 6.3 project close/archive`.
- Story 6.2 strictly depends on Story 6.1 creating `transcribed` state and preserving assignment ownership.

### Architecture compliance
- FastAPI remains the workflow controller with strict Keycloak role checks and SQLAlchemy lifecycle updates.
- Keep source-of-truth in PostgreSQL models (`AudioFile`, `Assignment`, `Project`) without duplicate state layers.
- Preserve lifecycle semantics from PRD/API mapping: manager action happens only after transcripteur submission.

### Reuse-first guardrails (anti-reinvention)
- Reuse endpoint patterns already present in:
  - `POST /v1/transcriptions/{audio_id}/submit` (Story 6.1),
  - assignment/project owner guardrails from Story 2.4 routes,
  - consistent `detail: {"error": ...}` API error shape.
- Avoid introducing new enums/tables unless unavoidable; use existing statuses and fields.

### File structure requirements (expected touchpoints)
- `src/api/fastapi/main.py`
- `src/api/fastapi/test_main.py`
- `docs/api-mapping.md`
- `.bmad-outputs/implementation-artifacts/6-2-manager-approval-rejection.md`

### Testing requirements
- Keep tests deterministic and mock-driven in current backend style.
- Validate both approval and rejection branch behavior.
- Validate ownership and role enforcement paths (`Manager owner`, `Manager non-owner`, `Admin`).
- Validate lifecycle gate (`transcribed` only), and explicit conflict semantics outside that state.

### Previous story intelligence (6.1)
- 6.1 established submit endpoint, idempotency, and structured manager handoff logs.
- 6.2 should mirror this quality bar for explicit branch handling and response contract stability.

### Git intelligence summary
- Recent API work favors explicit edge-case tests and conservative status transitions.
- Keep implementation narrowly scoped to story tasks; no speculative workflow expansion.

### Latest technical information
- No additional dependency is needed; current FastAPI/SQLAlchemy/testing stack is sufficient.
- Continue existing logging/metrics style for workflow handoff observability.

### Project context reference
- No `project-context.md` found in repository.
- Authoritative references:
  - `docs/epics-and-stories.md`
  - `docs/prd.md`
  - `docs/architecture.md`
  - `docs/ux-design.md`
  - `docs/api-mapping.md`
  - `.bmad-outputs/implementation-artifacts/6-1-transcripteur-submission.md`

### References
- [Source: docs/epics-and-stories.md#Epic 6 — Chaîne de Validation & Gouvernance]
- [Source: docs/prd.md#4.5 Chaîne de Validation]
- [Source: docs/architecture.md#3. Modèle de Données Métier (PostgreSQL)]
- [Source: docs/api-mapping.md#3. Gouvernance & Validation]
- [Source: .bmad-outputs/implementation-artifacts/6-1-transcripteur-submission.md]
- [Source: src/api/fastapi/main.py]
- [Source: src/api/fastapi/test_main.py]

## Dev Agent Record
### Agent Model Used
Cursor agent (create-story) - 2026-03-31
Cursor agent (dev-story) - 2026-03-31

### Debug Log References
- Implemented `POST /v1/transcriptions/{audio_id}/validate` with owner/Admin RBAC and status guard (`transcribed` only).
- Added approval/rejection branches with `manager_validated_at` handling and rejection comment requirement.
- Added structured notification handoff log for both outcomes.
- Added Story 6.2 backend tests; executed targeted and full FastAPI test suites successfully.
- Applied code-review patch set: concurrency-safe transition, stale metadata reset on rejection, submit-cycle timestamp refresh, and privacy-safe logging payload.

### Completion Notes List
- Story 6.2 context artifact prepared for `dev-story` implementation.
- Completed manager validation endpoint with explicit 401/403/404/409 semantics and stable response contract.
- Approval path now transitions `transcribed -> validated` and stamps `Assignment.manager_validated_at`.
- Rejection path now enforces non-empty comment and transitions back to `assigned` for rework loop.
- Added regression tests for owner/admin authorization, non-owner rejection, lifecycle conflicts, missing resources, and rejection comment handling.
- Updated API mapping documentation for Story 6.2 contract details and transport-agnostic notification handoff semantics.
- Test evidence: `pytest src/api/fastapi/test_main.py -k "transcription_submit or transcription_validate" -q` (16 passed) and `pytest src/api/fastapi/test_main.py -q` (184 passed).
- Review patch validation: `pytest src/api/fastapi/test_main.py -k "transcription_submit or transcription_validate" -q` (24 passed) and `pytest src/api/fastapi/test_main.py -q` (192 passed).

### File List
- `.bmad-outputs/implementation-artifacts/6-2-manager-approval-rejection.md`
- `src/api/fastapi/main.py`
- `src/api/fastapi/test_main.py`
- `docs/api-mapping.md`
- `.bmad-outputs/implementation-artifacts/sprint-status.yaml`

### Change Log
- 2026-03-31: Implemented Story 6.2 manager approval/rejection endpoint, tests, and API mapping updates; story moved to `review`.
- 2026-03-31: Code review patches applied and verified; Story 6.2 moved to `done`.

---

## Traduction francaise (reference)
**Statut :** `ready-for-dev`

**Histoire :** En tant que Manager, je veux approuver ou rejeter une transcription soumise avec commentaire, afin d'assurer le controle qualite avant la cloture du projet.

**Points cles :**
1. Endpoint manager `POST /v1/transcriptions/{audio_id}/validate` avec RBAC strict.
2. Approbation: `transcribed -> validated` + `manager_validated_at`.
3. Rejet: commentaire obligatoire + retour en statut de reprise pour le transcripteur.
4. Cohérence des statuts dashboard et non-regression de la chaine 6.1 -> 6.2.
