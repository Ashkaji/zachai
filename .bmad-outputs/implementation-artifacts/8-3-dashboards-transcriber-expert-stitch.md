# Story 8-3: Transcriber & Expert Dashboards (Azure Flow)

## Description
Refine and implement high-fidelity dashboards for Transcriber and Expert roles following the "Azure Flow" design system. Ensure the Expert role (previously lacking a design) is consistently declinated from the core aesthetic.

## Acceptance Criteria
1.  **Transcriber Dashboard**: Clear task prioritization, productivity metrics, and work queue with Azure Flow styling.
2.  **Expert Dashboard**: Conflict resolution metrics, Label Studio integration status, and quality indicators.
3.  **Visual Consistency**: Use Glassmorphism for floating toolbars and No-Line rule for lists.
4.  **Interaction**: Hover effects on tasks and clear status "halos" for active items.

## Technical Tasks
- [x] Consolidate Stitch design artifacts for Transcriber and Expert.
- [x] Decline "Azure Flow" aesthetic for the Expert role via Stitch generation.
- [x] Implement enhanced `TranscriberDashboard` in `RoleDashboards.tsx`.
- [x] Implement enhanced `ExpertDashboard` in `RoleDashboards.tsx`.
- [x] Verify responsive behavior for mobile workers.

## Definition of Done
- Dashboards align with the "Azure Flow" North Star.
- Performance metrics are clearly readable in light and dark modes.
- Tests pass.
