# Story 9.1: Azure Design Tokens & Theme Playground

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a Developer,
I want a dedicated route `/dev/playground` to validate all UI primitives (`Card`, `Metric`, `Badge`, `AzureTable`) against the "No-Line" rule in both Light and Dark modes,
So that we eliminate visual debt and ensure 100% compliance with the `theme.css` variables.

## Acceptance Criteria

1. **Given** le fichier `src/frontend/src/theme/theme.css` consolidé
   **When** j'accède à `/dev/playground`
   **Then** je vois tous les composants atomiques déclinés en Light et Dark modes
   **And** aucun composant ne possède de bordure de 1px (vérifié par inspection CSS)
   **And** les espacements respectent strictement les variables `--spacing-*`

## Tasks / Subtasks

- [x] Task 1: Initialize/Consolidate `theme.css` (AC: 1)
  - [x] Extract existing CSS tokens (Light/Dark) from previous artifacts and Stitch specs.
  - [x] Consolidate tokens in `src/frontend/src/theme/theme.css`.
  - [x] Ensure spacing variables `--spacing-*` are defined and strictly adhered to.
- [x] Task 2: Create/Refactor Atomic Components (AC: 1)
  - [x] Refactor or create `Card` component strictly without 1px borders (No-Line rule, using tonal separation instead).
  - [x] Refactor or create `Metric = Metric component.
  - [x] Refactor or create `Badge` component.
  - [x] Ensure they support the `data-theme` application.
- [x] Task 3: Build Theme Playground Route (AC: 1)
  - [x] Create `/dev/playground` route accessible for developers.
  - [x] Render `Card`, `Metric`, and `Badge` instances in both themes side-by-side or togglable.
  - [x] Ensure the playground highlights the "Azure Flow" visual identity.

## Dev Notes

- **Relevant architecture patterns and constraints:**
  - "Azure Flow" visual identity: dark mode (#0A0E14), electric blue accents (#3D9BFF), glassmorphism (backdrop-blur).
  - "No-Line rule": strictly avoid 1px borders, use tonal separation (e.g. `surface-container-low` vs `surface-container-high`).
- **Source tree components to touch:**
  - `src/frontend/src/theme/theme.css`
  - `src/frontend/src/shared/ui/Primitives.tsx`
  - `src/frontend/src/App.tsx` (for routing `/dev/playground`)
- **Testing standards summary:**
  - Component styling must strictly use defined CSS variables for colors, backgrounds, and spacing. Manual verification in playground.

### Project Structure Notes

- Shared UI primitives go in `src/frontend/src/shared/ui/Primitives.tsx`.
- Theme definitions in `src/frontend/src/theme/theme.css`.
- Ensure components work harmoniously before using them for the complex Dashboard builds.

### References

- [Source: .bmad-outputs/planning-artifacts/epics.md#Epic 9: Shell "Azure Flow", Notifications & Primitives Atomiques]
- [Source: docs/ui-artifacts/component-architecture.md#Theme and design tokens]
- [Source: docs/ux-design.md]

## Dev Agent Record

### Agent Model Used

Gemini 2.5 Pro

### Debug Log References

### Completion Notes List
