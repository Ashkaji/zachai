# Story 13.1: Restore failure broadcast (collaborators)

Status: done

<!-- Ultimate context engine analysis completed — comprehensive developer guide created -->

## Story

**As a** collaborator connected to the same document,

**I want** the system to broadcast an explicit **restore failure** to every connected client when a snapshot restore aborts after the collaboration lock is taken,

**So that** nobody mistakes an unlock / “restored” signal for a successful restore.

## Context (Epic 13)

**Epic 13 — L6:** Harden multi-user flows after Epic 12, address perf/UX debt from retros 11–12, and keep integration docs aligned with the real API surface.

**This story:** Closes the gap identified in Story 12.3 review: after `document_locked`, if `_restore_document_from_snapshot_core` raises (integrity mismatch, MinIO error, missing Yjs payload, etc.), the `finally` block still publishes `document_unlocked`, and Hocuspocus maps that to `zachai:document_restored`. Remote users therefore behave as if restore succeeded. FR21 (Epic 13 complement) requires explicit **restore failure semantics** for all clients.

**Cross-story note:** 13.2 (Redis verse cache) and 13.3 (API docs) are independent; this story only touches restore signaling + UI + tests.

## Acceptance Criteria

1. **Given** a restore that **fails after** the Redis lock is acquired and `document_locked` has been published (or would have been seen by clients as “restoring”),
   **when** the server releases the lock and notifies collaborators,
   **then** a **dedicated** Redis / Hocuspocus message is emitted (e.g. `document_restore_failed` on `hocuspocus:signals`, or an equivalent name **documented in code and in this story**) with a **stable JSON payload** that includes: integer **`schema_version`** (start at `1`; bump only on breaking field renames/removals), **`document_id`**, machine-readable **`code`**, and optional short **`message`** (or **`detail`**) for UI copy — see **Payload contract** below.
2. **And** Hocuspocus **fan-out** delivers a **distinct** client-facing stateless type (e.g. `zachai:document_restore_failed`) so it is not confused with `zachai:document_restored`.
3. **And** the **UI** shows an **explicit error** state for remote collaborators (banner, modal, or inline alert — consistent with existing Azure-style patterns in the editor), **not** the same UX as a successful restore (which only clears the restoring overlay).
4. **And** **tests** extend the patterns in `test_story_12_3.py`: cover at least one **failure** path through the shared restore core (or canonical route) asserting that the **failure signal** is published (and ordering relative to `document_unlocked` is defined and tested), aligned with existing mocks for Redis `publish`.

## Tasks / Subtasks

- [x] **Contract & backend** (AC: 1, 4)
  - [x] Define stable payload shape (**`schema_version`**, **`document_id`**, **`code`**, optional **`message`**) and **error codes** (enum or documented string constants), e.g. `INTEGRITY_MISMATCH`, `SNAPSHOT_FETCH_FAILED`, `SNAPSHOT_PAYLOAD_INVALID`, `STORAGE_ERROR`, `AUDIO_NOT_FOUND` — reuse HTTP-oriented cases already raised inside `_restore_document_from_snapshot_core` where possible. Do not put raw MinIO paths or stack traces in `message` (see **Security / UI copy**).
  - [x] In `main.py`, refactor `_restore_document_from_snapshot_core` so the `finally` block can distinguish **success vs failure** (e.g. success flag, or `except` + re-raise with side effect). Publish **`document_restore_failed`** to `hocuspocus:signals` **before** `document_unlocked` when failure occurred after lock was taken; keep existing **`document_unlocked` + lock delete** behavior for all exits.
  - [x] Ensure **no** `reload` signal is sent on failure (already true today — preserve).
- [x] **Hocuspocus** (AC: 2)
  - [x] In `src/collab/hocuspocus/src/index.ts`, subscribe handler for `hocuspocus:signals`: handle new `document_restore_failed` (or chosen name) and `broadcastStateless` a **new** payload type `zachai:document_restore_failed` with the same stable fields the API published.
  - [x] Do **not** map failure cleanup to `zachai:document_restored`; only success path should imply “restored” semantics (current `document_unlocked` → `zachai:document_restored` remains for the **successful** unlock path).
- [x] **Frontend** (AC: 3)
  - [x] In `TranscriptionEditor.tsx`, extend the `hp.on("stateless", …)` handler: on `zachai:document_restore_failed`, clear the “restoring” overlay **and** set a dedicated error state (message from payload or generic fallback).
  - [x] Ensure the **initiator** of restore already sees HTTP errors from `POST /v1/snapshots/{id}/restore`; avoid duplicate noisy toasts if both HTTP error and stateless fire for the same user — follow **Initiator vs stateless deduplication** in Dev Notes.
