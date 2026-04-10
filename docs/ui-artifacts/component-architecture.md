# ZachAI Frontend Component Tree (L1)

## App shell and routing

- `src/frontend/src/App.tsx`
  - auth gates (loading/error/login)
  - role resolution from OIDC claims
  - wraps shell in `ThemeProvider`
- `src/frontend/src/app/AppShell.tsx`
  - role-aware sidebar navigation
  - top navbar with theme switch and notifications
  - main viewport route switching
  - legacy editor fallback route for migration
- `src/frontend/src/app/navigation.ts`
  - navigation map by role (`admin`, `manager`, `transcriber`, `expert`)

## Theme and design tokens

- `src/frontend/src/theme/theme.css`
  - DS-inspired light/dark tokens
  - typography (`Manrope`, `Inter`)
  - spacing, radius, button primitives
- `src/frontend/src/theme/ThemeContext.tsx`
  - mode state and localStorage persistence
  - `data-theme` sync on root

## Shared UI primitives

- `src/frontend/src/shared/ui/Primitives.tsx`
  - `Card`
  - `Metric`
  - `DataTable`

## Dashboards by role

- `src/frontend/src/features/dashboard/RoleDashboards.tsx`
  - `AdminDashboard`
  - `ManagerDashboard`
  - `TranscriberDashboard`
  - `ExpertDashboard`
  - dashboards Admin/Manager/Transcripteur branchés API (`/v1/projects`, `/v1/golden-set/status`, `/v1/me/audio-tasks`)

## Migration compatibility

- `src/frontend/src/editor/TranscriptionEditor.tsx`
  - kept accessible via "Éditeur hérité" route while L2-L5 screens are implemented.

## L2 — Nouveau projet (Manager)

- `src/frontend/src/features/project-wizard/NewProjectWizard.tsx`
  - stepper 4 étapes : nature & métadonnées, labels, import audio (fichiers + glisser-déposer), assignation transcripteurs
  - entrées : item sidebar « Nouveau projet », bouton header « Nouveau projet », CTA « Créer un projet » sur le dashboard manager
  - branché backend : `POST /v1/natures`, `POST /v1/projects`, `POST /v1/projects/{id}/audio-files/upload`, `POST /v1/projects/{id}/audio-files/register`, `POST /v1/projects/{id}/assign`
