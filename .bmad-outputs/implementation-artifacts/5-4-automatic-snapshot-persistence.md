# Story 5.4: automatic-snapshot-persistence

Status: done

<!-- Ultimate context engine analysis completed - comprehensive developer guide created. -->

## Story
**As the** system,  
**I want** to detect editor inactivity and trigger snapshot export (DOCX/JSON) to MinIO automatically,  
**so that** document version history is preserved without manual action.

## Acceptance Criteria
1. **Inactivity-driven trigger (debounced)**
   1. Given collaborative edits are flowing through Hocuspocus/Yjs for a document (`audio_files.id`),
   2. When no Yjs update is received for the configured inactivity window,
   3. Then exactly one snapshot callback is emitted for that idle period (no callback storm),
   4. And any new update resets the timer immediately.

2. **Snapshot callback contract**
   1. Given an inactivity trigger fires,
   2. Then Hocuspocus posts to `POST /v1/editor/callback/snapshot` with authenticated internal-call semantics already used for worker callbacks,
   3. And payload includes `document_id` and `yjs_state_binary` (or equivalent canonical serialized Yjs state),
   4. So downstream export can deterministically rebuild DOCX/JSON.

3. **Export worker pipeline and integrity**
   1. Given FastAPI receives a valid snapshot callback,
   2. Then Export Worker converts and uploads DOCX/JSON under `snapshots/{document_id}/...` in MinIO,
   3. And SHA-256 checksum validation is enforced before finalizing upload,
   4. With retry policy + DLQ behavior on failures (3 retries then admin alert), matching PRD workflow and architecture guardrails.

4. **Non-blocking collaboration**
   1. Given snapshots are asynchronous,
   2. Then editor collaboration latency and write path remain unaffected (target < 50ms perceived sync still holds),
   3. And users continue editing while snapshot work executes in background.

5. **Security and authorization boundaries**
   1. Snapshot callback endpoint is not publicly callable by regular users,
   2. Internal auth/secret validation is required,
   3. Snapshot objects are written only to project-scoped MinIO snapshot paths and never expose raw internal credentials.

6. **Observability and failure handling**
   1. Success/failure events are logged with document id, snapshot id/version, and timing,
   2. Failures are visible for operations/debugging (including DLQ path),
   3. Repeated callback failures do not crash Hocuspocus or block ongoing sessions.

7. **Restore safety prerequisite (forward compatibility)**
   1. Snapshot metadata is stored in a way that supports Story 5.x history/restore UX timeline,
   2. And concurrent restore safety requirement remains enforceable (document lock during restore per architecture edge-case note).

8. **Out of scope (explicit)**
   1. UI timeline/preview/restore interactions stay in subsequent story scope.
   2. Real-time grammar check remains Story 5.5.

## Tasks / Subtasks
- [x] **Hocuspocus idle detection + callback emission** (AC: 1, 2, 4, 6)
  - [x] Implement/update debounced inactivity logic on document updates (respecting reset-on-update semantics).
  - [x] Ensure callback dispatch is idempotent per idle window (no duplicate fire while one is in-flight for same window).
  - [x] Serialize canonical Yjs state for callback payload.

- [x] **FastAPI snapshot callback hardening** (AC: 2, 5, 6)
  - [x] Verify `POST /v1/editor/callback/snapshot` contract and internal auth check in `src/api/fastapi/main.py` (or routed module).
  - [x] Validate payload shape and reject malformed/oversized submissions with explicit status codes.
  - [x] Add structured logging and correlation fields for snapshot processing.

- [x] **Export Worker conversion + MinIO upload** (AC: 3, 6)
  - [x] Implement DOCX and JSON generation from Yjs state in worker pipeline.
  - [x] Compute/verify SHA-256 checksum before upload finalization.
  - [x] Write outputs to `snapshots/{document_id}/` with deterministic naming/versioning.
  - [x] Implement retry and DLQ escalation (3 retries then admin alert).

