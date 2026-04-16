# Story 6.3: project-closure-golden-set-archival

Status: done

<!-- Ultimate context engine analysis completed - comprehensive developer guide created. -->

## Story
**As the** System,  
**I want** to detect when all audios of a project are Manager-validated and close the project while triggering Golden Set archival orchestration,  
**so that** governance is enforced and downstream archival/flywheel workflows start automatically.

## Acceptance Criteria
1. **Project closure endpoint + RBAC**
   1. Given `POST /v1/projects/{project_id}/close` is called,
   2. Then only project owner Manager (or Admin support role) can close,
   3. And non-owner/non-authorized users are rejected with explicit 403 semantics.

2. **Closure precondition: all audios validated**
   1. Given a project has any audio not in `validated`,
   2. Then closure is rejected with clear conflict semantics,
   3. And response explains project is not yet closure-eligible.

3. **Successful closure transition**
   1. Given all project audios are `validated`,
   2. Then `Project.status` transitions to `completed`,
   3. And response returns stable closure metadata for dashboard refresh.

4. **Camunda archival trigger contract**
   1. Given successful closure,
   2. Then system triggers Camunda process key `golden-set-archival` with project context payload,
   3. And orchestration trigger behavior stays transport-resilient (loggable handoff contract).

5. **Idempotency and lifecycle guardrails**
   1. Given project is already `completed`,
   2. Then repeated close call is idempotent-safe (no duplicate state mutation and no duplicate unintended side effects),
   3. And missing project returns 404.

6. **Story boundary protection**
   1. Story 6.3 must not alter Story 6.1 submit semantics or Story 6.2 validation semantics,
   2. And must not redesign Golden Set ingestion internals beyond the closure handoff trigger.

## Tasks / Subtasks
- [x] **Implement project closure endpoint** (AC: 1, 2, 3, 5)
  - [x] Add/complete `POST /v1/projects/{project_id}/close` in `src/api/fastapi/main.py`.
  - [x] Reuse existing RBAC and ownership helpers (`_require_manager_or_admin`, `_require_project_owner_or_admin`).
  - [x] Resolve project + related audio status view in a consistent SQLAlchemy query path.

- [x] **Enforce closure eligibility and lifecycle transition** (AC: 2, 3, 5)
  - [x] Reject closure when any project audio is not `validated`.
  - [x] Transition `Project.status` to `completed` only when eligible.
  - [x] Handle already completed project with idempotent behavior.
  - [x] Return stable payload with `project_id`, `status`, and closure timestamp/flags as applicable.

- [x] **Trigger Camunda archival handoff** (AC: 4)
  - [x] Trigger Camunda process `golden-set-archival` with required project context.
  - [x] Keep trigger path resilient and observable via structured logs.
  - [x] Avoid introducing unnecessary infrastructure dependencies in this story.

- [x] **Protect regressions and governance boundaries** (AC: 6)
  - [x] Confirm Story 6.1 and 6.2 routes/semantics remain unchanged.
  - [x] Ensure closure logic does not mutate Golden Set ingestion contracts outside scope.
  - [x] Preserve existing API error contract style (`detail: {"error": ...}`).

- [x] **Extend backend tests (red-green-refactor)** (AC: 1-6)
  - [x] Add tests in `src/api/fastapi/test_main.py` for:
    - [x] owner manager successful close when all audios are validated,
    - [x] admin support path,
    - [x] non-owner manager forbidden,
    - [x] invalid role forbidden,
    - [x] missing project 404,
    - [x] conflict when any audio is not validated,
    - [x] idempotent repeat close behavior,
    - [x] Camunda handoff trigger invocation and resilient failure logging behavior.

- [x] **Update API mapping documentation** (AC: 1, 2, 4, 5)
  - [x] Refine `POST /v1/projects/{project_id}/close` in `docs/api-mapping.md` with auth, preconditions, payload, errors, and orchestration handoff contract.

### Review Findings
- [x] [Review][Patch] Prevent Camunda start before durable close commit (split-brain risk) [`src/api/fastapi/main.py`]
- [x] [Review][Patch] Close race can double-trigger archival workflow under concurrent requests [`src/api/fastapi/main.py`]
- [x] [Review][Patch] Restrict broad exception masking in close handoff path to expected Camunda failures [`src/api/fastapi/main.py`]
- [x] [Review][Patch] Align idempotent close response shape with stable contract metadata [`src/api/fastapi/main.py`]
- [x] [Review][Patch] Block lifecycle bypass via legacy `PUT /v1/projects/{project_id}/status` path to `completed` [`src/api/fastapi/main.py`]
- [x] [Review][Patch] Add missing resilience tests (Camunda non-2xx branch and closure edge coverage) [`src/api/fastapi/test_main.py`]

## Dev Notes
### Story foundation and dependencies
- Epic 6 chain: `6.1 submit -> 6.2 manager validation -> 6.3 project close/archive`.
- Story 6.3 depends on Story 6.2 delivering reliable `validated` status on all audios before closure.

### Architecture compliance
- FastAPI remains orchestration layer with strict Keycloak RBAC and SQLAlchemy state transitions.
- Source-of-truth remains PostgreSQL models (`Project`, `AudioFile`, `Assignment`) with no duplicate workflow state store.
- Camunda remains orchestration engine for archival process starts (`golden-set-archival`), using existing REST client patterns.

