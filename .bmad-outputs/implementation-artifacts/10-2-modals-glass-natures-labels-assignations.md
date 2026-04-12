# Story 10.2: Modals "Glass" de Gestion (Assignation/Nature)

Status: ready-for-dev

## Story

As a **Manager**,  
I want to manage project settings and audio assignments via high-fidelity glassmorphism modals,  
so that I can perform administrative tasks in a visually immersive and intuitive interface.

## Acceptance Criteria

1. **Global Modal Primitive (Shared UI)**
   - Extract the `Modal` component to a dedicated shared UI file (e.g., `src/frontend/src/shared/ui/Modals.tsx`).
   - Apply the `za-glass` class for the **Glassmorphism** effect (backdrop-blur, translucent background).
   - Implement **Azure Flow** aesthetics: subtle glow border, rounded corners (`var(--radius-lg)`), and smooth entry animation.
   - Add support for different sizes: `sm`, `md` (default), `lg`, `xl`.

2. **Refined Bulk Assignment Modal**
   - Use the new Glass Modal for audio assignments.
   - Replace the simple text input with a **Searchable Selection** component (placeholder for real user list if backend supports it, otherwise keep ID input with better validation).
   - Display a summary of selected items (count, project name) within the modal.

3. **Project Settings Modal (Nature & Labels)**
   - Add a "Paramètres" button in the `ProjectDetailManager` header.
   - Open a Glass Modal showing current project details:
     - Project Name (read-only).
     - Nature Name (read-only for now).
     - **Labels Schema:** List the labels associated with the project's nature.
   - Add placeholders/UI for future "Update" actions.

4. **User Experience**
   - Ensure modals are closeable via: Close button (X), clicking the backdrop, and pressing the `Escape` key.
   - Modals must be fully responsive and centered on all screen sizes.

## Tasks / Subtasks

- [x] **Step 1: Modal Primitive Refactoring**
  - [x] Create `src/frontend/src/shared/ui/Modals.tsx`.
  - [x] Implement the `GlassModal` component with `za-glass` and Azure Flow styles.
  - [x] Add `Escape` key and backdrop click listeners.

- [x] **Step 2: Assignment Modal Upgrade**
  - [x] Update `ProjectDetailManager` to use the new `GlassModal`.
  - [x] Improve the assignment UI (header, selected items summary).

- [x] **Step 3: Project Settings UI**
  - [x] Add the "Paramètres" button to `ProjectDetailManager`.
  - [x] Build the `ProjectSettingsModal` showing Nature and Labels.

- [x] **Step 4: Validation**
  - [x] Verify modal accessibility (keyboard navigation).
  - [x] Test glassmorphism rendering in both light and dark modes.

## Dev Notes

### UI Specs (Azure Flow)
- **Background:** `color-mix(in srgb, var(--color-surface-hi) 60%, transparent)`.
- **Blur:** `backdrop-filter: blur(20px)`.
- **Border:** `1px solid var(--color-outline)`.
- **Shadow:** `0 20px 50px rgba(0,0,0,0.5)`.

### Component Structure
```tsx
export function Modal({ isOpen, onClose, title, children, size = 'md' }: ModalProps) {
  if (!isOpen) return null;
  // ... portal or absolute positioning ...
}
```

## References
- `docs/ux-design.md` (Azure Flow aesthetic)
- `src/frontend/src/theme/theme.css` (Glass classes)
- `src/frontend/src/features/projects/ProjectDetailManager.tsx` (Current internal Modal)

---

## Traduction FR (résumé opérationnel)

- **Objectif:** Harmoniser les modals de gestion avec le design "Glassmorphism" et ajouter la gestion des paramètres projet.
- **Fonctionnalités:**
  - Nouveau composant `GlassModal` partagé (effet de flou, bordures néon).
  - Modal d'assignation améliorée.
  - Modal de paramètres projet (visualisation de la Nature et des Labels).
- **Navigation:** Nouveau bouton "Paramètres" dans le détail projet.