- [x] **Snapshot metadata persistence** (AC: 7)
  - [x] Persist metadata required for future history timeline and restore operations (timestamp, object keys, checksum, size, origin).
  - [x] Keep schema/design aligned with existing PostgreSQL conventions and avoid parallel, incompatible storage models.

- [x] **Docs and operations updates** (AC: 2, 3, 5, 6)
  - [x] Update `docs/api-mapping.md` for snapshot callback auth, payload, and errors.
  - [x] Update runbook/readme sections for snapshot worker env vars and failure triage.

- [x] **Automated tests** (AC: 1-6)
  - [x] Backend tests for callback auth, payload validation, and error paths.
  - [x] Worker tests for checksum verification, retry/DLQ behavior, and MinIO key placement.
  - [x] Collaboration-side test (or deterministic integration harness) validating debounce/reset behavior and single callback per idle window.

### Review Findings

- [x] [Review][Defer] **DLQ escalation vs explicit admin alert** — deferred, pre-existing. Explicit operator alert channel (pager/webhook/metrics) is deferred to a dedicated ops-observability story; current ERROR+DLQ visibility is sufficient for Story 5.4 scope.

- [x] [Review][Patch] **Harden `SNAPSHOT_IDLE_MS` parsing** [`src/collab/hocuspocus/src/index.ts` (SNAPSHOT_IDLE_MS)] — fixed with bounded parsing and safe fallback.

- [x] [Review][Patch] **Clean up idle snapshot state on document unload** [`src/collab/hocuspocus/src/index.ts`, `snapshotScheduler.ts`] — fixed with `afterUnloadDocument` cleanup plus scheduler `purge(documentId)`.

## Dev Notes
### Story foundation and dependencies
- Epic 5 objective: sovereign collaborative editor with robust persistence and history.
- Direct dependency chain: Story 5.1 (Hocuspocus/Yjs collaboration) and Story 5.3 (audio-text sync completed) already established the core editor runtime.
- Story 5.4 must extend existing collaboration infrastructure; do not introduce a second persistence channel that conflicts with current Hocuspocus/PostgreSQL model.

### Relevant architecture requirements
- `docs/architecture.md` defines asynchronous snapshot engine: Hocuspocus webhook to Export Worker, upload to MinIO `snapshots/`, checksum validation required.
- Collaboration persistence exists via PostgreSQL (`YjsLog`); snapshot generation is an asynchronous export concern, not a replacement for Yjs durability.
- Known edge case in architecture: editing during inactivity/snapshot requires debounce timer reset on every update.

### Reuse-first guardrails (anti-reinvention)
- Reuse existing internal callback authentication patterns from current FastAPI worker callbacks.
- Reuse existing MinIO client/presigned/upload utilities and error taxonomy where available.
- Reuse current Redis/PostgreSQL connection and logging conventions; avoid introducing new infrastructure unless required.

### File structure requirements (expected touchpoints)
- `src/collab/hocuspocus/src/index.ts` (or adjacent Hocuspocus service modules)
- `src/api/fastapi/main.py` plus existing callback helpers/modules
- Export worker service files under current worker directory used for document export
- `docs/api-mapping.md` and relevant operator docs/README

### Testing requirements
- Preserve collaboration behavior under load; snapshot logic must not mutate shared editor document state in a way that causes extra Yjs churn.
- Add regression coverage for:
  - duplicate callback prevention in idle windows,
  - retry and DLQ path,
  - checksum failure handling,
  - malformed callback payload rejection.

### Previous story intelligence (from 5.3)
- 5.3 enforced "no CRDT mutation for presentation-only behavior"; same principle applies here: snapshot triggering must not interfere with editor state updates.
- Recent commits show emphasis on reconnect resilience and test hardening; follow same quality bar for retry boundaries and deterministic tests.

