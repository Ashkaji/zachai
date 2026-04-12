# Story 10.1: Vue Détail Projet & Actions Groupées (L2)

Status: done

## Story

As a **Manager**,  
I want to perform bulk actions on audio files within a project (assignment, validation) and access a more detailed view of my project's progress,  
so that I can manage large volumes of files efficiently and maintain total oversight.

## Acceptance Criteria

1. **Bulk Selection in DataTable**
   - [x] Add a checkbox column to the audio `DataTable`.
   - [x] Implement a "Select All" checkbox in the header that only affects currently **visible** (filtered) items.
   - [x] **Selection Reset:** Clear the selection automatically when filters or sorting change to prevent accidental "hidden" actions.
   - [x] Show a floating bulk action bar at the bottom of the screen when one or more rows are selected.

2. **Bulk Assignment Action**
   - [x] Implement "Assign Selected" button.
   - [x] Open a modal to select a Transcripteur from a list (Implemented as ID text input for MVP).
   - [x] **Constraint:** Only `uploaded` or `assigned` audios are eligible.
   - [x] **Execution:** Implement sequential or limited-concurrency (max 5) API calls to `POST /v1/projects/{project_id}/assign`.

3. **Bulk Validation/Rejection Action**
   - [x] Implement "Validate Selected" and "Reject Selected" buttons.
   - [x] **Constraint:** Only `transcribed` audios are eligible for validation/rejection.
   - [x] **Rejection Modal:** If rejecting, a shared comment is mandatory and must be validated as non-empty.
   - [x] **Execution:** Sequential API calls to `POST /v1/transcriptions/{audio_id}/validate`.

4. **Batch Operation Feedback & Progress**
   - [x] Show a **progress indicator** (e.g., "Processing 12 of 50...") during bulk operations.
   - [x] Provide a final **summary report** (e.g., "48 succeeded, 2 failed") with the option to retry only failed items.
   - [x] Update the UI state (e.g., reload project data) only after the entire batch is completed.

5. **Deep-Dive Analytics Cards**
   - [x] Add new metrics to the detail header (rounded to 1 decimal place):
     - [x] **Progress %:** (Validated Audios / Total Audios) * 100.
     - [ ] **Avg Confidence:** Average Whisper confidence across all transcribed audios (Postponed: backend missing confidence in AudioRow).
     - [x] **Total Duration:** Sum of `duration_s` for all audios, formatted as `HH:MM:SS`.

6. **Enhanced Status Halos (Azure Flow)**
   - [x] Status badges in the table must use the "Azure Flow" halo effect:
     - [x] **Validated:** Green glow (`box-shadow` or `filter: drop-shadow`).
     - [x] **In Progress / Transcribed:** Blue pulse/glow effect.
     - [x] **Uploaded:** Neutral glow.

7. **Audit Trail Entry Point**
   - [x] Add an "Historique" button in the header that navigates to the Audit Trail view (Story 10.4 placeholder).

## Tasks / Subtasks

- [x] **Step 1: UI Enhancement (Bulk Selection)**
  - [x] Update `DataTable` primitive to support a checkbox column and header selection.
  - [x] Add `selectedIds` (Set) state to `ProjectDetailManager`.
  - [x] Implement the floating `BulkActionBar` with selection count and action buttons.

- [x] **Step 2: Bulk Actions Implementation**
  - [x] Implement a `useBatchAction` hook or utility to handle sequential/throttled API calls and progress tracking.
  - [x] Build the bulk assignment modal (Transcripteur list).
  - [x] Build the bulk rejection modal (Comment input).
  - [x] Implement the batch summary report UI (Toasts or small Modal).

- [x] **Step 3: Analytics & Aesthetics**
  - [x] Calculate analytics with proper rounding and formatting (duration).
  - [x] Apply CSS-based halo/glow effects to status badges in `DataTable`.

- [x] **Step 4: Validation**
  - [x] Test selection logic: visible items only, reset on filter change.
  - [x] Verify batch concurrency control (no more than 5 parallel requests).
  - [x] Ensure the UI reflects new statuses only after batch completion.

## Dev Notes

### UI Primitives & Styling
- **DataTable:** Add `selectable?: boolean`, `selectedIds?: Set<number | string>`, `onSelectChange?: (ids: Set<number>) => void`.
- **Azure Flow Glow:** Use `filter: drop-shadow(0 0 8px var(--color-glow-blue))` for the halos.

### Concurrency
- Use `for...of` with `await` for simple sequential execution, or a helper like `p-limit` if available (otherwise, simple sequential is safer for now).

### State Management
- `const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());`
- Clear on: `useEffect(() => setSelectedIds(new Set()), [statusFilter, sortField]);`

## References
- `docs/ux-design.md` (Azure Flow aesthetic)
- `src/frontend/src/features/projects/ProjectDetailManager.tsx` (Current implementation)
- `docs/api-mapping.md` (Existing endpoints)

---

## Traduction FR (résumé opérationnel)

- **Objectif:** Actions groupées et métriques L2 pour le Manager.
- **Fonctionnalités:**
  - Sélection multiple (uniquement items visibles).
  - Actions groupées sécurisées (exécution séquentielle, barre de progression).
  - Rapport de fin de batch (succès/échecs).
  - Métriques: Progression %, Confiance Whisper, Durée totale formatée.
  - Design "Azure Flow": Effets de halo néon sur les badges de statut.
