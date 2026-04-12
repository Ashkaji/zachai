# Story 12.3: Restauration Sécurisée avec Verrou de Concurrence

Status: done

## Story
**As a User**, I want to restore a document snapshot safely so that I can revert mistakes or recover previous versions without worrying about concurrent edits corrupting the state.

## Acceptance Criteria

### 1. Restoration API with Concurrency Lock
- [x] **POST /v1/snapshots/{snapshot_id}/restore**: Trigger the restoration process:
    - **Step 1: Check Auth**: User must have `write` access to the project.
    - **Step 2: Set Lock**: Create a Redis key `lock:document:{doc_id}:restoring` with a TTL of 60s.
    - **Step 3: Signal Collaboration**: Broadcast a "Document Locked" message to all connected clients (via Hocuspocus/Yjs Awareness or a dedicated Redis Pub/Sub channel).
    - **Step 4: Swap Yjs State**:
        - Fetch the Yjs binary from the snapshot in MinIO.
        - Replace the latest state in the `yjs_logs` table (or append as a new authoritative snapshot).
    - **Step 5: Flush Hocuspocus Cache**: Signal the Hocuspocus server to reload the document state from the database.
    - **Step 6: Release Lock**: Delete the Redis key.
- [x] **Conflict Prevention**: Any `POST /v1/editor/ticket` or Hocuspocus `onUpdate` hook MUST check for the presence of the lock key and reject operations with a 423 (Locked) status or equivalent.

### 2. UI: Restoration Workflow
- [x] **Restore Button**: Add a "Restore this version" button in the History side panel (visible only when a snapshot is selected).
- [x] **Confirmation Modal**: Before restoring, show a "Danger Zone" modal:
    - "This will overwrite all current changes. This action cannot be undone (except by another restore)."
- [x] **Locking State UI**: While restoration is in progress, all users connected to the document should see a "Document being restored by [User Name]..." overlay, blocking all inputs.

### 3. Verification & Integrity
- [x] **State Integrity**: Verify that after restoration, the document exactly matches the snapshot state.
- [x] **Collaborator Reconnect**: Ensure all users are automatically re-synced with the new state after the lock is released.

## Tasks / Subtasks

- [x] **Task 1: Redis Locking Logic**
  - [x] Implement the locking/unlocking utility in FastAPI.
  - [x] Integrate lock check in `onAuthenticate` or a custom Hocuspocus hook.
- [x] **Task 2: Restoration Implementation**
  - [x] Implement the `POST /v1/snapshots/{snapshot_id}/restore` endpoint.
  - [x] Implement the state swap logic in PostgreSQL.
- [x] **Task 3: Frontend Restoration UI**
  - [x] Add the "Restore" button and its confirmation modal.
  - [x] Implement the "Locked" overlay in the editor.
- [x] **Task 4: Resilience Test**
  - [x] Simulate a concurrent edit during restoration and verify it is blocked.

### Review Findings

- [x] [Review][Patch] Expand automated tests for canonical restore and integrity failure — `test_story_12_3.py` should cover `POST /v1/snapshots/{snapshot_id}/restore` (e.g. import/call `restore_snapshot_by_id`) and assert that SHA-256 mismatch against `SnapshotArtifact.yjs_sha256` yields HTTP 502, so the primary API and integrity checks stay guarded. [`src/api/fastapi/test_story_12_3.py`]
- [x] [Review][Defer] Remote collaborators only see lock/unlock stateless messages — if restore fails after the lock is taken, `document_unlocked` still runs and clients may assume success; only the caller receives the HTTP error. Consider a future `document_restore_failed` (or similar) broadcast. [`src/api/fastapi/main.py` ~3876–3878] — deferred, product enhancement

## Dev Notes
- Use `REDIS_URL` for the lock storage.
- The state swap should be wrapped in a transaction.
- Hocuspocus reload: You might need to disconnect users to force a full re-sync if Hocuspocus doesn't support hot-reloading state from the database via a simple signal.

## References
- **Architecture**: `docs/architecture.md` (§7 Points d'Attention - Edge Cases).
- **UX Design**: `docs/ux-design.md` (§7.3 Restauration).
- **Existing Logic**: `src/api/fastapi/main.py` (`YjsLog` and `SnapshotArtifact`).

---

## Dev Agent Record

### Implementation Plan
- Centralized restore in `_restore_document_from_snapshot_core`: Redis lock (60s), `document_locked` / `document_unlocked` on `hocuspocus:signals`, MinIO Yjs fetch, SHA-256 integrity check against `SnapshotArtifact.yjs_sha256`, transactional `yjs_logs` replace, audit log, `reload` signal, lock delete in `finally`.
- Canonical route `POST /v1/snapshots/{snapshot_id}/restore`; legacy `POST /v1/editor/restore/{audio_id}` preserved.
- Hocuspocus: Redis handler broadcasts `zachai:document_restoring` / `zachai:document_restored` via `broadcastStateless` to all connections in the room.
- Frontend: `HocuspocusProvider` `stateless` listener + overlay; restore uses canonical snapshot path; Danger Zone copy per AC.

### Debug Log
- (none)

### Completion Notes
- **English:** Story 12.3 is implemented end-to-end: Redis lock + pub/sub collaboration signals, Hocuspocus stateless fan-out, `423` on ticket when locked, integrity hash on snapshot bytes, UI restore flow with shared overlay for all collaborators.
- **Français :** La story 12.3 est livrée : verrou Redis, signaux de collaboration, diffusion Hocuspocus sans état, code 423 sur le ticket si verrou, contrôle d’intégrité SHA-256, interface de restauration avec overlay pour tous les collaborateurs.

## File List
- `src/api/fastapi/main.py`
- `src/collab/hocuspocus/src/index.ts`
- `src/frontend/src/editor/TranscriptionEditor.tsx`
- `src/api/fastapi/test_story_12_3.py`
- `.bmad-outputs/implementation-artifacts/sprint-status.yaml`

## Change Log
- 2026-04-12: Story 12.3 — secure restore with Redis lock, `POST /v1/snapshots/{snapshot_id}/restore`, collaboration signals, integrity check, Hocuspocus + frontend overlay, tests (`test_story_12_3.py`).
- 2026-04-12: Code review follow-up — `test_restore_snapshot_by_id_canonical_path`, `test_restore_integrity_mismatch_returns_502` in `test_story_12_3.py`.
