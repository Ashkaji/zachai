# Story 9.3: Unified Notification Provider & Event Bus

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a User,
I want a centralized `NotificationProvider` that filters incoming events into 3 tiers (Critical, Informational, Audit-only),
So that I stay informed via the "Glass" panel without being overwhelmed by technical logs.

## Acceptance Criteria

1. **Given** un événement entrant via WebSocket (ou bus local de test)
   **When** l'événement est de type "Critical"
   **Then** il apparaît dans le panneau de notifications avec un badge rouge.
2. **When** l'événement est de type "Audit-only"
   **Then** il est stocké en état local (pour consultation future) mais n'affiche aucune alerte visuelle au User.
3. **And** le `NotificationProvider` est accessible via un hook `useNotifications()` partout dans l'application.

## Tasks / Subtasks

- [x] Task 1: Create `NotificationProvider` Context (AC: 3)
  - [x] Define types for Notifications (`NotificationTier`: Critical, Informational, Audit).
  - [x] Implement `NotificationContext` and `NotificationProvider` in `src/frontend/src/shared/notifications/`.
  - [x] Implement `useNotifications` hook.
- [x] Task 2: Implement Event Bus Logic (AC: 1, 2)
  - [x] Create a simple Event Bus (EventEmitter-like) to subscribe to events.
  - [x] Wire the Event Bus to the `NotificationProvider`.
  - [x] Implement filtering logic based on tiers.
- [x] Task 3: Integrate with `AppShell` (AC: 1)
  - [x] Replace hardcoded notifications in `AppShell.tsx` with state from `useNotifications()`.
  - [x] Update the notifications panel to display tiered notifications.
  - [x] Add visual indicators (red badge for Critical).
- [x] Task 4: Validation in Playground (AC: 1, 2)
  - [x] Add a "Notification Test" section to `src/frontend/src/dev/Playground.tsx`.
  - [x] Add buttons to trigger test events of different tiers.

## Dev Notes

- **Relevant architecture patterns and constraints:**
  - Glassmorphism for the notification panel (existing `za-glass`).
  - Tiered filtering: `Critical` (immediate alert), `Informational` (standard notification), `Audit` (silent log).
  - Use React Context for global state management.
- **Source tree components to touch:**
  - `src/frontend/src/shared/notifications/NotificationContext.tsx` (New)
  - `src/frontend/src/app/AppShell.tsx`
  - `src/frontend/src/dev/Playground.tsx`
  - `src/frontend/src/App.tsx` (to wrap with provider)
- **Testing standards summary:**
  - Verify tier filtering in the UI.
  - Ensure performance is not impacted by high-frequency audit logs.

### Project Structure Notes

- Keep notification logic in `src/frontend/src/shared/notifications/`.
- Ensure it supports future WebSocket integration (Hocuspocus or dedicated socket).

### References

- [Source: .bmad-outputs/planning-artifacts/epics.md#Story 9.3: Unified Notification Provider & Event Bus]
- [Source: docs/ux-design.md#4. Layout & Structure]

## Dev Agent Record

### Agent Model Used

Gemini 2.5 Pro

### Debug Log References

### Completion Notes List

- Implemented `NotificationContext` with a lightweight `NotificationEventBus`.
- Added `NotificationTier` filtering to separate audit logs from user-facing alerts.
- Integrated `NotificationProvider` at the root in `App.tsx`.
- Updated `AppShell` to dynamically render `activeNotifications`.
- Added test triggers to `Playground.tsx`.

### File List

- `src/frontend/src/shared/notifications/NotificationContext.tsx`
- `src/frontend/src/App.tsx`
- `src/frontend/src/app/AppShell.tsx`
- `src/frontend/src/dev/Playground.tsx`