### Reuse-first guardrails (anti-reinvention)
- Reuse endpoint and guard patterns established in:
  - Story 2.4 manager ownership checks,
  - Story 6.1 submit route lifecycle handling,
  - Story 6.2 validation route error and logging contracts.
- Keep error contracts explicit and consistent with existing `detail.error` semantics.
- Avoid introducing new enum families, new persistence tables, or broad BPMN redesign unless strictly required by closure trigger.

### File structure requirements (expected touchpoints)
- `src/api/fastapi/main.py`
- `src/api/fastapi/test_main.py`
- `docs/api-mapping.md`
- `.bmad-outputs/implementation-artifacts/6-3-project-closure-golden-set-archival.md`
- `.bmad-outputs/implementation-artifacts/sprint-status.yaml`

### Testing requirements
- Keep tests deterministic and mock-driven in current backend style.
- Validate both happy path and protection edges (403/404/409 + idempotency).
- Validate closure precondition against mixed audio states.
- Validate Camunda handoff contract invocation and failure-tolerant behavior.

### Previous story intelligence (6.2)
- Story 6.2 hardened lifecycle correctness with race-safe status transition and strict guardrails.
- Story 6.3 should preserve that quality bar for state integrity and observability.
- Story 6.2 introduced privacy-safe notification logs; closure logs should follow metadata-only principles.

### Git intelligence summary
- Recent commits in this area favor explicit edge-case tests and conservative lifecycle transitions.
- Reuse established patterns in `main.py` and `test_main.py` rather than introducing parallel abstractions.

### Latest technical information
- Current stack is sufficient (FastAPI, SQLAlchemy, existing Camunda REST client); no new dependency expected.
- Use current Camunda trigger conventions already present for process starts and resilient logging on orchestration boundaries.

### Project context reference
- No `project-context.md` found in repository.
- Authoritative references:
  - `docs/epics-and-stories.md`
  - `docs/prd.md`
  - `docs/architecture.md`
  - `docs/ux-design.md`
  - `docs/api-mapping.md`
  - `.bmad-outputs/implementation-artifacts/6-2-manager-approval-rejection.md`

### References
- [Source: docs/epics-and-stories.md#Epic 6 — Chaîne de Validation & Gouvernance]
- [Source: docs/prd.md#4.5 Chaîne de Validation]
- [Source: docs/architecture.md#3. Modèle de Données Métier (PostgreSQL)]
- [Source: docs/api-mapping.md#3. Gouvernance & Validation]
- [Source: .bmad-outputs/implementation-artifacts/6-2-manager-approval-rejection.md]
- [Source: src/api/fastapi/main.py]
- [Source: src/api/fastapi/test_main.py]

## Dev Agent Record
### Agent Model Used
Cursor agent (create-story) - 2026-03-31
Cursor agent (dev-story) - 2026-03-31

### Debug Log References
- Implemented `POST /v1/projects/{project_id}/close` with owner/Admin RBAC and strict closure eligibility (`all validated`).
- Added idempotent-safe completed-project behavior and stable closure response contract.
- Added resilient Camunda `golden-set-archival` handoff start with structured logging.
- Added Story 6.3 route tests and executed targeted + full FastAPI test suites successfully.

### Completion Notes List
- Story 6.3 context artifact prepared for `dev-story` implementation.
- Closure preconditions, Camunda handoff contract, and lifecycle guardrails extracted from PRD/architecture/epics.
- Implemented governance closure flow: eligible project transitions to `completed` and emits Camunda archival trigger handoff.
- Added protection edges for unauthorized roles, non-owner manager access, missing project, invalid lifecycle, and idempotent replay.
- Updated API mapping contract for `/v1/projects/{project_id}/close` including auth, preconditions, errors, idempotency, and observability.
- Test evidence: `pytest src/api/fastapi/test_main.py -k "project_close or transcription_submit or transcription_validate" -q` (32 passed) and `pytest src/api/fastapi/test_main.py -q` (200 passed).
- Review patch evidence: `pytest src/api/fastapi/test_main.py -k "project_close or update_status or transcription_submit or transcription_validate" -q` (39 passed) and `pytest src/api/fastapi/test_main.py -q` (203 passed).

### File List
- `.bmad-outputs/implementation-artifacts/6-3-project-closure-golden-set-archival.md`
- `src/api/fastapi/main.py`
- `src/api/fastapi/test_main.py`
- `docs/api-mapping.md`
- `.bmad-outputs/implementation-artifacts/sprint-status.yaml`

### Change Log
- 2026-03-31: Implemented Story 6.3 project closure endpoint, Camunda archival handoff, backend tests, and API contract updates; story moved to `review`.
- 2026-03-31: Code review patch set applied (concurrency, idempotent shape, lifecycle bypass guard, resilience tests); story moved to `done`.

---

## Traduction francaise (reference)
**Statut :** `ready-for-dev`

**Histoire :** En tant que Systeme, je veux detecter quand tous les audios d'un projet sont validates par le Manager et declencher la cloture avec orchestration d'archivage Golden Set.

**Points cles :**
1. Endpoint `POST /v1/projects/{project_id}/close` avec RBAC Manager proprietaire/Admin.
2. Precondition stricte: tous les audios du projet en statut `validated`.
3. Transition projet vers `completed` + handoff Camunda `golden-set-archival`.
4. Idempotence, guardrails de cycle de vie, et non-regression des stories 6.1/6.2.
