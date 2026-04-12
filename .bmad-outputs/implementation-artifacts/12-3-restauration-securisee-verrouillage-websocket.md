# Story 12.3: Restauration Sécurisée avec Verrou de Concurrence

Status: ready-for-dev

## Story
**As a User**, I want to restore a document snapshot safely so that I can revert mistakes or recover previous versions without worrying about concurrent edits corrupting the state.

## Acceptance Criteria

### 1. Restoration API with Concurrency Lock
- [ ] **POST /v1/snapshots/{snapshot_id}/restore**: Trigger the restoration process:
    - **Step 1: Check Auth**: User must have `write` access to the project.
    - **Step 2: Set Lock**: Create a Redis key `lock:document:{doc_id}:restoring` with a TTL of 60s.
    - **Step 3: Signal Collaboration**: Broadcast a "Document Locked" message to all connected clients (via Hocuspocus/Yjs Awareness or a dedicated Redis Pub/Sub channel).
    - **Step 4: Swap Yjs State**:
        - Fetch the Yjs binary from the snapshot in MinIO.
        - Replace the latest state in the `yjs_logs` table (or append as a new authoritative snapshot).
    - **Step 5: Flush Hocuspocus Cache**: Signal the Hocuspocus server to reload the document state from the database.
    - **Step 6: Release Lock**: Delete the Redis key.
- [ ] **Conflict Prevention**: Any `POST /v1/editor/ticket` or Hocuspocus `onUpdate` hook MUST check for the presence of the lock key and reject operations with a 423 (Locked) status or equivalent.

### 2. UI: Restoration Workflow
- [ ] **Restore Button**: Add a "Restore this version" button in the History side panel (visible only when a snapshot is selected).
- [ ] **Confirmation Modal**: Before restoring, show a "Danger Zone" modal:
    - "This will overwrite all current changes. This action cannot be undone (except by another restore)."
- [ ] **Locking State UI**: While restoration is in progress, all users connected to the document should see a "Document being restored by [User Name]..." overlay, blocking all inputs.

### 3. Verification & Integrity
- [ ] **State Integrity**: Verify that after restoration, the document exactly matches the snapshot state.
- [ ] **Collaborator Reconnect**: Ensure all users are automatically re-synced with the new state after the lock is released.

## Tasks / Subtasks

- [ ] **Task 1: Redis Locking Logic**
  - [ ] Implement the locking/unlocking utility in FastAPI.
  - [ ] Integrate lock check in `onAuthenticate` or a custom Hocuspocus hook.
- [ ] **Task 2: Restoration Implementation**
  - [ ] Implement the `POST /v1/snapshots/{snapshot_id}/restore` endpoint.
  - [ ] Implement the state swap logic in PostgreSQL.
- [ ] **Task 3: Frontend Restoration UI**
  - [ ] Add the "Restore" button and its confirmation modal.
  - [ ] Implement the "Locked" overlay in the editor.
- [ ] **Task 4: Resilience Test**
  - [ ] Simulate a concurrent edit during restoration and verify it is blocked.

## Dev Notes
- Use `REDIS_URL` for the lock storage.
- The state swap should be wrapped in a transaction.
- Hocuspocus reload: You might need to disconnect users to force a full re-sync if Hocuspocus doesn't support hot-reloading state from DB via a simple signal.

## References
- **Architecture**: `docs/architecture.md` (§7 Points d'Attention - Edge Cases).
- **UX Design**: `docs/ux-design.md` (§7.3 Restauration).
- **Existing Logic**: `src/api/fastapi/main.py` (`YjsLog` and `SnapshotArtifact`).
