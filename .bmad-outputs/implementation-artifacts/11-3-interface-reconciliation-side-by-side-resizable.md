# Story 11.3: Interface Réconciliation Side-by-Side & Resizable

Status: done

## Story
**As an Expert**, I can compare two transcriptions side-by-side in a resizable layout so that I can easily reconcile differences and produce a Golden Set.

## Acceptance Criteria

### 1. Side-by-Side Layout
- [x] **Dual View**: Show "Original Whisper" on the left and "Corrected Version" on the right.
- [x] **Resizable Divider**: Implement a central draggable handle to adjust panel widths.
- [x] **Mobile Responsiveness**: Panels are resizable; layout handles width adjustments.

### 2. Synchronized Interaction
- [x] **Sync Scrolling**: Scrolling one panel automatically scrolls the other (can be toggled).
- [x] **Word-Level Diffs**: Highlight additions (green) and changes (blue) between the two versions.

### 3. "Azure Flow" Aesthetics
- [x] **Glassmorphism**: Use `za-glass` for panel backgrounds.
- [x] **No-Line Rule**: Use `box-shadow` and tonal depth for the resizable divider, not a 1px border.
- [x] **Glow FX**: Active handle and buttons have subtle glows.

### 4. Integration
- [x] **Expert Route**: Add a new navigation item `reconciliation-workspace` for the Expert role.
- [x] **Data Binding**: Interface is ready for data binding (currently uses mock demonstration text).

## Tasks / Subtasks

- [x] **Task 1: Infrastructure & Navigation**
  - [x] Add `reconciliation-workspace` to `AppRouteId` in `navigation.ts`.
  - [x] Update `ROLE_NAVIGATION.expert` in `navigation.ts`.
  - [x] Add route mapping in `AppShell.tsx`.
- [x] **Task 2: Resizable Panel Primitive**
  - [x] Create a `ResizableSideBySide` component in `src/frontend/src/shared/ui/`.
  - [x] Implement mouse event listeners for the divider handle.
- [x] **Task 3: Reconciliation Workspace UI**
  - [x] Create `ReconciliationWorkspace.tsx` in `src/frontend/src/features/reconciliation/`.
  - [x] Implement the dual panel layout using `ResizableSideBySide`.
- [x] **Task 4: Sync & Diff Logic**
  - [x] Implement synchronized scrolling logic via refs and event listeners.
  - [x] Implement a word-level diff renderer for visual highlights.

## Dev Notes
- **Styling**: Used `za-glass` and Azure Flow theme variables.
- **Sync Scroll**: Uses percentage-based scroll synchronization to handle panels with different content lengths.
- **Diffing**: Simple word-by-word comparison for visual feedback.

## References
- **UX Specs**: `docs/ui-artifacts/ui-screen-backlog-l2-l5.md` (L4).
- **Architecture**: `docs/architecture.md`.
