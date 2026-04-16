# Story 8-2: Admin & Manager Dashboards (Azure Flow)

## Description
Implement high-fidelity dashboards for Admin and Manager roles using the "Azure Flow" design system. Focus on atmospheric depth, glassmorphism, and the "No-Line" rule.

## Acceptance Criteria
1.  **Admin Dashboard**: Desktop layout with system health (CPU/RAM), global project activity, and critical logs.
2.  **Manager Dashboard**: Enhanced version of the current dashboard with better project cards and team status summaries.
3.  **Visual Consistency**: Both light and dark modes must follow the tonal separation rules (no 1px borders).
4.  **Glassmorphism**: Sidebar and floating toolbars must use backdrop-blur.

## Technical Tasks
- [x] Consolidate Stitch design artifacts for Admin and Manager roles.
- [x] Create `src/frontend/src/features/admin/AdminDashboard.tsx` (Integrated in RoleDashboards.tsx).
- [x] Create `src/frontend/src/features/dashboard/ManagerDashboardFull.tsx` (Integrated in RoleDashboards.tsx).
- [x] Implement floating Sidebar with Glassmorphism.
- [x] Update `AppShell.tsx` to use the new navigation layout.

## Definition of Done
- Dashboards look identical to Stitch specifications.
- Responsive design works on Desktop.
- All dashboard metrics are correctly displayed.
