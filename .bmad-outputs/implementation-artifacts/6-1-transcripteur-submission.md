# Story 6.1: transcripteur-submission

Status: review

<!-- Ultimate context engine analysis completed - comprehensive developer guide created. -->

## Story
**As a** Transcripteur,  
**I want** to submit my completed transcription from the editor workflow,  
**so that** the assigned audio status moves to `transcribed` and the Manager can review it.

## Acceptance Criteria
1. **Submit endpoint and access control**
   1. Given `POST /v1/transcriptions/{audio_id}/submit` is called,
   2. Then only the assigned Transcripteur for that `audio_id` (or Admin for support) can submit,
   3. And unauthorized role or non-assigned user is rejected with explicit 403 semantics.

2. **State transition and assignment timestamp**
   1. Given a valid submission on an eligible audio,
   2. Then `AudioFile.status` transitions to `transcribed`,
   3. And `Assignment.submitted_at` is set once (idempotent-safe behavior on repeats),
   4. And existing `manager_validated_at` is not incorrectly modified.

3. **Eligibility guardrails**
   1. Submission is accepted only when the audio belongs to an active assignment lifecycle (`assigned` or `in_progress`),
   2. And submission is rejected for invalid lifecycle states (for example `uploaded`, `validated`) with clear 409/400 behavior,
   3. And `404` is returned when audio/assignment is missing.

4. **Manager notification contract**
   1. Given a successful submission,
   2. Then the system emits a notification event/log payload that manager-facing flows can consume,
   3. And the response contract explicitly reports success and resulting status for dashboard refresh.

5. **Dashboard/task visibility consistency**
   1. After submission, manager views relying on `audio_counts_by_status` include the incremented `transcribed` count,
   2. And transcripteur task list no longer treats the item as editable work-in-progress.

6. **No regression to existing editor correction flow**
   1. Existing Story 4.2 correction ingestion guardrail remains coherent: once status is `transcribed`, `POST /v1/golden-set/frontend-correction` still returns conflict behavior as currently tested.

## Tasks / Subtasks
- [x] **Implement submission API route** (AC: 1, 2, 3, 4)
  - [x] Add `POST /v1/transcriptions/{audio_id}/submit` in `src/api/fastapi/main.py`.
  - [x] Reuse `get_current_user`, `get_roles`, and assignment ownership checks already used in dashboard/editor routes.
  - [x] Resolve target audio with assignment in one query pattern consistent with current SQLAlchemy style (`select(...).where(...).options(...)`).
  - [x] Enforce role/user checks: assigned Transcripteur or Admin.

- [x] **Apply lifecycle transition and idempotency behavior** (AC: 2, 3)
  - [x] Allow transition from `assigned|in_progress` to `transcribed`.
  - [x] Set `Assignment.submitted_at` on first successful submit; preserve existing value on repeats.
  - [x] Return stable response payload including `audio_id`, `status`, `submitted_at`, and `idempotent` flag.
  - [x] Keep `manager_validated_at` untouched.

- [x] **Add notification hook/log contract** (AC: 4)
  - [x] Emit structured log event for manager notification handoff (audio, project, transcripteur, timestamp).
  - [x] Keep implementation transport-agnostic (no new infra dependency required in this story).

- [x] **Align dashboard/task query semantics** (AC: 5)
  - [x] Verify no code change required for project counts (`transcribed` already aggregated); if needed, patch response builders.
  - [x] Ensure `GET /v1/me/audio-tasks` behavior remains coherent for submitted work state.

- [x] **Extend automated backend tests** (AC: 1-6)
  - [x] Add tests in `src/api/fastapi/test_main.py` for:
    - [x] success submit by assigned transcripteur,
    - [x] 403 for non-assigned transcripteur/invalid role,
    - [x] 404 for missing audio/assignment,
    - [x] conflict/validation for invalid source status,
    - [x] idempotent repeat submit behavior,
    - [x] regression check that frontend-correction conflict remains true after submit.

- [x] **Update API docs** (AC: 1, 3, 4)
  - [x] Confirm and refine the existing section in `docs/api-mapping.md` for `POST /v1/transcriptions/{audio_id}/submit` with exact status-code semantics and response shape.

## Dev Notes
### Story foundation and dependencies
- Epic 6 defines the validation chain: Transcripteur submission first, then Manager approval/rejection (Story 6.2), then project closure (Story 6.3).
- This story is the entry point to governance workflow and must preserve current Epic 2 dashboard assumptions.