- [x] **Tests** (AC: 4)
  - [x] Add test(s) in `test_story_12_3.py` (or a new focused module if imports get heavy) mirroring `test_restore_integrity_mismatch_returns_502`: assert `publish` calls include a JSON payload with `document_restore_failed` (or chosen type) **and** assert lock deletion / unlock still occur.
- [x] **Documentation**
  - [x] Document the **stateless message contract** (types + `schema_version` + fields) for integrators: **prefer** a subsection under the existing **Editor & collaboration** (or equivalent) area in `docs/api-mapping.md` (aligned with Story 13.3 structure). Fallback: a short comment block in `main.py` next to `_publish_hocuspocus_signal` / payload helpers. Only add a new file such as `docs/collaboration-signals.md` if it stays small and avoids duplicating `api-mapping.md`.

## Dev Notes

### Problem statement (current behavior)

- `_restore_document_from_snapshot_core` in `main.py` publishes `document_locked`, then runs MinIO + DB work inside `try`, and in **`finally`** always publishes `document_unlocked` and deletes the Redis lock key.
- Hocuspocus maps `document_unlocked` → `zachai:document_restored` (`index.ts` ~322–336).
- On **failure**, remote clients still receive `zachai:document_restored` and clear the restoring overlay as if the document were successfully restored — **incorrect**.

### Intended behavior

- After lock + `document_locked`, if restore **throws** before successful completion: publish a **failure** signal with stable `code`, then publish `document_unlocked` (lock cleanup). Hocuspocus broadcasts **`zachai:document_restore_failed`** so collaborators see **failure**, not success.
- On **success**: keep existing sequence (`document_locked` → … → `_signal_hocuspocus_reload` → … → `document_unlocked` → `zachai:document_restored`).

### Out of scope

- If the request **fails before** the Redis lock is acquired (e.g. `423` “already restoring”) or **before** `document_locked` is published, there is **no** collaborator “restoring” overlay to correct via fan-out; this story does not require a failure broadcast in those paths.

### Payload contract (Redis `hocuspocus:signals` → Hocuspocus → clients)

- **Server message `type`:** `document_restore_failed` (or the single chosen name documented in code).
- **JSON fields (v1):**
  - `schema_version` — integer, use `1` until a breaking change is needed.
  - `document_id` — integer (audio / document id).
  - `code` — machine-readable string for branching and tests (e.g. `INTEGRITY_MISMATCH`).
  - `message` — optional, short user-facing string; may be omitted so the client uses a **generic string per `code`**.
- **Client stateless type:** `zachai:document_restore_failed` with the same fields (forwarded by Hocuspocus).

### Security / UI copy

- Use **`code`** for logic; map to localized or generic copy on the client. Do **not** put MinIO object keys, internal paths, or exception stack traces in Redis payloads or stateless messages.

### Initiator vs stateless deduplication

- The **initiator** already gets the error from **`POST /v1/snapshots/{snapshot_id}/restore`** (HTTP body).
- **Recommended pattern:** while a local restore request is in flight (from click → HTTP response), **ignore** `zachai:document_restore_failed` for the same `document_id` for the error UI only, or show the **HTTP error once** and use stateless only to clear `remoteRestoring` / sync overlay state — avoid duplicate error toasts for the same action. Remote collaborators (no in-flight HTTP) **must** rely on stateless for the failure UX.

### Project structure & files

| Area | Path |
|------|------|
| Restore core + Redis pub | `src/api/fastapi/main.py` (`_restore_document_from_snapshot_core`, `_publish_hocuspocus_signal`) |
| Stateless fan-out | `src/collab/hocuspocus/src/index.ts` (`hocuspocus:signals` handler) |
| Editor UX | `src/frontend/src/editor/TranscriptionEditor.tsx` (`stateless` listener, restoring overlay state) |
| Tests | `src/api/fastapi/test_story_12_3.py` |

### Architecture compliance

- [Source: `docs/architecture.md` — Collaboration / Hocuspocus, edge case “Lock document pendant restauration snapshot”]
- Redis channel **`hocuspocus:signals`** remains the integration point; do not introduce a second channel unless required — extend message `type` values only.
- Preserve **423** behavior on `POST /v1/editor/ticket` when lock is held (`test_editor_ticket_423_when_restore_lock_held`).

### Testing standards

- Follow **`test_story_12_3.py`** patterns: patch `main._redis_client`, `internal_client`, mock DB chain, assert `publish` call strings contain expected JSON fragments.
- Run targeted tests: `pytest src/api/fastapi/test_story_12_3.py -q` (and frontend/unit tests if added).

