# Story 9.4: Azure Flow Shell: Responsive Layout & Breadcrumbs

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a User,
I want a sidebar that becomes collapsible on Tablet widths and breadcrumbs derived from the `navigation.ts` mapping,
So that je peux naviguer efficacement et savoir exactement où je suis (ex: Azure Flow / Dashboard).

## Acceptance Criteria

1. **Given** une largeur de fenêtre < 1024px
   **When** je clique sur le bouton de réduction
   **Then** la sidebar se rétracte pour ne montrer que les icônes (Glass effect conservé).
2. **And** le header affiche des breadcrumbs dynamiques (ex: "Azure Flow > Manager > Projets") qui reflètent la route active.

## Tasks / Subtasks

- [x] Task 1: Implement Collapsible Sidebar (AC: 1)
  - [x] Add `isCollapsed` state to `AppShell.tsx` (responsive default based on `window.innerWidth < 1024`).
  - [x] Add a toggle button inside the sidebar to collapse/expand.
  - [x] Update sidebar CSS to animate width transition (e.g., from 280px to 80px).
  - [x] Hide text labels and show only icons (or initials if icons are absent) when collapsed.
  - [x] Adjust `main` element's `marginLeft` dynamically based on sidebar state.
- [x] Task 2: Implement Dynamic Breadcrumbs (AC: 2)
  - [x] Update `AppShell.tsx` header to display a breadcrumb trail.
  - [x] Map the `activeRoute` to its full path using `ROLE_NAVIGATION` (e.g., "ZachAI > [Role] > [Page]").
  - [x] Style the breadcrumbs using existing text primitives (muted colors for parents, primary for current).
- [x] Task 3: Responsive CSS & Validation
  - [x] Add media queries to `theme.css` or inline styles for responsive adjustments.
  - [x] Verify transitions are smooth and do not cause layout thrashing.
  - [x] Validate on desktop (> 1024px) and tablet (< 1024px) widths.

## Dev Notes

- **Relevant architecture patterns and constraints:**
  - Glassmorphism for the sidebar (existing `za-glass`).
  - Transition animations should use CSS `transition: width 0.3s ease, margin-left 0.3s ease`.
  - Ensure the sidebar toggle button is accessible (aria-labels).
- **Source tree components to touch:**
  - `src/frontend/src/app/AppShell.tsx`
  - `src/frontend/src/theme/theme.css`
  - `src/frontend/src/app/navigation.ts` (if needed for breadcrumb labels)
- **Testing standards summary:**
  - Verify layout adjustments when resizing the browser window.
  - Check that breadcrumbs update correctly when navigating between views.

### Project Structure Notes

- Keep all layout logic self-contained within `AppShell.tsx`.

### References

- [Source: .bmad-outputs/planning-artifacts/epics.md#Story 9.4: Azure Flow Shell: Responsive Layout & Breadcrumbs]
- [Source: docs/ux-design.md#4. Layout & Structure]

## Dev Agent Record

### Agent Model Used

Gemini 2.5 Pro

### Debug Log References

### Completion Notes List

- Implemented responsive sidebar that collapses below 1024px width.
- Animated sidebar width and main content margin-left.
- Installed `lucide-react` and added icons to `navigation.ts`.
- Integrated dynamic breadcrumbs in the header indicating `Azure Flow > [Role] > [Current Page]`.
- Verified build and TypeScript types.

### File List

- `src/frontend/src/app/AppShell.tsx`
- `src/frontend/src/app/navigation.ts`
- `src/frontend/package.json`
