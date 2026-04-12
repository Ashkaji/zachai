# Story 10.3: Validation One-Click & Modal de Rejet Structurée

Status: done

## Story

As a **Manager**,  
I want to validate or reject transcriptions directly from the project list with a single click and use structured rejection motifs,  
so that I can accelerate the review process while maintaining consistent feedback for workers.

## Acceptance Criteria

1. **Inline Quick Actions (DataTable)**
   - [x] Add an "Actions" column to the `DataTable` in `ProjectDetailManager`.
   - [x] Display quick action buttons only for audios in `transcribed` status:
     - [x] **Checkmark (Green):** One-click validation (triggers `validateAudio` for this single ID).
     - [x] **Cross (Red):** One-click rejection (opens the Rejection Modal for this single ID).
   - [x] Show a loading spinner or disable buttons during the individual API call.

2. **Structured Rejection Modal**
   - [x] Enhance the Rejection Modal (shared between bulk and individual actions).
   - [x] Add a **Dropdown of Common Motifs**:
     - "Qualité audio insuffisante"
     - "Erreurs de transcription majeures"
     - "Formatage / Ponctuation incorrecte"
     - "Citations bibliques manquantes"
     - "Autre (préciser...)"
   - [x] If "Autre" is selected, the free-text comment field becomes mandatory.
   - [x] For predefined motifs, the comment field is optional but recommended.

3. **Visual Feedback**
   - [x] Use **Azure Flow** styled icons (Heroicons or similar SVG paths) for the inline buttons.
   - [x] Implement a subtle hover effect (glow) on action icons.

4. **Integration**
   - [x] Ensure the `useBatchAction` or a similar pattern is used to handle the single validation/rejection to maintain consistent progress feedback if needed, or use a simpler per-row state.

## Tasks / Subtasks

- [x] **Step 1: DataTable Actions Column**
  - [x] Update `DataTable` in `ProjectDetailManager` to include an "Actions" column.
  - [x] Implement conditional rendering for Validate/Reject buttons (status `transcribed`).

- [x] **Step 2: Modal Refactoring (Motifs)**
  - [x] Create a list of standard rejection motifs.
  - [x] Update the `GlassModal` for rejection to include a `<select>` or similar component for motifs.
  - [x] Update state logic to handle motif + comment.

- [x] **Step 3: Single Action Logic**
  - [x] Implement `handleSingleValidate` and `handleSingleReject` functions.
  - [x] Connect these functions to the `DataTable` action buttons.

- [ ] **Step 4: Validation**
  - [ ] Verify that a rejection without a motif or comment (if "Autre") is blocked.
  - [ ] Ensure the list refreshes correctly after a single action.

## Dev Notes

### UI Specs
- **Icons:** Use simple SVGs for Check (CheckIcon) and X (XMarkIcon).
- **Buttons:** `za-btn--ghost` with specific text colors (`var(--color-success)` / `var(--color-error)`).

### Backend Compatibility
- Ensure the `validateAudio(id, success, comment, token)` function in `dashboardApi.ts` supports the concatenated `[Motif] Comment` string if the backend doesn't have a separate motif field.

## References
- `src/frontend/src/features/projects/ProjectDetailManager.tsx`
- `src/frontend/src/features/dashboard/dashboardApi.ts`

---

## Traduction FR (résumé opérationnel)

- **Objectif:** Accélérer la revue via des actions rapides en ligne et des motifs de rejet standardisés.
- **Fonctionnalités:**
  - Colonne "Actions" dans le tableau (visible pour le statut `transcrit`).
  - Validation/Rejet en un clic.
  - Modal de rejet avec liste déroulante de motifs (Qualité, Erreurs, Formatage, etc.).
  - Commentaire obligatoire si motif "Autre".
