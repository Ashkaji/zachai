# Story 12.2: Visual Diff "Ghost Mode"

Status: ready-for-dev

## Story
**As a User**, I want to view document changes in a "Ghost Mode" interface so that I can easily identify what has been added or removed compared to a previous version of the document.

## Acceptance Criteria

### 1. Snapshot Timeline (Side Panel)
- [ ] **GET /v1/audio-files/{audio_id}/snapshots**: Return a list of available snapshots for a given document.
    - JSON: `[{ "snapshot_id": string, "created_at": iso8601, "source": string }, ...]`
    - Data sourced from `snapshot_artifacts` table.
- [ ] **UI Component**: Implement a vertical timeline in a right side panel:
    - Each node represents a snapshot.
    - Display date/time and source.
    - Interactive "nodes" that trigger the Ghost Mode on click.

### 2. Ghost Mode Implementation (Visual Diff)
- [ ] **GET /v1/snapshots/{snapshot_id}/yjs**: Return the raw Yjs binary state of a snapshot.
    - Auth: User must have access to the project.
    - Action: Fetch from MinIO using the key stored in `snapshot_artifacts`.
- [ ] **Frontend Diff Engine**:
    - Implement a diffing logic between the current Yjs document and the selected snapshot.
    - Use a **Web Worker** to perform the diff to prevent blocking the UI thread for large documents.
- [ ] **Visual Styles**:
    - **Added Text**: Highlighted with a soft glow (using a ProseMirror decoration).
    - **Deleted Text**: Displayed in "Spectral Blue" (faded/ghostly appearance) using `::before` or `::after` pseudo-elements or custom decorations that don't affect the document flow.

### 3. Interactive Preview
- [ ] **Hover Preview**: Survoler un Snapshot dans la timeline affiche un aperçu rapide (overlay) des changements majeurs.
- [ ] **Toggle Mode**: Allow the user to toggle Ghost Mode on/off.

## Tasks / Subtasks

- [ ] **Task 1: Backend Endpoints**
  - [ ] Implement `GET /v1/audio-files/{audio_id}/snapshots`.
  - [ ] Implement `GET /v1/snapshots/{snapshot_id}/yjs` (with proper auth check).
- [ ] **Task 2: Frontend History Panel**
  - [ ] Create the `HistoryPanel` component.
  - [ ] Add the vertical timeline UI.
- [ ] **Task 3: Diff Logic & Ghost Mode**
  - [ ] Implement the Tiptap extension for Ghost Mode decorations.
  - [ ] Create a Web Worker for computing the diff (e.g., using `diff-match-patch` or similar).
  - [ ] Apply "Spectral Blue" and "Glow" styles.

## Dev Notes
- For diffing, you can compare the plain text of the two Yjs documents and map the changes back to indices/offsets in the editor.
- "Spectral Blue" style: `color: rgba(0, 120, 212, 0.4); text-decoration: line-through;`.
- Glow style: `background-color: rgba(0, 120, 212, 0.1); border-bottom: 2px solid #0078d4;`.

## References
- **UX Design**: `docs/ux-design.md` (§5.B Versioning & "Ghost Mode").
- **Architecture**: `docs/architecture.md` (§1.A Snapshot Engine).
- **Existing Models**: `SnapshotArtifact` in `main.py`.