### Project structure notes

- Align naming with existing signals: `document_locked`, `document_unlocked`, `reload`, `zachai:document_restoring`, `zachai:document_restored`.
- New names should be **grep-friendly** and consistent across Python JSON → Redis → TypeScript → frontend.

### References

- [Source: `.bmad-outputs/planning-artifacts/epics.md` — Epic 13, Story 13.1]
- [Source: `.bmad-outputs/implementation-artifacts/12-3-restauration-securisee-verrouillage-websocket.md` — implementation + deferred “document_restore_failed”]
- [Source: `src/api/fastapi/main.py` — `_restore_document_from_snapshot_core` ~3791–3900]
- [Source: `src/collab/hocuspocus/src/index.ts` — Redis `hocuspocus:signals` ~303–344]
- [Source: `src/frontend/src/editor/TranscriptionEditor.tsx` — `hp.on("stateless", …)`, `setRemoteRestoringBy`, restoring overlay]

---

## Dev Agent Record

### Agent Model Used

_(Cursor agent — implementation session 2026-04-13)_

### Debug Log References

_(none)_

### Completion Notes List

- Implemented `document_restore_failed` on `hocuspocus:signals` with v1 payload (`schema_version`, `document_id`, `code`, optional `message`) via `DocumentRestoreFailureCode` + `_document_restore_failed_signal`; `finally` publishes failure **before** `document_unlocked` when `document_locked` was emitted and an exception occurred.
- Hocuspocus forwards to `zachai:document_restore_failed`; `document_unlocked` still maps only to `zachai:document_restored`.
- Editor: fixed banner + dismiss for remote failures; refs suppress duplicate UX when local HTTP restore already failed or request is in flight.
- Tests: `test_restore_integrity_mismatch_returns_502` asserts ordering and payload; `docs/api-mapping.md` §15 documents stateless contract.

**Notes (FR) :** Signal d’échec explicite avant déverrouillage ; pas de `reload` sur échec ; contrat documenté dans `api-mapping.md` et commentaires `main.py`.

### File List

- `src/api/fastapi/main.py`
- `src/collab/hocuspocus/src/index.ts`
- `src/frontend/src/editor/TranscriptionEditor.tsx`
- `src/api/fastapi/test_story_12_3.py`
- `docs/api-mapping.md` (subsection §15 messages stateless)
- `.bmad-outputs/implementation-artifacts/sprint-status.yaml`

### Change Log

- 2026-04-13 (Story 13-1): Restore failure broadcast for collaborators; Redis/Hocuspocus/frontend + tests + API mapping.

---

## Traduction française (référence)

**En tant que** collaborateur connecté au même document, **je veux** que le système diffuse un **échec de restauration** explicite à tous les clients lorsqu’une restauration abandonne après verrouillage, **afin que** personne ne confonde un déverrouillage avec une restauration réussie.

**Critères d’acceptation :** message dédié sur le canal existant avec payload stable (`schema_version`, `code`, etc.) ; fan-out Hocuspocus distinct de « restauré » ; UI d’erreur explicite pour les collaborateurs distants ; pas de doublon toast initiator/HTTP ; tests alignés sur `test_story_12_3.py`.

### Review Findings

- [ ] [Review][Patch] Risky `BaseException` usage in restore core [src/api/fastapi/main.py:3977]
- [ ] [Review][Patch] Unprotected concurrent publishes in `finally` block [src/api/fastapi/main.py:3982]
- [ ] [Review][Patch] Incomplete `HTTPException.detail` type handling [src/api/fastapi/main.py:3814]
- [ ] [Review][Patch] Stale failure alert on successful restoration [src/frontend/src/editor/TranscriptionEditor.tsx:573]
- [ ] [Review][Patch] Style Debt: Inline styles and hardcoded z-index [src/frontend/src/editor/TranscriptionEditor.tsx:1446]
- [ ] [Review][Patch] Missing `AttributeError` mapping in signal builder [src/api/fastapi/main.py:3843]
- [ ] [Review][Patch] Hardcoded English strings in failure code map [src/frontend/src/editor/TranscriptionEditor.tsx:49]
- [ ] [Review][Patch] Brittle string-matching for error codes [src/api/fastapi/main.py:3825]
- [x] [Review][Defer] Network I/O in `finally` block [src/api/fastapi/main.py:3981] — deferred, pre-existing
- [x] [Review][Defer] Triple fallback in UI rendering [src/frontend/src/editor/TranscriptionEditor.tsx:595] — deferred, pre-existing
- [x] [Review][Defer] Z-index escalation strategy [src/frontend/src/editor/TranscriptionEditor.tsx:1454] — deferred, pre-existing