### Architecture compliance
- FastAPI remains a lean orchestrator with RBAC gatekeeping; do not introduce direct DB bypass or new side-channel state stores.
- Use existing SQLAlchemy models `AudioFile`, `Assignment`, and `AudioFileStatus`.
- Respect existing lifecycle meaning: `transcribed` is a human-workflow state, not a processing state.

### Reuse-first guardrails (anti-reinvention)
- Reuse existing auth helper patterns used in:
  - assignment dashboard routes (`/v1/projects/{project_id}/assign`, `/v1/me/audio-tasks`),
  - editor/media authorization patterns,
  - golden-set correction guardrails that already rely on status transitions.
- Do not add new enums or duplicate status systems; extend current route layer only.

### File structure requirements (expected touchpoints)
- `src/api/fastapi/main.py`
- `src/api/fastapi/test_main.py`
- `docs/api-mapping.md` (if contract detail needs update)
- `.bmad-outputs/implementation-artifacts/6-1-transcripteur-submission.md` (this story file)

### Testing requirements
- Keep tests deterministic with current async test conventions in `test_main.py`.
- Validate both positive path and protection edges (403/404/409).
- Validate that submission does not break Story 4.2 expected conflict on further correction submissions.

### Git intelligence summary
- Recent changes emphasize robust edge-case handling and test hardening in `src/api/fastapi/main.py` + `test_main.py`.
- Follow same pattern: explicit errors, bounded behavior, and contract-focused tests.

### Latest technical information
- No external library upgrade is required for this story; use current FastAPI/SQLAlchemy stack already present in repo.
- Preserve existing API error semantics conventions used across endpoints (`detail: {"error": ...}` style).

### Project context reference
- No `project-context.md` was found in this repository.
- Authoritative references used:
  - `docs/epics-and-stories.md`
  - `docs/prd.md`
  - `docs/architecture.md`
  - `docs/ux-design.md`
  - `docs/api-mapping.md`

### References
- [Source: docs/epics-and-stories.md#Epic 6 — Chaîne de Validation & Gouvernance]
- [Source: docs/prd.md#4.3 Workflow de Transcription (Frontend Tiptap)]
- [Source: docs/prd.md#4.5 Chaîne de Validation]
- [Source: docs/architecture.md#3. Modèle de Données Métier (PostgreSQL)]
- [Source: docs/api-mapping.md#3. Gouvernance & Validation]
- [Source: src/api/fastapi/main.py]
- [Source: src/api/fastapi/test_main.py]

## Dev Agent Record
### Agent Model Used
Cursor agent (implementation) - 2026-03-31

### Debug Log References
- `python -m pytest "src/api/fastapi/test_main.py" -k "transcription_submit" -q`
- `python -m pytest "src/api/fastapi/test_main.py" -q`

### Completion Notes List
- Added `POST /v1/transcriptions/{audio_id}/submit` with JWT role gate (`Transcripteur|Admin`), assignment ownership checks, and consistent `detail.error` responses.
- Implemented lifecycle transition `assigned|in_progress -> transcribed`, first-write `submitted_at`, and idempotent replay behavior for already submitted transcriptions.
- Added structured manager handoff log event (`transcription_submitted ... manager_notification_handoff=queued`) without introducing new infrastructure dependencies.
- Added Story 6.1 backend tests covering happy path, admin bypass, wrong user/role, missing audio/assignment, invalid lifecycle status, and idempotent repeat.
- Verified existing Story 4.2 regression check remains valid for corrections after submit (`transcribed` returns 409 on frontend-correction route).

### File List
- `.bmad-outputs/implementation-artifacts/6-1-transcripteur-submission.md`
- `.bmad-outputs/implementation-artifacts/sprint-status.yaml`
- `docs/api-mapping.md`
- `src/api/fastapi/main.py`
- `src/api/fastapi/test_main.py`

### Change Log
- 2026-03-31: Implemented Story 6.1 submission endpoint, added full backend test coverage, updated API contract docs, and prepared story for review.

---

## Traduction francaise (reference)
**Statut :** `ready-for-dev`

**Histoire :** En tant que Transcripteur, je veux soumettre ma transcription terminee pour qu'elle passe au statut `transcribed` et qu'un Manager puisse lancer la revue qualite.

**Points cles :**
1. Endpoint `POST /v1/transcriptions/{audio_id}/submit` avec controle strict d'assignation.
2. Transition d'etat vers `transcribed` + horodatage `submitted_at`.
3. Garde-fous lifecycle et erreurs explicites (403/404/409).
4. Coherence dashboard/taches et non-regression du flux Golden Set deja en place.