### Git intelligence summary
- Recent branch history centers on Story 5.3 completion and reconnect-policy robustness.
- Keep commit-level patterns: explicit edge-case tests, conservative behavior under transient failures, and docs parity for API contracts.

### Latest technical information
- Hocuspocus persistence guidance favors debounced store hooks and queueing store operations to avoid concurrent store races.
- Yjs best practice remains binary update/state handling (`Uint8Array`) and periodic consolidation strategies for storage efficiency.

### Project context reference
- No dedicated `project-context.md` detected; authoritative references are:
  - `docs/epics-and-stories.md`
  - `docs/prd.md`
  - `docs/architecture.md`
  - `docs/ux-design.md`
  - `docs/api-mapping.md`

## Dev Agent Record
### Agent Model Used
Cursor agent (implementation) - 2026-03-30

### Debug Log References
- `npm test` in `src/collab/hocuspocus`
- `py -3.14 -m pytest test_main.py -q` in `src/api/fastapi`
- `py -3.14 -m pytest test_main.py -q` in `src/workers/export-worker`

### Completion Notes List
- Added debounced idle snapshot scheduling in Hocuspocus with in-flight guarding and callback dispatch to FastAPI.
- Implemented secured FastAPI `POST /v1/editor/callback/snapshot` endpoint with base64 payload validation, export-worker forwarding, structured logs, and metadata persistence to `snapshot_artifacts`.
- Added new `src/workers/export-worker` service for DOCX/JSON snapshot generation, MinIO upload with SHA-256 metadata verification, deterministic object naming, retries, and DLQ fallback.
- Added regression tests for snapshot callback path (FastAPI), export worker retry/DLQ behavior, and collaboration scheduler debounce semantics.
- Updated compose/env/docs for snapshot pipeline operations (`SNAPSHOT_*`, `EXPORT_WORKER_*`) and exported service health endpoint.

### File List
- `.bmad-outputs/implementation-artifacts/5-4-automatic-snapshot-persistence.md`
- `.bmad-outputs/implementation-artifacts/sprint-status.yaml`
- `README.md`
- `docs/api-mapping.md`
- `src/.env.example`
- `src/api/fastapi/main.py`
- `src/api/fastapi/test_main.py`
- `src/collab/hocuspocus/package.json`
- `src/collab/hocuspocus/src/index.ts`
- `src/collab/hocuspocus/src/snapshotScheduler.ts`
- `src/collab/hocuspocus/src/snapshotScheduler.test.ts`
- `src/compose.yml`
- `src/workers/export-worker/Dockerfile`
- `src/workers/export-worker/main.py`
- `src/workers/export-worker/requirements.txt`
- `src/workers/export-worker/test_main.py`

### Change Log
- 2026-03-30: Implemented Story 5.4 end-to-end snapshot persistence pipeline (Hocuspocus inactivity callback, FastAPI callback hardening, export-worker conversion/upload with checksum + retry/DLQ, metadata persistence, docs/env/compose updates, and automated tests).
- 2026-03-30: Code review follow-ups — safe `SNAPSHOT_IDLE_MS` parsing, snapshot scheduler `purge()` + `afterUnloadDocument` cleanup, extra scheduler unit test; alerting transport deferred to ops-observability story (documented in `deferred-work.md`).

---

## Traduction francaise (reference)
**Statut :** `done`

**Histoire :** En tant que systeme, je veux detecter l'inactivite d'edition et declencher automatiquement un export snapshot (DOCX/JSON) vers MinIO, afin de conserver l'historique des versions sans intervention manuelle.

**Points clés :**
1. Debounce/reset strict sur chaque update Yjs pour eviter les storms de callbacks.
2. Webhook snapshot interne authentifie vers `POST /v1/editor/callback/snapshot`.
3. Export Worker asynchrone avec verification SHA-256, retries et DLQ.
4. Aucun impact sur la latence de collaboration ni blocage de l'edition en cours.
5. Metadonnees snapshot persistantes pour supporter la timeline/restauration future.

